"""One-command survey import for a non-Python operator."""

import argparse
import os
import re
from datetime import date
from pathlib import Path
from typing import Sequence

from utility_assets.db import get_engine
from utility_assets.ingestion import IngestionInputError, OutputPaths, ingest_csv
from utility_assets.reports import nearest_asset, surveyors_on


ROOT = Path(__file__).resolve().parents[2]
LOCAL_DATABASE = ROOT / "output" / "survey.sqlite3"


def prepare_database() -> None:
    """Create the local survey database when the operator has not configured one."""

    if os.environ.get("DATABASE_URL"):
        return
    LOCAL_DATABASE.parent.mkdir(parents=True, exist_ok=True)
    os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///{LOCAL_DATABASE.resolve().as_posix()}"
    get_engine.cache_clear()
    from alembic import command
    from alembic.config import Config

    command.upgrade(Config(str(ROOT / "alembic.ini")), "head")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="utility-assets-import",
        description="Load a field survey CSV. With no database setting, this creates output/survey.sqlite3 and writes the rejects, map, summary, and log under output/.",
    )
    parser.add_argument("csv_file", type=Path, help="path to the handheld survey CSV")
    parser.add_argument("--rejects", type=Path, default=Path("output/rejects.csv"), help="rejects CSV path")
    parser.add_argument("--map", dest="map_file", type=Path, default=Path("output/map.geojson"), help="GeoJSON map path")
    parser.add_argument("--summary", type=Path, default=Path("output/summary.txt"), help="plain-text summary path")
    parser.add_argument("--log", type=Path, default=Path("output/ingestion.log"), help="append-only run log path")
    parser.add_argument("--strict", action="store_true", help="roll back the whole import if any row is rejected")
    parser.add_argument("--nearest", nargs=2, type=float, metavar=("LAT", "LON"), help="nearest accepted asset to a position")
    parser.add_argument("--surveyors-on", metavar="YYYY-MM-DD", help="list surveyors from this run on a day")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.nearest:
        try:
            nearest_asset((), *args.nearest)
        except ValueError as exc:
            parser.error(str(exc))
    survey_day = None
    if args.surveyors_on:
        try:
            if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", args.surveyors_on):
                raise ValueError
            survey_day = date.fromisoformat(args.surveyors_on)
        except ValueError:
            parser.error("--surveyors-on must be a valid YYYY-MM-DD date")
    prepare_database()
    paths = OutputPaths(args.rejects, args.map_file, args.summary, args.log)
    try:
        result = ingest_csv(args.csv_file, paths=paths, strict=args.strict)
    except IngestionInputError as exc:
        parser.exit(1, f"Import failed: {exc}\n")

    print(f"Rows read: {result.rows_read}")
    print(f"Rows accepted: {result.accepted}")
    print(f"Rows rejected: {result.rejected}")
    print(f"Rejects file: {paths.rejects}")
    if result.aborted:
        print("Strict mode: all database changes from this run were rolled back.")
        return 2
    print(f"Map file: {paths.map_file}")
    print(f"Summary report: {paths.summary}")

    if args.nearest:
        nearest = nearest_asset(result.accepted_records, *args.nearest)
        if nearest:
            print(f"Nearest asset: {nearest[0].asset_id} ({nearest[1]:.3f} km)")
        else:
            print("Nearest asset: none in this run")
    if survey_day:
        names = surveyors_on(result.accepted_records, survey_day)
        print(f"Surveyors on {survey_day.isoformat()}: {', '.join(names) if names else 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
