# Runbook: current Commit 1 scaffold

This runbook describes what is runnable **now**. The application currently serves
`/health` and `/docs`, and the database schema can be created. CSV ingestion,
automatic migration and seeding, sign-in, asset routes and reports are scheduled
for later commits. The included CSV is [synthetic](data/README.md).

## Prerequisite

Install and start Docker Desktop in Linux-container mode, then open PowerShell
in the repository directory. Confirm that `docker compose version` works.
Docker was unavailable on the development host when this file was written, so
the container commands below have not yet had a live smoke test.

## Start and inspect the scaffold

Run these commands from the repository root:

```powershell
docker compose up --build -d
docker compose ps
Invoke-RestMethod http://localhost:8000/health
```

The health response should be `{"status":"ok"}`. Open
<http://localhost:8000/docs> to see the current API documentation. Only the
health operation exists at this stage. If port 8000 is occupied, create a local
`.env` file containing `APP_PORT=8001`, run `docker compose up --build -d` again,
and use port 8001 in the URLs. Do not commit `.env`.

## Create the schema and run the test

Automatic migration is planned for Commit 3. For this scaffold, apply the
migration once after starting Compose:

```powershell
docker compose run --rm app alembic upgrade head
docker compose run --rm app python -m pytest -q
```

The test uses a temporary SQLite database and should report `1 passed`. It
does not change the PostgreSQL review database. To verify the review database
has the schema, run:

```powershell
docker compose exec db psql -U utility_assets -d utility_assets -c '\dt'
```

The table list should include `assets`, `visits`, `seed_runs` and
`alembic_version`. There is no data import command yet; the 62-row CSV is
present as input for the next ingestion commit.

## Stop and reset

```powershell
docker compose down
```

PostgreSQL keeps its data on container `tmpfs`, with no host data mount or
Docker data volume. `down` erases the review database. The next `up` creates
an empty database; until Commit 3 is implemented, rerun the migration command
above. Stopping or restarting only `app` leaves the database intact while
`db` stays running.

For startup problems, inspect `docker compose ps` and
`docker compose logs app db`. The database is intentionally not published to
the host; use `docker compose exec db ...` for inspection.
