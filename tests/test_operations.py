"""Request limits, retry information, timing and deployment configuration."""

import logging

import pytest
from fastapi.testclient import TestClient

from utility_assets import operations
from utility_assets.config import parse_cors_origins, request_limit
from utility_assets.main import create_app
from utility_assets.operations import SlidingWindowLimiter


def test_sliding_window_is_per_caller_and_reopens_at_60_seconds():
    limiter = SlidingWindowLimiter(2)
    assert limiter.check("first", 0) == (True, 1, 0)
    assert limiter.check("first", 1) == (True, 0, 0)
    assert limiter.check("second", 1) == (True, 1, 0)
    assert limiter.check("first", 2) == (False, 0, 58)
    assert limiter.check("first", 61) == (True, 1, 0)


def test_http_limit_health_exemption_timing_header_and_safe_log(monkeypatch, caplog):
    monkeypatch.setenv("REQUESTS_PER_MINUTE", "2")
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:3000")
    clock = [100.0]
    monkeypatch.setattr(operations, "monotonic", lambda: clock[0])
    with TestClient(create_app()) as client, caplog.at_level(logging.INFO, logger="uvicorn.error"):
        first = client.get("/docs?secret=never-log-this")
        second = client.get("/docs")
        denied = client.get("/docs", headers={"Origin": "http://localhost:3000"})
        assert (first.status_code, second.status_code, denied.status_code) == (200, 200, 429)
        assert denied.json() == {"errors": [{"field": "request", "message": "rate limit exceeded"}]}
        assert denied.headers["retry-after"] == "60"
        assert denied.headers["ratelimit-limit"] == "2"
        assert denied.headers["ratelimit-remaining"] == "0"
        assert denied.headers["access-control-allow-origin"] == "http://localhost:3000"
        assert float(denied.headers["x-response-time-ms"]) >= 0
        assert client.get("/health").status_code == 200
        assert client.get("/health").status_code == 200
        assert "x-response-time-ms" in client.get("/health").headers
        clock[0] += 60
        assert client.get("/docs").status_code == 200
    assert "path=/docs status=429" in caplog.text
    assert "duration_ms=" in caplog.text
    assert "never-log-this" not in caplog.text


def test_cors_origins_and_request_limit_configuration(monkeypatch):
    assert parse_cors_origins("https://app.example,http://localhost:3000") == (
        "https://app.example", "http://localhost:3000"
    )
    for invalid in ("*", "https://*.example", "https://app.example/path"):
        with pytest.raises(ValueError, match="CORS_ORIGINS"):
            parse_cors_origins(invalid)
    monkeypatch.setenv("REQUESTS_PER_MINUTE", "0")
    with pytest.raises(ValueError, match="positive integer"):
        request_limit()
    monkeypatch.setenv("REQUESTS_PER_MINUTE", "75")
    assert request_limit() == 75
