# Local performance check — 18 September 2026

Run `python scripts/benchmark_local.py` from the project root after installing
the package and test dependencies. The script creates a disposable SQLite
database, imports the synthetic 62-row CSV, signs in, warms the summary cache,
and measures 20 requests per endpoint through FastAPI's TestClient. It reports
the slowest client-observed request and the median `X-Response-Time-Ms` value.
It sets a high request limit only for this measurement.

Measured on Windows 11 build 26200 with Python 3.12.14 and SQLite/TestClient:

- Asset page of 25: **6.41 ms** slowest client request; target below 500 ms.
- Single asset: **4.04 ms** slowest client request; target below 200 ms.
- Cached summary: **4.28 ms** slowest client request; target below 100 ms.
- Synthetic CSV ingestion (62 rows, 51 accepted, 11 rejected): **0.059 s**; target below 5 s.

These figures are local development measurements. The final Docker/PostgreSQL
smoke test and timings remain to be run on a host with Docker available. Run the
script again on the review host rather than treating these numbers as portable.
