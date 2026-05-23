"""Shared data models and domain-specific exception types."""

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

CaptchaChallengeHandler = Callable[[str], str]


class PikPakError(Exception):
    """Base exception for user-facing PikPak workflow failures."""

    stage = "pikpak"

    def __init__(self, message: str, *, remote_node_id: str | None = None) -> None:
        super().__init__(message)
        self.remote_node_id = remote_node_id


class AuthError(PikPakError):
    """Authentication or session-management failure."""

    stage = "auth"


class ShareError(PikPakError):
    """Share metadata or restore failure."""

    stage = "share"


class ResolveError(PikPakError):
    """Direct-url resolution failure."""

    stage = "resolve"


class CleanupError(PikPakError):
    """Remote cleanup failure after the main workflow finished."""

    stage = "cleanup"


@dataclass(slots=True)
class AuthSession:
    """Persisted auth state for username/password login plus token refresh."""

    username: str
    auth_file: Path
    device_id: str
    access_token: str = ""
    refresh_token: str = ""
    user_id: str | None = None
    updated_at: str | None = None


@dataclass(slots=True)
class ShareTarget:
    """Parsed share-url target, optionally narrowed to a specific shared node."""

    share_id: str
    file_id: str | None = None


@dataclass(slots=True)
class DriveNode:
    """Minimal drive node metadata used across restore, traversal, and URL resolution."""

    node_id: str
    name: str
    kind: str | None = None


@dataclass(slots=True)
class ShareSelection:
    """The share items we want PikPak to restore into the current account."""

    pass_code_token: str
    restore_ids: list[str]
    root_name: str | None = None
    root_kind: str | None = None


@dataclass(slots=True)
class ResolvedUrl:
    """One direct URL resolved from the restored root tree."""

    relative_path: Path
    direct_url: str = ""


@dataclass(slots=True)
class WorkflowOptions:
    """User-provided CLI options for the share URL-resolution workflow."""

    share_url: str
    username: str
    password: str
    auth_file: Path
    delete: bool = True
    captcha_handler: CaptchaChallengeHandler | None = None


@dataclass(slots=True)
class WorkflowResult:
    """The final workflow result returned to the CLI entrypoint."""

    entries: list[ResolvedUrl]
    warnings: list[str] = field(default_factory=list)
