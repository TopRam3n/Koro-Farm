"""Crop catalogue: shared crops, organization-private crops, and validation of orders against it."""
from datetime import date

from two_orgs import add_member, as_user, ensure_roles, factory, http  # noqa: F401  (pytest fixtures)
from src.backend.app.demand.domain.models import Buyer
from src.backend.app.identity.domain.models import Organization
from src.backend.app.identity.domain.permissions import RoleCode

from uuid import uuid4


def _two_coordinators(factory):
    with factory() as session:
        ensure_roles(session)
        orgs = []
        for label in ("Alpha", "Beta"):
            org = Organization(id=uuid4(), name=f"{label} Exports", slug=f"{label.lower()}-{uuid4().hex[:6]}")
            session.add(org); session.flush()
            user = add_member(session, org.id, RoleCode.PROCUREMENT_MANAGER, label)
            buyer = Buyer(organization_id=org.id, name=f"{label} Hotel", buyer_type="HOTEL", destination="Ocho Rios")
            session.add(buyer); session.flush()
            orgs.append({"org": org.id, "user": user.id, "buyer": buyer.id})
        session.commit()
    return orgs


def _order(http, who, crop: str):
    return http.post("/requirements", headers=as_user(who["user"], who["org"]), json={
        "buyer_id": str(who["buyer"]), "crop": crop, "grade": "A", "required_quantity_kg": "730",
        "delivery_window_start": str(date(2026, 12, 1)), "delivery_window_end": str(date(2026, 12, 12))})


def test_shared_catalogue_includes_previous_crops_and_scotch_bonnet(http, factory) -> None:
    a, _ = _two_coordinators(factory)
    codes = {row["code"] for row in http.get("/crops", headers=as_user(a["user"], a["org"])).json()}
    assert {"GINGER", "SWEET_POTATO", "BREADFRUIT", "SCOTCH_BONNET"} <= codes


def test_long_crop_codes_persist_and_round_trip(http, factory) -> None:
    a, _ = _two_coordinators(factory)
    for crop in ("SCOTCH_BONNET", "SWEET_POTATO", "BREADFRUIT"):
        created = _order(http, a, crop)
        assert created.status_code == 201, created.text
        fetched = http.get(f"/requirements/{created.json()['id']}", headers=as_user(a["user"], a["org"]))
        assert fetched.json()["crop"] == crop


def test_unknown_crop_is_rejected_not_stored(http, factory) -> None:
    a, _ = _two_coordinators(factory)
    response = _order(http, a, "UNOBTAINIUM")
    assert response.status_code == 422
    assert "crop catalogue" in response.text
    assert http.get("/requirements", headers=as_user(a["user"], a["org"])).json() == []


def test_private_crops_belong_to_one_organization(http, factory) -> None:
    a, b = _two_coordinators(factory)
    created = http.post("/crops", headers=as_user(a["user"], a["org"]), json={"code": "pak_choi", "name": "Pak choi"})
    assert created.status_code == 201, created.text
    assert created.json()["code"] == "PAK_CHOI" and created.json()["shared"] is False
    assert _order(http, a, "PAK_CHOI").status_code == 201
    assert "PAK_CHOI" not in {row["code"] for row in http.get("/crops", headers=as_user(b["user"], b["org"])).json()}
    assert _order(http, b, "PAK_CHOI").status_code == 422
    assert http.post("/crops", headers=as_user(a["user"], a["org"]), json={"code": "GINGER", "name": "Dup"}).status_code == 409


def test_crop_creation_requires_permission(http, factory) -> None:
    a, _ = _two_coordinators(factory)
    with factory() as session:
        auditor = add_member(session, a["org"], RoleCode.AUDITOR, "auditor")
        session.commit()
    assert http.post("/crops", headers=as_user(auditor.id, a["org"]), json={"code": "SORREL", "name": "Sorrel"}).status_code == 403
