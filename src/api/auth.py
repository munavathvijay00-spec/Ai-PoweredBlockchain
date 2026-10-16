"""Authentication and RBAC for ChainScope privileged operations.

Supports explicit API credentials for automation plus short-lived, HttpOnly,
server-signed browser sessions for viewer and analyst product experiences.
Roles are always assigned by the server; callers cannot self-assign them.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass

from fastapi import HTTPException, Request, status

from src.utils.config import get_settings

VIEWER_SESSION_COOKIE = "chainscope_viewer_session"
ANALYST_SESSION_COOKIE = "chainscope_analyst_session"
# Backward-compatible alias used by the existing viewer-session route.
SESSION_COOKIE = VIEWER_SESSION_COOKIE


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
        # Existing deployments already have API_KEY. It remains an admin-grade
        # bootstrap credential and can exchange into a least-privilege analyst session.
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


def _session_secret(purpose: str) -> str:
    explicit_name = (
        "ANALYST_SESSION_SIGNING_KEY" if purpose == "analyst" else "VIEWER_SESSION_SIGNING_KEY"
    )
    explicit = os.getenv(explicit_name, "").strip()
    if explicit:
        return explicit

    source = os.getenv("EVIDENCE_SIGNING_KEY", "").strip() or get_settings().api_key.strip()
    if not source:
        return ""
    return hmac.new(
        source.encode("utf-8"),
        f"chainscope/{purpose}-session/v1".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def viewer_session_configured() -> bool:
    return bool(_session_secret("viewer"))


def analyst_session_configured() -> bool:
    return bool(_session_secret("analyst"))


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}")


def _issue_session(*, role: str, subject: str, purpose: str, ttl_seconds: int) -> tuple[str, int]:
    secret = _session_secret(purpose)
    if not secret:
        raise RuntimeError(f"{purpose.title()} session signing key is not configured")
    now = int(time.time())
    exp = now + max(60, min(int(ttl_seconds), 86400))
    payload = {
        "sub": subject[:128],
        "role": role,
        "iat": now,
        "exp": exp,
        "v": 1,
        "purpose": purpose,
    }
    encoded = _b64encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    signature = hmac.new(secret.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).digest()
    return f"{encoded}.{_b64encode(signature)}", exp


def issue_viewer_session(subject: str = "web-viewer", ttl_seconds: int = 1800) -> tuple[str, int]:
    return _issue_session(role="viewer", subject=subject, purpose="viewer", ttl_seconds=ttl_seconds)


def issue_analyst_session(subject: str = "web-analyst", ttl_seconds: int = 3600) -> tuple[str, int]:
    return _issue_session(role="analyst", subject=subject, purpose="analyst", ttl_seconds=ttl_seconds)


def _principal_from_cookie(request: Request, *, cookie_name: str, role: str, purpose: str) -> Principal | None:
    token = request.cookies.get(cookie_name, "").strip()
    secret = _session_secret(purpose)
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
    if payload.get("role") != role or payload.get("purpose") != purpose:
        return None
    if int(payload.get("exp") or 0) <= int(time.time()):
        return None
    subject = str(payload.get("sub") or f"web-{role}")[:128]
    return Principal(subject=subject, role=role)


def _principal_from_session(request: Request) -> Principal | None:
    # Prefer the stronger role when both cookies are present.
    analyst = _principal_from_cookie(
        request,
        cookie_name=ANALYST_SESSION_COOKIE,
        role="analyst",
        purpose="analyst",
    )
    if analyst:
        return analyst
    return _principal_from_cookie(
        request,
        cookie_name=VIEWER_SESSION_COOKIE,
        role="viewer",
        purpose="viewer",
    )


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
