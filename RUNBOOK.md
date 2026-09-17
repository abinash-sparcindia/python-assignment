# Runbook: review build

The app runs with PostgreSQL in Docker Compose. A new review database is
automatically migrated and seeded from the [synthetic 62-row CSV](data/README.md)
when the stack starts. It should contain 51 assets and 51 visits; 11 bad rows
are retained in a rejects file. The API provides `/health`, `/auth/login`,
`/auth/me`, administrator-only `/users`, the six asset routes, and `/docs`.

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

## Sign in as the review administrator

Retrieve the randomly generated credentials from the app container. The file
is not mounted on the host and is not included in logs:

```powershell
docker compose exec app cat /run/utility-assets/review-admin.txt
```

Use the returned username and password to sign in:

```powershell
$credentials = docker compose exec -T app cat /run/utility-assets/review-admin.txt
$reviewUser = (($credentials | Where-Object { $_ -like 'username=*' }) -split '=', 2)[1]
$reviewPassword = (($credentials | Where-Object { $_ -like 'password=*' }) -split '=', 2)[1]
$body = @{ username = $reviewUser; password = $reviewPassword } | ConvertTo-Json
$login = Invoke-RestMethod -Method Post -Uri http://localhost:8000/auth/login -ContentType 'application/json' -Body $body
Invoke-RestMethod http://localhost:8000/auth/me -Headers @{ Authorization = "Bearer $($login.access_token)" }
Invoke-RestMethod http://localhost:8000/assets -Headers @{ Authorization = "Bearer $($login.access_token)" }
```

The final command should return `review-admin` with the `administrator` role.
An administrator may create surveyor or administrator accounts with `POST
/users`; the interactive form is at <http://localhost:8000/docs>. Restarting
`app` generates new review credentials, so retrieve the file again afterward.

The asset list is ordered by `asset_id` and returns `items`, `total`, `limit`
and `offset`. Use `?limit=25&offset=25` for the next page. Signed-in surveyors
can list, read, create, fully replace, and partially update assets; only an
administrator can delete. A successful write adds a visit. A full create or
replacement must supply every CSV field, including `elevation_m` (which may
be `null`). A patch supplies only fields to change. To try a read in PowerShell:

```powershell
Invoke-RestMethod http://localhost:8000/assets/AA-0001 -Headers @{ Authorization = "Bearer $($login.access_token)" }
```

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
