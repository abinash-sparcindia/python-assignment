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
docker compose --profile test run --rm test
```

The database counts should both be 51. The test command uses a separate
PostgreSQL `db-test` container with a temporary database; the test suite resets
that database and never targets the review DB. The files `output/rejects.csv`,
`output/map.geojson`, `output/summary.txt` and `output/ingestion.log` are
written in the project directory. Checked-in examples are in
[`deliverables/`](deliverables/README.md). The default local test suite uses
throwaway SQLite files; the Compose test command exercises PostgreSQL.

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

Each HTTP response includes `X-Response-Time-Ms`. App logs record the method,
path, response status, duration and caller IP without request bodies or query
strings (`docker compose logs app`). The default limit is 60 requests per IP
within a rolling minute; a rejected request returns HTTP 429 and `Retry-After`
in seconds. `/health` stays available during a limit. Set
`REQUESTS_PER_MINUTE` in a local `.env` before startup to adjust the review
limit. `CORS_ORIGINS` accepts comma-separated exact origins such as
`http://localhost:3000`; wildcard entries are rejected. Local repeatable
timings are in [PERFORMANCE.md](PERFORMANCE.md).

The asset list is ordered by `asset_id` and returns `items`, `total`, `limit`
and `offset`. Use `?limit=25&offset=25` for the next page. Filter with
`asset_type`, `status`, `surveyor`, `min_score`, `max_score`, or `search` (name
substring, case-insensitive). The filters combine, and `total` counts matching
assets. Signed-in surveyors
can list, read, create, fully replace, and partially update assets; only an
administrator can delete. A successful write adds a visit. A full create or
replacement must supply every CSV field, including `elevation_m` (which may
be `null`). A patch supplies only fields to change. To try a read in PowerShell:

```powershell
Invoke-RestMethod http://localhost:8000/assets/AA-0001 -Headers @{ Authorization = "Bearer $($login.access_token)" }
Invoke-RestMethod 'http://localhost:8000/assets?asset_type=pole&min_score=0&max_score=4&limit=25' -Headers @{ Authorization = "Bearer $($login.access_token)" }
Invoke-RestMethod http://localhost:8000/assets/PL-0001/visits -Headers @{ Authorization = "Bearer $($login.access_token)" }
Invoke-RestMethod http://localhost:8000/reports/most-visited -Headers @{ Authorization = "Bearer $($login.access_token)" }
Invoke-RestMethod http://localhost:8000/reports/summary -Headers @{ Authorization = "Bearer $($login.access_token)" }
Invoke-RestMethod http://localhost:8000/reports/repairs -Headers @{ Authorization = "Bearer $($login.access_token)" }
Invoke-RestMethod 'http://localhost:8000/reports/nearest?latitude=20.24&longitude=85.78' -Headers @{ Authorization = "Bearer $($login.access_token)" }
Invoke-RestMethod 'http://localhost:8000/reports/surveyors-by-day?day=2026-09-01' -Headers @{ Authorization = "Bearer $($login.access_token)" }
```

Visit history returns `items`, `total`, `limit`, and `offset`, newest survey
first. Most-visited returns up to 10 assets by default, ordered by visit count
then asset ID. Both require sign-in.

The summary returns current asset counts, average scores and worst assets by
type, the geographic extent, and IDs needing repair. The repair report lists
active assets below score 5. Nearest uses geographic distance and returns one
asset with distance in kilometres; it returns 404 when the database is empty.
Surveyors-by-day reads visit history, including older surveys of an asset whose
current surveyor has since changed. Summary is cached for no more than 60
seconds; any committed asset change or accepted CSV import advances the
database revision and refreshes it on the next request.

An administrator can upload a later CSV directly. The upload uses the same
validation and import rules as the CLI. Accepted rows refresh current asset
details and append visits; rejected originals and reasons are returned in the
JSON response. `?strict=true` rolls back all accepted rows if any row fails.
The upload has a 5 MiB limit and keeps working files only temporarily.

```powershell
$csvBytes = [System.IO.File]::ReadAllBytes((Resolve-Path 'data/survey_export.csv'))
Invoke-RestMethod -Method Post -Uri 'http://localhost:8000/imports/assets?strict=true' -Headers @{ Authorization = "Bearer $($login.access_token)" } -ContentType 'text/csv' -Body $csvBytes
```

The bundled synthetic CSV has rejected rows, so this strict example reports
`aborted=true` and leaves the database unchanged. For a normal later import,
omit `?strict=true` and supply a daily CSV.

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
docker compose --profile test down
```

PostgreSQL stores its data on container `tmpfs`, without a host data mount or
Docker data volume. `down` clears the database. The next `up` creates and
seeds a fresh database automatically. Restarting only `app` keeps the database
and does not create duplicate seed visits. Generated files in `output/` stay
on the host so a reviewer can inspect them after shutdown.
