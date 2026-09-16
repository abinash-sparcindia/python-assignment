"""Transactional CSV ingestion shared by the CLI and review-stack startup."""

import csv
import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from sqlalchemy.engine import Engine
from sqlalchemy.exc import DataError, IntegrityError
from sqlalchemy.orm import Session

from utility_assets.db import get_engine
from utility_assets.models import Asset, SeedRun, Visit
from utility_assets.reports import render_summary, to_geojson
from utility_assets.validation import EXPECTED_COLUMNS, CleanAssetRecord, RecordValidationError, validate_record


class IngestionInputError(ValueError):
    """The input file is missing, unreadable, or does not have the required schema."""


class _StrictAbort(Exception):
    pass


@dataclass(frozen=True)
class OutputPaths:
    rejects: Path
    map_file: Path
    summary: Path
    log: Path

    @classmethod
    def in_directory(cls, directory: Path) -> "OutputPaths":
        return cls(
            rejects=directory / "rejects.csv",
            map_file=directory / "map.geojson",
            summary=directory / "summary.txt",
            log=directory / "ingestion.log",
        )


@dataclass(frozen=True)
class RejectedRow:
    original: dict[str, object]
    reason: str


@dataclass(frozen=True)
class IngestionResult:
    rows_read: int
    accepted_records: tuple[CleanAssetRecord, ...]
    rejected_rows: tuple[RejectedRow, ...]
    paths: OutputPaths
    aborted: bool = False
    skipped: bool = False

    @property
    def accepted(self) -> int:
        return len(self.accepted_records)

    @property
    def rejected(self) -> int:
        return len(self.rejected_rows)


def _read_csv(source: Path) -> tuple[list[str], list[dict[str | None, object]]]:
    try:
        with source.open(newline="", encoding="utf-8-sig") as file:
            reader = csv.DictReader(file)
            fields = reader.fieldnames
            if not fields:
                raise IngestionInputError("CSV has no header row")
            if len(fields) != len(set(fields)):
                raise IngestionInputError("CSV has duplicate column names")
            missing = [field for field in EXPECTED_COLUMNS if field not in fields]
            if missing:
                raise IngestionInputError(f"CSV is missing required columns: {', '.join(missing)}")
            return fields, list(reader)
    except (OSError, UnicodeError, csv.Error) as exc:
        raise IngestionInputError(f"Cannot read CSV {source}: {exc}") from exc


def _write_rejects(fields: list[str], rows: list[RejectedRow], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    has_overflow = any("extra_values" in row.original for row in rows)
    output_fields = fields + (["extra_values"] if has_overflow else []) + ["reason"]
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=output_fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({**row.original, "reason": row.reason})


def _append_log(
    path: Path, *, source: Path, status: str, rows_read: int, accepted: int, rejected: int
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with path.open("a", encoding="utf-8") as file:
        file.write(
            f"{timestamp} source={source} status={status} "
            f"read={rows_read} accepted={accepted} rejected={rejected}\n"
        )


def _store_record(session: Session, record: CleanAssetRecord) -> None:
    asset = session.get(Asset, record.asset_id)
    values = {
        "name": record.name,
        "asset_type": record.asset_type,
        "latitude": record.latitude,
        "longitude": record.longitude,
        "elevation_m": record.elevation_m,
        "surveyed_on": record.surveyed_on,
        "surveyor": record.surveyor,
        "status": record.status,
        "condition_score": record.condition_score,
        "attributes": record.attributes,
    }
    if asset is None:
        session.add(Asset(asset_id=record.asset_id, **values))
    else:
        for field, value in values.items():
            setattr(asset, field, value)
    session.add(
        Visit(
            asset_id=record.asset_id,
            surveyed_on=record.surveyed_on,
            surveyor=record.surveyor,
            condition_score=record.condition_score,
            notes=None,
        )
    )
    session.flush()


def ingest_csv(
    source: Path,
    *,
    paths: OutputPaths,
    strict: bool = False,
    engine: Engine | None = None,
    today: date | None = None,
    seed_key: str | None = None,
) -> IngestionResult:
    """Import good rows, preserve rejected originals, and optionally seed once.

    A later survey for an existing DB asset appends a visit and refreshes its
    current details. A second occurrence of the same code within one file is
    rejected. Strict mode rolls back every write from this run.
    """

    source = Path(source)
    run_at = datetime.now(timezone.utc)
    if engine is None:
        engine = get_engine()
    try:
        fields, rows = _read_csv(source)
    except IngestionInputError:
        _append_log(paths.log, source=source, status="invalid-input", rows_read=0, accepted=0, rejected=0)
        raise

    accepted: list[CleanAssetRecord] = []
    rejected: list[RejectedRow] = []
    seen_in_run: set[str] = set()
    aborted = False
    skipped = False
    try:
        with Session(engine) as session, session.begin():
            if seed_key and session.get(SeedRun, seed_key):
                skipped = True
            else:
                for row in rows:
                    original: dict[str, object] = {field: row.get(field, "") for field in fields}
                    if None in row:
                        original["extra_values"] = json.dumps(row[None])
                        rejected.append(RejectedRow(original, "row: has more values than the header"))
                        if strict:
                            raise _StrictAbort
                        continue
                    try:
                        clean = validate_record(row, existing_ids=seen_in_run, today=today)
                    except RecordValidationError as exc:
                        rejected.append(RejectedRow(original, str(exc)))
                        if strict:
                            raise _StrictAbort from exc
                        continue
                    try:
                        with session.begin_nested():
                            _store_record(session, clean)
                    except (IntegrityError, DataError):
                        rejected.append(RejectedRow(original, "asset_id: database constraint failed"))
                        if strict:
                            raise _StrictAbort
                        continue
                    seen_in_run.add(clean.asset_id)
                    accepted.append(clean)
                if seed_key:
                    session.add(SeedRun(key=seed_key))
    except _StrictAbort:
        aborted = True
        accepted.clear()

    if skipped:
        return IngestionResult(len(rows), (), (), paths, skipped=True)

    _write_rejects(fields, rejected, paths.rejects)
    if not aborted:
        paths.map_file.parent.mkdir(parents=True, exist_ok=True)
        with paths.map_file.open("w", encoding="utf-8") as file:
            json.dump(to_geojson(accepted), file, ensure_ascii=False, indent=2)
            file.write("\n")
        paths.summary.parent.mkdir(parents=True, exist_ok=True)
        paths.summary.write_text(
            render_summary(accepted, run_at=run_at, rows_read=len(rows), rows_rejected=len(rejected)),
            encoding="utf-8",
        )
    _append_log(
        paths.log,
        source=source,
        status="strict-aborted" if aborted else "completed",
        rows_read=len(rows),
        accepted=len(accepted),
        rejected=len(rejected),
    )
    return IngestionResult(
        len(rows), tuple(accepted), tuple(rejected), paths, aborted=aborted
    )
