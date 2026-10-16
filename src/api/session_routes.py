"""Short-lived browser session bootstrap for read-only product experiences."""
from __future__ import annotations

import os
from fastapi import APIRouter, HTTPException, Request, Response, status

from src.api.auth import SESSION_COOKIE, authenticate, issue_viewer_session

router = APIRouter(prefix="/api/session", tags=["session"])


def _secure_cookie(request: Request) -> bool:
    forwarded = request.headers.get("x-forwarded-proto", "").split(",", 1)[0].strip().lower()
    return forwarded == "https" or request.url.scheme == "https"


@router.post("/viewer")
async def create_viewer_session(request: Request, response: Response):
    """Issue or refresh a short-lived HttpOnly viewer session.

    The session is intentionally read-only. Analyst/admin mutations continue to require
    explicit privileged credentials, so this endpoint never upgrades browser users.
    """
    if not os.getenv("VIEWER_SESSION_SIGNING_KEY", "").strip():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Viewer sessions are not configured",
        )

    # Reuse a valid session rather than rotating identities on every call.
    try:
        principal = authenticate(request)
        if principal.role == "viewer" and principal.subject == "web-viewer":
            return {"role": "viewer", "status": "active"}
    except HTTPException:
        pass

    token, exp = issue_viewer_session(subject="web-viewer", ttl_seconds=1800)
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        max_age=1800,
        expires=1800,
        path="/api",
        secure=_secure_cookie(request),
        httponly=True,
        samesite="strict",
    )
    response.headers["Cache-Control"] = "no-store"
    return {"role": "viewer", "status": "issued", "expires_at": exp}


@router.delete("/viewer", status_code=204)
async def clear_viewer_session(response: Response):
    response.delete_cookie(key=SESSION_COOKIE, path="/api")
    response.headers["Cache-Control"] = "no-store"
    return Response(status_code=204)
