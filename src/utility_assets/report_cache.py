"""Short-lived summary cache keyed by a database-backed asset revision."""

from threading import Lock
from time import monotonic
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from utility_assets.models import Asset, ReportRevision
from utility_assets.reports import summary_statistics
from utility_assets.validation import CleanAssetRecord


TTL_SECONDS = 60


def bump_report_revision(session: Session) -> None:
    """Advance the revision in the caller's transaction, so rollback undoes it."""
    result = session.execute(
        update(ReportRevision)
        .where(ReportRevision.id == 1)
        .values(version=ReportRevision.version + 1)
    )
    if result.rowcount == 0:
        # Base.metadata.create_all() does not run Alembic's initial insert.
        session.add(ReportRevision(id=1, version=1))


def _record(asset: Asset) -> CleanAssetRecord:
    return CleanAssetRecord(
        asset_id=asset.asset_id,
        name=asset.name,
        asset_type=asset.asset_type,
        latitude=asset.latitude,
        longitude=asset.longitude,
        elevation_m=asset.elevation_m,
        surveyed_on=asset.surveyed_on,
        surveyor=asset.surveyor,
        status=asset.status,
        condition_score=asset.condition_score,
        attributes=asset.attributes,
    )


class SummaryCache:
    def __init__(self, ttl_seconds: int = TTL_SECONDS):
        self.ttl_seconds = ttl_seconds
        self._lock = Lock()
        self._key: tuple[str, int] | None = None
        self._expires_at = 0.0
        self._value: dict[str, Any] | None = None

    def clear(self) -> None:
        with self._lock:
            self._key = None
            self._expires_at = 0.0
            self._value = None

    def get(self, session: Session) -> dict[str, Any]:
        revision = session.scalar(select(ReportRevision.version).where(ReportRevision.id == 1)) or 0
        key = (str(session.get_bind().url), revision)
        now = monotonic()
        with self._lock:
            if self._key == key and now < self._expires_at and self._value is not None:
                return self._value
        records = [_record(asset) for asset in session.scalars(select(Asset).order_by(Asset.asset_id))]
        value = summary_statistics(records)
        with self._lock:
            self._key = key
            self._expires_at = monotonic() + self.ttl_seconds
            self._value = value
        return value


summary_cache = SummaryCache()
