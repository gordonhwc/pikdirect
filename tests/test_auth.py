import json

import pytest

from auth import (
    derive_device_id,
    load_auth_session,
    save_auth_session,
)
from models import AuthError, AuthSession


def test_load_auth_session_creates_new_session_when_file_is_missing(tmp_path):
    auth_file = tmp_path / "auth.json"

    session = load_auth_session(auth_file, "alice@example.com", "secret")

    assert session.username == "alice@example.com"
    assert session.auth_file == auth_file.resolve()
    assert session.device_id == derive_device_id("alice@example.com", "secret")
    assert session.access_token == ""
    assert session.refresh_token == ""


def test_load_auth_session_accepts_refreshable_session(tmp_path):
    auth_file = tmp_path / "auth.json"
    auth_file.write_text(
        json.dumps(
            {
                "username": "alice@example.com",
                "access_token": "access-token",
                "refresh_token": "refresh-token",
                "device_id": "device-id",
            }
        ),
        encoding="utf-8",
    )

    session = load_auth_session(auth_file, "alice@example.com", "secret")

    assert session.username == "alice@example.com"
    assert session.access_token == "access-token"
    assert session.refresh_token == "refresh-token"
    assert session.device_id == "device-id"
    assert session.auth_file == auth_file.resolve()


def test_load_auth_session_rejects_mismatched_username(tmp_path):
    auth_file = tmp_path / "auth.json"
    auth_file.write_text(
        json.dumps({"username": "bob@example.com", "device_id": "device-id"}),
        encoding="utf-8",
    )

    with pytest.raises(AuthError, match="does not match"):
        load_auth_session(auth_file, "alice@example.com", "secret")


def test_save_auth_session_round_trips(tmp_path):
    session = AuthSession(
        username="alice@example.com",
        access_token="access-token",
        refresh_token="refresh-token",
        device_id="device-id",
        auth_file=tmp_path / "auth.json",
        user_id="user-id",
    )

    save_auth_session(session)
    loaded = load_auth_session(session.auth_file, "alice@example.com", "secret")

    assert loaded.username == "alice@example.com"
    assert loaded.access_token == "access-token"
    assert loaded.refresh_token == "refresh-token"
    assert loaded.device_id == "device-id"
    assert loaded.user_id == "user-id"
    assert loaded.updated_at is not None


def test_derive_device_id_returns_stable_md5():
    assert derive_device_id("alice@example.com", "secret") == "8a6fa7cd11c17d00c98a0637dfcc2b9a"
