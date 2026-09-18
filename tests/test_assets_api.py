"""Network asset lifecycle, field errors, visit retention and roles."""

import csv
import io
import secrets

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from utility_assets.auth import get_session, hash_password
from utility_assets.main import create_app
from utility_assets.models import Asset, User, Visit
from utility_assets.ingestion import OutputPaths, ingest_csv
from utility_assets import report_cache
from utility_assets.validation import EXPECTED_COLUMNS


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


def test_filters_search_paging_and_history(client, db_session):
    headers = credential(client, db_session, "surveyor")
    records = [
        {**sample("AA-0001"), "name": "North Pole", "asset_type": "pole", "surveyor": "Rita Sen", "condition_score": 3},
        {**sample("AA-0002"), "name": "South Valve", "asset_type": "valve", "surveyor": "Arun Rai", "condition_score": 8},
        {**sample("AA-0003"), "name": "North Valve", "asset_type": "valve", "surveyor": "Rita Sen", "condition_score": 6},
    ]
    for record in records:
        assert client.post("/assets", json=record, headers=headers).status_code == 201
    assert client.patch("/assets/AA-0001", json={"condition_score": 4, "notes": "follow-up"}, headers=headers).status_code == 200
    found = client.get(
        "/assets?asset_type=POLE&status=active&surveyor=rita%20sen&min_score=4&max_score=5&search=nOrTh",
        headers=headers,
    )
    assert found.status_code == 200
    assert found.json()["total"] == 1
    assert found.json()["items"][0]["asset_id"] == "AA-0001"
    assert client.get("/assets?search=%25", headers=headers).json()["total"] == 0
    assert client.get("/assets?min_score=8&max_score=3", headers=headers).status_code == 422
    assert client.get("/assets?asset_type=cable", headers=headers).status_code == 422
    assert client.get("/assets?status=retired", headers=headers).status_code == 422
    visits = client.get("/assets/AA-0001/visits?limit=1", headers=headers)
    assert visits.status_code == 200
    assert visits.json()["total"] == 2
    assert visits.json()["items"][0]["notes"] == "follow-up"
    assert client.get("/assets/AA-9999/visits", headers=headers).status_code == 404
    ranking = client.get("/reports/most-visited?limit=2", headers=headers)
    assert ranking.json() == [
        {"asset_id": "AA-0001", "visit_count": 2},
        {"asset_id": "AA-0002", "visit_count": 1},
    ]


def _csv_bytes(rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=EXPECTED_COLUMNS)
    writer.writeheader()
    for row in rows:
        writer.writerow({**row, "attribute_json": '{"material":"steel"}'})
    return stream.getvalue().encode("utf-8")


def test_admin_csv_upload_reuses_ingestion_and_reports_rejects(client, db_session):
    surveyor = credential(client, db_session, "surveyor")
    administrator = credential(client, db_session, "administrator")
    payload = _csv_bytes([sample("AA-0001"), {**sample("AA-0002"), "latitude": "100N"}])
    endpoint = "/imports/assets"
    assert client.post(endpoint, content=payload, headers={"Content-Type": "text/csv"}).status_code == 401
    assert client.post(endpoint, content=payload, headers={**surveyor, "Content-Type": "text/csv"}).status_code == 403
    uploaded = client.post(endpoint, content=payload, headers={**administrator, "Content-Type": "text/csv"})
    assert uploaded.status_code == 200
    assert (uploaded.json()["rows_read"], uploaded.json()["accepted"], uploaded.json()["rejected"]) == (2, 1, 1)
    assert uploaded.json()["rejected_rows"][0]["original"]["latitude"] == "100N"
    with Session(db_session.bind) as session:
        assert session.scalar(select(func.count()).select_from(Asset)) == 1
        assert session.scalar(select(func.count()).select_from(Visit)) == 1
    repeated = client.post(endpoint, content=_csv_bytes([{**sample("AA-0001"), "condition_score": 5}]), headers={**administrator, "Content-Type": "text/csv"})
    assert repeated.json()["accepted"] == 1
    with Session(db_session.bind) as session:
        assert session.get(Asset, "AA-0001").condition_score == 5
        assert session.scalar(select(func.count()).select_from(Visit)) == 2


def test_strict_upload_rolls_back_and_bad_schema_returns_422(client, db_session):
    administrator = credential(client, db_session, "administrator")
    headers = {**administrator, "Content-Type": "text/csv"}
    payload = _csv_bytes([sample("AA-0001"), {**sample("AA-0002"), "condition_score": 12}])
    aborted = client.post("/imports/assets?strict=true", content=payload, headers=headers)
    assert aborted.status_code == 200
    assert (aborted.json()["aborted"], aborted.json()["accepted"], aborted.json()["rejected"]) == (True, 0, 1)
    assert client.post("/imports/assets", content=b"asset_id,name\nAA-0001,Missing\n", headers=headers).status_code == 422
    assert client.post("/imports/assets", content=b"", headers=headers).status_code == 422
    with Session(db_session.bind) as session:
        assert session.scalar(select(func.count()).select_from(Asset)) == 0


def test_openapi_documents_discovery_inputs_and_responses(client):
    schema = client.get("/openapi.json").json()
    routes = schema["paths"]
    filters = {parameter["name"] for parameter in routes["/assets"]["get"]["parameters"]}
    assert {"asset_type", "status", "surveyor", "min_score", "max_score", "search", "limit", "offset"} <= filters
    assert "200" in routes["/assets/{asset_id}/visits"]["get"]["responses"]
    assert "200" in routes["/reports/most-visited"]["get"]["responses"]
    upload = routes["/imports/assets"]["post"]
    assert "text/csv" in upload["requestBody"]["content"]
    assert "200" in upload["responses"]


def test_live_reports_include_current_assets_and_historical_surveyors(client, db_session):
    headers = credential(client, db_session, "surveyor")
    first = {**sample("AA-0001"), "asset_type": "pole", "latitude": 0, "longitude": 0, "condition_score": 2}
    second = {**sample("AA-0002"), "asset_type": "pole", "latitude": 0, "longitude": 1, "condition_score": 8}
    third = {**sample("AA-0003"), "asset_type": "valve", "latitude": 1, "longitude": 1, "condition_score": 4, "status": "proposed"}
    for row in (first, second, third):
        assert client.post("/assets", json=row, headers=headers).status_code == 201
    assert client.patch("/assets/AA-0001", json={"surveyor": "New Inspector", "surveyed_on": "2026-09-02"}, headers=headers).status_code == 200

    summary = client.get("/reports/summary", headers=headers)
    assert summary.status_code == 200
    values = summary.json()
    assert values["total_assets"] == 3
    assert values["by_type"]["pole"]["average_condition"] == 5
    assert values["by_type"]["pole"]["worst_asset_id"] == "AA-0001"
    assert values["extent"] == {"min_latitude": 0, "min_longitude": 0, "max_latitude": 1, "max_longitude": 1}
    assert values["repair_asset_ids"] == ["AA-0001"]
    repairs = client.get("/reports/repairs", headers=headers).json()
    assert [item["asset"]["asset_id"] for item in repairs] == ["AA-0001"]
    assert repairs[0]["condition_band"] == "CRITICAL"
    nearest = client.get("/reports/nearest?latitude=0&longitude=0.8", headers=headers)
    assert nearest.status_code == 200
    assert nearest.json()["asset"]["asset_id"] == "AA-0002"
    assert nearest.json()["distance_km"] == pytest.approx(22.239, abs=0.002)
    assert client.get("/reports/nearest?latitude=91&longitude=0", headers=headers).status_code == 422
    assert client.get("/reports/surveyors-by-day?day=2026-09-01", headers=headers).json()["surveyors"] == ["Rita Sen"]
    assert client.get("/reports/surveyors-by-day?day=2026-09-02", headers=headers).json()["surveyors"] == ["New Inspector"]
    assert client.get("/reports/surveyors-by-day?day=invalid", headers=headers).status_code == 422
    assert client.get("/reports/summary").status_code == 401


def test_summary_cache_reuses_result_expires_and_invalidates_after_writes(client, db_session, monkeypatch):
    surveyor = credential(client, db_session, "surveyor")
    administrator = credential(client, db_session, "administrator")
    calls = []
    real_summary = report_cache.summary_statistics
    monkeypatch.setattr(report_cache, "summary_statistics", lambda records: (calls.append(len(records)), real_summary(records))[1])
    clock = [100.0]
    monkeypatch.setattr(report_cache, "monotonic", lambda: clock[0])

    assert client.get("/reports/summary", headers=surveyor).json()["total_assets"] == 0
    assert client.get("/reports/summary", headers=surveyor).json()["total_assets"] == 0
    assert calls == [0]
    clock[0] += 59
    client.get("/reports/summary", headers=surveyor)
    assert calls == [0]
    clock[0] += 1
    client.get("/reports/summary", headers=surveyor)
    assert calls == [0, 0]

    assert client.post("/assets", json=sample(), headers=surveyor).status_code == 201
    assert client.get("/reports/summary", headers=surveyor).json()["total_assets"] == 1
    assert calls == [0, 0, 1]
    assert client.patch("/assets/AA-0001", json={"condition_score": 3}, headers=surveyor).status_code == 200
    assert client.get("/reports/summary", headers=surveyor).json()["repair_asset_ids"] == ["AA-0001"]
    assert calls == [0, 0, 1, 1]
    assert client.put("/assets/AA-0001", json={**sample(), "condition_score": 9}, headers=surveyor).status_code == 200
    assert client.get("/reports/summary", headers=surveyor).json()["repair_asset_ids"] == []
    assert len(calls) == 5
    assert client.delete("/assets/AA-0001", headers=administrator).status_code == 204
    assert client.get("/reports/summary", headers=surveyor).json()["total_assets"] == 0
    assert len(calls) == 6


def test_summary_refreshes_after_bulk_and_cli_imports(client, db_session, tmp_path):
    administrator = credential(client, db_session, "administrator")
    assert client.get("/reports/summary", headers=administrator).json()["total_assets"] == 0
    body = _csv_bytes([sample("AA-0001")])
    uploaded = client.post("/imports/assets", content=body, headers={**administrator, "Content-Type": "text/csv"})
    assert uploaded.json()["accepted"] == 1
    assert client.get("/reports/summary", headers=administrator).json()["total_assets"] == 1

    source = tmp_path / "later.csv"
    source.write_bytes(_csv_bytes([sample("AA-0002")]))
    ingest_csv(source, paths=OutputPaths.in_directory(tmp_path / "outputs"), engine=db_session.bind)
    assert client.get("/reports/summary", headers=administrator).json()["total_assets"] == 2
