# Synthetic survey export

`survey_export.csv` is a deterministic, **made-up** replacement for the missing
62-record input referenced by the assignment PDF. Regenerate it with
`python scripts/generate_sample_data.py`. It is suitable for building and
demonstrating the application, but is not evidence that the utility's original
export was processed.

The CSV has 62 data rows. Rows 1-51 are intended to be accepted after cleaning.
They include extra and repeated spaces, mixed-case asset types and surveyor
names, compass coordinates, blank optional elevations and valid JSON
attributes. Rows 52-62 are intended to be rejected, one each for:

1. Latitude out of range.
2. Longitude that is not numeric.
3. Duplicate asset code.
4. Missing asset code.
5. Malformed asset code.
6. Condition score above 10.
7. Blank condition score.
8. Future survey date.
9. Invalid JSON attributes.
10. Unrecognised asset type.
11. Decommissioned asset with a condition score above 2.

Expected result for an empty database: **51 accepted, 11 rejected**. The
south/west compass examples are intentionally outside Bhubaneswar after
normalization so the parser's sign handling can be demonstrated; geographic
extent from this synthetic fixture is not a real survey extent.
