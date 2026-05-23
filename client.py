"""Synchronous PikPak API client used by the CLI workflow."""

import json
import re
import time
from dataclasses import dataclass
from hashlib import md5
from typing import Any, Self

import httpx

from config import (
    API_BASE_URL,
    CAPTCHA_REDIRECT_URI,
    DEFAULT_CLIENT_ID,
    DEFAULT_CLIENT_SECRET,
    DEFAULT_CLIENT_VERSION,
    DEFAULT_PARENT_ID,
    DEFAULT_PACKAGE_NAME,
    DEFAULT_TIMEOUT_SECONDS,
    DEFAULT_USER_AGENT,
    ERROR_CODE_ACCESS_TOKEN_EXPIRED,
    ERROR_CODE_ACCESS_TOKEN_INVALID,
    ERROR_CODE_CAPTCHA_TOKEN_EXPIRED,
    ERROR_CODE_REFRESH_TOKEN_INVALID,
    ERROR_CODE_TOO_MANY_REQUESTS,
    ERROR_CODE_UNAUTHORIZED,
    USER_BASE_URL,
    WEB_CAPTCHA_ALGORITHMS,
)
from models import (
    AuthError,
    AuthSession,
    CaptchaChallengeHandler,
    CleanupError,
    DriveNode,
    ResolveError,
    ShareError,
    ShareTarget,
)

EMAIL_RE = re.compile(r"\w+([-+.]\w+)*@\w+([-.]\w+)*\.\w+([-.]\w+)*")


@dataclass(slots=True)
class ApiError(RuntimeError):
    """Internal representation of an API failure returned by PikPak."""

    message: str
    code: int | str | None = None
    status_code: int | None = None

    def __str__(self) -> str:
        return self.message


def is_auth_api_error(error: ApiError) -> bool:
    """Return whether the API error represents an expired or invalid access token."""
    return error.status_code in {401, 403} or error.code in {
        ERROR_CODE_ACCESS_TOKEN_EXPIRED,
        ERROR_CODE_ACCESS_TOKEN_INVALID,
        ERROR_CODE_UNAUTHORIZED,
        str(ERROR_CODE_ACCESS_TOKEN_EXPIRED),
        str(ERROR_CODE_ACCESS_TOKEN_INVALID),
        str(ERROR_CODE_UNAUTHORIZED),
    }


def is_captcha_api_error(error: ApiError) -> bool:
    """Return whether the API error represents an expired captcha token."""
    return error.code in {
        ERROR_CODE_CAPTCHA_TOKEN_EXPIRED,
        str(ERROR_CODE_CAPTCHA_TOKEN_EXPIRED),
    }


def is_refresh_token_invalid_error(error: ApiError) -> bool:
    """Return whether the API error means the refresh token can no longer be used."""
    return error.code in {
        ERROR_CODE_REFRESH_TOKEN_INVALID,
        str(ERROR_CODE_REFRESH_TOKEN_INVALID),
    }


def build_captcha_sign(device_id: str) -> tuple[str, str]:
    """Generate the web captcha sign used by PikPak shield init."""
    timestamp = str(int(time.time() * 1000))
    digest = f"{DEFAULT_CLIENT_ID}{DEFAULT_CLIENT_VERSION}{DEFAULT_PACKAGE_NAME}{device_id}{timestamp}"

    for algorithm in WEB_CAPTCHA_ALGORITHMS:
        digest = md5(f"{digest}{algorithm}".encode("utf-8")).hexdigest()

    return timestamp, f"1.{digest}"


def get_action(method: str, url: str) -> str:
    """Convert a request into PikPak captcha action syntax."""
    path = httpx.URL(url).raw_path.decode("utf-8")
    return f"{method.upper()}:{path}"


def is_email(value: str) -> bool:
    """Return whether the username looks like an email address."""
    return EMAIL_RE.fullmatch(value) is not None


def is_phone_number(value: str) -> bool:
    """Return whether the username looks like a phone number."""
    return 11 <= len(value) <= 18 and value.isascii()


def _coerce_nonempty_string(value: Any) -> str | None:
    """Convert a JSON value to a stripped string when possible."""
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _parse_json_response(response: httpx.Response) -> dict[str, Any]:
    """Parse a response as a JSON object when possible."""
    try:
        parsed_payload = response.json()
    except ValueError:
        parsed_payload = {}

    if isinstance(parsed_payload, dict):
        return parsed_payload

    return {}


class PikPakClient:
    """Minimal synchronous client for the PikPak endpoints used by the CLI."""

    def __init__(
        self,
        session: AuthSession,
        *,
        password: str,
        captcha_handler: CaptchaChallengeHandler | None = None,
        http_client: httpx.Client | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self.session = session
        self.password = password
        self._captcha_handler = captcha_handler
        self._owns_http_client = http_client is None
        self._http_client = http_client or httpx.Client(
            timeout=timeout,
            follow_redirects=True,
        )
        self._captcha_token = ""

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        """Close the owned HTTP client."""
        if self._owns_http_client:
            self._http_client.close()

    def init(self) -> None:
        """Initialize auth state by preferring refresh over a fresh login."""
        if self.session.refresh_token:
            self.refresh_access_token()
            return

        self.login()

    def login(self) -> None:
        """Authenticate with username/password and persist fresh tokens."""
        signin_url = f"{USER_BASE_URL}/v1/auth/signin"

        if not self.session.username or not self.password:
            raise AuthError("username and password are required for login")

        if not self._captcha_token:
            self._refresh_captcha_token_for_login(get_action("POST", signin_url))

        try:
            response = self._send_json(
                "POST",
                signin_url,
                params={"client_id": DEFAULT_CLIENT_ID},
                json_body={
                    "captcha_token": self._captcha_token,
                    "client_id": DEFAULT_CLIENT_ID,
                    "client_secret": DEFAULT_CLIENT_SECRET,
                    "username": self.session.username,
                    "password": self.password,
                },
                include_auth=False,
                include_captcha=True,
            )
        except ApiError as exc:
            raise AuthError(str(exc)) from exc

        self._update_session_tokens(response, require_refresh_token=True)

    def refresh_access_token(self) -> None:
        """Refresh the current access token, falling back to login if needed."""
        if not self.session.refresh_token:
            raise AuthError("no refresh token is available")

        try:
            response = self._send_json(
                "POST",
                f"{USER_BASE_URL}/v1/auth/token",
                params={"client_id": DEFAULT_CLIENT_ID},
                json_body={
                    "client_id": DEFAULT_CLIENT_ID,
                    "client_secret": DEFAULT_CLIENT_SECRET,
                    "grant_type": "refresh_token",
                    "refresh_token": self.session.refresh_token,
                },
                include_auth=False,
                user_agent="",
            )
        except ApiError as exc:
            if is_refresh_token_invalid_error(exc):
                self.session.refresh_token = ""
                self.login()
                return

            raise AuthError(str(exc)) from exc

        self._update_session_tokens(response, require_refresh_token=True)

    def get_share(self, target: ShareTarget) -> dict[str, Any]:
        """Fetch share metadata and the root share detail payload."""
        share_url = f"{API_BASE_URL}/drive/v1/share"
        detail_url = f"{API_BASE_URL}/drive/v1/share/detail"

        try:
            self._refresh_captcha_token_after_login(get_action("GET", share_url))
            share_response = self._request_api(
                "GET",
                share_url,
                params={
                    "share_id": target.share_id,
                    "pass_code": "",
                    "thumbnail_size": "SIZE_LARGE",
                    "limit": "100",
                },
            )

            pass_code_token = str(share_response.get("pass_code_token", "")).strip()
            if not pass_code_token:
                raise ShareError("share response is missing pass_code_token")

            self._refresh_captcha_token_after_login(get_action("GET", detail_url))
            detail_response = self._request_api(
                "GET",
                detail_url,
                params={
                    "parent_id": "",
                    "share_id": target.share_id,
                    "thumbnail_size": "SIZE_LARGE",
                    "with_audit": "true",
                    "limit": "100",
                    "filters": json.dumps(
                        {
                            "phase": {"eq": "PHASE_TYPE_COMPLETE"},
                            "trashed": {"eq": False},
                        }
                    ),
                    "page_token": "",
                    "pass_code_token": pass_code_token,
                },
            )
        except AuthError:
            raise
        except ShareError:
            raise
        except RuntimeError as exc:
            raise ShareError(str(exc)) from exc

        detail_response["pass_code_token"] = pass_code_token
        return detail_response

    def save_shared_items(
        self,
        share_id: str,
        pass_code_token: str,
        file_ids: list[str],
    ) -> str:
        """Save shared items into the current account."""
        restore_url = f"{API_BASE_URL}/drive/v1/share/restore"

        try:
            self._refresh_captcha_token_after_login(get_action("POST", restore_url))
            response = self._request_api(
                "POST",
                restore_url,
                json_body={
                    "share_id": share_id,
                    "pass_code_token": pass_code_token,
                    "file_ids": file_ids,
                    "parent_id": DEFAULT_PARENT_ID,
                },
            )
        except AuthError:
            raise
        except RuntimeError as exc:
            raise ShareError(str(exc)) from exc

        restored_root_id = self._extract_restored_root_id(response)
        if restored_root_id is None:
            raise ShareError("restore response did not contain a restored root id")

        return restored_root_id

    def get_node_payload(self, node_id: str) -> dict[str, Any]:
        """Fetch raw metadata for a single drive node."""
        file_url = f"{API_BASE_URL}/drive/v1/files/{node_id}"

        try:
            self._refresh_captcha_token_after_login(get_action("GET", file_url))
            return self._request_api("GET", file_url)
        except AuthError:
            raise
        except RuntimeError as exc:
            raise ResolveError(str(exc)) from exc

    def get_node(self, node_id: str) -> DriveNode:
        """Fetch parsed metadata for a single drive node."""
        response = self.get_node_payload(node_id)
        node = self._extract_drive_node(response)
        if node is None:
            raise ResolveError("drive metadata did not contain node information")
        return node

    def list_folder_children(self, parent_id: str) -> list[DriveNode]:
        """List all direct children of a drive folder."""
        list_url = f"{API_BASE_URL}/drive/v1/files"
        page_token = ""
        children: list[DriveNode] = []

        while True:
            try:
                self._refresh_captcha_token_after_login(get_action("GET", list_url))
                response = self._request_api(
                    "GET",
                    list_url,
                    params={
                        "parent_id": parent_id,
                        "thumbnail_size": "SIZE_LARGE",
                        "with_audit": "true",
                        "limit": "100",
                        "filters": json.dumps(
                            {
                                "phase": {"eq": "PHASE_TYPE_COMPLETE"},
                                "trashed": {"eq": False},
                            }
                        ),
                        "page_token": page_token,
                    },
                )
            except AuthError:
                raise
            except RuntimeError as exc:
                raise ResolveError(str(exc)) from exc

            children.extend(self._extract_drive_node_list(response.get("files")))

            next_page_token = _coerce_nonempty_string(response.get("next_page_token"))
            if next_page_token is None:
                break
            page_token = next_page_token

        return children

    def get_direct_url(self, file_id: str) -> str:
        """Fetch a direct URL for a saved file."""
        response = self.get_node_payload(file_id)
        direct_url = self._extract_direct_url(response)
        if direct_url is None:
            raise ResolveError("direct URL was not present in the file metadata")
        return direct_url

    def delete_node(self, node_id: str) -> None:
        """Permanently delete a restored drive node from the account."""
        delete_url = f"{API_BASE_URL}/drive/v1/files:batchDelete"

        try:
            self._refresh_captcha_token_after_login(get_action("POST", delete_url))
            self._request_api(
                "POST",
                delete_url,
                json_body={"ids": [node_id]},
            )
        except AuthError:
            raise
        except RuntimeError as exc:
            raise CleanupError(str(exc), remote_node_id=node_id) from exc

    def _request_api(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, str] | None = None,
        json_body: dict[str, Any] | None = None,
        retry_auth: bool = True,
        retry_captcha: bool = True,
    ) -> dict[str, Any]:
        """Send an authenticated drive request with automatic retry for auth issues."""
        if not self.session.access_token:
            raise AuthError("session does not contain an access token")

        try:
            return self._send_json(
                method,
                url,
                params=params,
                json_body=json_body,
                include_auth=True,
                include_captcha=True,
            )
        except ApiError as exc:
            if retry_auth and is_auth_api_error(exc):
                self.refresh_access_token()
                return self._request_api(
                    method,
                    url,
                    params=params,
                    json_body=json_body,
                    retry_auth=False,
                    retry_captcha=retry_captcha,
                )

            if retry_captcha and is_captcha_api_error(exc):
                self._refresh_captcha_token_after_login(get_action(method, url))
                return self._request_api(
                    method,
                    url,
                    params=params,
                    json_body=json_body,
                    retry_auth=retry_auth,
                    retry_captcha=False,
                )

            if is_auth_api_error(exc):
                raise AuthError("access token is invalid or expired") from exc

            if exc.code in {ERROR_CODE_TOO_MANY_REQUESTS, str(ERROR_CODE_TOO_MANY_REQUESTS)}:
                raise RuntimeError(f"rate limited: {exc}") from exc

            raise RuntimeError(str(exc)) from exc

    def _refresh_captcha_token_for_login(self, action: str) -> None:
        """Request a captcha token for username/password login."""
        meta_key = "username"

        if is_email(self.session.username):
            meta_key = "email"
        elif is_phone_number(self.session.username):
            meta_key = "phone_number"

        self._refresh_captcha_token(
            action,
            {meta_key: self.session.username},
            include_auth=False,
        )

    def _refresh_captcha_token_after_login(self, action: str) -> None:
        """Request a captcha token for authenticated drive requests."""
        if not self.session.user_id:
            raise AuthError("session does not contain a user id")

        timestamp, sign = build_captcha_sign(self.session.device_id)
        self._refresh_captcha_token(
            action,
            {
                "client_version": DEFAULT_CLIENT_VERSION,
                "package_name": DEFAULT_PACKAGE_NAME,
                "user_id": self.session.user_id,
                "timestamp": timestamp,
                "captcha_sign": sign,
            },
            include_auth=True,
        )

    def _refresh_captcha_token(
        self,
        action: str,
        meta: dict[str, str],
        *,
        include_auth: bool,
    ) -> None:
        """Request a captcha token from PikPak shield init."""
        payload = {
            "client_id": DEFAULT_CLIENT_ID,
            "action": action,
            "device_id": self.session.device_id,
            "meta": meta,
            "redirect_uri": CAPTCHA_REDIRECT_URI,
            "captcha_token": self._captcha_token,
        }

        try:
            response = self._send_json(
                "POST",
                f"{USER_BASE_URL}/v1/shield/captcha/init",
                params={"client_id": DEFAULT_CLIENT_ID},
                json_body=payload,
                include_auth=include_auth,
                include_captcha=False,
            )
        except ApiError as exc:
            raise AuthError(str(exc)) from exc

        verification_url = _coerce_nonempty_string(response.get("url"))
        if verification_url is not None:
            if self._captcha_handler is None:
                raise AuthError(f"captcha verification required: {verification_url}")

            verified_token = _coerce_nonempty_string(
                self._captcha_handler(verification_url)
            )
            if verified_token is None:
                raise AuthError("captcha verification did not provide a captcha_token")

            self._captcha_token = verified_token
            return

        captcha_token = _coerce_nonempty_string(response.get("captcha_token"))
        if captcha_token is None:
            raise AuthError("captcha init did not return captcha_token")

        self._captcha_token = captcha_token

    def _update_session_tokens(
        self,
        payload: dict[str, Any],
        *,
        require_refresh_token: bool,
    ) -> None:
        """Update the persisted session from an auth response."""
        access_token = _coerce_nonempty_string(payload.get("access_token"))
        refresh_token = _coerce_nonempty_string(payload.get("refresh_token"))
        user_id = _coerce_nonempty_string(payload.get("sub"))

        if access_token is None:
            raise AuthError("auth response did not contain access_token")

        if require_refresh_token and refresh_token is None:
            raise AuthError("auth response did not contain refresh_token")

        self.session.access_token = access_token

        if refresh_token is not None:
            self.session.refresh_token = refresh_token

        if user_id is not None:
            self.session.user_id = user_id

    def _send_json(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, str] | None = None,
        json_body: dict[str, Any] | None = None,
        include_auth: bool,
        include_captcha: bool = False,
        user_agent: str | None = None,
    ) -> dict[str, Any]:
        """Send a JSON request and raise a structured internal API error when needed."""
        headers = self._build_headers(
            include_auth=include_auth,
            include_captcha=include_captcha,
            user_agent=user_agent,
        )

        try:
            response = self._http_client.request(
                method=method,
                url=url,
                params=params,
                json=json_body,
                headers=headers,
            )
        except httpx.HTTPError as exc:
            raise ApiError(f"http request failed: {exc}") from exc

        payload = _parse_json_response(response)
        error_code = payload.get("error_code")
        error_message = self._extract_error_message(payload)

        if response.status_code in {401, 403}:
            raise ApiError(
                error_message or "access token is invalid or expired",
                code=error_code,
                status_code=response.status_code,
            )

        if error_code not in {None, 0, "0"}:
            raise ApiError(
                error_message or f"PikPak API error {error_code}",
                code=error_code,
                status_code=response.status_code,
            )

        if response.is_error:
            raise ApiError(
                error_message or f"unexpected status code: {response.status_code}",
                code=error_code,
                status_code=response.status_code,
            )

        return payload

    def _build_headers(
        self,
        *,
        include_auth: bool,
        include_captcha: bool,
        user_agent: str | None,
    ) -> dict[str, str]:
        """Build common request headers for PikPak endpoints."""
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": DEFAULT_USER_AGENT if user_agent is None else user_agent,
            "X-Client-ID": DEFAULT_CLIENT_ID,
            "X-Device-ID": self.session.device_id,
        }

        if include_auth:
            if not self.session.access_token:
                raise AuthError("session does not contain an access token")
            headers["Authorization"] = f"Bearer {self.session.access_token}"

        if include_captcha and self._captcha_token:
            headers["X-Captcha-Token"] = self._captcha_token

        return headers

    @staticmethod
    def _extract_error_message(payload: dict[str, Any]) -> str | None:
        """Extract a user-readable API error message when present."""
        error_value = payload.get("error")
        description_value = payload.get("error_description")
        message_value = payload.get("message")

        if isinstance(description_value, str) and description_value.strip():
            return description_value.strip()

        if isinstance(error_value, str) and error_value.strip():
            return error_value.strip()

        if isinstance(message_value, str) and message_value.strip():
            return message_value.strip()

        return None

    @staticmethod
    def _extract_restored_root_id(payload: dict[str, Any]) -> str | None:
        """Parse the restore response into a restored root node id."""
        return _coerce_nonempty_string(payload.get("file_id")) or _coerce_nonempty_string(
            payload.get("id")
        )

    @staticmethod
    def _extract_drive_node(payload: dict[str, Any]) -> DriveNode | None:
        """Parse one drive payload object into the local drive-node model."""
        node_id = _coerce_nonempty_string(payload.get("id"))
        name = _coerce_nonempty_string(payload.get("name"))
        if node_id is None or name is None:
            return None

        return DriveNode(
            node_id=node_id,
            name=name,
            kind=_coerce_nonempty_string(payload.get("kind")),
        )

    @classmethod
    def _extract_drive_node_list(cls, value: Any) -> list[DriveNode]:
        """Parse a list of drive payload objects."""
        if not isinstance(value, list):
            return []

        nodes: list[DriveNode] = []
        for item in value:
            if not isinstance(item, dict):
                continue
            node = cls._extract_drive_node(item)
            if node is not None:
                nodes.append(node)

        return nodes

    @staticmethod
    def _extract_direct_url(payload: dict[str, Any]) -> str | None:
        """Extract the best available direct URL from file metadata."""
        web_content_link = payload.get("web_content_link")
        if isinstance(web_content_link, str) and web_content_link.strip():
            return web_content_link.strip()

        medias_value = payload.get("medias")
        if isinstance(medias_value, list):
            for media in medias_value:
                if not isinstance(media, dict):
                    continue

                link = media.get("link")
                if isinstance(link, dict):
                    url = link.get("url")
                    if isinstance(url, str) and url.strip():
                        return url.strip()

                redirect_link = media.get("redirect_link")
                if isinstance(redirect_link, str) and redirect_link.strip():
                    return redirect_link.strip()

        return None
