"""Tests for the CLI entrypoint and its URL output formatting."""

import subprocess
import sys
from pathlib import Path

import pytest

import main
from models import AuthError, ResolvedUrl, WorkflowResult


def test_main_uses_default_auth_file_in_current_directory(
    monkeypatch,
    tmp_path,
    capsys,
) -> None:
    monkeypatch.chdir(tmp_path)
    recorded: dict[str, object] = {}

    def fake_run_workflow(options) -> WorkflowResult:
        recorded["auth_file"] = options.auth_file
        recorded["username"] = options.username
        recorded["password"] = options.password
        recorded["delete"] = options.delete
        return WorkflowResult(
            entries=[ResolvedUrl(relative_path=Path("shared.bin"), direct_url="https://download.example/file.bin")]
        )

    monkeypatch.setattr(main, "run_workflow", fake_run_workflow)
    monkeypatch.setattr(main.getpass, "getpass", lambda _prompt: "secret")

    main.main(["https://mypikpak.com/s/share-id", "--username", "alice@example.com"])
    captured = capsys.readouterr()

    assert recorded["auth_file"] == (tmp_path / ".pikdirect-auth.json").resolve()
    assert recorded["username"] == "alice@example.com"
    assert recorded["password"] == "secret"
    assert recorded["delete"] is True
    assert captured.out.strip() == "https://download.example/file.bin"


def test_main_uses_password_flag_without_prompt(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    recorded: dict[str, object] = {}

    def fake_run_workflow(options) -> WorkflowResult:
        recorded["password"] = options.password
        return WorkflowResult(
            entries=[ResolvedUrl(relative_path=Path("shared.bin"), direct_url="https://download.example/file.bin")]
        )

    monkeypatch.setattr(main, "run_workflow", fake_run_workflow)
    monkeypatch.setattr(
        main.getpass,
        "getpass",
        lambda _prompt: (_ for _ in ()).throw(AssertionError("prompt should not be used")),
    )

    main.main(
        [
            "https://mypikpak.com/s/share-id",
            "--username",
            "alice@example.com",
            "--password",
            "secret",
        ]
    )
    captured = capsys.readouterr()

    assert recorded["password"] == "secret"
    assert captured.out.strip() == "https://download.example/file.bin"


def test_extract_captcha_token_from_callback_url() -> None:
    assert (
        main.extract_captcha_token(
            "xlaccsdk01://xbase.cloud/callback?state=harbor&captcha_token=verified-token"
        )
        == "verified-token"
    )


def test_extract_captcha_token_rejects_challenge_url() -> None:
    assert (
        main.extract_captcha_token(
            "https://user.mypikpak.net/captcha/v2/txCaptcha.html?captcha_token=initial-token"
        )
        is None
    )


def test_prompt_for_captcha_challenge_prints_url_and_reads_token(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        main.builtins,
        "input",
        lambda _prompt: "xlaccsdk01://xbase.cloud/callback?captcha_token=verified-token",
    )

    token = main.prompt_for_captcha_challenge("https://captcha.example/challenge")
    captured = capsys.readouterr()

    assert token == "verified-token"
    assert "https://captcha.example/challenge" in captured.err
    assert "filter for xlaccsdk01://" in captured.err


def test_prompt_for_captcha_challenge_requires_verified_token(monkeypatch) -> None:
    monkeypatch.setattr(
        main.builtins,
        "input",
        lambda _prompt: "",
    )

    with pytest.raises(AuthError, match="verified captcha_token"):
        main.prompt_for_captcha_challenge("https://captcha.example/challenge")


def test_main_prints_multiple_resolved_urls(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.chdir(tmp_path)

    def fake_run_workflow(_options) -> WorkflowResult:
        return WorkflowResult(
            entries=[
                ResolvedUrl(
                    relative_path=Path("Season 1").joinpath("Episode 01.mkv"),
                    direct_url="https://download.example/episode-01",
                ),
                ResolvedUrl(
                    relative_path=Path("Season 1").joinpath("Episode 02.mkv"),
                    direct_url="https://download.example/episode-02",
                ),
            ]
        )

    monkeypatch.setattr(main, "run_workflow", fake_run_workflow)

    main.main(
        [
            "https://mypikpak.com/s/share-id",
            "--username",
            "alice@example.com",
            "--password",
            "secret",
            "--no-delete",
        ]
    )
    captured = capsys.readouterr()

    assert captured.out.strip().splitlines() == [
        "Season 1/Episode 01.mkv\thttps://download.example/episode-01",
        "Season 1/Episode 02.mkv\thttps://download.example/episode-02",
    ]


def test_main_script_invocation_shows_help() -> None:
    project_root = Path(__file__).resolve().parent.parent
    result = subprocess.run(
        [sys.executable, "main.py", "--help"],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "--username" in result.stdout
    assert "--delete" in result.stdout
