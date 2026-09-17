# Utility asset survey assignment

This repository is being built in three reviewable milestones; see [PLAN.md](PLAN.md).
For commands to run it, see [RUNBOOK.md](RUNBOOK.md). Day 1 now includes the
synthetic 62-row survey export, a one-command ingestion CLI, automatic review
database seeding, geographic/report outputs and an API health endpoint. Day 2
has added sign-in, user roles, administrator-controlled account creation, and
the six authenticated asset operations. `GET /assets` returns a stable page
(`limit` defaults to 25 and is capped at 100); `GET /assets/{asset_id}` reads
one asset; `POST /assets` creates one; `PUT /assets/{asset_id}` replaces a full
record; `PATCH /assets/{asset_id}` corrects selected fields; and
`DELETE /assets/{asset_id}` removes an asset and its visits. Surveyors can read
and write assets; deletion requires an administrator. Each successful create,
replace, or patch adds a visit, with optional `notes`. Full writes use the same
field names and validation rules as the CSV (`attribute_json` accepts a JSON
value or JSON-encoded string). The search filters, visit-history endpoint, and
bulk upload follow in the next commit.

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

The app now applies migrations and imports the synthetic CSV on a fresh
database, then starts the API. It skips the seed on an app-only restart. The
`db` service and image build still need a Docker smoke test; Docker is not
installed on the current development host.

## Current local checks

With Python 3.12 available, install from the lock file and the package:

```sh
python -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python -m pip install --no-deps -e .
.venv/bin/python -m pytest -q
```

On Windows, replace `.venv/bin/python` with `.venv/Scripts/python.exe`.
The tests use temporary SQLite files and never touch the review DB.
PostgreSQL integration checks will be added as the application is completed.

The CSV is [synthetic](data/README.md); it is not the missing utility export.
