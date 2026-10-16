from starlette.requests import Request

from src.api.auth import SESSION_COOKIE, authenticate, issue_viewer_session


def _request_with_cookie(token: str) -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/wallets/0x0/copilot",
        "headers": [(b"cookie", f"{SESSION_COOKIE}={token}".encode())],
        "client": ("127.0.0.1", 12345),
        "scheme": "https",
        "server": ("testserver", 443),
        "query_string": b"",
    }
    return Request(scope)


def test_signed_viewer_session_authenticates(monkeypatch):
    monkeypatch.setenv("VIEWER_SESSION_SIGNING_KEY", "test-session-secret-with-enough-entropy")
    token, expires_at = issue_viewer_session(ttl_seconds=300)
    principal = authenticate(_request_with_cookie(token))

    assert principal.subject == "web-viewer"
    assert principal.role == "viewer"
    assert expires_at > 0


def test_tampered_viewer_session_is_rejected(monkeypatch):
    monkeypatch.setenv("VIEWER_SESSION_SIGNING_KEY", "test-session-secret-with-enough-entropy")
    token, _ = issue_viewer_session(ttl_seconds=300)
    encoded, signature = token.rsplit(".", 1)
    replacement = "A" if signature[-1] != "A" else "B"
    tampered = f"{encoded}.{signature[:-1]}{replacement}"

    try:
        authenticate(_request_with_cookie(tampered))
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 401
    else:
        raise AssertionError("Tampered viewer session should not authenticate")
