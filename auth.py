"""Session file loading and persistence helpers for PikPak auth state."""

import json
from datetime import datetime, timezone
from hashlib import md5
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from models import AuthError, AuthSession


def derive_device_id(username: str, password: str) -> str:
    """Mirror pikpak-go and derive the device id from the login credentials."""
    digest = md5(f"{username}{password}".encode("utf-8"))
    return digest.hexdigest()


def load_auth_session(auth_file: Path, username: str, password: str) -> AuthSession:
    """Load a saved session or build a fresh one for the supplied credentials."""
    auth_path = auth_file.expanduser()
    normalized_username = username.strip()

    if not normalized_username:
        raise AuthError("username is empty")

    if not password:
        raise AuthError("password is empty")

    if not auth_path.exists():
        return AuthSession(
            username=normalized_username,
            auth_file=auth_path.resolve(),
            device_id=derive_device_id(normalized_username, password),
        )

    try:
        raw_text = auth_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise AuthError(f"failed to read auth file: {auth_path}") from exc

    try:
        payload: Any = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise AuthError(f"auth file is not valid JSON: {auth_path}") from exc

    if not isinstance(payload, dict):
        raise AuthError("auth file must contain a JSON object")

    username_value = payload.get("username")
    if not isinstance(username_value, str) or not username_value.strip():
        raise AuthError("auth file must contain a string 'username'")

    if username_value.strip() != normalized_username:
        return AuthSession(
            username=normalized_username,
            auth_file=auth_path.resolve(),
            device_id=derive_device_id(normalized_username, password),
        )

    device_id_value = payload.get("device_id")
    if isinstance(device_id_value, str) and device_id_value.strip():
        device_id = device_id_value.strip()
    else:
        device_id = derive_device_id(normalized_username, password)

    access_token_value = payload.get("access_token", "")
    access_token = ""
    if isinstance(access_token_value, str) and access_token_value.strip():
        access_token = access_token_value.strip()

    refresh_token_value = payload.get("refresh_token", "")
    refresh_token = ""
    if isinstance(refresh_token_value, str) and refresh_token_value.strip():
        refresh_token = refresh_token_value.strip()

    user_id_value = payload.get("user_id")
    user_id = user_id_value.strip() if isinstance(user_id_value, str) and user_id_value.strip() else None
    updated_at_value = payload.get("updated_at")
    updated_at = updated_at_value.strip() if isinstance(updated_at_value, str) and updated_at_value.strip() else None

    return AuthSession(
        username=normalized_username,
        auth_file=auth_path.resolve(),
        device_id=device_id,
        access_token=access_token,
        refresh_token=refresh_token,
        user_id=user_id,
        updated_at=updated_at,
    )


def save_auth_session(session: AuthSession) -> None:
    """Persist the current auth session to disk."""
    auth_path = session.auth_file.expanduser().resolve()
    auth_path.parent.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc).isoformat()
    session.updated_at = now

    payload = {
        "username": session.username,
        "device_id": session.device_id,
        "access_token": session.access_token,
        "refresh_token": session.refresh_token,
        "updated_at": session.updated_at,
    }

    if session.user_id is not None:
        payload["user_id"] = session.user_id

    with NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=auth_path.parent,
        delete=False,
    ) as tmp_file:
        json.dump(payload, tmp_file, indent=2)
        tmp_file.write("\n")
        tmp_path = Path(tmp_file.name)

    try:
        tmp_path.replace(auth_path)
    except OSError as exc:
        tmp_path.unlink(missing_ok=True)
        raise AuthError(f"failed to write auth file: {auth_path}") from exc
