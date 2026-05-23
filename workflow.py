"""Top-level orchestration for restore, URL resolution, and cleanup."""

import time
from pathlib import Path

from auth import load_auth_session, save_auth_session
from client import PikPakClient
from models import (
    AuthError,
    CleanupError,
    DriveNode,
    ResolveError,
    ResolvedUrl,
    ShareSelection,
    WorkflowOptions,
    WorkflowResult,
)
from share import extract_share_selection, parse_share_url

KIND_FILE = "drive#file"
KIND_FOLDER = "drive#folder"
RESOLVE_ATTEMPTS = 10
RESOLVE_DELAY_SECONDS = 1.0


def run_workflow(options: WorkflowOptions) -> WorkflowResult:
    """Execute the restore, direct-url resolution, and cleanup workflow."""
    session = load_auth_session(
        options.auth_file,
        options.username,
        options.password,
    )
    target = parse_share_url(options.share_url)
    warnings = _build_warnings(delete=options.delete)

    with PikPakClient(
        session,
        password=options.password,
        captcha_handler=options.captcha_handler,
    ) as client:
        restored_root_id: str | None = None
        entries: list[ResolvedUrl] = []
        primary_error: Exception | None = None
        cleanup_error: CleanupError | None = None
        session_error: AuthError | None = None

        try:
            client.init()
            share_payload = client.get_share(target)
            selection = extract_share_selection(share_payload, target)
            restored_root_id = client.save_shared_items(
                target.share_id,
                selection.pass_code_token,
                selection.restore_ids,
            )
            entries = _resolve_urls(client, restored_root_id, selection)
        except Exception as exc:
            primary_error = exc
        finally:
            try:
                save_auth_session(session)
            except AuthError as exc:
                session_error = exc

            if restored_root_id is not None and options.delete:
                try:
                    client.delete_node(restored_root_id)
                except CleanupError as exc:
                    cleanup_error = exc

        _raise_post_run_errors(
            restored_root_id=restored_root_id,
            primary_error=primary_error,
            session_error=session_error,
            cleanup_error=cleanup_error,
        )

        if not entries:
            raise ResolveError("workflow did not resolve any direct URLs")

        return WorkflowResult(entries=entries, warnings=warnings)


def _build_warnings(*, delete: bool) -> list[str]:
    """Build user-facing workflow warnings."""
    if not delete:
        return []

    return ["direct download links may stop working after the restored node is deleted"]


def _raise_post_run_errors(
    *,
    restored_root_id: str | None,
    primary_error: Exception | None,
    session_error: AuthError | None,
    cleanup_error: CleanupError | None,
) -> None:
    """Raise deferred workflow errors after session persistence and cleanup."""
    if session_error is not None:
        if primary_error is not None:
            raise AuthError(f"{session_error}. original error: {primary_error}") from primary_error
        raise session_error

    if cleanup_error is not None:
        cleanup_message = (
            f"{cleanup_error}. remote_node_id={restored_root_id}"
            if restored_root_id is not None
            else str(cleanup_error)
        )

        if primary_error is not None:
            cleanup_message = f"{cleanup_message}. original error: {primary_error}"

        raise CleanupError(cleanup_message, remote_node_id=restored_root_id) from primary_error

    if primary_error is not None:
        raise primary_error


def _resolve_urls(
    client: PikPakClient,
    restored_root_id: str,
    selection: ShareSelection,
) -> list[ResolvedUrl]:
    """Resolve all direct URLs under the restored root node."""
    last_error: ResolveError | None = None

    for attempt in range(RESOLVE_ATTEMPTS):
        try:
            restored_root = client.get_node(restored_root_id)
            file_nodes = _collect_from_restored_root(client, restored_root, selection)
        except ResolveError as exc:
            last_error = exc
            file_nodes = []

        if file_nodes:
            return [
                ResolvedUrl(
                    relative_path=relative_path,
                    direct_url=client.get_direct_url(file_id),
                )
                for file_id, relative_path in file_nodes
            ]

        if attempt < RESOLVE_ATTEMPTS - 1:
            time.sleep(RESOLVE_DELAY_SECONDS)

    if last_error is not None:
        raise last_error

    raise ResolveError("restored root did not resolve to share files")


def _collect_from_restored_root(
    client: PikPakClient,
    restored_root: DriveNode,
    selection: ShareSelection,
) -> list[tuple[str, Path]]:
    """Collect file ids and relative paths while skipping the synthetic restore container."""
    if restored_root.kind == KIND_FILE:
        return [(restored_root.node_id, Path(restored_root.name))]

    if restored_root.kind != KIND_FOLDER:
        raise ResolveError(f"restored root has unsupported kind: {restored_root.kind!r}")

    children = sorted(client.list_folder_children(restored_root.node_id), key=lambda node: node.name)
    if not children:
        return []

    if selection.root_kind == KIND_FOLDER and len(selection.restore_ids) == 1:
        shared_root = _find_selected_root(children, selection.root_name)
        if shared_root is not None:
            return _collect_files(client, shared_root, Path())

    file_nodes: list[tuple[str, Path]] = []
    for child in children:
        file_nodes.extend(_collect_files(client, child, Path(child.name)))

    return file_nodes


def _find_selected_root(children: list[DriveNode], root_name: str | None) -> DriveNode | None:
    """Find the shared root folder restored under the synthetic container."""
    if root_name is None:
        return children[0] if len(children) == 1 else None

    for child in children:
        if child.name == root_name:
            return child

    return children[0] if len(children) == 1 else None


def _collect_files(
    client: PikPakClient,
    node: DriveNode,
    relative_path: Path,
) -> list[tuple[str, Path]]:
    """Recursively collect file ids and relative paths under a node."""
    if node.kind == KIND_FILE:
        final_relative_path = relative_path if relative_path.parts else Path(node.name)
        return [(node.node_id, final_relative_path)]

    if node.kind != KIND_FOLDER:
        raise ResolveError(f"drive node has unsupported kind: {node.kind!r}")

    file_nodes: list[tuple[str, Path]] = []
    children = sorted(client.list_folder_children(node.node_id), key=lambda child: child.name)

    for child in children:
        file_nodes.extend(_collect_files(client, child, relative_path / child.name))

    return file_nodes
