"""API abuse protection and browser-facing security controls.

Redis is used when REDIS_URL is configured so limits remain coherent across replicas.
A process-local sliding window remains as a fail-safe if Redis is unavailable.
Expensive API work is additionally bounded with a process semaphore to avoid memory spikes.
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import time
import uuid
from collections import defaultdict, deque
from typing import Deque

from fastapi import HTTPException, Request
from redis.asyncio import Redis
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from src.api.auth import authenticate
from src.utils.config import get_settings

_EXPENSIVE_PREFIXES = (
    "/api/ml/",
    "/api/evaluation/",
    "/api/entities",
    "/api/analyst/",
)
_WALLET_PREFIX = "/api/wallets/"
_WALLET_READ_SUFFIXES = (
    "/balance",
    "/transfers",
    "/indexed-graph",
)
_INTERNAL_PATHS = {"/metrics", "/docs", "/redoc", "/openapi.json"}


def _wallet_interactive_read(path: str) -> bool:
    return path.startswith(_WALLET_PREFIX) and any(path.endswith(suffix) for suffix in _WALLET_READ_SUFFIXES)


def _rate_bucket(path: str, authenticated: bool) -> str:
    """Keep interactive graph reads usable without weakening AI/deep-analysis protection."""
    if _wallet_interactive_read(path):
        return "wallet_read"
    if path.startswith(_WALLET_PREFIX) or any(path.startswith(prefix) for prefix in _EXPENSIVE_PREFIXES):
        return "expensive"
    return "authenticated" if authenticated else "public"


def _capacity_bounded(path: str) -> bool:
    return path.startswith(_WALLET_PREFIX) or any(path.startswith(prefix) for prefix in _EXPENSIVE_PREFIXES)


class AbuseProtectionMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self.settings = get_settings()
        self._buckets: dict[tuple[str, str], Deque[float]] = defaultdict(deque)
        self._expensive_slots = asyncio.Semaphore(max(1, int(self.settings.expensive_max_concurrency)))
        redis_url = os.getenv("REDIS_URL", "").strip()
        self._redis = Redis.from_url(redis_url, encoding="utf-8", decode_responses=True) if redis_url else None

    def _ip_key(self, request: Request) -> str:
        forwarded = request.headers.get("x-forwarded-for")
        raw = forwarded.split(",", 1)[0].strip() if forwarded else (request.client.host if request.client else "unknown")
        return hashlib.sha256(raw.encode()).hexdigest()[:24]

    def _identity(self, request: Request) -> tuple[str, bool]:
        """Use credential identity for trusted users; keep anonymous viewer sessions IP-scoped."""
        try:
            principal = authenticate(request)
            if principal.role == "viewer" and principal.subject == "web-viewer":
                return f"ip:{self._ip_key(request)}", False
            stable = hashlib.sha256(f"{principal.role}:{principal.subject}".encode()).hexdigest()[:24]
            return f"principal:{stable}", True
        except HTTPException:
            return f"ip:{self._ip_key(request)}", False

    def _bucket_name(self, path: str, authenticated: bool) -> str:
        return _rate_bucket(path, authenticated)

    def _limit(self, bucket: str) -> int:
        if bucket == "wallet_read":
            value = self.settings.wallet_read_rate_limit_per_minute
        elif bucket == "expensive":
            value = self.settings.expensive_rate_limit_per_minute
        elif bucket == "authenticated":
            value = self.settings.authenticated_rate_limit_per_minute
        else:
            value = self.settings.public_rate_limit_per_minute
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
                pass
        allowed, retry_after = self._local_allowed(client, bucket, time.monotonic())
        return allowed, retry_after, "local_fallback"

    def _secure(self, response, request_id: str | None = None):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; base-uri 'self'; frame-ancestors 'none'; object-src 'none'; "
            "img-src 'self' data: https:; style-src 'self' 'unsafe-inline'; "
            "script-src 'self'; connect-src 'self' https: wss:; form-action 'self'",
        )
        if request_id:
            response.headers.setdefault("X-Request-ID", request_id)
        return response

    async def _call_with_expensive_slot(self, request: Request, call_next, request_id: str):
        timeout = max(0.1, float(self.settings.expensive_queue_timeout_seconds))
        try:
            await asyncio.wait_for(self._expensive_slots.acquire(), timeout=timeout)
        except asyncio.TimeoutError:
            return self._secure(JSONResponse(
                status_code=503,
                headers={"Retry-After": "2"},
                content={"detail": "Investigation capacity is busy; retry shortly", "request_id": request_id},
            ), request_id)
        try:
            return await call_next(request)
        finally:
            self._expensive_slots.release()

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        incoming_request_id = request.headers.get("x-request-id", "").strip()
        request_id = incoming_request_id[:128] if incoming_request_id else str(uuid.uuid4())
        request.state.request_id = request_id

        if path in _INTERNAL_PATHS:
            try:
                principal = authenticate(request)
            except HTTPException:
                return self._secure(JSONResponse(status_code=404, content={"detail": "Not found"}), request_id)
            if principal.role != "admin":
                return self._secure(JSONResponse(status_code=403, content={"detail": "Admin role required"}), request_id)

        if request.method in {"POST", "PUT", "PATCH"}:
            content_length = request.headers.get("content-length")
            try:
                length = int(content_length) if content_length is not None else 0
            except ValueError:
                length = 0
            if length > int(self.settings.max_request_body_bytes):
                return self._secure(JSONResponse(
                    status_code=413,
                    content={"detail": "Request body too large", "request_id": request_id},
                ), request_id)

        capacity_bounded = _capacity_bounded(path)
        bucket = None
        if path != "/" and not path.startswith("/app") and path not in _INTERNAL_PATHS:
            client, authenticated = self._identity(request)
            bucket = self._bucket_name(path, authenticated)
            allowed, retry_after, limiter = await self._allowed(client, bucket)
            if not allowed:
                return self._secure(JSONResponse(
                    status_code=429,
                    headers={"Retry-After": str(retry_after), "X-RateLimit-Limit": str(self._limit(bucket))},
                    content={"detail": "Rate limit exceeded", "bucket": bucket, "limiter": limiter, "request_id": request_id},
                ), request_id)

        if capacity_bounded:
            response = await self._call_with_expensive_slot(request, call_next, request_id)
        else:
            response = await call_next(request)
        if bucket:
            response.headers.setdefault("X-RateLimit-Limit", str(self._limit(bucket)))
        return self._secure(response, request_id)
