"""Focused tests for PikPak auth helpers and low-level client behavior."""

import httpx

from client import ApiError, PikPakClient, build_captcha_sign
from models import AuthSession


def make_session(tmp_path, **overrides) -> AuthSession:
    """Build a minimal auth session for client unit tests."""
    defaults = {
        "username": "alice@example.com",
        "auth_file": tmp_path / "auth.json",
        "device_id": "224700c2228930385f0c379b2f10db13",
        "access_token": "access-token",
        "refresh_token": "refresh-token",
        "user_id": "user-id",
    }
    defaults.update(overrides)
    return AuthSession(**defaults)


def test_build_captcha_sign_matches_current_working_web_value(monkeypatch):
    monkeypatch.setattr("client.time.time", lambda: 1775915353.253)

    timestamp, captcha_sign = build_captcha_sign("224700c2228930385f0c379b2f10db13")

    assert timestamp == "1775915353253"
    assert captcha_sign == "1.7a4e260133817f3d164dcaf70a9d01e6"


def test_after_login_captcha_init_includes_authorization_header(tmp_path):
    recorded_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        recorded_requests.append(request)
        return httpx.Response(200, json={"captcha_token": "next-captcha-token"})

    transport = httpx.MockTransport(handler)
    session = make_session(tmp_path)

    with PikPakClient(
        session,
        password="secret",
        http_client=httpx.Client(transport=transport, follow_redirects=True),
    ) as client:
        client._refresh_captcha_token_after_login("GET:/drive/v1/share")

    assert len(recorded_requests) == 1
    assert recorded_requests[0].headers["Authorization"] == "Bearer access-token"
    assert recorded_requests[0].headers["X-Device-ID"] == session.device_id


def test_login_captcha_init_skips_authorization_header(tmp_path):
    recorded_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        recorded_requests.append(request)
        return httpx.Response(200, json={"captcha_token": "login-captcha-token"})

    transport = httpx.MockTransport(handler)
    session = make_session(tmp_path, access_token="")

    with PikPakClient(
        session,
        password="secret",
        http_client=httpx.Client(transport=transport, follow_redirects=True),
    ) as client:
        client._refresh_captcha_token_for_login("POST:/v1/auth/signin")

    assert len(recorded_requests) == 1
    assert "Authorization" not in recorded_requests[0].headers
    assert recorded_requests[0].headers["X-Device-ID"] == session.device_id


def test_refresh_invalid_falls_back_to_login(monkeypatch, tmp_path):
    session = make_session(tmp_path)
    client = PikPakClient(
        session,
        password="secret",
        http_client=httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(500))),
    )

    calls: list[str] = []

    def fake_send_json(*_args, **_kwargs):
        if not calls:
            calls.append("refresh")
            raise ApiError("refresh token is invalid", code=4126)
        calls.append("login")
        return {
            "access_token": "new-access-token",
            "refresh_token": "new-refresh-token",
            "sub": "new-user-id",
        }

    monkeypatch.setattr(client, "_send_json", fake_send_json)
    monkeypatch.setattr(client, "_refresh_captcha_token_for_login", lambda _action: None)

    client.refresh_access_token()

    assert calls == ["refresh", "login"]
    assert session.access_token == "new-access-token"
    assert session.refresh_token == "new-refresh-token"
    assert session.user_id == "new-user-id"
