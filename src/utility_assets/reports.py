"""Reusable survey analysis and geographic output functions."""

import math
from collections import defaultdict
from collections.abc import Iterable, Sequence
from datetime import date, datetime
from typing import Any

from utility_assets.validation import ASSET_TYPES, CleanAssetRecord

EARTH_RADIUS_KM = 6371.0088


def condition_band(score: int) -> str:
    if not 0 <= score <= 10:
        raise ValueError("condition score must be from 0 to 10")
    if score >= 8:
        return "GOOD"
    if score >= 5:
        return "FAIR"
    if score >= 3:
        return "POOR"
    return "CRITICAL"


def repair_assets(records: Iterable[CleanAssetRecord]) -> list[CleanAssetRecord]:
    return sorted(
        (record for record in records if record.status == "active" and record.condition_score < 5),
        key=lambda record: (record.condition_score, record.asset_id),
    )


def surveyors_on(records: Iterable[CleanAssetRecord], day: date) -> list[str]:
    return sorted({record.surveyor for record in records if record.surveyed_on == day})


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    lat1_rad, lat2_rad = math.radians(lat1), math.radians(lat2)
    latitude_delta = math.radians(lat2 - lat1)
    longitude_delta = math.radians(lon2 - lon1)
    a = (
        math.sin(latitude_delta / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(longitude_delta / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(min(1.0, max(0.0, a))))


def nearest_asset(
    records: Iterable[CleanAssetRecord], latitude: float, longitude: float
) -> tuple[CleanAssetRecord, float] | None:
    if not all(math.isfinite(value) for value in (latitude, longitude)):
        raise ValueError("position must contain finite coordinates")
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise ValueError("position is outside latitude or longitude range")
    nearest: tuple[CleanAssetRecord, float] | None = None
    for record in records:
        distance = haversine_km(latitude, longitude, record.latitude, record.longitude)
        if nearest is None or (distance, record.asset_id) < (nearest[1], nearest[0].asset_id):
            nearest = (record, distance)
    return nearest


def summary_statistics(records: Sequence[CleanAssetRecord]) -> dict[str, Any]:
    grouped: dict[str, list[CleanAssetRecord]] = defaultdict(list)
    for record in records:
        grouped[record.asset_type].append(record)

    by_type: dict[str, dict[str, Any]] = {}
    for asset_type in sorted(ASSET_TYPES):
        group = grouped[asset_type]
        worst = min(group, key=lambda item: (item.condition_score, item.asset_id)) if group else None
        by_type[asset_type] = {
            "count": len(group),
            "average_condition": sum(item.condition_score for item in group) / len(group) if group else None,
            "worst_asset_id": worst.asset_id if worst else None,
            "worst_score": worst.condition_score if worst else None,
        }

    extent = None
    if records:
        extent = {
            "min_latitude": min(item.latitude for item in records),
            "min_longitude": min(item.longitude for item in records),
            "max_latitude": max(item.latitude for item in records),
            "max_longitude": max(item.longitude for item in records),
        }
    return {
        "total_accepted": len(records),
        "by_type": by_type,
        "extent": extent,
        "repair_asset_ids": [item.asset_id for item in repair_assets(records)],
    }


def to_geojson(records: Iterable[CleanAssetRecord]) -> dict[str, Any]:
    features = []
    for record in records:
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [record.longitude, record.latitude],
                },
                "properties": {
                    "asset_id": record.asset_id,
                    "name": record.name,
                    "asset_type": record.asset_type,
                    "elevation_m": record.elevation_m,
                    "surveyed_on": record.surveyed_on.isoformat(),
                    "surveyor": record.surveyor,
                    "status": record.status,
                    "condition_score": record.condition_score,
                    "condition_band": condition_band(record.condition_score),
                    "attributes": record.attributes,
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}


def render_summary(
    records: Sequence[CleanAssetRecord], *, run_at: datetime, rows_read: int, rows_rejected: int
) -> str:
    stats = summary_statistics(records)
    lines = [
        "UTILITY ASSET SURVEY - INGESTION SUMMARY",
        f"Run time: {run_at.isoformat(timespec='seconds')}",
        "",
        f"{'Asset type':<14} {'Count':>5} {'Avg score':>10}  Worst asset",
        "-" * 50,
    ]
    for asset_type, values in stats["by_type"].items():
        average = f"{values['average_condition']:.2f}" if values["average_condition"] is not None else "-"
        worst = (
            f"{values['worst_asset_id']} ({values['worst_score']})"
            if values["worst_asset_id"]
            else "-"
        )
        lines.append(f"{asset_type:<14} {values['count']:>5} {average:>10}  {worst}")

    lines.extend(
        [
            "",
            f"Rows read: {rows_read}",
            f"Rows accepted: {stats['total_accepted']}",
            f"Rows rejected: {rows_rejected}",
        ]
    )
    extent = stats["extent"]
    if extent:
        lines.append(
            "Survey extent: "
            f"lat {extent['min_latitude']:.6f} to {extent['max_latitude']:.6f}; "
            f"lon {extent['min_longitude']:.6f} to {extent['max_longitude']:.6f}"
        )
    else:
        lines.append("Survey extent: no accepted assets")
    repair_ids = stats["repair_asset_ids"]
    lines.append(f"Need repair (active, score < 5): {', '.join(repair_ids) if repair_ids else 'none'}")
    return "\n".join(lines) + "\n"
