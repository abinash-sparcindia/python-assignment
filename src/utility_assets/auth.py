"""Password storage, signed credentials, roles and account endpoints."""

import re
from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import APIRouter, Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from utility_assets.config import get_settings
from utility_assets.db import get_engine
from utility_assets.errors import ApiError
from utility_assets.models import User


router = APIRouter(tags=["identity"])
bearer = HTTPBearer(auto_error=False)
password_hasher = PasswordHasher()
USERNAME_PATTERN = re.compile(r"^[a-z0-9_.-]{3,50}$")


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int


class NewUser(BaseModel):
    username: str
    password: str = Field(min_length=12)
    role: Literal["surveyor", "administrator"]

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        normalized = value.casefold()
        if not USERNAME_PATTERN.fullmatch(normalized):
            raise ValueError("must be 3-50 letters, digits, dots, underscores or hyphens")
        return normalized


class UserView(BaseModel):
    username: str
    role: Literal["surveyor", "administrator"]


def get_session():
    with Session(get_engine()) as session:
        yield session


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password_hash: str, candidate: str) -> bool:
    try:
        return password_hasher.verify(password_hash, candidate)
    except (VerificationError, InvalidHashError):
        return False


def _signing_secret() -> str:
    secret = get_settings().signing_secret
    if not secret or len(secret) < 32:
        raise RuntimeError("SIGNING_SECRET must be supplied and at least 32 characters")
    return secret


def issue_token(user: User, *, expires_at: datetime | None = None) -> str:
    now = datetime.now(timezone.utc)
    lifetime = get_settings().token_lifetime_minutes
    if lifetime <= 0:
        raise RuntimeError("TOKEN_LIFETIME_MINUTES must be positive")
    expiry = expires_at or now + timedelta(minutes=lifetime)
    return jwt.encode(
        {"sub": user.username, "iat": now, "exp": expiry},
        _signing_secret(),
        algorithm="HS256",
    )


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    session: Annotated[Session, Depends(get_session)],
) -> User:
    if credentials is None or credentials.scheme.casefold() != "bearer":
        raise ApiError(401, "authorization", "sign-in required")
    try:
        claims = jwt.decode(
            credentials.credentials,
            _signing_secret(),
            algorithms=["HS256"],
            options={"require": ["exp", "iat", "sub"]},
        )
    except jwt.InvalidTokenError as exc:
        raise ApiError(401, "authorization", "credential is invalid or expired") from exc
    username = claims.get("sub")
    if not isinstance(username, str):
        raise ApiError(401, "authorization", "credential is invalid or expired")
    user = session.scalar(select(User).where(User.username == username))
    if user is None:
        raise ApiError(401, "authorization", "credential is invalid or expired")
    return user


def require_administrator(user: Annotated[User, Depends(get_current_user)]) -> User:
    if user.role != "administrator":
        raise ApiError(403, "authorization", "administrator permission required")
    return user


@router.post("/auth/login", response_model=TokenResponse)
def login(payload: LoginRequest, session: Annotated[Session, Depends(get_session)]) -> TokenResponse:
    username = payload.username.casefold()
    user = session.scalar(select(User).where(User.username == username))
    if user is None or not verify_password(user.password_hash, payload.password):
        raise ApiError(401, "credentials", "username or password is incorrect")
    return TokenResponse(
        access_token=issue_token(user),
        expires_in=get_settings().token_lifetime_minutes * 60,
    )


@router.get("/auth/me", response_model=UserView)
def me(user: Annotated[User, Depends(get_current_user)]) -> UserView:
    return UserView(username=user.username, role=user.role)


@router.post("/users", response_model=UserView, status_code=201)
def create_user(
    payload: NewUser,
    _administrator: Annotated[User, Depends(require_administrator)],
    session: Annotated[Session, Depends(get_session)],
) -> UserView:
    user = User(
        username=payload.username,
        password_hash=hash_password(payload.password),
        role=payload.role,
    )
    session.add(user)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise ApiError(409, "username", "is already in use") from exc
    return UserView(username=user.username, role=user.role)
