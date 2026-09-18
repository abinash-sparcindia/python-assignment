# Final verification and demo handoff

## Completed on 18 September 2026

- Three reviewable commits were made on each planned day (nine implementation
  commits, plus the initial plan commit). The working tree was clean before
  this final handoff commit.
- `python -m pytest -q` passed: **67 tests** using disposable SQLite databases.
  The tests cover migration, automatic seed, CLI, CSV rejects, asset operations,
  roles, reports, caching, request limits, and the checked-in deliverables.
- `python scripts/generate_deliverables.py` produced
  [`rejects.csv`](deliverables/rejects.csv),
  [`map.geojson`](deliverables/map.geojson), and
  [`summary.txt`](deliverables/summary.txt) from the synthetic fixture.
  The verification test reproduces their contents, ignoring only the summary's
  run timestamp.
- Local timing measurements and the repeatable command are recorded in
  [PERFORMANCE.md](PERFORMANCE.md). These are SQLite/TestClient results.
- The tracked example configuration contains no live passwords or signing
  secrets. The review stack generates its administrator password and signing
  key at startup, and its PostgreSQL data directory is mounted on tmpfs.

## Pending on a Docker host

Docker is not installed on the development host used for this commit. These
checks must be run before claiming a fully verified Docker delivery:

1. From a fresh checkout, run `docker compose up --build -d`. Check
   `docker compose ps`, `docker compose logs app`, `/health`, and `/docs`.
   Confirm the seed reports 62 read, 51 accepted, and 11 rejected.
2. Run `docker compose --profile test run --rm test`. It should pass the full
   suite against `utility_assets_test` in the separate `db-test` container.
3. Restart only `app` before making manual writes and confirm assets and
   visits remain at 51. Follow [RUNBOOK.md](RUNBOOK.md) to sign in, read
   assets, test surveyor delete refusal, and check summary refresh after a
   write. Check a rate-limit refusal with a low `REQUESTS_PER_MINUTE` setting
   in a local `.env`.
4. Record PostgreSQL timing results for a page of 25, one asset, a cached
   summary, and the 62-row import. Compare them with the targets in
   [PERFORMANCE.md](PERFORMANCE.md).
5. Run `docker compose --profile test down`; run
   `docker compose up --build -d` again and confirm the fresh tmpfs database
   seeds back to 51 assets and 51 visits. Finish with
   `docker compose --profile test down`.

## 5–8 minute recording outline

The recording is pending the Docker run above. Capture a 5–8 minute screen
recording on that host and keep it with the handoff:

1. Show `docker compose up --build -d`, healthy services, the 51/11 seed log,
   and the generated rejects, map and summary files.
2. Open `/docs`, sign in as the review administrator, and fetch an asset.
3. Sign in as a surveyor and show a forbidden delete (`403`) alongside an
   unsigned asset request (`401`).
4. Fetch `/reports/summary`, patch a test asset, then fetch it again to show
   immediate cache refresh.
5. Set a low request limit in the ignored `.env`, recreate `app` with
   `docker compose up -d --force-recreate app`, retrieve its new review
   credentials, then show `429` with `Retry-After` and `/health` still succeeds.
6. Show the PostgreSQL test command and finish with
   `docker compose --profile test down` to clear the temporary databases.

The input CSV is synthetic. Verification against the utility's actual CSV
remains pending until that file is supplied.
