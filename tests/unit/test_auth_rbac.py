from fastapi import HTTPException
from starlette.requests import Request

from src.api import auth


def _request(headers=None):
    raw = [(key.lower().encode(), value.encode()) for key, value in (headers or {}).items()]
    return Request({"type": "http", "method": "GET", "path": "/api/analyst/test", "headers": raw})


def test_authentication_rejects_missing_credentials(monkeypatch):
    monkeypatch.setattr(auth, "_configured_credentials", lambda: [("analyst", "analyst", "secret")])
    monkeypatch.setattr(auth, "_principal_from_session", lambda request: None)
    try:
        auth.authenticate(_request())
        assert False, "missing credential should fail"
    except HTTPException as exc:
        assert exc.status_code == 401


def test_role_is_server_derived(monkeypatch):
    monkeypatch.setattr(auth, "_configured_credentials", lambda: [("team-a", "analyst", "secret")])
    principal = auth.authenticate(_request({"Authorization": "Bearer secret", "X-Role": "admin"}))
    assert principal.subject == "team-a"
    assert principal.role == "analyst"


def test_analyst_cannot_use_admin_dependency(monkeypatch):
    monkeypatch.setattr(auth, "_configured_credentials", lambda: [("team-a", "analyst", "secret")])
    dependency = auth.require_roles("admin")
    try:
        dependency(_request({"X-API-Key": "secret"}))
        assert False, "analyst must not become admin"
    except HTTPException as exc:
        assert exc.status_code == 403


def test_signed_analyst_session_grants_analyst_not_admin(monkeypatch):
    monkeypatch.setattr(auth, "_session_secret", lambda purpose: "test-signing-secret")
    token, _ = auth.issue_analyst_session(subject="browser:team-a", ttl_seconds=600)
    request = _request({"Cookie": f"{auth.ANALYST_SESSION_COOKIE}={token}"})

    principal = auth.authenticate(request)
    assert principal.subject == "browser:team-a"
    assert principal.role == "analyst"

    try:
        auth.require_admin(request)
        assert False, "analyst session must never become admin"
    except HTTPException as exc:
        assert exc.status_code == 403


def test_viewer_session_cannot_write_as_analyst(monkeypatch):
    monkeypatch.setattr(auth, "_session_secret", lambda purpose: "test-signing-secret")
    token, _ = auth.issue_viewer_session(subject="web-viewer", ttl_seconds=600)
    request = _request({"Cookie": f"{auth.VIEWER_SESSION_COOKIE}={token}"})

    principal = auth.authenticate(request)
    assert principal.role == "viewer"
    try:
        auth.require_analyst(request)
        assert False, "viewer session must not satisfy analyst role"
    except HTTPException as exc:
        assert exc.status_code == 403
