"""Shared cleaning and validation for CSV imports and network writes.

This module does not write to storage. Callers decide whether to reject a CSV
row or return an API validation response, using the same field-level issues.
"""

import json
import math
import re
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any


EXPECTED_COLUMNS = (
    "asset_id",
    "name",
    "asset_type",
    "latitude",
    "longitude",
    "elevation_m",
    "surveyed_on",
    "surveyor",
    "status",
    "condition_score",
    "attribute_json",
)
ASSET_TYPES = frozenset({"pole", "valve", "manhole", "transformer"})
STATUSES = frozenset({"active", "decommissioned", "proposed"})
ASSET_ID_PATTERN = re.compile(r"^[A-Z]{2}-[0-9]{4}$")
DATE_PATTERN = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
INTEGER_PATTERN = re.compile(r"^[+-]?[0-9]+$")
MISSING = object()


@dataclass(frozen=True)
class FieldIssue:
    field: str
    message: str


class RecordValidationError(ValueError):
    def __init__(self, issues: list[FieldIssue]):
        self.issues = tuple(issues)
        super().__init__("; ".join(f"{item.field}: {item.message}" for item in issues))

    def as_dict(self) -> dict[str, list[dict[str, str]]]:
        return {
            "errors": [
                {"field": item.field, "message": item.message} for item in self.issues
            ]
        }


@dataclass(frozen=True)
class CleanAssetRecord:
    asset_id: str
    name: str
    asset_type: str
    latitude: float
    longitude: float
    elevation_m: float | None
    surveyed_on: date
    surveyor: str
    status: str
    condition_score: int
    attributes: Any


def _tidy_text(value: object, *, title_case: bool = False) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = " ".join(value.split())
    return cleaned.title() if title_case else cleaned


def _coordinate(value: object, axis: str, issues: list[FieldIssue]) -> float | None:
    field = "latitude" if axis == "latitude" else "longitude"
    allowed_suffixes = "NS" if axis == "latitude" else "EW"
    if isinstance(value, bool) or value is None:
        issues.append(FieldIssue(field, "must be a number"))
        return None
    if isinstance(value, str):
        text = value.strip()
        suffix = text[-1:].upper()
        number_text = text[:-1].strip()
        try:
            float(number_text)
            has_numeric_compass_prefix = bool(number_text)
        except ValueError:
            has_numeric_compass_prefix = False
        if suffix in "NSEW" and has_numeric_compass_prefix:
            if suffix not in allowed_suffixes:
                issues.append(FieldIssue(field, f"compass letter must be {allowed_suffixes[0]} or {allowed_suffixes[1]}"))
                return None
            if number_text.startswith(("+", "-")):
                issues.append(FieldIssue(field, "do not combine a sign with a compass letter"))
                return None
            text = number_text
        else:
            suffix = ""
        try:
            number = float(text)
        except ValueError:
            issues.append(FieldIssue(field, "must be a number"))
            return None
        if suffix in ("S", "W"):
            number = -abs(number)
    else:
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError):
            issues.append(FieldIssue(field, "must be a number"))
            return None
    if not math.isfinite(number):
        issues.append(FieldIssue(field, "must be a finite number"))
        return None
    limit = 90 if field == "latitude" else 180
    if not -limit <= number <= limit:
        issues.append(FieldIssue(field, f"must be between {-limit} and {limit}"))
        return None
    return number


def _elevation(value: object, issues: list[FieldIssue]) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, str) and not value.strip():
        return None
    if isinstance(value, bool):
        issues.append(FieldIssue("elevation_m", "must be a number when present"))
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        issues.append(FieldIssue("elevation_m", "must be a number when present"))
        return None
    if not math.isfinite(number):
        issues.append(FieldIssue("elevation_m", "must be a finite number"))
        return None
    return number


def _survey_date(value: object, issues: list[FieldIssue], today: date) -> date | None:
    if isinstance(value, date) and not hasattr(value, "hour"):
        result = value
    elif isinstance(value, str) and DATE_PATTERN.fullmatch(value):
        try:
            result = date.fromisoformat(value)
        except ValueError:
            result = None
    else:
        result = None
    if result is None:
        issues.append(FieldIssue("surveyed_on", "must be a valid date in YYYY-MM-DD form"))
        return None
    if result > today:
        issues.append(FieldIssue("surveyed_on", "must not be later than today"))
        return None
    return result


def _score(value: object, issues: list[FieldIssue]) -> int | None:
    if isinstance(value, bool):
        score = None
    elif isinstance(value, int):
        score = value
    elif isinstance(value, str) and INTEGER_PATTERN.fullmatch(value.strip()):
        try:
            score = int(value.strip())
        except ValueError:
            score = None
    else:
        score = None
    if score is None:
        issues.append(FieldIssue("condition_score", "must be a whole number from 0 to 10"))
        return None
    if not 0 <= score <= 10:
        issues.append(FieldIssue("condition_score", "must be between 0 and 10"))
        return None
    return score


def _reject_non_json_constant(_value: str) -> None:
    raise ValueError("non-JSON numeric constant")


def _attributes(value: object, issues: list[FieldIssue]) -> Any:
    if value is MISSING:
        issues.append(FieldIssue("attribute_json", "is required"))
        return MISSING
    if isinstance(value, str):
        try:
            return json.loads(value, parse_constant=_reject_non_json_constant)
        except (json.JSONDecodeError, ValueError):
            issues.append(FieldIssue("attribute_json", "must be valid JSON"))
            return MISSING
    try:
        json.dumps(value, allow_nan=False)
    except (TypeError, ValueError, OverflowError):
        issues.append(FieldIssue("attribute_json", "must be valid JSON"))
        return MISSING
    return value


def validate_record(
    raw: Mapping[str, object],
    *,
    existing_ids: Collection[str] = (),
    today: date | None = None,
) -> CleanAssetRecord:
    """Return a clean record or all field errors without modifying the input.

    `existing_ids` is supplied by the caller. For an update, exclude the asset
    being updated; for an import, include all codes seen earlier in the run.
    """

    issues: list[FieldIssue] = []
    asset_id = raw.get("asset_id")
    if not isinstance(asset_id, str) or not asset_id:
        issues.append(FieldIssue("asset_id", "is required"))
    elif not ASSET_ID_PATTERN.fullmatch(asset_id):
        issues.append(FieldIssue("asset_id", "must match AA-0000 using capital letters"))
    elif asset_id in existing_ids:
        issues.append(FieldIssue("asset_id", "is already in use"))

    name = _tidy_text(raw.get("name"), title_case=True)
    if not name or not 3 <= len(name) <= 120:
        issues.append(FieldIssue("name", "must contain 3 to 120 characters after tidying"))

    asset_type = raw.get("asset_type")
    if isinstance(asset_type, str):
        asset_type = asset_type.strip().casefold()
    if not isinstance(asset_type, str) or asset_type not in ASSET_TYPES:
        issues.append(FieldIssue("asset_type", "must be pole, valve, manhole or transformer"))

    latitude = _coordinate(raw.get("latitude"), "latitude", issues)
    longitude = _coordinate(raw.get("longitude"), "longitude", issues)
    elevation_m = _elevation(raw.get("elevation_m"), issues)
    surveyed_on = _survey_date(raw.get("surveyed_on"), issues, today or date.today())

    surveyor = _tidy_text(raw.get("surveyor"), title_case=True)
    if not surveyor or len(surveyor) > 120:
        issues.append(FieldIssue("surveyor", "must contain 1 to 120 characters after tidying"))

    status = raw.get("status")
    if isinstance(status, str):
        status = status.strip().casefold()
    if not isinstance(status, str) or status not in STATUSES:
        issues.append(FieldIssue("status", "must be active, decommissioned or proposed"))

    condition_score = _score(raw.get("condition_score"), issues)
    attributes = _attributes(raw.get("attribute_json", MISSING), issues)

    if status == "decommissioned" and condition_score is not None and condition_score > 2:
        issues.append(FieldIssue("condition_score", "must not exceed 2 for a decommissioned asset"))

    if issues:
        raise RecordValidationError(issues)
    assert isinstance(asset_id, str)
    assert isinstance(name, str)
    assert isinstance(asset_type, str)
    assert isinstance(latitude, float)
    assert isinstance(longitude, float)
    assert isinstance(surveyed_on, date)
    assert isinstance(surveyor, str)
    assert isinstance(status, str)
    assert isinstance(condition_score, int)
    return CleanAssetRecord(
        asset_id=asset_id,
        name=name,
        asset_type=asset_type,
        latitude=latitude,
        longitude=longitude,
        elevation_m=elevation_m,
        surveyed_on=surveyed_on,
        surveyor=surveyor,
        status=status,
        condition_score=condition_score,
        attributes=attributes,
    )
