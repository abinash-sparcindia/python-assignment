"""Boundary and real-export-shape checks for the shared validation layer."""

import csv
from datetime import date, timedelta
from pathlib import Path

import pytest

from utility_assets.validation import (
    EXPECTED_COLUMNS,
    RecordValidationError,
    validate_record,
)


TODAY = date(2026, 9, 16)
SAMPLE = Path(__file__).resolve().parents[1] / "data" / "survey_export.csv"


def good_row() -> dict[str, object]:
    return {
        "asset_id": "PL-0001",
        "name": "  BHUBANESWAR   POLE  1 ",
        "asset_type": "PoLe",
        "latitude": "20.25 N",
        "longitude": "85.82 E",
        "elevation_m": "",
        "surveyed_on": "2026-09-01",
        "surveyor": " anita   DAS ",
        "status": "ACTIVE",
        "condition_score": "8",
        "attribute_json": '{"height_m":9}',
    }


def test_normalizes_without_changing_original_values():
    original = good_row()
    cleaned = validate_record(original, today=TODAY)
    assert cleaned.asset_id == "PL-0001"
    assert cleaned.name == "Bhubaneswar Pole 1"
    assert cleaned.asset_type == "pole"
    assert cleaned.latitude == 20.25
    assert cleaned.longitude == 85.82
    assert cleaned.elevation_m is None
    assert cleaned.surveyor == "Anita Das"
    assert cleaned.status == "active"
    assert cleaned.condition_score == 8
    assert cleaned.attributes == {"height_m": 9}
    assert original["name"] == "  BHUBANESWAR   POLE  1 "


def test_compass_signs_and_inclusive_boundaries():
    row = good_row()
    row.update(
        latitude="90 S",
        longitude="180 W",
        condition_score=0,
        elevation_m="-3.5",
        attribute_json=["valid", 1],
    )
    cleaned = validate_record(row, today=TODAY)
    assert (cleaned.latitude, cleaned.longitude, cleaned.condition_score) == (-90, -180, 0)
    assert cleaned.elevation_m == -3.5
    assert cleaned.attributes == ["valid", 1]


@pytest.mark.parametrize(
    ("changes", "field", "message"),
    [
        ({"asset_id": ""}, "asset_id", "required"),
        ({"asset_id": "pL-0001"}, "asset_id", "capital letters"),
        ({"name": " x  "}, "name", "3 to 120"),
        ({"name": "x" * 121}, "name", "3 to 120"),
        ({"asset_type": "cable"}, "asset_type", "pole"),
        ({"asset_type": []}, "asset_type", "pole"),
        ({"latitude": "90.0001"}, "latitude", "between -90 and 90"),
        ({"latitude": True}, "latitude", "number"),
        ({"latitude": "20 E"}, "latitude", "compass letter"),
        ({"latitude": "-20 S"}, "latitude", "combine a sign"),
        ({"latitude": "NaN"}, "latitude", "finite"),
        ({"longitude": "west-ish"}, "longitude", "number"),
        ({"longitude": "-180.0001"}, "longitude", "between -180 and 180"),
        ({"elevation_m": "not recorded"}, "elevation_m", "number"),
        ({"elevation_m": "NaN"}, "elevation_m", "finite"),
        ({"surveyed_on": "2026-02-30"}, "surveyed_on", "valid date"),
        ({"surveyed_on": "2026-9-1"}, "surveyed_on", "YYYY-MM-DD"),
        ({"surveyed_on": (TODAY + timedelta(days=1)).isoformat()}, "surveyed_on", "later than today"),
        ({"surveyor": "  "}, "surveyor", "1 to 120"),
        ({"status": "retired"}, "status", "active"),
        ({"status": []}, "status", "active"),
        ({"condition_score": "14"}, "condition_score", "between 0 and 10"),
        ({"condition_score": ""}, "condition_score", "whole number"),
        ({"condition_score": 7.0}, "condition_score", "whole number"),
        ({"attribute_json": "{height_m:9}"}, "attribute_json", "valid JSON"),
        ({"attribute_json": "NaN"}, "attribute_json", "valid JSON"),
        ({"attribute_json": ""}, "attribute_json", "valid JSON"),
        ({"status": "decommissioned", "condition_score": "3"}, "condition_score", "decommissioned"),
    ],
)
def test_rejects_invalid_field_with_readable_reason(changes, field, message):
    row = good_row()
    row.update(changes)
    with pytest.raises(RecordValidationError) as caught:
        validate_record(row, today=TODAY)
    assert any(issue.field == field and message in issue.message for issue in caught.value.issues)


def test_duplicate_and_multiple_issues_have_structured_errors():
    row = good_row()
    row["longitude"] = "broken"
    with pytest.raises(RecordValidationError) as caught:
        validate_record(row, existing_ids={"PL-0001"}, today=TODAY)
    assert caught.value.as_dict() == {
        "errors": [
            {"field": "asset_id", "message": "is already in use"},
            {"field": "longitude", "message": "must be a number"},
        ]
    }


def test_synthetic_export_has_expected_accept_and_reject_split():
    with SAMPLE.open(newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        assert tuple(reader.fieldnames or ()) == EXPECTED_COLUMNS
        rows = list(reader)
    assert len(rows) == 62

    seen: set[str] = set()
    rejected: list[tuple[int, set[str]]] = []
    for number, row in enumerate(rows, start=1):
        try:
            clean = validate_record(row, existing_ids=seen, today=TODAY)
        except RecordValidationError as exc:
            rejected.append((number, {issue.field for issue in exc.issues}))
        else:
            seen.add(clean.asset_id)

    assert len(seen) == 51
    assert rejected == [
        (52, {"latitude"}),
        (53, {"longitude"}),
        (54, {"asset_id"}),
        (55, {"asset_id"}),
        (56, {"asset_id"}),
        (57, {"condition_score"}),
        (58, {"condition_score"}),
        (59, {"surveyed_on"}),
        (60, {"attribute_json"}),
        (61, {"asset_type"}),
        (62, {"condition_score"}),
    ]
