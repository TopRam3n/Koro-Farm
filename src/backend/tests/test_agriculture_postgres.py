"""Agricultural intelligence schema (migration 0029), offline importer and forecasting baselines on PostgreSQL.

Every figure loaded here is synthetic and labelled as such: nothing resembles or claims to be an official statistic.
Skipped unless POSTGRES_TEST_DATABASE_URL is set.
"""
import os
import pathlib
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

POSTGRES_URL = os.getenv("POSTGRES_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not POSTGRES_URL, reason="dedicated PostgreSQL test database not configured")
BACKEND = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture()
def agri_db(monkeypatch):
    name = f"korofarm_r1_disposable_agri_{uuid4().hex[:10]}"
    admin = create_engine(make_url(POSTGRES_URL).set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    url = make_url(POSTGRES_URL).set(database=name)
    monkeypatch.setenv("DATABASE_URL", url.render_as_string(hide_password=False))
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    engine = create_engine(url)
    try:
        yield url, config, engine
    finally:
        engine.dispose()
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


def test_the_agri_schema_matches_the_mapping_and_stays_closed(agri_db) -> None:
    from src.backend.app.agriculture.domain.models import AgriBase
    from test_migrations_postgres import _supabase_like_roles

    url, config, engine = agri_db
    _supabase_like_roles(url)
    command.upgrade(config, "head")
    inspector = inspect(engine)
    tables = set(inspector.get_table_names(schema="agri"))
    assert tables == {t.name for t in AgriBase.metadata.sorted_tables}
    for table in AgriBase.metadata.sorted_tables:
        columns = {c["name"] for c in inspector.get_columns(table.name, schema="agri")}
        assert {c.name for c in table.columns} == columns, table.name
    # Operational tables stay in public; agri.crops and public.crops are different tables in different schemas.
    assert "requirements" not in tables and "organizations" not in tables
    with engine.connect() as connection:
        for role in ("anon", "authenticated", "service_role"):
            assert not connection.execute(text("select has_schema_privilege(:r, 'agri', 'USAGE')"), {"r": role}).scalar()
            assert not connection.execute(text(
                "select count(*) from pg_class c join pg_namespace n on n.oid = c.relnamespace cross join pg_roles r "
                "where n.nspname = 'agri' and c.relkind = 'r' and r.rolname = :r "
                "and (has_table_privilege(r.oid, c.oid, 'SELECT') or has_table_privilege(r.oid, c.oid, 'INSERT'))"), {"r": role}).scalar()
        assert not connection.execute(text("select has_schema_privilege('public', 'agri', 'USAGE')")).scalar()
        assert connection.execute(text("select count(*) from agri.observations")).scalar() == 0  # nothing invented
    # The Data API audit covers agri too and still passes.
    from src.backend.scripts import check_staging
    assert check_staging.check_data_api_grants(engine).status == "PASS"


def test_constraints_keep_one_current_revision_and_reject_impossible_values(agri_db) -> None:
    url, config, engine = agri_db
    command.upgrade(config, "head")
    from src.backend.app.agriculture import ingestion
    factory = sessionmaker(bind=engine)
    with factory() as session:
        ingestion.load_reference(session, ingestion.REFERENCE_DIR, apply=True)
        session.commit()
    with engine.begin() as connection:
        dataset = connection.execute(text("select id from agri.datasets where code = 'QCL'")).scalar()
        crop = connection.execute(text("select id from agri.crops where code = 'GINGER'")).scalar()
        area = connection.execute(text("select id from agri.geo_areas where code = 'JM'")).scalar()
        publication = uuid4()
        connection.execute(text("insert into agri.publications (id, dataset_id, version_label, retrieved_at, content_sha256, retrieved_by) "
                                "values (:id, :d, 'synthetic', now(), :sha, 'test')"), {"id": publication, "d": dataset, "sha": "a" * 64})
        values = {"d": dataset, "p": publication, "c": crop, "g": area}
        insert = text("insert into agri.observations (id, dataset_id, publication_id, measure_code, crop_id, geo_area_id, period_type, "
                      "period_start, period_end, value, unit_code, value_canonical, canonical_unit_code, status, is_current) values "
                      "(:id, :d, :p, 'PRODUCTION', :c, :g, 'YEAR', '2020-01-01', :end, :v, 'TONNE', :v, 'TONNE', 'FINAL', :current)")
        connection.execute(insert, {**values, "id": uuid4(), "v": 10, "end": "2020-12-31", "current": True})
    for bad in ({"v": 11, "end": "2020-12-31", "current": True},     # a second current version of the same figure
                {"v": -1, "end": "2020-12-31", "current": False},    # negative quantity
                {"v": 1, "end": "2019-12-31", "current": False}):    # period ends before it starts
        with pytest.raises(IntegrityError):
            with engine.begin() as connection:
                connection.execute(insert, {**values, "id": uuid4(), **bad})
    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(text("insert into agri.publications (id, dataset_id, version_label, retrieved_at, content_sha256, retrieved_by) "
                                    "values (:id, :d, 'dup', now(), :sha, 'test')"), {"id": uuid4(), "d": dataset, "sha": "a" * 64})
    # A downgrade never destroys ingested data.
    with pytest.raises(Exception, match="refusing to drop"):
        command.downgrade(config, "0028_notifications_consent")


# --- Offline importer (synthetic data only) ---------------------------------------------------------------------

SYNTHETIC = "SYNTHETIC TEST VALUE, not a statistic"
HEADER = "source_code,dataset_code,crop,geography,measure,period_type,period,value,unit,status,quality_flag,source_row_reference,notes\n"


def _template(tmp_path, name, lines):
    path = tmp_path / name
    path.write_text(HEADER + "".join(f"MOA_AMID,AREA_PRODUCTION_FARMGATE,{line},{SYNTHETIC}\n" for line in lines), encoding="utf-8")
    return path


def _approve(session, code):
    from src.backend.app.agriculture.domain.models import Source
    session.scalar(select(Source).where(Source.code == code)).licence_review_status = "APPROVED"
    session.flush()


def test_template_import_is_dry_run_first_licence_gated_idempotent_and_keeps_revisions(agri_db, tmp_path) -> None:
    from src.backend.app.agriculture import ingestion
    from src.backend.app.agriculture.domain.models import Observation, Publication, ValidationIssue

    _, config, engine = agri_db
    command.upgrade(config, "head")
    factory = sessionmaker(bind=engine)
    first = _template(tmp_path, "edition-1.csv", [
        "Ginger,St. Ann,PRODUCTION,YEAR,2023,\"1,000\",TONNE,FINAL,,r1",
        "Ginger,Saint Ann,FARMGATE_PRICE,YEAR,2023,454,JMD_PER_LB,PROVISIONAL,,r2",
        "Ginger,St. Ann,PRODUCTION,YEAR,2023,\"1,000\",TONNE,FINAL,,r1",          # the same row again: duplicate
        "Dragon fruit,St. Ann,PRODUCTION,YEAR,2023,5,TONNE,FINAL,,r3",             # no reviewed mapping
        "Ginger,St. Ann,PRODUCTION,YEAR,2022,-4,TONNE,FINAL,,r4",                  # negative
        "Ginger,St. Ann,PRODUCTION,YEAR,2021,7,HA,FINAL,,r5",                       # wrong unit for the measure
        "Ginger,St. Ann,AREA_REAPED,QUARTER,2023-Q5,7,HA,FINAL,,r6",                # impossible period
    ])
    with factory() as session:
        ingestion.load_reference(session, apply=True)
        session.commit()
    with factory() as session:
        dry = ingestion.import_observations(session, first, operator="test")
        session.commit()
        assert (dry.mode, dry.rows_read, dry.rows_accepted, dry.rows_duplicate, dry.rows_rejected) == ("DRY_RUN", 7, 2, 1, 4)
        assert {i["rule"] for i in dry.issues} >= {"UNKNOWN_CROP", "NEGATIVE_VALUE", "UNIT_MEASURE_MISMATCH", "INVALID_PERIOD"}
        assert session.scalar(select(Publication.id)) is None and session.scalar(select(Observation.id)) is None  # nothing kept
        with pytest.raises(ingestion.ImportRefused, match="PERMISSION_REQUIRED"):
            ingestion.import_observations(session, first, operator="test", apply=True)
        session.rollback()
    with factory() as session:
        _approve(session, "MOA_AMID")  # test only: the real Ministry licence review is still PERMISSION_REQUIRED
        applied = ingestion.import_observations(session, first, operator="test", apply=True)
        session.commit()
        assert applied.status == "SUCCEEDED" and applied.rows_accepted == 2
        price = session.scalar(select(Observation).where(Observation.measure_code == "FARMGATE_PRICE"))
        assert price.value == Decimal("454") and price.unit_code == "JMD_PER_LB" and price.canonical_unit_code == "JMD_PER_KG"
        assert abs(price.value_canonical - Decimal("1000.89867032")) < Decimal("0.001")   # 454 J$/lb is 1000.9 J$/kg
        assert session.scalar(select(ValidationIssue.id).where(ValidationIssue.rule_code == "UNKNOWN_CROP")) is not None
        again = ingestion.import_observations(session, first, operator="test", apply=True)
        assert again.status == "ALREADY_IMPORTED" and again.ingestion_run_id == applied.ingestion_run_id

    second = _template(tmp_path, "edition-2.csv", [
        "Ginger,St. Ann,PRODUCTION,YEAR,2023,1100,TONNE,FINAL,,r1",   # revised figure
        "Ginger,St. Ann,PRODUCTION,YEAR,2024,9000,TONNE,PROVISIONAL,,r2",  # more than 5x the year before
    ])
    with factory() as session:
        revised = ingestion.import_observations(session, second, operator="test", apply=True)
        session.commit()
        assert revised.revisions == 1 and any(i["rule"] == "OUTLIER_PERIOD_CHANGE" for i in revised.issues)
        rows = session.scalars(select(Observation).where(Observation.measure_code == "PRODUCTION", Observation.period_start == date(2023, 1, 1))
                               .order_by(Observation.revision_number)).all()
        assert [(r.value, r.revision_number, r.is_current) for r in rows] == [(Decimal("1000"), 1, False), (Decimal("1100"), 2, True)]
        assert rows[1].supersedes_id == rows[0].id and rows[1].status == "REVISED"
        publications = session.scalars(select(Publication).order_by(Publication.created_at)).all()
        assert publications[1].supersedes_publication_id == publications[0].id


def test_faostat_rows_are_always_kept_but_become_statistics_only_through_verified_codes(agri_db, tmp_path) -> None:
    from src.backend.app.agriculture import ingestion
    from src.backend.app.agriculture.domain.models import Crop, FaostatObservation, Observation

    _, config, engine = agri_db
    command.upgrade(config, "head")
    factory = sessionmaker(bind=engine)
    columns = "Area Code,Area Code (M49),Area,Item Code,Item Code (CPC),Item,Element Code,Element,Year Code,Year,Unit,Value,Flag,Note\n"
    path = tmp_path / "faostat-synthetic.csv"
    path.write_text(columns + "".join([
        f"109,'388,Jamaica,720,01657,\"Ginger, raw\",5510,Production,2022,2022,t,123.5,E,{SYNTHETIC}\n",
        f"109,'388,Jamaica,720,01657,\"Ginger, raw\",5312,Area harvested,2022,2022,ha,10,A,{SYNTHETIC}\n",
        f"109,'388,Jamaica,720,01657,\"Ginger, raw\",5412,Yield,2022,2022,hg/ha,99,A,{SYNTHETIC}\n",
        f"109,'388,Jamaica,999,0,Something else,5510,Production,2022,2022,t,1,A,{SYNTHETIC}\n",
    ]), encoding="utf-8")
    with factory() as session:
        ingestion.load_reference(session, apply=True)
        _approve(session, "FAOSTAT")
        unverified = ingestion.import_faostat(session, path, dataset_code="QCL", operator="test", apply=True)
        session.commit()
        assert unverified.faostat_rows == 4 and unverified.rows_accepted == 0
        assert {i["rule"] for i in unverified.issues} == {"UNVERIFIED_ELEMENT"}
        assert session.scalar(select(Observation.id)) is None
        assert len(session.scalars(select(FaostatObservation)).all()) == 4

    verified_map = tmp_path / "element_map_verified.csv"
    verified_map.write_text("element_code,element_name,fao_unit,measure_code,unit_code,verified\n"
                            "5510,Production,t,PRODUCTION,TONNE,true\n5312,Area harvested,ha,AREA_HARVESTED,HA,true\n"
                            "5412,Yield,kg/ha,YIELD,KG_PER_HA,true\n", encoding="utf-8")
    second = tmp_path / "faostat-synthetic-2.csv"
    second.write_text(path.read_text(encoding="utf-8").replace("123.5", "124.5"), encoding="utf-8")
    with factory() as session:
        session.scalar(select(Crop).where(Crop.code == "GINGER")).fao_item_code_verified = True  # test only
        mapped = ingestion.import_faostat(session, second, dataset_code="QCL", operator="test", apply=True, element_map=verified_map)
        session.commit()
        assert mapped.rows_accepted == 2 and mapped.rows_rejected == 1  # yield in hg/ha differs from the mapped kg/ha: refused
        assert {i["rule"] for i in mapped.issues} >= {"UNIT_MISMATCH", "UNVERIFIED_ITEM"}
        production = session.scalar(select(Observation).where(Observation.measure_code == "PRODUCTION"))
        assert production.value == Decimal("124.5") and production.status == "ESTIMATE" and production.source_flag == "E"


def test_reference_loading_is_additive_and_names_normalise() -> None:
    from src.backend.app.agriculture.ingestion import normalize, parse_period
    assert normalize("St. Ann") == normalize("Saint Ann") == normalize("ST ANN") == "ST ANN"
    assert normalize("Kingston & St. Andrew") == "KINGSTON AND ST ANDREW"
    assert parse_period("QUARTER", "2024-Q1") == (date(2024, 1, 1), date(2024, 3, 31))
    assert parse_period("QUARTER", "2024-Q4") == (date(2024, 10, 1), date(2024, 12, 31))
    assert parse_period("MONTH", "2024-02") == (date(2024, 2, 1), date(2024, 2, 29))
    for bad in (("YEAR", "24"), ("QUARTER", "2024-Q0"), ("MONTH", "2024-13")):
        with pytest.raises(ValueError):
            parse_period(*bad)


def test_evidence_queries_are_read_only_and_forecast_runs_are_stored_with_their_metrics(agri_db, tmp_path) -> None:
    from src.backend.app.agriculture import evidence as ev, ingestion
    from src.backend.app.agriculture.domain.models import Crop, Forecast, GeoArea, ModelEvaluation, ModelRun
    from src.backend.app.agriculture.forecasting import LastValue, backtest, record_model_run

    _, config, engine = agri_db
    command.upgrade(config, "head")
    factory = sessionmaker(bind=engine)
    lines = [f"Ginger,Jamaica,PRODUCTION,YEAR,{year},{value},TONNE,FINAL,,r{year}" for year, value in
             ((2018, 100), (2019, 110), (2020, 105), (2021, 120), (2022, 125), (2023, 130))]
    path = _template(tmp_path, "series.csv", lines)
    with factory() as session:
        ingestion.load_reference(session, apply=True)
        _approve(session, "MOA_AMID")
        ingestion.import_observations(session, path, operator="test", apply=True)
        session.commit()

    with engine.connect() as connection:
        rows = ev.run_query(connection, "series", {"crop": "GINGER", "measure": "PRODUCTION", "area": "JM", "from_year": 2018, "to_year": 2023})
        assert [r["value"] for r in rows] == [Decimal(v) for v in ("100", "110", "105", "120", "125", "130")]
        assert {r["source"] for r in rows} == {"MOA_AMID"} and rows[0]["attribution_text"].startswith("Source: Agricultural Marketing")
        connection.execute(text("select 1"))
        with pytest.raises(ev.EvidenceError, match="dedicated connection"):
            ev.run_query(connection, "series", {"crop": "GINGER", "measure": "PRODUCTION", "area": "JM", "from_year": 2018, "to_year": 2023})
    items = ev.build_evidence(rows)
    assert items[-1].value == "130" and items[-1].citation["licence_review_status"] == "APPROVED" and "revision 1" in items[-1].statement

    values = [float(r["value"]) for r in rows]
    evaluation = backtest(values, {"last_value": LastValue()}, min_train=3)["models"]["last_value"]
    with factory() as session:
        crop = session.scalar(select(Crop).where(Crop.code == "GINGER"))
        area = session.scalar(select(GeoArea).where(GeoArea.code == "JM"))
        model = LastValue().fit(values)
        run = record_model_run(session, model=model, purpose="BACKTEST", measure_code="PRODUCTION", crop_id=crop.id, geo_area_id=area.id,
                               period_type="YEAR", target_periods=[date(2024, 1, 1), date(2025, 1, 1)], forecasts=model.predict(2),
                               unit_code="TONNE", created_by="test", training=(date(2018, 1, 1), date(2023, 12, 31)),
                               evaluation=evaluation, data_snapshot=[str(r["observation_id"]) for r in rows])
        session.commit()
        stored = session.scalars(select(Forecast).where(Forecast.model_run_id == run.id).order_by(Forecast.horizon)).all()
        assert [(f.horizon, f.point) for f in stored] == [(1, Decimal("130")), (2, Decimal("130"))]
        assert all(f.lower <= f.point <= f.upper for f in stored)
        metrics = {m.metric_code for m in session.scalars(select(ModelEvaluation).where(ModelEvaluation.model_run_id == run.id))}
        assert {"mae", "rmse", "mase"} <= metrics
        assert len(session.get(ModelRun, run.id).data_snapshot) == 6
    with engine.connect() as connection:
        forecasts = ev.run_query(connection, "forecasts", {"crop": "GINGER", "measure": "PRODUCTION", "area": "JM"})
    assert [f["horizon"] for f in forecasts] == [1, 2] and forecasts[0]["model_code"] == "last_value"


def test_the_reviewed_read_only_role_reads_statistics_only(agri_db) -> None:
    """deploy/sql/agri_readonly_role.sql: SELECT on agri, nothing on operational tables, no writes. Idempotent."""
    _, config, engine = agri_db
    command.upgrade(config, "head")
    script = (BACKEND.parents[1] / "deploy" / "sql" / "agri_readonly_role.sql").read_text(encoding="utf-8")
    raw = engine.raw_connection()
    try:
        raw.autocommit = True
        with raw.cursor() as cursor:
            cursor.execute(script)
            cursor.execute(script)  # applying twice changes nothing
        with engine.connect() as connection:
            check = lambda table, privilege: connection.execute(
                text("select has_table_privilege('korofarm_agri_reader', :t, :p)"), {"t": table, "p": privilege}).scalar()
            assert check("agri.observations", "SELECT") and check("agri.forecasts", "SELECT")
            assert not check("agri.observations", "INSERT") and not check("agri.observations", "UPDATE")
            assert not check("public.requirements", "SELECT") and not check("public.contact_consents", "SELECT")
            assert not connection.execute(text("select rolcanlogin from pg_roles where rolname = 'korofarm_agri_reader'")).scalar()
    finally:
        with raw.cursor() as cursor:
            cursor.execute("drop owned by korofarm_agri_reader; drop role if exists korofarm_agri_reader")
        raw.close()


def test_forecast_lineage_and_explicit_rights_decisions_govern_external_processing(agri_db, tmp_path) -> None:
    """WP5 review correction: a forecast reaches an external model only with complete source lineage and an explicit
    EXTERNAL_LLM decision for its run. Source licences are recorded with the decision, never applied implicitly."""
    from src.backend.app.agriculture import evidence as ev, ingestion, lineage
    from src.backend.app.agriculture.domain.models import Crop, GeoArea, Observation, Source
    from src.backend.app.agriculture.forecasting import LastValue, record_model_run
    from test_agri_intelligence import ENABLED

    _, config, engine = agri_db
    command.upgrade(config, "head")
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    moa = _template(tmp_path, "moa.csv", [f"Ginger,Jamaica,PRODUCTION,YEAR,{y},{v},TONNE,FINAL,,r{y}" for y, v in ((2019, 100), (2020, 110), (2021, 120))])
    faostat = tmp_path / "faostat.csv"
    faostat.write_text("Area Code,Area Code (M49),Area,Item Code,Item Code (CPC),Item,Element Code,Element,Year Code,Year,Unit,Value,Flag,Note\n"
                       f"109,'388,Jamaica,720,01657,Ginger,5510,Production,2022,2022,t,130,A,{SYNTHETIC}\n", encoding="utf-8")
    element_map = tmp_path / "map.csv"
    element_map.write_text("element_code,element_name,fao_unit,measure_code,unit_code,verified\n5510,Production,t,PRODUCTION,TONNE,true\n", encoding="utf-8")
    with factory() as session:
        ingestion.load_reference(session, apply=True)
        _approve(session, "MOA_AMID")
        ingestion.import_observations(session, moa, operator="test", apply=True)
        _approve(session, "FAOSTAT")  # test only: to import a row; reset below to show mixed licence states
        session.scalar(select(Crop).where(Crop.code == "GINGER")).fao_item_code_verified = True
        ingestion.import_faostat(session, faostat, dataset_code="QCL", operator="test", apply=True, element_map=element_map)
        session.scalar(select(Source).where(Source.code == "FAOSTAT")).licence_review_status = "NOT_REVIEWED"
        session.commit()

    def run_inputs(session):
        crop = session.scalar(select(Crop).where(Crop.code == "GINGER"))
        area = session.scalar(select(GeoArea).where(GeoArea.code == "JM"))
        observations = session.scalars(select(Observation).order_by(Observation.period_start)).all()
        model = LastValue().fit([float(o.value) for o in observations])
        common = dict(purpose="FORECAST", measure_code="PRODUCTION", crop_id=crop.id, geo_area_id=area.id, period_type="YEAR",
                      forecasts=model.predict(1), unit_code="TONNE", created_by="test")
        return model, observations, common

    with factory() as session:
        model, observations, common = run_inputs(session)
        with pytest.raises(ValueError, match="not recorded observations"):  # an unknown input never becomes lineage
            record_model_run(session, model=model, data_snapshot=[str(uuid4())], target_periods=[date(2023, 1, 1)], **common)
        session.rollback()
    with factory() as session:
        model, observations, common = run_inputs(session)
        mixed = record_model_run(session, model=model, data_snapshot=[str(o.id) for o in observations],
                                 target_periods=[date(2023, 1, 1)], **common)
        session.commit()
        found = lineage.lineage_of(session, mixed.id)
        assert found.complete and found.inputs == 4
        assert {(s["code"], s["licence_review_status"]) for s in found.sources} == {("MOA_AMID", "APPROVED"), ("FAOSTAT", "NOT_REVIEWED")}

    def evidence_now():
        with engine.connect() as connection:
            rows = ev.run_query(connection, "forecasts", {"crop": "GINGER", "measure": "PRODUCTION", "area": "JM"})
        return ev.build_evidence(rows)

    items = evidence_now()                                            # mixed sources, no decision yet
    assert items[0].kind == "forecast" and items[0].citation["lineage"]["complete"]
    assert not ev.provider_permitted(items, 100, ENABLED)[0]
    assert "no recorded EXTERNAL_LLM rights decision" in ev.provider_permitted(items, 100, ENABLED)[1]
    with factory() as session:
        with pytest.raises(lineage.RightsDecisionError, match="approval reference"):
            lineage.record_rights_decision(session, model_run_id=mixed.id, purpose="EXTERNAL_LLM", permitted=True,
                                           basis="product owner reviewed the sources", decided_by="po")
        lineage.record_rights_decision(session, model_run_id=mixed.id, purpose="EXTERNAL_LLM", permitted=False,
                                       basis="FAOSTAT rights not yet reviewed", decided_by="po")
        session.commit()
    assert "is NOT_PERMITTED" in ev.provider_permitted(evidence_now(), 100, ENABLED)[1]           # restricted
    with factory() as session:
        decision = lineage.record_rights_decision(session, model_run_id=mixed.id, purpose="EXTERNAL_LLM", permitted=True,
                                                  basis="product owner approved synthetic evaluation of this run", decided_by="po",
                                                  approval_reference="PO-TEST-1")
        session.commit()
        assert {s["code"] for s in decision.source_statuses} == {"MOA_AMID", "FAOSTAT"}  # what the decider saw is kept
    assert ev.provider_permitted(evidence_now(), 100, ENABLED) == (True, "permitted")              # approved, explicitly

    with factory() as session:                                         # missing lineage: a run with no recorded inputs
        model, observations, common = run_inputs(session)
        empty = record_model_run(session, model=model, data_snapshot=[], target_periods=[date(2024, 1, 1)], **common)
        session.commit()
        assert not lineage.lineage_of(session, empty.id).complete
        with pytest.raises(lineage.RightsDecisionError, match="lineage is incomplete"):
            lineage.record_rights_decision(session, model_run_id=empty.id, purpose="EXTERNAL_LLM", permitted=True,
                                           basis="attempt to permit unknown lineage", decided_by="po", approval_reference="PO-X")
        session.rollback()
        # Even a PERMITTED row written around the API cannot release a forecast whose lineage is unknown.
        session.execute(text("insert into agri.derived_rights_decisions (id, model_run_id, purpose, decision, basis, decided_by, approval_reference) "
                             "values (:id, :run, 'EXTERNAL_LLM', 'PERMITTED', 'written directly', 'test', 'PO-X')"), {"id": uuid4(), "run": empty.id})
        session.commit()
    newest = [e for e in evidence_now() if e.citation["model_run_id"] == str(empty.id)]
    assert newest and not ev.provider_permitted(newest, 100, ENABLED)[0]
    assert "lineage is unknown" in ev.provider_permitted(newest, 100, ENABLED)[1]
    # Recorded lineage and decisions are never dropped by a downgrade.
    with pytest.raises(Exception, match="refusing to drop"):
        command.downgrade(config, "0029_agricultural_intelligence")
