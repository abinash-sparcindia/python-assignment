"""Network asset lifecycle, field errors, visit retention and roles."""

import secrets

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from utility_assets.auth import get_session, hash_password
from utility_assets.main import create_app
from utility_assets.models import Asset, User, Visit


@pytest.fixture
def client(db_session, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", str(db_session.bind.url))
    monkeypatch.setenv("SIGNING_SECRET", secrets.token_urlsafe(48))
    app = create_app()

    def test_session():
        with Session(db_session.bind) as session:
            yield session

    app.dependency_overrides[get_session] = test_session
    with TestClient(app) as test_client:
        yield test_client


def credential(client, db_session, role):
    password = secrets.token_urlsafe(24)
    username = f"user-{secrets.token_hex(4)}"
    db_session.add(User(username=username, password_hash=hash_password(password), role=role))
    db_session.commit()
    response = client.post("/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def sample(asset_id="AA-0001"):
    return {
        "asset_id": asset_id,
        "name": "  north  pole ",
        "asset_type": "POLE",
        "latitude": "12.5N",
        "longitude": "77.25E",
        "elevation_m": None,
        "surveyed_on": "2026-09-01",
        "surveyor": "  rita  sen ",
        "status": "active",
        "condition_score": 7,
        "attribute_json": {"material": "steel"},
    }


def test_six_operations_keep_visits_and_cascade_on_delete(client, db_session):
    surveyor = credential(client, db_session, "surveyor")
    administrator = credential(client, db_session, "administrator")
    assert client.get("/assets").status_code == 401

    created = client.post("/assets", json={**sample(), "notes": "Initial survey"}, headers=surveyor)
    assert created.status_code == 201
    assert created.json()["name"] == "North Pole"
    assert created.json()["attribute_json"] == {"material": "steel"}
    assert client.get("/assets/AA-0001", headers=surveyor).json() == created.json()
    listing = client.get("/assets", headers=surveyor)
    assert listing.json()["total"] == 1
    assert listing.json()["items"] == [created.json()]

    patched = client.patch(
        "/assets/AA-0001", json={"condition_score": 5, "notes": "Recheck"}, headers=surveyor
    )
    assert patched.status_code == 200
    assert patched.json()["name"] == "North Pole"
    assert patched.json()["condition_score"] == 5
    replaced = client.put(
        "/assets/AA-0001", json={**sample(), "name": "south valve", "asset_type": "valve"}, headers=surveyor
    )
    assert replaced.status_code == 200
    assert replaced.json()["name"] == "South Valve"
    with Session(db_session.bind) as session:
        visits = session.scalars(select(Visit).where(Visit.asset_id == "AA-0001").order_by(Visit.id)).all()
        assert [visit.condition_score for visit in visits] == [7, 5, 7]
        assert [visit.notes for visit in visits] == ["Initial survey", "Recheck", None]

    denied = client.delete("/assets/AA-0001", headers=surveyor)
    assert denied.status_code == 403
    assert denied.json()["errors"][0]["field"] == "authorization"
    assert client.delete("/assets/AA-0001", headers=administrator).status_code == 204
    assert client.get("/assets/AA-0001", headers=surveyor).status_code == 404
    with Session(db_session.bind) as session:
        assert session.scalar(select(func.count()).select_from(Asset)) == 0
        assert session.scalar(select(func.count()).select_from(Visit)) == 0


def test_invalid_duplicate_missing_and_immutable_id(client, db_session):
    headers = credential(client, db_session, "surveyor")
    bad = {**sample(), "latitude": "91N", "condition_score": 11}
    invalid = client.post("/assets", json=bad, headers=headers)
    assert invalid.status_code == 422
    assert {item["field"] for item in invalid.json()["errors"]} == {"latitude", "condition_score"}
    assert client.post("/assets", json=sample(), headers=headers).status_code == 201
    duplicate = client.post("/assets", json=sample(), headers=headers)
    assert duplicate.status_code == 409
    assert duplicate.json()["errors"][0]["field"] == "asset_id"
    assert client.put("/assets/AA-9999", json=sample(), headers=headers).status_code == 404
    assert client.patch("/assets/AA-0001", json={"asset_id": "BB-0001"}, headers=headers).status_code == 422
    assert client.put("/assets/AA-0001", json={**sample(), "asset_id": "BB-0001"}, headers=headers).status_code == 422
    assert client.put("/assets/AA-0001", json={"name": "Short"}, headers=headers).status_code == 422
    assert client.patch("/assets/AA-0001", json={"condition_score": 99}, headers=headers).status_code == 422
    assert client.patch("/assets/AA-0001", json={"unknown": 1}, headers=headers).status_code == 422
    assert client.patch("/assets/AA-0001", json={}, headers=headers).status_code == 422
    with Session(db_session.bind) as session:
        assert session.scalar(select(func.count()).select_from(Visit)) == 1


def test_list_has_stable_bounded_pages(client, db_session):
    headers = credential(client, db_session, "surveyor")
    for code in ("AA-0002", "AA-0001", "AA-0003"):
        assert client.post("/assets", json=sample(code), headers=headers).status_code == 201
    page = client.get("/assets?limit=2&offset=1", headers=headers)
    assert page.status_code == 200
    assert page.json()["total"] == 3
    assert [asset["asset_id"] for asset in page.json()["items"]] == ["AA-0002", "AA-0003"]
    assert client.get("/assets?limit=101", headers=headers).status_code == 422


def test_patch_preserves_json_string_attribute(client, db_session):
    headers = credential(client, db_session, "surveyor")
    payload = {**sample(), "attribute_json": '"external reference"'}
    assert client.post("/assets", json=payload, headers=headers).status_code == 201
    changed = client.patch("/assets/AA-0001", json={"condition_score": 6}, headers=headers)
    assert changed.status_code == 200
    assert changed.json()["attribute_json"] == "external reference"
