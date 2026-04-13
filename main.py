"""Command-line entrypoint for the pikdirect CLI."""

import argparse
import getpass
import sys
from pathlib import Path

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


def build_workflow_options(args: argparse.Namespace) -> WorkflowOptions:
    """Convert parsed arguments into workflow options."""
    return WorkflowOptions(
        share_url=args.share_url,
        username=args.username.strip(),
        password=resolve_password(args),
        auth_file=args.auth_file.expanduser().resolve(),
        delete=args.delete,
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
