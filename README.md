# Utility asset survey assignment

This repository is being built in three reviewable milestones; see [PLAN.md](PLAN.md).
For commands to run it, see [RUNBOOK.md](RUNBOOK.md). Day 1 now includes the
synthetic 62-row survey export, a one-command ingestion CLI, automatic review
database seeding, geographic/report outputs and an API health endpoint.
Authentication and asset API routes are planned for Day 2.

## Review database design

`compose.yaml` defines a PostgreSQL container whose data directory is `tmpfs`.
It has no host data mount or Docker data volume. Stopping the database container,
including `docker compose down`, erases its contents. The API container uses the
database over the private Compose network; PostgreSQL has no published port.
The database currently uses trust authentication **only for this isolated review
stack** so a fresh checkout can start without a manually created secret. The
Day 2 authentication work will generate the API signing secret and reviewer
account at startup; neither will be committed. Do not use this Compose
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
The database test uses a temporary SQLite file and never touches the review DB.
PostgreSQL integration checks will be added as the application is completed.

The CSV is [synthetic](data/README.md); it is not the missing utility export.
