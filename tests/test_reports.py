"""Checks for report calculations and the mapping interchange format."""

from datetime import date, datetime, timezone

import pytest

from utility_assets.reports import (
    condition_band,
    haversine_km,
    nearest_asset,
    render_summary,
    repair_assets,
    summary_statistics,
    surveyors_on,
    to_geojson,
)
from utility_assets.validation import validate_record


def records():
    base = {
        "name": "Test pole",
        "asset_type": "pole",
        "latitude": "0",
        "longitude": "0",
        "elevation_m": "",
        "surveyed_on": "2026-09-01",
        "surveyor": "Anita Das",
        "status": "active",
        "condition_score": "8",
        "attribute_json": '{"height_m":9}',
    }
    return [
        validate_record({**base, "asset_id": "PL-0001"}, today=date(2026, 9, 16)),
        validate_record(
            {**base, "asset_id": "PL-0002", "longitude": "1", "condition_score": "2"},
            today=date(2026, 9, 16),
        ),
        validate_record(
            {**base, "asset_id": "VA-0003", "asset_type": "valve", "status": "proposed", "condition_score": "4", "surveyor": "Rahul Sen"},
            today=date(2026, 9, 16),
        ),
    ]


def test_condition_bands_and_repair_filter():
    assert [condition_band(score) for score in (10, 8, 7, 5, 4, 3, 2, 0)] == [
        "GOOD", "GOOD", "FAIR", "FAIR", "POOR", "POOR", "CRITICAL", "CRITICAL"
    ]
    assert [record.asset_id for record in repair_assets(records())] == ["PL-0002"]


def test_geodesic_nearest_and_surveyors():
    group = records()
    assert haversine_km(0, 0, 0, 1) == pytest.approx(111.195, abs=0.002)
    nearest = nearest_asset(group, 0, 0.8)
    assert nearest is not None
    assert nearest[0].asset_id == "PL-0002"
    assert nearest[1] == pytest.approx(22.239, abs=0.002)
    assert surveyors_on(group, date(2026, 9, 1)) == ["Anita Das", "Rahul Sen"]


def test_summary_extent_worst_asset_and_geojson():
    group = records()
    summary = summary_statistics(group)
    assert summary["total_accepted"] == 3
    assert summary["by_type"]["pole"]["average_condition"] == 5
    assert summary["by_type"]["pole"]["worst_asset_id"] == "PL-0002"
    assert summary["extent"] == {
        "min_latitude": 0,
        "min_longitude": 0,
        "max_latitude": 0,
        "max_longitude": 1,
    }
    geojson = to_geojson(group)
    assert geojson["features"][1]["geometry"]["coordinates"] == [1, 0]
    assert geojson["features"][1]["properties"]["condition_band"] == "CRITICAL"
    text = render_summary(group, run_at=datetime(2026, 9, 16, tzinfo=timezone.utc), rows_read=4, rows_rejected=1)
    assert "PL-0002 (2)" in text
    assert "Rows read: 4" in text
    assert "Rows rejected: 1" in text
