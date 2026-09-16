"""Initial API shell; ingestion and protected routes are later milestones."""

from fastapi import FastAPI

app = FastAPI(title="Utility Asset Service", version="0.1.0")


@app.get("/health", tags=["monitoring"])
def health() -> dict[str, str]:
    return {"status": "ok"}
