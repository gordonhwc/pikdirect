"""Tests for the top-level restore, URL resolution, and cleanup workflow."""

from pathlib import Path
from typing import Self

import pytest

import workflow
from models import (
    AuthError,
    AuthSession,
    CaptchaChallengeHandler,
    CleanupError,
    DriveNode,
    ResolveError,
    WorkflowOptions,
)


class FakeClient:
    """Test double for the PikPak client used by workflow tests."""

    instances: list[Self] = []
    share_payload = {
        "pass_code_token": "pct",
        "files": [
            {
                "id": "share-file-id",
                "name": "shared.bin",
                "kind": "drive#file",
            }
        ],
    }
    restored_root_id = "restored-root"
    node_map: dict[str, DriveNode] = {}
    child_map: dict[str, list[DriveNode]] = {}
    direct_urls: dict[str, str] = {}
    get_share_error: Exception | None = None
    init_error: Exception | None = None
    save_error: Exception | None = None
    node_error: Exception | None = None
    direct_url_error: Exception | None = None
    delete_error: Exception | None = None

    def __init__(
        self,
        session: AuthSession,
        *,
        password: str,
        captcha_handler: CaptchaChallengeHandler | None = None,
    ) -> None:
        self.session = session
        self.password = password
        self.captcha_handler = captcha_handler
        self.deleted_ids: list[str] = []
        self.saved_calls: list[tuple[str, str, list[str]]] = []
        self.direct_url_calls: list[str] = []
        self.init_called = False
        FakeClient.instances.append(self)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def init(self) -> None:
        self.init_called = True
        if self.init_error is not None:
            raise self.init_error

        self.session.access_token = "fresh-access-token"
        self.session.refresh_token = "fresh-refresh-token"
        self.session.user_id = "user-id"

    def get_share(self, _target):
        if self.get_share_error is not None:
            raise self.get_share_error
        return self.share_payload

    def save_shared_items(
        self,
        share_id: str,
        pass_code_token: str,
        file_ids: list[str],
    ) -> str:
        if self.save_error is not None:
            raise self.save_error

        self.saved_calls.append((share_id, pass_code_token, file_ids))
        return self.restored_root_id

    def get_node(self, node_id: str) -> DriveNode:
        if self.node_error is not None:
            raise self.node_error
        return self.node_map[node_id]

    def list_folder_children(self, parent_id: str) -> list[DriveNode]:
        return self.child_map.get(parent_id, [])

    def get_direct_url(self, file_id: str) -> str:
        if self.direct_url_error is not None:
            raise self.direct_url_error

        self.direct_url_calls.append(file_id)
        return self.direct_urls[file_id]

    def delete_node(self, node_id: str) -> None:
        if self.delete_error is not None:
            raise self.delete_error
        self.deleted_ids.append(node_id)


def make_options(tmp_path: Path, **overrides) -> WorkflowOptions:
    """Build default workflow options for tests."""
    defaults = {
        "share_url": "https://mypikpak.com/s/share-id",
        "username": "alice@example.com",
        "password": "secret",
        "auth_file": tmp_path / "auth.json",
        "delete": True,
    }
    defaults.update(overrides)
    return WorkflowOptions(**defaults)


def setup_fake_workflow(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> list[AuthSession]:
    """Install fake collaborators for workflow tests."""
    FakeClient.instances = []
    FakeClient.get_share_error = None
    FakeClient.init_error = None
    FakeClient.save_error = None
    FakeClient.node_error = None
    FakeClient.direct_url_error = None
    FakeClient.delete_error = None
    FakeClient.share_payload = {
        "pass_code_token": "pct",
        "files": [
            {
                "id": "share-file-id",
                "name": "shared.bin",
                "kind": "drive#file",
            }
        ],
    }
    FakeClient.restored_root_id = "restored-root"
    FakeClient.node_map = {
        "restored-root": DriveNode(
            node_id="restored-root",
            name="Pack From Shared",
            kind="drive#folder",
        ),
        "restored-file": DriveNode(
            node_id="restored-file",
            name="shared.bin",
            kind="drive#file",
        ),
    }
    FakeClient.child_map = {
        "restored-root": [
            DriveNode(
                node_id="restored-file",
                name="shared.bin",
                kind="drive#file",
            )
        ]
    }
    FakeClient.direct_urls = {
        "restored-file": "https://download.example/shared.bin",
    }

    recorded_saved_sessions: list[AuthSession] = []

    monkeypatch.setattr(
        workflow,
        "load_auth_session",
        lambda path, username, password: AuthSession(
            username=username,
            access_token="stale-access-token",
            refresh_token="refresh-token",
            device_id="device-id",
            auth_file=path.resolve(),
        ),
    )
    monkeypatch.setattr(workflow, "save_auth_session", recorded_saved_sessions.append)
    monkeypatch.setattr(workflow, "PikPakClient", FakeClient)
    monkeypatch.setattr(workflow, "RESOLVE_DELAY_SECONDS", 0.0)

    return recorded_saved_sessions


def test_run_workflow_resolves_urls_from_restored_folder(monkeypatch, tmp_path) -> None:
    saved_sessions = setup_fake_workflow(monkeypatch, tmp_path)
    options = make_options(tmp_path)

    result = workflow.run_workflow(options)

    assert len(result.entries) == 1
    assert result.entries[0].relative_path == Path("shared.bin")
    assert result.entries[0].direct_url == "https://download.example/shared.bin"
    assert result.warnings == [
        "direct download links may stop working after the restored node is deleted"
    ]
    assert FakeClient.instances[0].init_called is True
    assert FakeClient.instances[0].saved_calls == [
        ("share-id", "pct", ["share-file-id"])
    ]
    assert FakeClient.instances[0].direct_url_calls == ["restored-file"]
    assert FakeClient.instances[0].deleted_ids == ["restored-root"]
    assert len(saved_sessions) == 1
    assert saved_sessions[0].access_token == "fresh-access-token"
    assert saved_sessions[0].refresh_token == "fresh-refresh-token"


def test_run_workflow_passes_captcha_handler_to_client(monkeypatch, tmp_path) -> None:
    setup_fake_workflow(monkeypatch, tmp_path)

    def captcha_handler(_url: str) -> str:
        return "verified-captcha-token"

    options = make_options(tmp_path, captcha_handler=captcha_handler)

    workflow.run_workflow(options)

    assert FakeClient.instances[0].captcha_handler is captcha_handler


def test_run_workflow_keeps_restored_node_when_delete_is_disabled(monkeypatch, tmp_path) -> None:
    setup_fake_workflow(monkeypatch, tmp_path)
    options = make_options(tmp_path, delete=False)

    result = workflow.run_workflow(options)

    assert len(result.entries) == 1
    assert result.warnings == []
    assert FakeClient.instances[0].deleted_ids == []


def test_run_workflow_includes_restored_root_when_cleanup_fails(monkeypatch, tmp_path) -> None:
    setup_fake_workflow(monkeypatch, tmp_path)
    FakeClient.delete_error = CleanupError("delete failed", remote_node_id="restored-root")
    options = make_options(tmp_path)

    with pytest.raises(CleanupError, match="remote_node_id=restored-root"):
        workflow.run_workflow(options)


def test_run_workflow_surfaces_init_error_early(monkeypatch, tmp_path) -> None:
    setup_fake_workflow(monkeypatch, tmp_path)
    FakeClient.init_error = AuthError("invalid username or password")
    options = make_options(tmp_path)

    with pytest.raises(AuthError, match="invalid username or password"):
        workflow.run_workflow(options)

    assert FakeClient.instances[0].init_called is True


def test_run_workflow_surfaces_url_resolution_failure(monkeypatch, tmp_path) -> None:
    setup_fake_workflow(monkeypatch, tmp_path)
    FakeClient.direct_url_error = ResolveError("direct URL missing")
    options = make_options(tmp_path)

    with pytest.raises(ResolveError, match="direct URL missing"):
        workflow.run_workflow(options)

    assert FakeClient.instances[0].deleted_ids == ["restored-root"]


def test_run_workflow_traverses_nested_folder_share(monkeypatch, tmp_path) -> None:
    setup_fake_workflow(monkeypatch, tmp_path)
    FakeClient.share_payload = {
        "pass_code_token": "pct",
        "file_info": {
            "id": "shared-folder-id",
            "name": "Episodes",
            "kind": "drive#folder",
        },
    }
    FakeClient.node_map = {
        "restored-root": DriveNode(
            node_id="restored-root",
            name="Pack From Shared",
            kind="drive#folder",
        ),
        "shared-folder": DriveNode(
            node_id="shared-folder",
            name="Episodes",
            kind="drive#folder",
        ),
        "season-folder": DriveNode(
            node_id="season-folder",
            name="Season 1",
            kind="drive#folder",
        ),
        "episode-file": DriveNode(
            node_id="episode-file",
            name="Episode 01.mkv",
            kind="drive#file",
        ),
    }
    FakeClient.child_map = {
        "restored-root": [
            DriveNode(
                node_id="shared-folder",
                name="Episodes",
                kind="drive#folder",
            )
        ],
        "shared-folder": [
            DriveNode(
                node_id="season-folder",
                name="Season 1",
                kind="drive#folder",
            )
        ],
        "season-folder": [
            DriveNode(
                node_id="episode-file",
                name="Episode 01.mkv",
                kind="drive#file",
            )
        ],
    }
    FakeClient.direct_urls = {
        "episode-file": "https://download.example/Episode%2001.mkv",
    }
    options = make_options(tmp_path)

    result = workflow.run_workflow(options)

    assert len(result.entries) == 1
    assert result.entries[0].relative_path == Path("Season 1").joinpath("Episode 01.mkv")
    assert result.entries[0].direct_url == "https://download.example/Episode%2001.mkv"
