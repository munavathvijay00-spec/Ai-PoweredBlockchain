"""Authentication and RBAC for privileged analyst operations.

This is a server-side credential boundary: callers cannot grant themselves roles through
request payloads or headers. Production can provide distinct VIEWER/ANALYST/ADMIN keys;
API_KEY remains an admin fallback so existing deployments can be migrated safely.
"""
from __future__ import annotations

import hmac
import os
from dataclasses import dataclass
from typing import Iterable

from fastapi import HTTPException, Request, status

from src.utils.config import get_settings


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


def authenticate(request: Request) -> Principal:
    presented = _extract_credential(request)
    if not presented:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    for subject, role, secret in _configured_credentials():
        if hmac.compare_digest(presented, secret):
            return Principal(subject=subject, role=role)
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid credentials",
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
