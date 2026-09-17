"""Authenticated asset operations backed by the shared survey validator."""

import json
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, Query, Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from utility_assets.auth import get_current_user, get_session, require_administrator
from utility_assets.errors import ApiError
from utility_assets.models import Asset, User, Visit
from utility_assets.validation import CleanAssetRecord, EXPECTED_COLUMNS, validate_record


router = APIRouter(prefix="/assets", tags=["assets"])
ASSET_FIELDS = frozenset(EXPECTED_COLUMNS)
WRITE_FIELDS = ASSET_FIELDS | {"notes"}


class AssetView(BaseModel):
    asset_id: str
    name: str
    asset_type: str
    latitude: float
    longitude: float
    elevation_m: float | None
    surveyed_on: str
    surveyor: str
    status: str
    condition_score: int
    attribute_json: Any


class AssetPage(BaseModel):
    items: list[AssetView]
    total: int
    limit: int
    offset: int


def _view(asset: Asset) -> AssetView:
    return AssetView(
        asset_id=asset.asset_id,
        name=asset.name,
        asset_type=asset.asset_type,
        latitude=asset.latitude,
        longitude=asset.longitude,
        elevation_m=asset.elevation_m,
        surveyed_on=asset.surveyed_on.isoformat(),
        surveyor=asset.surveyor,
        status=asset.status,
        condition_score=asset.condition_score,
        attribute_json=asset.attributes,
    )


def _raw(asset: Asset) -> dict[str, Any]:
    return {
        "asset_id": asset.asset_id,
        "name": asset.name,
        "asset_type": asset.asset_type,
        "latitude": asset.latitude,
        "longitude": asset.longitude,
        "elevation_m": asset.elevation_m,
        "surveyed_on": asset.surveyed_on,
        "surveyor": asset.surveyor,
        "status": asset.status,
        "condition_score": asset.condition_score,
        # The validator interprets strings as JSON source text. Re-encode a
        # stored JSON string so an unrelated PATCH preserves its actual value.
        "attribute_json": json.dumps(asset.attributes),
    }


def _check_payload(payload: dict[str, Any], *, full: bool) -> str | None:
    unknown = set(payload) - WRITE_FIELDS
    if unknown:
        raise ApiError(422, sorted(unknown)[0], "is not a supported field")
    if full:
        missing = ASSET_FIELDS - set(payload)
        if missing:
            raise ApiError(422, sorted(missing)[0], "is required for a full record")
    elif not payload:
        raise ApiError(422, "request", "at least one field is required")
    notes = payload.get("notes")
    if notes is not None and not isinstance(notes, str):
        raise ApiError(422, "notes", "must be text or null")
    return notes


def _apply(asset: Asset, record: CleanAssetRecord) -> None:
    asset.name = record.name
    asset.asset_type = record.asset_type
    asset.latitude = record.latitude
    asset.longitude = record.longitude
    asset.elevation_m = record.elevation_m
    asset.surveyed_on = record.surveyed_on
    asset.surveyor = record.surveyor
    asset.status = record.status
    asset.condition_score = record.condition_score
    asset.attributes = record.attributes


def _visit(asset: Asset, record: CleanAssetRecord, notes: str | None) -> None:
    asset.visits.append(
        Visit(
            surveyed_on=record.surveyed_on,
            surveyor=record.surveyor,
            condition_score=record.condition_score,
            notes=notes,
        )
    )


def _find(session: Session, asset_id: str) -> Asset:
    asset = session.get(Asset, asset_id)
    if asset is None:
        raise ApiError(404, "asset_id", "asset was not found")
    return asset


@router.get("", response_model=AssetPage)
def list_assets(
    _user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AssetPage:
    total = session.scalar(select(func.count()).select_from(Asset)) or 0
    assets = session.scalars(select(Asset).order_by(Asset.asset_id).limit(limit).offset(offset)).all()
    return AssetPage(items=[_view(asset) for asset in assets], total=total, limit=limit, offset=offset)


@router.get("/{asset_id}", response_model=AssetView)
def get_asset(
    asset_id: str,
    _user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> AssetView:
    return _view(_find(session, asset_id))


@router.post("", response_model=AssetView, status_code=201)
def create_asset(
    payload: Annotated[dict[str, Any], Body()],
    _user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> AssetView:
    notes = _check_payload(payload, full=True)
    record = validate_record(payload)
    if session.get(Asset, record.asset_id) is not None:
        raise ApiError(409, "asset_id", "is already in use")
    asset = Asset(asset_id=record.asset_id)
    _apply(asset, record)
    _visit(asset, record, notes)
    session.add(asset)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise ApiError(409, "asset_id", "is already in use") from exc
    return _view(asset)


@router.put("/{asset_id}", response_model=AssetView)
def replace_asset(
    asset_id: str,
    payload: Annotated[dict[str, Any], Body()],
    _user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> AssetView:
    asset = _find(session, asset_id)
    notes = _check_payload(payload, full=True)
    if payload.get("asset_id") != asset_id:
        raise ApiError(422, "asset_id", "must match the URL")
    record = validate_record(payload)
    _apply(asset, record)
    _visit(asset, record, notes)
    session.commit()
    return _view(asset)


@router.patch("/{asset_id}", response_model=AssetView)
def patch_asset(
    asset_id: str,
    payload: Annotated[dict[str, Any], Body()],
    _user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> AssetView:
    asset = _find(session, asset_id)
    notes = _check_payload(payload, full=False)
    if "asset_id" in payload:
        raise ApiError(422, "asset_id", "cannot be changed by a partial update")
    merged = _raw(asset)
    merged.update({key: value for key, value in payload.items() if key in ASSET_FIELDS})
    record = validate_record(merged)
    _apply(asset, record)
    _visit(asset, record, notes)
    session.commit()
    return _view(asset)


@router.delete("/{asset_id}", status_code=204)
def delete_asset(
    asset_id: str,
    _administrator: Annotated[User, Depends(require_administrator)],
    session: Annotated[Session, Depends(get_session)],
) -> Response:
    asset = _find(session, asset_id)
    session.delete(asset)
    session.commit()
    return Response(status_code=204)
