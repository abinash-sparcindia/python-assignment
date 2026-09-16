# Runbook: Day 1 review build

The app runs with PostgreSQL in Docker Compose. A new review database is
automatically migrated and seeded from the [synthetic 62-row CSV](data/README.md)
when the stack starts. It should contain 51 assets and 51 visits; 11 bad rows
are retained in a rejects file. The API currently provides `/health` and
`/docs`. Authentication and asset network routes are Day 2 work.

## Prerequisite

Install and start Docker Desktop in Linux-container mode. Open PowerShell in
the repository root and confirm `docker compose version` works. Docker was not
available on the development host when this runbook was written, so the
container commands have not had a live smoke test yet.

## Start and check the review stack

```powershell
docker compose up --build -d
docker compose ps
docker compose logs app
Invoke-RestMethod http://localhost:8000/health
```

The app log should show `read=62 accepted=51 rejected=11`. The health response
should be `{"status":"ok"}`. Open <http://localhost:8000/docs> to see the
published API documentation. No separate migration or seed command is needed.

If port 8000 is occupied, create a local `.env` file containing `APP_PORT=8001`,
run `docker compose up --build -d` again, and use port 8001 in the URLs. Do not
commit `.env`.

## Inspect data and generated files

```powershell
docker compose exec db psql -U utility_assets -d utility_assets -c "SELECT COUNT(*) FROM assets;"
docker compose exec db psql -U utility_assets -d utility_assets -c "SELECT COUNT(*) FROM visits;"
docker compose run --rm app python -m pytest -q
```

The database counts should both be 51. The files `output/rejects.csv`,
`output/map.geojson`, `output/summary.txt` and `output/ingestion.log` are
written in the project directory. The tests use throwaway SQLite databases;
they do not change the review database.

## Run the ingestion CLI

```powershell
docker compose run --rm app utility-assets-import --help
docker compose run --rm app utility-assets-import data/survey_export.csv --strict --rejects output/strict-rejects.csv
```

The strict example encounters a bad row and exits with code 2. Its earlier
provisional database changes roll back, leaving the seeded assets and visits
unchanged. It writes the rejected original row and reason to
`output/strict-rejects.csv`. A normal import of the same sample file is also possible,
but each accepted row is treated as a later survey visit and adds another visit
to the existing asset. Use a new daily CSV for normal operations.

Run `utility-assets-import --help` for `--rejects`, `--map`, `--summary`,
`--log`, `--nearest LAT LON` and `--surveyors-on YYYY-MM-DD` options. The CLI
checks required columns before touching the database and logs each run.

## Stop and reset

```powershell
docker compose down
```

PostgreSQL stores its data on container `tmpfs`, without a host data mount or
Docker data volume. `down` clears the database. The next `up` creates and
seeds a fresh database automatically. Restarting only `app` keeps the database
and does not create duplicate seed visits. Generated files in `output/` stay
on the host so a reviewer can inspect them after shutdown.
