"""Authenticated live reports derived from current assets and visit history."""

import math
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from utility_assets.assets_api import AssetView, _view
from utility_assets.auth import get_current_user, get_session
from utility_assets.errors import ApiError
from utility_assets.models import Asset, User, Visit
from utility_assets.report_cache import summary_cache
from utility_assets.reports import condition_band, haversine_km


router = APIRouter(prefix="/reports", tags=["reports"])


class TypeStatistics(BaseModel):
    count: int
    average_condition: float | None
    worst_asset_id: str | None
    worst_score: int | None


class Extent(BaseModel):
    min_latitude: float
    min_longitude: float
    max_latitude: float
    max_longitude: float


class SummaryReport(BaseModel):
    total_assets: int
    by_type: dict[str, TypeStatistics]
    extent: Extent | None
    repair_asset_ids: list[str]


class RepairItem(BaseModel):
    asset: AssetView
    condition_band: str


class NearestResult(BaseModel):
    asset: AssetView
    distance_km: float


class SurveyorsByDay(BaseModel):
    day: date
    surveyors: list[str]


@router.get("/summary", response_model=SummaryReport)
def summary(
    _user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> SummaryReport:
    values = summary_cache.get(session)
    return SummaryReport(
        total_assets=values["total_accepted"],
        by_type=values["by_type"],
        extent=values["extent"],
        repair_asset_ids=values["repair_asset_ids"],
    )


@router.get("/repairs", response_model=list[RepairItem])
def repairs(
    _user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> list[RepairItem]:
    assets = session.scalars(
        select(Asset)
        .where(Asset.status == "active", Asset.condition_score < 5)
        .order_by(Asset.condition_score, Asset.asset_id)
    ).all()
    return [RepairItem(asset=_view(asset), condition_band=condition_band(asset.condition_score)) for asset in assets]


@router.get("/nearest", response_model=NearestResult)
def nearest(
    _user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    latitude: float,
    longitude: float,
) -> NearestResult:
    for field, value, limit in (("latitude", latitude, 90), ("longitude", longitude, 180)):
        if not math.isfinite(value) or not -limit <= value <= limit:
            raise ApiError(422, field, f"must be a finite number between {-limit} and {limit}")
    closest: tuple[Asset, float] | None = None
    for asset in session.scalars(select(Asset).order_by(Asset.asset_id)):
        distance = haversine_km(latitude, longitude, asset.latitude, asset.longitude)
        if closest is None or (distance, asset.asset_id) < (closest[1], closest[0].asset_id):
            closest = (asset, distance)
    if closest is None:
        raise ApiError(404, "asset", "no assets are available")
    return NearestResult(asset=_view(closest[0]), distance_km=closest[1])


@router.get("/surveyors-by-day", response_model=SurveyorsByDay)
def surveyors_by_day(
    _user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    day: Annotated[date, Query(description="Survey date in YYYY-MM-DD form")],
) -> SurveyorsByDay:
    names = session.scalars(select(Visit.surveyor).where(Visit.surveyed_on == day).distinct().order_by(Visit.surveyor)).all()
    return SurveyorsByDay(day=day, surveyors=list(names))
