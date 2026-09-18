# Utility asset survey assignment

This project provides a command-line CSV importer and an authenticated API for
utility asset surveys. For setup and operating commands, see
[RUNBOOK.md](RUNBOOK.md). The repository includes a synthetic 62-row survey
export, automatic review database seeding, rejects and geographic/report
outputs. `GET /assets` returns a stable page
(`limit` defaults to 25 and is capped at 100); `GET /assets/{asset_id}` reads
one asset; `POST /assets` creates one; `PUT /assets/{asset_id}` replaces a full
record; `PATCH /assets/{asset_id}` corrects selected fields; and
`DELETE /assets/{asset_id}` removes an asset and its visits. Surveyors can read
and write assets; deletion requires an administrator. Each successful create,
replace, or patch adds a visit, with optional `notes`. Full writes use the same
field names and validation rules as the CSV (`attribute_json` accepts a JSON
value or JSON-encoded string). The list accepts `asset_type`, `status`,
`surveyor`, `min_score`, `max_score`, and case-insensitive `search` filters.
`GET /assets/{asset_id}/visits` pages visit history, and
`GET /reports/most-visited` ranks assets by visit count. Administrators can submit
raw UTF-8 CSV as `text/csv` to `POST /imports/assets`, optionally with
`?strict=true`; the response contains counts and original rejected rows.
The API also exposes live `GET /reports/summary`, `/reports/repairs`,
`/reports/nearest?latitude=...&longitude=...`, and
`/reports/surveyors-by-day?day=YYYY-MM-DD`. Summary results are cached for at
most 60 seconds. A database revision advances with every committed asset write
or accepted CSV import, so the next summary request refreshes immediately,
including after an import from a separate CLI process.

The API applies an in-process sliding request limit per client IP (default 60
requests in 60 seconds), returns `429` with `Retry-After` when exceeded, and
exempts `/health`. Response headers include `X-Response-Time-Ms`; logs record
method, path, status, duration, and client IP without query strings or bodies.
The review stack runs one API process, so the in-memory limiter covers that
process. A multi-process deployment needs a shared external limiter.
`CORS_ORIGINS` accepts comma-separated exact HTTP(S) origins; wildcards are
rejected. `DATABASE_URL`, `SIGNING_SECRET`, `TOKEN_LIFETIME_MINUTES`,
`CORS_ORIGINS`, and `REQUESTS_PER_MINUTE` configure a non-review deployment.
See [PERFORMANCE.md](PERFORMANCE.md) for repeatable local timing checks.

## Review database design

`compose.yaml` defines a PostgreSQL container whose data directory is `tmpfs`.
It has no host data mount or Docker data volume. Stopping the database container,
including `docker compose down`, erases its contents. The API container uses the
database over the private Compose network; PostgreSQL has no published port.
The database currently uses trust authentication **only for this isolated review
stack** so a fresh checkout can start without a manually created secret. The
review app generates its API signing secret and a fresh administrator password
at startup; neither is committed or printed in logs. The password is kept only
in a container-local file described in the runbook. A restart of `app` changes
that password and invalidates existing tokens. Do not use this Compose
configuration as a production deployment.

The app applies migrations and imports the synthetic CSV on a fresh database,
then starts the API. It skips the seed on an app-only restart. A separate
`db-test` Compose service uses another tmpfs PostgreSQL database named
`utility_assets_test`; `docker compose --profile test run --rm test` runs the
suite against it. The test fixture refuses a `TEST_DATABASE_URL` whose database
name does not end in `_test`, to protect the review database. Docker is not
available in the current verification environment, so this Compose workflow
still needs a live smoke test.

## Current local checks

With Python 3.12 available, install from the lock file and the package:

```sh
python -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python -m pip install --no-deps -e .
.venv/bin/python -m pytest -q
```

On Windows, replace `.venv/bin/python` with `.venv/Scripts/python.exe`.
The default tests use temporary SQLite files. For the isolated PostgreSQL test
run, use the Compose command above. Neither test path touches the review DB.

The checked-in [synthetic deliverables](deliverables/README.md) include one
rejects CSV, GeoJSON map and text report. Run
`python scripts/generate_deliverables.py` to regenerate them. See
[FINAL_VERIFICATION.md](FINAL_VERIFICATION.md) for verified checks and the
remaining Docker and recording steps.

The CSV is [synthetic](data/README.md); it is not the missing utility export.
