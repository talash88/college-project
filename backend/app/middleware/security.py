"""Security middleware: headers, request IDs, in-memory rate limiting.

Rate limiting is intentionally dependency-free (sliding window per client IP
in process memory). Correct for single-process college deployment and local
development; a multi-replica production setup would need a shared store
(e.g. Redis) instead. Disabled automatically when ENVIRONMENT == "test" so
the deterministic suite never trips it.
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

REQUEST_ID_HEADER = "X-Request-ID"

AsgiApp = Callable[
    [MutableMapping[str, Any], Callable[[], Awaitable[MutableMapping[str, Any]]], Callable[[MutableMapping[str, Any]], Awaitable[None]]],
    Awaitable[None],
]

_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "X-Frame-Options": "DENY",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach safe response headers and a per-request correlation ID."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = uuid4().hex
        request.state.request_id = request_id
        response = await call_next(request)
        for name, value in _SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding-window rate limiter keyed by (client IP, bucket).

    Buckets are (path matcher, limit per 60s) evaluated in order; the first
    match wins, otherwise the default bucket applies. Exceeded requests get
    429 JSON with Retry-After. Only X-Forwarded-For is deliberately NOT
    trusted (no proxy in this deployment); the direct peer IP is the key.
    """

    def __init__(
        self,
        app: AsgiApp,
        *,
        enabled: bool = True,
        default_per_minute: int = 600,
        auth_per_minute: int = 20,
        upload_per_minute: int = 30,
        ai_per_minute: int = 60,
        search_per_minute: int = 120,
    ):
        super().__init__(app)
        self.enabled = enabled
        self.default_limit = default_per_minute
        self.auth_paths = (
            "/api/v1/auth/login",
            "/api/v1/auth/register",
            "/api/v1/auth/refresh",
        )
        self.auth_limit = auth_per_minute
        self.upload_limit = upload_per_minute
        self.ai_limit = ai_per_minute
        self.search_limit = search_per_minute
        self._hits: dict[tuple[str, str], deque[float]] = {}

    def _bucket(self, path: str, method: str) -> tuple[str, int]:
        if path in self.auth_paths:
            return "auth", self.auth_limit
        if method == "POST" and ("/attachments" in path or "/work-files" in path):
            return "upload", self.upload_limit
        if method == "POST" and (
            "/reanalyze" in path
            or "/recalculate" in path
            or "/recommendations/" in path
            or "/classification/run" in path
        ):
            return "ai", self.ai_limit
        if path == "/api/v1/knowledge" or path.endswith("/related-solutions"):
            return "search", self.search_limit
        return "default", self.default_limit

    def _allowed(self, key: tuple[str, str], limit: int, now: float) -> tuple[bool, int]:
        window_start = now - 60.0
        hits = self._hits.get(key)
        if hits is None:
            hits = self._hits[key] = deque()
        while hits and hits[0] <= window_start:
            hits.popleft()
        if len(hits) >= limit:
            retry_after = int(hits[0] - window_start) + 1 if hits else 60
            return False, retry_after
        hits.append(now)
        if len(self._hits) > 10000:
            # Memory hygiene: drop the oldest idle buckets.
            oldest = min(self._hits.items(), key=lambda kv: kv[1][-1] if kv[1] else 0.0)[0]
            del self._hits[oldest]
        return True, 0

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not self.enabled:
            return await call_next(request)
        client_ip = request.client.host if request.client else "unknown"
        bucket, limit = self._bucket(request.url.path, request.method)
        allowed, retry_after = self._allowed((client_ip, bucket), limit, time.monotonic())
        if not allowed:
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Please slow down and try again."},
                headers={"Retry-After": str(retry_after)},
            )
        return await call_next(request)
