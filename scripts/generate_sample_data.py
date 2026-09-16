"""Create the synthetic 62-row handheld export used for local development.

The assignment references a CSV but does not include it in this repository. This
generator is deterministic and deliberately includes the documented data faults.
It never represents its output as the utility's original survey.
"""

import csv
import json
from pathlib import Path


OUTPUT = Path(__file__).resolve().parents[1] / "data" / "survey_export.csv"
FIELDS = [
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
]
TYPES = [("PL", "pole"), ("VA", "valve"), ("MH", "manhole"), ("TR", "transformer")]
SURVEYORS = ["Anita Das", "Rahul Sen", "Priya Nair", "Mohan Rao"]


def main() -> None:
    rows = []
    for number in range(1, 52):
        prefix, asset_type = TYPES[(number - 1) % len(TYPES)]
        condition = number % 11
        status = "decommissioned" if number % 17 == 0 else "active"
        if status == "decommissioned":
            condition = number % 3
        elif number % 13 == 0:
            status = "proposed"
        if asset_type == "pole":
            attributes = {"height_m": 8 + number % 5}
        elif asset_type == "valve":
            attributes = {"bore_mm": 80 + 10 * (number % 4)}
        elif asset_type == "manhole":
            attributes = {"depth_m": round(1.2 + 0.1 * (number % 8), 1)}
        else:
            attributes = {"rating_kva": 100 + 25 * (number % 6)}
        rows.append(
            {
                "asset_id": f"{prefix}-{number:04d}",
                "name": f"Bhubaneswar {asset_type} {number}",
                "asset_type": asset_type,
                "latitude": f"{20.2400 + number * 0.0011:.4f}",
                "longitude": f"{85.7800 + number * 0.0013:.4f}",
                "elevation_m": "" if number % 6 == 0 else str(35 + number % 12),
                "surveyed_on": f"2026-09-{1 + number % 10:02d}",
                "surveyor": SURVEYORS[(number - 1) % len(SURVEYORS)],
                "status": status,
                "condition_score": str(condition),
                "attribute_json": json.dumps(attributes, separators=(",", ":")),
            }
        )

    # Valid but untidy values: all should normalize without losing the row.
    rows[0]["name"] = "  BHUBANESWAR   POLE  1  "
    rows[1]["asset_type"] = "VaLvE"
    rows[2]["latitude"] = "20.2433 N"
    rows[2]["longitude"] = "85.7839 E"
    rows[3]["surveyor"] = "  rahul   SEN  "
    rows[4]["surveyor"] = "ANITA DAS"
    rows[5]["latitude"] = "20.2466 S"
    rows[6]["longitude"] = "85.7891 W"

    # Eleven rejected rows cover each invalid-input class in the assignment.
    faults = [
        ("latitude outside range", {"asset_id": "PL-0052", "latitude": "91.2"}),
        ("longitude not numeric", {"asset_id": "VA-0053", "longitude": "east-ish"}),
        ("duplicate code", {"asset_id": rows[0]["asset_id"]}),
        ("missing code", {"asset_id": ""}),
        ("malformed code", {"asset_id": "P-0056"}),
        ("rating above 10", {"asset_id": "VA-0057", "condition_score": "14"}),
        ("blank rating", {"asset_id": "MH-0058", "condition_score": ""}),
        ("future survey", {"asset_id": "TR-0059", "surveyed_on": "2099-01-01"}),
        ("invalid JSON", {"asset_id": "PL-0060", "attribute_json": "{height_m: 9}"}),
        ("unknown type", {"asset_id": "VA-0061", "asset_type": "cable"}),
        (
            "decommissioned rating above 2",
            {"asset_id": "MH-0062", "status": "decommissioned", "condition_score": "7"},
        ),
    ]
    for index, (_, changes) in enumerate(faults, start=52):
        row = rows[(index - 1) % len(rows)].copy()
        row.update(changes)
        rows.append(row)

    assert len(rows) == 62
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} synthetic records to {OUTPUT}")


if __name__ == "__main__":
    main()
