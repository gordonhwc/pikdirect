"""Command-line entrypoint for the pikdirect CLI."""

import argparse
import builtins
import getpass
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from config import DEFAULT_AUTH_FILE_NAME
from models import AuthError, ResolvedUrl, WorkflowOptions
from workflow import run_workflow


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(
        prog="pikdirect",
        description="Resolve direct URLs from a PikPak shared file or folder.",
    )
    parser.add_argument("share_url", help="PikPak share URL")
    parser.add_argument(
        "--username",
        required=True,
        help="PikPak username, email, or phone number",
    )
    parser.add_argument(
        "--password",
        help="PikPak password. Omit this flag to be prompted securely",
    )
    parser.add_argument(
        "--auth-file",
        type=Path,
        default=Path(DEFAULT_AUTH_FILE_NAME),
        help="Path to the JSON auth session file",
    )
    parser.add_argument(
        "--delete",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Delete the temporary restored node after resolving the direct URLs",
    )
    return parser


def resolve_password(args: argparse.Namespace) -> str:
    """Resolve the password from flags or a secure prompt."""
    if args.password is not None:
        return args.password

    try:
        return getpass.getpass("PikPak password: ")
    except EOFError as exc:
        raise AuthError("password was not provided and interactive prompt failed") from exc


def extract_captcha_token(value: str) -> str | None:
    """Extract a captcha token from a pasted callback URL."""
    cleaned_value = value.strip()
    if not cleaned_value:
        return None

    parsed_url = urlparse(cleaned_value)
    if parsed_url.scheme in {"http", "https"} and parsed_url.netloc:
        return None

    query_values = parse_qs(parsed_url.query)
    token_values = query_values.get("captcha_token")
    if not token_values or not token_values[0].strip():
        return None

    return token_values[0].strip()


def prompt_for_captcha_challenge(verification_url: str) -> str:
    """Prompt the user to complete a PikPak captcha challenge."""
    print("Captcha verification required.", file=sys.stderr)
    print(f"Open this URL in a browser:\n{verification_url}", file=sys.stderr)
    print(
        "Before completing verification, open DevTools Network. "
        "After verification, filter for xlaccsdk01://, copy that request URL, "
        "and paste it here.",
        file=sys.stderr,
    )

    try:
        captcha_token = extract_captcha_token(builtins.input("Captcha callback URL: "))
    except EOFError as exc:
        raise AuthError(f"captcha verification required: {verification_url}") from exc

    if captcha_token is None:
        raise AuthError("captcha verification requires a verified captcha_token")

    return captcha_token


def build_workflow_options(args: argparse.Namespace) -> WorkflowOptions:
    """Convert parsed arguments into workflow options."""
    return WorkflowOptions(
        share_url=args.share_url,
        username=args.username.strip(),
        password=resolve_password(args),
        auth_file=args.auth_file.expanduser().resolve(),
        delete=args.delete,
        captcha_handler=prompt_for_captcha_challenge,
    )


def emit_result_lines(entries: list[ResolvedUrl]) -> None:
    """Print resolved direct URLs in a CLI-friendly format."""
    if len(entries) == 1:
        print(entries[0].direct_url)
        return

    for entry in entries:
        print(f"{entry.relative_path}\t{entry.direct_url}")


def main(argv: list[str] | None = None) -> None:
    """Run the CLI."""
    parser = build_parser()
    args = parser.parse_args(argv)
    options = build_workflow_options(args)
    result = run_workflow(options)

    for warning in result.warnings:
        print(f"warning: {warning}", file=sys.stderr)

    emit_result_lines(result.entries)


if __name__ == "__main__":
    main()
