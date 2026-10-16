"""Authentication and RBAC for privileged analyst operations.

Supports two server-side credential boundaries:
1. Explicit API credentials for analyst/admin automation.
2. Short-lived signed viewer sessions for read-only product experiences such as Grounded AI.

Callers cannot self-assign roles through request payloads or headers.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from typing import Iterable

from fastapi import HTTPException, Request, status

from src.utils.config import get_settings

SESSION_COOKIE = "chainscope_viewer_session"


@dataclass(frozen=True)
class Principal:
    subject: str
    role: str


def _configured_credentials() -> list[tuple[str, str, str]]:
    settings = get_settings()
    candidates = [
        ("viewer", "viewer", os.getenv("VIEWER_API_KEY", "").strip()),
        ("analyst", "analyst", os.getenv("ANALYST_API_KEY", "").strip()),
        ("admin", "admin", os.getenv("ADMIN_API_KEY", "").strip()),
        ("legacy-admin", "admin", settings.api_key.strip()),
    ]
    return [(subject, role, secret) for subject, role, secret in candidates if secret]


def _extract_credential(request: Request) -> str | None:
    auth = request.headers.get("authorization", "").strip()
    if auth.lower().startswith("bearer "):
        value = auth[7:].strip()
        if value:
            return value
    value = request.headers.get("x-api-key", "").strip()
    return value or None


def _session_secret() -> str:
    return os.getenv("VIEWER_SESSION_SIGNING_KEY", "").strip()


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}")


def issue_viewer_session(subject: str = "web-viewer", ttl_seconds: int = 1800) -> tuple[str, int]:
    """Create a short-lived HMAC-signed read-only viewer session token."""
    secret = _session_secret()
    if not secret:
        raise RuntimeError("Viewer session signing key is not configured")
    now = int(time.time())
    exp = now + max(60, min(int(ttl_seconds), 86400))
    payload = {
        "sub": subject,
        "role": "viewer",
        "iat": now,
        "exp": exp,
        "v": 1,
    }
    encoded = _b64encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    signature = hmac.new(secret.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).digest()
    return f"{encoded}.{_b64encode(signature)}", exp


def _principal_from_session(request: Request) -> Principal | None:
    token = request.cookies.get(SESSION_COOKIE, "").strip()
    secret = _session_secret()
    if not token or not secret or "." not in token:
        return None
    encoded, provided_signature = token.rsplit(".", 1)
    expected = hmac.new(secret.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).digest()
    try:
        supplied = _b64decode(provided_signature)
        if not hmac.compare_digest(expected, supplied):
            return None
        payload = json.loads(_b64decode(encoded))
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    if payload.get("role") != "viewer" or int(payload.get("exp") or 0) <= int(time.time()):
        return None
    subject = str(payload.get("sub") or "web-viewer")[:128]
    return Principal(subject=subject, role="viewer")


def authenticate(request: Request) -> Principal:
    presented = _extract_credential(request)
    if presented:
        for subject, role, secret in _configured_credentials():
            if hmac.compare_digest(presented, secret):
                return Principal(subject=subject, role=role)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    session_principal = _principal_from_session(request)
    if session_principal:
        return session_principal

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_roles(*roles: str):
    allowed = frozenset(roles)

    def dependency(request: Request) -> Principal:
        principal = authenticate(request)
        if principal.role not in allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return principal

    return dependency


require_viewer = require_roles("viewer", "analyst", "admin")
require_analyst = require_roles("analyst", "admin")
require_admin = require_roles("admin")
