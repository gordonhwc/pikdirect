"""Tests for share URL parsing and share-selection extraction."""

import pytest

from models import ShareError
from share import extract_share_selection, parse_share_url


def test_parse_share_url_accepts_simple_share() -> None:
    target = parse_share_url("https://mypikpak.com/s/VOpL4RhhnLZWqTB5WCex0_wio2")

    assert target.share_id == "VOpL4RhhnLZWqTB5WCex0_wio2"
    assert target.file_id is None


def test_parse_share_url_rejects_wrong_host() -> None:
    with pytest.raises(ShareError, match="unsupported share host"):
        parse_share_url("https://example.com/s/VOpL4RhhnLZWqTB5WCex0_wio2")


def test_parse_share_url_rejects_missing_share_id() -> None:
    with pytest.raises(ShareError, match="must look like"):
        parse_share_url("https://mypikpak.com/s/")


def test_extract_share_selection_accepts_single_file_share() -> None:
    target = parse_share_url("https://mypikpak.com/s/share-id")

    selection = extract_share_selection(
        {
            "pass_code_token": "pct",
            "files": [
                {
                    "id": "share-file-id",
                    "name": "shared.bin",
                    "kind": "drive#file",
                }
            ],
        },
        target,
    )

    assert selection.pass_code_token == "pct"
    assert selection.restore_ids == ["share-file-id"]
    assert selection.root_name == "shared.bin"
    assert selection.root_kind == "drive#file"


def test_extract_share_selection_accepts_folder_share() -> None:
    target = parse_share_url("https://mypikpak.com/s/share-id")

    selection = extract_share_selection(
        {
            "pass_code_token": "pct",
            "file_info": {
                "id": "shared-folder-id",
                "name": "Episodes",
                "kind": "drive#folder",
            },
        },
        target,
    )

    assert selection.restore_ids == ["shared-folder-id"]
    assert selection.root_name == "Episodes"
    assert selection.root_kind == "drive#folder"


def test_extract_share_selection_resolves_targeted_shared_node() -> None:
    target = parse_share_url("https://mypikpak.com/s/share-id/specific-file-id")

    selection = extract_share_selection(
        {
            "pass_code_token": "pct",
            "files": [
                {
                    "id": "specific-file-id",
                    "name": "episode-01.mkv",
                    "kind": "drive#file",
                },
                {
                    "id": "other-file-id",
                    "name": "episode-02.mkv",
                    "kind": "drive#file",
                },
            ],
        },
        target,
    )

    assert selection.restore_ids == ["specific-file-id"]
    assert selection.root_name == "episode-01.mkv"
    assert selection.root_kind == "drive#file"


def test_extract_share_selection_deduplicates_repeated_payload_nodes() -> None:
    target = parse_share_url("https://mypikpak.com/s/share-id/specific-file-id")

    selection = extract_share_selection(
        {
            "pass_code_token": "pct",
            "file_info": {
                "id": "specific-file-id",
                "name": "episode-01.mkv",
                "kind": "drive#file",
            },
            "files": [
                {
                    "id": "specific-file-id",
                    "name": "episode-01.mkv",
                    "kind": "drive#file",
                }
            ],
        },
        target,
    )

    assert selection.restore_ids == ["specific-file-id"]
