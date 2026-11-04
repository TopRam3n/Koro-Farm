"""Staging infrastructure tooling: connection settings, provisioning and the read-only readiness check.

Nothing here contacts a real Supabase project or provider: HTTP is a stand-in and the databases are SQLite and the
disposable PostgreSQL test instance. These tests prove the tools' behaviour, not connectivity to any real service.
"""
import json
from uuid import uuid4

import pytest

from src.backend.app.identity.domain.models import MembershipStatus, Organization, OrganizationMembership, UserAccount
from src.backend.app.identity.domain.permissions import RoleCode
from src.backend.app.infrastructure.database.session import engine_options
from src.backend.scripts import check_staging, provision_staging
from src.backend.scripts.check_staging import HttpResult
from src.backend.tests.two_orgs import as_user, ensure_roles, factory, http  # noqa: F401  (fixtures)

POOLER = "postgresql+psycopg://app:placeholder@aws-0-region.pooler.supabase.com:{port}/postgres?sslmode=require"


# --- Connection settings -------------------------------------------------------------------------------------------

def test_transaction_pooler_turns_off_prepared_statements_and_session_mode_keeps_them() -> None:
    transaction = engine_options(POOLER.format(port=6543), {})
    assert transaction["connect_args"]["prepare_threshold"] is None
    session = engine_options(POOLER.format(port=5432), {})
    assert "prepare_threshold" not in session["connect_args"]
    assert session["pool_pre_ping"] and session["pool_size"] == 5 and session["max_overflow"] == 10
    assert session["connect_args"]["connect_timeout"] == 10 and session["connect_args"]["application_name"] == "korofarm"


def test_connection_settings_come_from_the_environment() -> None:
    options = engine_options(POOLER.format(port=5432), {
        "DB_POOL_SIZE": "3", "DB_MAX_OVERFLOW": "2", "DB_POOL_RECYCLE_SECONDS": "600", "DB_CONNECT_TIMEOUT_SECONDS": "4",
        "DB_APPLICATION_NAME": "korofarm-worker", "DB_PREPARED_STATEMENTS": "off"})
    assert (options["pool_size"], options["max_overflow"], options["pool_recycle"]) == (3, 2, 600)
    assert options["connect_args"] == {"connect_timeout": 4, "application_name": "korofarm-worker", "prepare_threshold": None}
    assert "prepare_threshold" not in engine_options(POOLER.format(port=6543), {"DB_PREPARED_STATEMENTS": "on"})["connect_args"]
    with pytest.raises(ValueError):
        engine_options(POOLER.format(port=5432), {"DB_PREPARED_STATEMENTS": "sometimes"})
    assert engine_options("sqlite+pysqlite:///:memory:", {}) == {"pool_pre_ping": True}


# --- Provisioning --------------------------------------------------------------------------------------------------

def _plan(tmp_path, **override) -> tuple:
    a, b, c = uuid4(), uuid4(), uuid4()
    plan = {
        "organizations": [{"slug": "staging-org-a", "name": "Staging Organization A"},
                          {"slug": "staging-org-b", "name": "Staging Organization B"}],
        "users": [
            {"id": str(a), "email": "Coordinator.A@example.test", "display_name": "Coordinator A",
             "memberships": [{"organization": "staging-org-a", "role": "SUPPLY_COORDINATOR"}]},
            {"id": str(b), "email": "colleague.a@example.test", "display_name": "Colleague A",
             "memberships": [{"organization": "staging-org-a", "role": "AUDITOR"}]},
            {"id": str(c), "email": "coordinator.b@example.test", "display_name": "Coordinator B",
             "memberships": [{"organization": "staging-org-b", "role": "SUPPLY_COORDINATOR"}]},
        ],
    }
    plan.update(override)
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan), encoding="utf-8")
    return path, (a, b, c)


def _counts(session) -> tuple:
    from sqlalchemy import func, select
    return tuple(session.scalar(select(func.count()).select_from(model))
                 for model in (Organization, UserAccount, OrganizationMembership))


def test_provisioning_is_a_dry_run_until_applied_then_idempotent(factory, tmp_path, capsys) -> None:
    with factory() as session:
        ensure_roles(session)
        session.commit()
        before = _counts(session)
    path, _ = _plan(tmp_path)
    env = {"APP_ENV": "staging"}
    assert provision_staging.main([str(path)], env=env, session_factory=factory) == 0
    out = capsys.readouterr().out
    assert "create:    organization staging-org-a" in out and "dry run: nothing was written" in out
    with factory() as session:
        assert _counts(session) == before

    assert provision_staging.main([str(path), "--apply"], env=env, session_factory=factory) == 0
    with factory() as session:
        assert _counts(session) == (before[0] + 2, before[1] + 3, before[2] + 3)
    capsys.readouterr()
    assert provision_staging.main([str(path), "--apply"], env=env, session_factory=factory) == 0
    out = capsys.readouterr().out
    assert "create:" not in out and "unchanged: membership coordinator.a@example.test -> staging-org-a" in out
    with factory() as session:
        assert _counts(session) == (before[0] + 2, before[1] + 3, before[2] + 3)


def test_provisioned_accounts_reach_only_their_own_organization(factory, http, tmp_path) -> None:
    with factory() as session:
        ensure_roles(session)
        session.commit()
    path, (a, b, c) = _plan(tmp_path)
    assert provision_staging.main([str(path), "--apply"], env={"APP_ENV": "staging"}, session_factory=factory) == 0
    from sqlalchemy import select
    with factory() as session:
        org = {o.slug: o.id for o in session.scalars(select(Organization).where(Organization.slug.like("staging-org-%")))}
    me = http.get("/me", headers=as_user(a, org["staging-org-a"]))
    assert me.status_code == 200 and me.json()["active_role"] == "SUPPLY_COORDINATOR"
    assert me.json()["active_organization_id"] == str(org["staging-org-a"]) and me.json()["email"] == "coordinator.a@example.test"
    # Organization B's id in the header is refused for an organization A account, and vice versa.
    assert http.get("/me", headers=as_user(a, org["staging-org-b"])).status_code == 403
    assert http.get("/me", headers=as_user(c, org["staging-org-a"])).status_code == 403
    assert http.get("/me", headers=as_user(c, org["staging-org-b"])).status_code == 200


def test_conflicts_are_reported_and_nothing_is_written(factory, tmp_path, capsys) -> None:
    path, (a, _, _) = _plan(tmp_path)
    with factory() as session:
        ensure_roles(session)
        session.add(UserAccount(id=uuid4(), email="coordinator.a@example.test", display_name="Someone Else"))
        session.commit()
        before = _counts(session)
    assert provision_staging.main([str(path), "--apply"], env={"APP_ENV": "staging"}, session_factory=factory) == 1
    captured = capsys.readouterr()
    assert "CONFLICT:  email coordinator.a@example.test already belongs to account" in captured.out
    assert "nothing was written" in captured.err
    with factory() as session:
        assert _counts(session) == before


def test_an_existing_membership_with_another_role_is_never_changed(factory, tmp_path, capsys) -> None:
    path, (a, _, _) = _plan(tmp_path)
    with factory() as session:
        ensure_roles(session)
        organization = Organization(name="Staging Organization A", slug="staging-org-a")
        session.add_all([organization, UserAccount(id=a, email="coordinator.a@example.test", display_name="Coordinator A")])
        session.flush()
        session.add(OrganizationMembership(user_id=a, organization_id=organization.id, role_code=RoleCode.AUDITOR,
                                           status=MembershipStatus.ACTIVE))
        session.commit()
        before = _counts(session)
    assert provision_staging.main([str(path), "--apply"], env={"APP_ENV": "staging"}, session_factory=factory) == 1
    assert "exists as AUDITOR" in capsys.readouterr().out
    with factory() as session:
        assert _counts(session) == before


@pytest.mark.parametrize("users, message", [
    ([{"id": "not-a-uuid", "email": "x@example.test", "display_name": "X", "memberships": []}], "Supabase user UUID"),
    ([{"id": str(uuid4()), "email": "x@example.test", "display_name": "X", "password": "nope", "memberships": []}],
     "passwords never belong"),
    ([{"id": str(uuid4()), "email": "x@example.test", "display_name": "X",
       "memberships": [{"organization": "staging-org-a", "role": "FARMER"}]}], "in-app invitation"),
    ([{"id": str(uuid4()), "email": "x@example.test", "display_name": "X",
       "memberships": [{"organization": "staging-org-a", "role": "PLATFORM_ADMIN"}]}], "--allow-platform-admin"),
    ([{"id": str(uuid4()), "email": "x@example.test", "display_name": "X",
       "memberships": [{"organization": "somewhere-else", "role": "AUDITOR"}]}], "listed in the plan"),
])
def test_plans_asking_for_what_the_script_never_does_are_refused(tmp_path, users, message) -> None:
    path, _ = _plan(tmp_path, users=users)
    with pytest.raises(provision_staging.PlanError, match=message):
        provision_staging.load_plan(path)


def test_provisioning_never_runs_in_production(tmp_path, capsys) -> None:
    path, _ = _plan(tmp_path)
    assert provision_staging.main([str(path), "--apply"], env={"APP_ENV": "production"}, session_factory=None) == 2
    assert "refusing to run in production" in capsys.readouterr().err


# --- Readiness check -----------------------------------------------------------------------------------------------

STAGING = {"APP_ENV": "staging", "SUPABASE_URL": "https://abcdefgh.supabase.co",
           "SUPABASE_PUBLISHABLE_KEY": "sb_publishable_PLACEHOLDERVALUE",
           "DATABASE_URL": "postgresql+psycopg://app:Sup3r-Secret-pw@127.0.0.1:1/postgres?sslmode=require"}


class FakeHttp:
    def __init__(self, responses: dict):
        self.responses = responses
        self.calls: list = []

    def __call__(self, method, url, headers=None, timeout=10):
        self.calls.append((method, url, dict(headers or {})))
        for (want_method, fragment), result in self.responses.items():
            if method == want_method and fragment in url and (fragment != "/me" or url.endswith("/me")):
                if callable(result):
                    return result(headers or {})
                return result
        raise AssertionError(f"unexpected request {method} {url}")


def _ok(body="", status=200, headers=None):
    return HttpResult(status, headers or {}, body)


def test_data_api_probe_fails_when_rows_are_readable_and_passes_when_refused() -> None:
    rows = FakeHttp({("GET", "/rest/v1/organizations"): _ok('[{"id": "x"}]')})
    assert check_staging.check_data_api_http(STAGING, rows).status == "FAIL"
    empty = FakeHttp({("GET", "/rest/v1/organizations"): _ok("[]")})
    assert check_staging.check_data_api_http(STAGING, empty).status == "WARN"
    for code in (401, 403, 404):
        refused = FakeHttp({("GET", "/rest/v1/organizations"): _ok('{"message": "no"}', code)})
        result = check_staging.check_data_api_http(STAGING, refused)
        assert result.status == "PASS" and str(code) in result.detail
    assert check_staging.check_data_api_http({"APP_ENV": "staging"}, rows).status == "SKIP"


def test_auth_settings_report_open_sign_up_and_disabled_email() -> None:
    def settings(**values):
        return FakeHttp({("GET", "/auth/v1/settings"): _ok(json.dumps(values))})
    assert check_staging.check_auth_settings(STAGING, settings(external={"email": True}, disable_signup=True)).status == "PASS"
    open_signup = check_staging.check_auth_settings(STAGING, settings(external={"email": True}, disable_signup=False))
    assert open_signup.status == "WARN" and "OPEN" in open_signup.detail
    assert check_staging.check_auth_settings(STAGING, settings(external={"email": False})).status == "FAIL"
    bad_key = FakeHttp({("GET", "/auth/v1/settings"): _ok("", 401)})
    assert check_staging.check_auth_settings(STAGING, bad_key).status == "FAIL"


def test_api_checks_cover_health_worker_auth_and_cors() -> None:
    def preflight(headers):
        origin = headers.get("Origin")
        allowed = origin == "https://staging.example.org"
        return _ok(status=200 if allowed else 400, headers={"access-control-allow-origin": origin} if allowed else {})
    fake = FakeHttp({
        ("GET", "/health/worker"): _ok('{"status": "DEGRADED", "worker": "STALE", "reasons": ["worker_not_running"]}', 503),
        ("GET", "/health"): _ok('{"status": "ok"}'),
        ("GET", "/me"): _ok('{"detail": "Bearer token required"}', 401),
        ("OPTIONS", "/me"): preflight,
    })
    checks = {c.name: c for c in check_staging.check_api("https://api.example.org/", "https://staging.example.org", fake)}
    assert checks["api_health"].status == "PASS"
    assert checks["worker_health"].status == "FAIL" and "worker_not_running" in checks["worker_health"].detail
    assert checks["api_auth"].status == "PASS"
    assert checks["cors"].status == "PASS" and "unrelated origin refused" in checks["cors"].detail

    leaky = FakeHttp({**fake.responses, ("OPTIONS", "/me"): lambda h: _ok(headers={"access-control-allow-origin": "*"})})
    assert {c.name: c for c in check_staging.check_api("https://api.example.org", "https://staging.example.org", leaky)}["cors"].status == "FAIL"


def test_configuration_and_model_provider_checks() -> None:
    assert check_staging.check_configuration(STAGING).status == "PASS"
    assert check_staging.check_configuration({**STAGING, "DATABASE_URL": ""}).status == "FAIL"
    assert check_staging.check_configuration({"APP_ENV": "development"}).status == "WARN"
    assert check_staging.check_model_provider(STAGING).status == "PASS"
    unapproved = check_staging.check_model_provider({**STAGING, "AGENT_MODEL_PROVIDER": "nebius"})
    assert unapproved.status == "PASS" and "not permitted" in unapproved.detail
    approved = check_staging.check_model_provider({**STAGING, "AGENT_MODEL_PROVIDER": "nebius",
                                                   "AGENT_MODEL_STAGING_APPROVAL": "PO-ref-1"})
    assert approved.status == "WARN" and "PO-ref-1" in approved.detail


def test_the_check_never_prints_credentials_and_fails_when_the_database_is_unreachable(capsys, tmp_path) -> None:
    fake = FakeHttp({("GET", "/rest/v1/"): _ok("", 401), ("GET", "/auth/v1/settings"): _ok('{"external": {"email": true}, "disable_signup": true}')})
    out_file = tmp_path / "result.json"
    assert check_staging.main(["--json", str(out_file)], env=STAGING, http=fake) == 1
    printed = capsys.readouterr().out + out_file.read_text(encoding="utf-8")
    assert "Sup3r-Secret-pw" not in printed and "PLACEHOLDERVALUE" not in printed
    assert "FAIL  database" in printed and "***" in printed
    assert all("PLACEHOLDERVALUE" not in url for _, url, _ in fake.calls)  # the key goes in headers, never URLs


def test_the_check_refuses_production(capsys) -> None:
    assert check_staging.main([], env={**STAGING, "APP_ENV": "production"}) == 2


# --- Local env-file runner -----------------------------------------------------------------------------------------

def test_env_file_runner_loads_values_without_printing_them(tmp_path, capfd) -> None:
    import sys
    from src.backend.scripts import with_env
    env_file = tmp_path / ".env.staging.local"  # outside the repository: never committable
    env_file.write_text('# staging\nAPP_ENV=staging\nexport SECRET_THING="v@lue with spaces"\n\nEMPTY=\n', encoding="utf-8")
    code = with_env.main(["--names", str(env_file), "--", sys.executable, "-c",
                          "import os, sys; sys.exit(0 if os.environ['SECRET_THING'] == 'v@lue with spaces' and os.environ['APP_ENV'] == 'staging' else 3)"])
    out, err = capfd.readouterr()
    assert code == 0
    assert "loaded: APP_ENV, EMPTY, SECRET_THING" in err and "v@lue" not in out + err


def test_env_file_runner_refuses_files_git_would_commit_and_malformed_lines(tmp_path, capfd) -> None:
    import sys
    from src.backend.scripts import with_env
    tracked_name = with_env.REPO / "src" / "backend" / "staging-values.txt"  # not matched by .gitignore
    tracked_name.write_text("A=1\n", encoding="utf-8")
    try:
        assert with_env.main([str(tracked_name), "--", sys.executable, "-c", "pass"]) == 2
        assert "git would commit it" in capfd.readouterr().err
    finally:
        tracked_name.unlink()
    ignored = with_env.REPO / "src" / "backend" / ".env.readiness-test.local"
    ignored.write_text("A=1\n", encoding="utf-8")
    try:
        assert with_env.main([str(ignored), "--", sys.executable, "-c", "pass"]) == 0
    finally:
        ignored.unlink()
    bad = tmp_path / ".env.bad"
    bad.write_text("this line holds a password-like thing\n", encoding="utf-8")
    assert with_env.main([str(bad), "--", sys.executable, "-c", "pass"]) == 2
    err = capfd.readouterr().err
    assert "line 1 is not KEY=VALUE" in err and "password-like" not in err
