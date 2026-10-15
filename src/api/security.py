"""Lightweight process-local API abuse protection.

This is intentionally conservative and dependency-free. It limits request bodies and
per-client request rate for public and expensive investigation routes. In multi-replica
production, use a shared gateway/Redis limiter; this middleware remains a local safety net.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Deque

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from src.utils.config import get_settings

_EXPENSIVE_PREFIXES = (
    "/api/wallets/",
    "/api/ml/",
    "/api/evaluation/",
    "/api/entities",
)


class AbuseProtectionMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self.settings = get_settings()
        self._buckets: dict[tuple[str, str], Deque[float]] = defaultdict(deque)

    def _client_key(self, request: Request) -> str:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",", 1)[0].strip()
        return request.client.host if request.client else "unknown"

    def _bucket_name(self, path: str) -> str:
        if any(path.startswith(prefix) for prefix in _EXPENSIVE_PREFIXES):
            return "expensive"
        return "public"

    def _limit(self, bucket: str) -> int:
        value = (
            self.settings.expensive_rate_limit_per_minute
            if bucket == "expensive"
            else self.settings.public_rate_limit_per_minute
        )
        return max(1, int(value))

    def _allowed(self, client: str, bucket: str, now: float) -> tuple[bool, int]:
        queue = self._buckets[(client, bucket)]
        cutoff = now - 60.0
        while queue and queue[0] < cutoff:
            queue.popleft()
        limit = self._limit(bucket)
        if len(queue) >= limit:
            retry_after = max(1, int(60 - (now - queue[0])))
            return False, retry_after
        queue.append(now)
        return True, 0

    async def dispatch(self, request: Request, call_next):
        if request.method in {"POST", "PUT", "PATCH"}:
            content_length = request.headers.get("content-length")
            try:
                length = int(content_length) if content_length is not None else 0
            except ValueError:
                length = 0
            if length > int(self.settings.max_request_body_bytes):
                return JSONResponse(
                    status_code=413,
                    content={"detail": "Request body too large"},
                )

        path = request.url.path
        if path not in {"/", "/metrics"} and not path.startswith("/app"):
            bucket = self._bucket_name(path)
            allowed, retry_after = self._allowed(self._client_key(request), bucket, time.monotonic())
            if not allowed:
                return JSONResponse(
                    status_code=429,
                    headers={"Retry-After": str(retry_after)},
                    content={"detail": "Rate limit exceeded", "bucket": bucket},
                )

        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        return response
