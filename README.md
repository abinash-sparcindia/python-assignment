# Utility asset survey assignment

This project provides a one-command CSV importer and an authenticated API for
utility asset surveys. The repository includes a **synthetic** 62-row survey
export because the utility's original file was not available. A fresh review
database is migrated and seeded automatically with 51 accepted assets and 11
rejected rows. The importer also produces GeoJSON, a text summary and a dated
run log. Detailed operating instructions are in [RUNBOOK.md](RUNBOOK.md).

## Start the review stack

Install and start Docker Desktop with Compose, then run from the repository root:

```sh
docker compose up --build -d
docker compose ps
```

Open <http://localhost:8000/docs> for interactive API documentation. The
unprotected `GET /health` route should return `{"status":"ok"}`. The review
administrator's random credentials are stored only in the app container:

```sh
docker compose exec app cat /run/utility-assets/review-admin.txt
```

Sign in through `POST /auth/login` and present the returned bearer token on
later requests. `GET /auth/me` shows the signed-in account. Only an
administrator can create another account with `POST /users`. No surveyor
account is pre-created; the administrator chooses its password at creation.
Passwords are not returned by the API. Use `docker compose down` to stop and
clear the review database. The generated files under `output/` remain on the
host for inspection.

## Network operations

- `GET /assets` lists a stable page (default 25, maximum 100) and accepts
  `limit`, `offset`, `asset_type`, `status`, `surveyor`, `min_score`, `max_score`
  and case-insensitive name `search`. The response includes the total count.
- `GET /assets/{asset_id}` fetches one asset. `POST /assets` creates one,
  `PUT /assets/{asset_id}` replaces all fields, `PATCH /assets/{asset_id}`
  corrects selected fields, and `DELETE /assets/{asset_id}` removes it and its
  visits. Full writes use the 11 CSV field names and the shared validator;
  `attribute_json` accepts a JSON value or JSON-encoded string. Every
  successful create, replace or patch adds a visit, with optional `notes`.
- `GET /assets/{asset_id}/visits` pages an asset's visit history.
- `GET /reports/summary` provides counts, average scores, worst assets, extent
  and repair IDs. `GET /reports/repairs` lists active assets below score 5;
  `GET /reports/most-visited` ranks visit counts. `GET /reports/nearest` takes
  `latitude` and `longitude`; `GET /reports/surveyors-by-day` takes `day`.
- `POST /imports/assets` accepts a raw UTF-8 CSV body with the `text/csv`
  content type. It reports accepted and rejected counts and the original rejected
  rows. `?strict=true` rolls back the import if any row is rejected.

All asset and report routes require sign-in. Surveyors may read, create and
correct assets. Administrators can additionally delete assets, upload CSVs and
create users. The summary is cached for at most 60 seconds and refreshed on
the next request after any committed asset change or accepted CSV import,
including an import from a separate CLI process.

## Command-line ingestion

The `utility-assets-import` command takes a CSV path and supports `--help`,
`--rejects`, `--map`, `--summary`, `--log` and `--strict`. It checks required
columns before writing, keeps original values and reasons for rejected rows,
and prints counts and output locations. In the review container:

```sh
docker compose run --rm app utility-assets-import --help
docker compose run --rm app utility-assets-import data/survey_export.csv --strict --rejects output/strict-rejects.csv
```

Supply a new daily CSV for a normal import. Re-importing the bundled sample
adds another visit to each accepted existing asset. The strict example above
finds an intentionally bad row, exits with code 2 and leaves the seeded
database unchanged. Use [RUNBOOK.md](RUNBOOK.md) for output-path options.

## Configuration and request limits

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

## Tests and deliverables

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
