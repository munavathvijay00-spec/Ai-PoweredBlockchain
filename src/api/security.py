"""API abuse protection and browser-facing security controls.

Redis is used when REDIS_URL is configured so limits remain coherent across replicas.
A process-local sliding window remains as a fail-safe if Redis is unavailable.
"""
from __future__ import annotations

import hashlib
import os
import time
from collections import defaultdict, deque
from typing import Deque

from fastapi import HTTPException, Request
from redis.asyncio import Redis
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from src.api.auth import authenticate
from src.utils.config import get_settings

_EXPENSIVE_PREFIXES = (
    "/api/wallets/",
    "/api/ml/",
    "/api/evaluation/",
    "/api/entities",
    "/api/analyst/",
)
_INTERNAL_PATHS = {"/metrics", "/docs", "/redoc", "/openapi.json"}


class AbuseProtectionMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self.settings = get_settings()
        self._buckets: dict[tuple[str, str], Deque[float]] = defaultdict(deque)
        redis_url = os.getenv("REDIS_URL", "").strip()
        self._redis = Redis.from_url(redis_url, encoding="utf-8", decode_responses=True) if redis_url else None

    def _client_key(self, request: Request) -> str:
        forwarded = request.headers.get("x-forwarded-for")
        raw = forwarded.split(",", 1)[0].strip() if forwarded else (request.client.host if request.client else "unknown")
        return hashlib.sha256(raw.encode()).hexdigest()[:24]

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

    def _local_allowed(self, client: str, bucket: str, now: float) -> tuple[bool, int]:
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

    async def _allowed(self, client: str, bucket: str) -> tuple[bool, int, str]:
        if self._redis is not None:
            try:
                now = int(time.time())
                window = now // 60
                key = f"chainscope:ratelimit:{bucket}:{client}:{window}"
                count = await self._redis.incr(key)
                if count == 1:
                    await self._redis.expire(key, 70)
                retry_after = max(1, 60 - (now % 60))
                return count <= self._limit(bucket), retry_after, "redis"
            except Exception:
                # Availability should not depend on Redis. Fall back to a stricter local
                # limiter and expose the limiter mode through the 429 response only.
                pass
        allowed, retry_after = self._local_allowed(client, bucket, time.monotonic())
        return allowed, retry_after, "local_fallback"

    def _secure(self, response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; base-uri 'self'; frame-ancestors 'none'; object-src 'none'; "
            "img-src 'self' data: https:; style-src 'self' 'unsafe-inline'; "
            "script-src 'self'; connect-src 'self' https: wss:; form-action 'self'",
        )
        return response

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        if path in _INTERNAL_PATHS:
            try:
                principal = authenticate(request)
            except HTTPException:
                return self._secure(JSONResponse(status_code=404, content={"detail": "Not found"}))
            if principal.role != "admin":
                return self._secure(JSONResponse(status_code=403, content={"detail": "Admin role required"}))

        if request.method in {"POST", "PUT", "PATCH"}:
            content_length = request.headers.get("content-length")
            try:
                length = int(content_length) if content_length is not None else 0
            except ValueError:
                length = 0
            if length > int(self.settings.max_request_body_bytes):
                return self._secure(JSONResponse(
                    status_code=413,
                    content={"detail": "Request body too large"},
                ))

        if path != "/" and not path.startswith("/app") and path not in _INTERNAL_PATHS:
            bucket = self._bucket_name(path)
            allowed, retry_after, limiter = await self._allowed(self._client_key(request), bucket)
            if not allowed:
                return self._secure(JSONResponse(
                    status_code=429,
                    headers={"Retry-After": str(retry_after)},
                    content={"detail": "Rate limit exceeded", "bucket": bucket, "limiter": limiter},
                ))

        response = await call_next(request)
        return self._secure(response)
