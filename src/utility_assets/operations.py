"""Per-caller request limits and safe request timing logs."""

import logging
import math
from collections import deque
from threading import Lock
from time import monotonic, perf_counter

from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send


# Uvicorn configures this logger for stderr in the review container. Its
# built-in access log is disabled so only these redacted path-only lines remain.
logger = logging.getLogger("uvicorn.error")
WINDOW_SECONDS = 60


class SlidingWindowLimiter:
    def __init__(self, limit: int):
        self.limit = limit
        self._calls: dict[str, deque[float]] = {}
        self._lock = Lock()
        self._next_cleanup = 0.0

    def check(self, caller: str, now: float) -> tuple[bool, int, int]:
        with self._lock:
            if now >= self._next_cleanup:
                for key, values in list(self._calls.items()):
                    while values and now - values[0] >= WINDOW_SECONDS:
                        values.popleft()
                    if not values:
                        del self._calls[key]
                self._next_cleanup = now + WINDOW_SECONDS
            calls = self._calls.setdefault(caller, deque())
            while calls and now - calls[0] >= WINDOW_SECONDS:
                calls.popleft()
            if len(calls) >= self.limit:
                retry_after = max(1, math.ceil(WINDOW_SECONDS - (now - calls[0])))
                return False, 0, retry_after
            calls.append(now)
            return True, self.limit - len(calls), 0


class OperationalMiddleware:
    def __init__(self, app: ASGIApp, limit: int):
        self.app = app
        self.limiter = SlidingWindowLimiter(limit)
        self.limit = limit

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = perf_counter()
        method = scope["method"]
        path = scope["path"]
        caller = scope.get("client")
        caller_ip = caller[0] if caller else "unknown"
        status = 500
        rate_headers: list[tuple[bytes, bytes]] = []
        if path != "/health":
            allowed, remaining, retry_after = self.limiter.check(caller_ip, monotonic())
            rate_headers = [
                (b"ratelimit-limit", str(self.limit).encode("ascii")),
                (b"ratelimit-remaining", str(remaining).encode("ascii")),
            ]
            if not allowed:
                rate_headers.append((b"retry-after", str(retry_after).encode("ascii")))

        async def send_with_timing(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                elapsed_ms = (perf_counter() - started) * 1000
                message.setdefault("headers", []).extend(
                    rate_headers + [(b"x-response-time-ms", f"{elapsed_ms:.3f}".encode("ascii"))]
                )
            await send(message)

        try:
            if path != "/health" and not allowed:
                response = JSONResponse(
                    status_code=429,
                    content={"errors": [{"field": "request", "message": "rate limit exceeded"}]},
                )
                await response(scope, receive, send_with_timing)
            else:
                await self.app(scope, receive, send_with_timing)
        finally:
            logger.info(
                "request method=%s path=%s status=%s duration_ms=%.3f caller=%s",
                method, path, status, (perf_counter() - started) * 1000, caller_ip,
            )
