"""Share URL parsing and share-response extraction helpers."""

import re
from typing import Any
from urllib.parse import urlparse

from config import ALLOWED_SHARE_HOSTS
from models import DriveNode, ShareError, ShareSelection, ShareTarget

SHARE_PATH_RE = re.compile(r"^/s/([^/]+)(?:/([^/]+))?/?$")


def parse_share_url(share_url: str) -> ShareTarget:
    """Parse and validate a PikPak share URL."""
    parsed = urlparse(share_url)

    if parsed.scheme not in {"http", "https"}:
        raise ShareError("share URL must use http or https")

    host = parsed.netloc.lower()
    if host not in ALLOWED_SHARE_HOSTS:
        raise ShareError(f"unsupported share host: {host}")

    match = SHARE_PATH_RE.fullmatch(parsed.path)
    if match is None:
        raise ShareError("share URL must look like '/s/<share_id>'")

    share_id, file_id = match.groups()

    return ShareTarget(
        share_id=share_id,
        file_id=file_id,
    )


def extract_share_selection(
    payload: dict[str, Any],
    target: ShareTarget,
) -> ShareSelection:
    """Extract the restorable share selection from a share response."""
    pass_code_token = payload.get("pass_code_token")
    if not isinstance(pass_code_token, str) or not pass_code_token.strip():
        raise ShareError("share response is missing pass_code_token")

    file_info = _extract_drive_node(payload.get("file_info"))
    listed_nodes = _extract_drive_node_list(payload.get("files"))
    fallback_node = _extract_drive_node(payload.get("file"))
    candidates = _deduplicate_nodes([*listed_nodes, file_info, fallback_node])

    if target.file_id is not None:
        matched_node = next(
            (node for node in candidates if node.node_id == target.file_id),
            None,
        )
        if matched_node is None:
            raise ShareError("share did not resolve to the requested file")
        return ShareSelection(
            pass_code_token=pass_code_token.strip(),
            restore_ids=[matched_node.node_id],
            root_name=matched_node.name,
            root_kind=matched_node.kind,
        )

    if file_info is not None:
        return ShareSelection(
            pass_code_token=pass_code_token.strip(),
            restore_ids=[file_info.node_id],
            root_name=file_info.name,
            root_kind=file_info.kind,
        )

    if listed_nodes:
        root_name = listed_nodes[0].name if len(listed_nodes) == 1 else None
        root_kind = listed_nodes[0].kind if len(listed_nodes) == 1 else None
        return ShareSelection(
            pass_code_token=pass_code_token.strip(),
            restore_ids=[node.node_id for node in listed_nodes],
            root_name=root_name,
            root_kind=root_kind,
        )

    if fallback_node is not None:
        return ShareSelection(
            pass_code_token=pass_code_token.strip(),
            restore_ids=[fallback_node.node_id],
            root_name=fallback_node.name,
            root_kind=fallback_node.kind,
        )

    raise ShareError("share did not resolve to restorable files")


def _extract_drive_node(value: Any) -> DriveNode | None:
    """Parse one share payload node into the local drive-node model."""
    if not isinstance(value, dict):
        return None

    node_id = str(value.get("id", "")).strip()
    name = str(value.get("name", "")).strip()
    kind = str(value.get("kind", "")).strip() or None
    if not node_id or not name:
        return None

    return DriveNode(
        node_id=node_id,
        name=name,
        kind=kind,
    )


def _extract_drive_node_list(value: Any) -> list[DriveNode]:
    """Parse a list of share payload nodes into drive nodes."""
    if not isinstance(value, list):
        return []

    nodes: list[DriveNode] = []
    for item in value:
        node = _extract_drive_node(item)
        if node is not None:
            nodes.append(node)

    return nodes


def _deduplicate_nodes(nodes: list[DriveNode | None]) -> list[DriveNode]:
    """Keep the first occurrence of each node id from a share payload."""
    unique_nodes: dict[str, DriveNode] = {}

    for node in nodes:
        if node is None or node.node_id in unique_nodes:
            continue
        unique_nodes[node.node_id] = node

    return list(unique_nodes.values())
