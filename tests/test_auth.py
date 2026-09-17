"""Authentication, permissions and review bootstrap checks."""

import os
import secrets
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from utility_assets.auth import get_session, hash_password, issue_token, verify_password
from utility_assets.db import get_engine
from utility_assets.main import create_app
from utility_assets.models import User
from utility_assets.startup import initialize_review_identity


@pytest.fixture
def client(db_session, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", str(db_session.bind.url))
    monkeypatch.setenv("SIGNING_SECRET", secrets.token_urlsafe(48))
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:3000")
    application = create_app()

    def test_session():
        with Session(db_session.bind) as session:
            yield session

    application.dependency_overrides[get_session] = test_session
    with TestClient(application) as test_client:
        yield test_client


def make_user(db_session, role="surveyor"):
    password = secrets.token_urlsafe(24)
    username = f"user-{secrets.token_hex(4)}"
    user = User(username=username, password_hash=hash_password(password), role=role)
    db_session.add(user)
    db_session.commit()
    return user, password


def sign_in(client, user, password):
    response = client.post("/auth/login", json={"username": user.username, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]


def test_sign_in_hashes_password_and_requires_credential(client, db_session):
    user, password = make_user(db_session)
    assert user.password_hash.startswith("$argon2id$")
    assert user.password_hash != password
    assert verify_password(user.password_hash, password)

    assert client.get("/health").status_code == 200
    denied = client.get("/auth/me")
    assert denied.status_code == 401
    assert denied.json() == {"errors": [{"field": "authorization", "message": "sign-in required"}]}

    token = sign_in(client, user, password)
    assert password not in token
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).json() == {
        "username": user.username,
        "role": "surveyor",
    }
    wrong = client.post("/auth/login", json={"username": user.username, "password": secrets.token_urlsafe(24)})
    assert wrong.status_code == 401
    assert password not in wrong.text


def test_expired_and_altered_credentials_are_refused(client, db_session):
    user, _password = make_user(db_session)
    expired = issue_token(user, expires_at=datetime.now(timezone.utc) - timedelta(minutes=1))
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {expired}"}).status_code == 401
    valid = issue_token(user)
    altered = valid + "x"
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {altered}"}).status_code == 401


def test_only_administrator_can_create_accounts(client, db_session):
    surveyor, surveyor_password = make_user(db_session)
    administrator, administrator_password = make_user(db_session, "administrator")
    surveyor_token = sign_in(client, surveyor, surveyor_password)
    admin_token = sign_in(client, administrator, administrator_password)
    new_password = secrets.token_urlsafe(24)
    payload = {"username": "New.Surveyor", "password": new_password, "role": "surveyor"}

    denied = client.post("/users", json=payload, headers={"Authorization": f"Bearer {surveyor_token}"})
    assert denied.status_code == 403
    assert denied.json()["errors"][0]["field"] == "authorization"
    assert client.post("/users", json=payload).status_code == 401

    created = client.post("/users", json=payload, headers={"Authorization": f"Bearer {admin_token}"})
    assert created.status_code == 201
    assert created.json() == {"username": "new.surveyor", "role": "surveyor"}
    assert new_password not in created.text
    duplicate = client.post("/users", json=payload, headers={"Authorization": f"Bearer {admin_token}"})
    assert duplicate.status_code == 409
    assert duplicate.json()["errors"][0]["field"] == "username"
    with Session(db_session.bind) as session:
        stored = session.scalar(select(User).where(User.username == "new.surveyor"))
        assert stored is not None and verify_password(stored.password_hash, new_password)


def test_invalid_user_payload_is_field_specific_and_does_not_echo_password(client, db_session):
    administrator, password = make_user(db_session, "administrator")
    token = sign_in(client, administrator, password)
    weak_password = secrets.token_urlsafe(3)
    response = client.post(
        "/users",
        json={"username": "bad space", "password": weak_password, "role": "surveyor"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422
    assert {error["field"] for error in response.json()["errors"]} == {"username", "password"}
    assert weak_password not in response.text


def test_cors_only_allows_configured_origin(client):
    allowed = client.options(
        "/auth/me",
        headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"},
    )
    assert allowed.headers.get("access-control-allow-origin") == "http://localhost:3000"
    denied = client.options(
        "/auth/me",
        headers={"Origin": "http://other.example", "Access-Control-Request-Method": "GET"},
    )
    assert "access-control-allow-origin" not in denied.headers


def test_review_bootstrap_writes_random_credentials_outside_logs(db_session, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DATABASE_URL", str(db_session.bind.url))
    monkeypatch.delenv("SIGNING_SECRET", raising=False)
    credentials_file = tmp_path / "credentials.txt"
    monkeypatch.setenv("REVIEW_CREDENTIALS_FILE", str(credentials_file))
    get_engine.cache_clear()
    try:
        initialize_review_identity()
        text = credentials_file.read_text(encoding="utf-8")
        username, password = (line.split("=", 1)[1] for line in text.splitlines())
        assert username == "review-admin"
        assert len(password) >= 24
        assert len(os.environ["SIGNING_SECRET"]) >= 32
        assert password not in capsys.readouterr().out
        with Session(db_session.bind) as session:
            user = session.scalar(select(User).where(User.username == username))
            assert user is not None and user.role == "administrator"
            assert verify_password(user.password_hash, password)
        initialize_review_identity()
        with Session(db_session.bind) as session:
            assert session.scalar(select(func.count()).select_from(User)) == 1
    finally:
        get_engine().dispose()
        get_engine.cache_clear()
