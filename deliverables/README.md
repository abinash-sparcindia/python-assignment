# Synthetic review deliverables

These files were generated from [`data/survey_export.csv`](../data/survey_export.csv),
the **made-up** 62-row fixture supplied with this project because the utility's
original export was not available. They are examples for review, not results
from real utility assets. Generate them again with
`python scripts/generate_deliverables.py`.

- `rejects.csv`: 11 original input rows with rejection reasons.
- `map.geojson`: 51 accepted, cleaned asset points.
- `summary.txt`: text report for the 51 accepted records. Its run timestamp
  changes when the script is rerun.

The Docker review stack also writes current-run outputs into the ignored
`output/` directory when it starts. Those files may differ in timestamp from
these checked-in examples.
