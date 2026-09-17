"""Network import and visit-frequency discovery endpoints."""

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Annotated

from fastapi import APIRouter, Body, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from utility_assets.auth import get_current_user, get_session, require_administrator
from utility_assets.errors import ApiError
from utility_assets.ingestion import IngestionInputError, OutputPaths, ingest_csv
from utility_assets.models import Asset, User, Visit


router = APIRouter(tags=["discovery"])
MAX_UPLOAD_BYTES = 5 * 1024 * 1024


class RejectedUploadRow(BaseModel):
    original: dict[str, object]
    reason: str


class UploadResult(BaseModel):
    rows_read: int
    accepted: int
    rejected: int
    aborted: bool
    rejected_rows: list[RejectedUploadRow]


class VisitedAsset(BaseModel):
    asset_id: str
    visit_count: int


@router.post("/imports/assets", response_model=UploadResult)
def upload_assets(
    body: Annotated[bytes, Body(
        media_type="text/csv",
        description="UTF-8 CSV with the 11 survey columns. Accepted rows update assets and append visits; rejected originals and reasons are returned.",
    )],
    _administrator: Annotated[User, Depends(require_administrator)],
    session: Annotated[Session, Depends(get_session)],
    strict: bool = False,
) -> UploadResult:
    if not body:
        raise ApiError(422, "file", "CSV upload is empty")
    if len(body) > MAX_UPLOAD_BYTES:
        raise ApiError(413, "file", "CSV upload exceeds 5 MiB")
    # Authentication read through this request's session. Release that
    # transaction before the importer opens its own write transaction.
    session.rollback()
    with TemporaryDirectory(prefix="utility-asset-upload-") as directory:
        source = Path(directory) / "upload.csv"
        source.write_bytes(body)
        try:
            result = ingest_csv(source, paths=OutputPaths.in_directory(Path(directory)), strict=strict, engine=session.bind)
        except IngestionInputError as exc:
            raise ApiError(422, "file", str(exc)) from exc
    return UploadResult(
        rows_read=result.rows_read,
        accepted=result.accepted,
        rejected=result.rejected,
        aborted=result.aborted,
        rejected_rows=[RejectedUploadRow(original=row.original, reason=row.reason) for row in result.rejected_rows],
    )


@router.get("/reports/most-visited", response_model=list[VisitedAsset])
def most_visited(
    _user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
) -> list[VisitedAsset]:
    count = func.count(Visit.id).label("visit_count")
    rows = session.execute(
        select(Asset.asset_id, count)
        .join(Visit, Visit.asset_id == Asset.asset_id)
        .group_by(Asset.asset_id)
        .order_by(count.desc(), Asset.asset_id)
        .limit(limit)
    ).all()
    return [VisitedAsset(asset_id=asset_id, visit_count=visit_count) for asset_id, visit_count in rows]
