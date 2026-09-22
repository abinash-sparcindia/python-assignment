# Outputs of one ingestion run

These files are the assignment deliverable from one run of the command-line
file loader against [`data/survey_export.csv`](../data/survey_export.csv):

```sh
utility-assets-import data/survey_export.csv \
  --rejects deliverables/rejects.csv \
  --map deliverables/map.geojson \
  --summary deliverables/summary.txt \
  --log deliverables/ingestion.log
```

- `rejects.csv`: every refused row, with its original values and the reason.
- `map.geojson`: every accepted asset as a map point.
- `summary.txt`: the printable survey summary. The run timestamp changes when
  the command is run again.
- `ingestion.log`: the dated line that command appended for this run.

Regenerate them with `python scripts/generate_deliverables.py`. That script
calls `utility-assets-import` against a throwaway database. A live stack also
writes a fresh set under `output/` when it starts; only the timestamp differs.
