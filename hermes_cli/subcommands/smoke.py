"""``hermes smoke`` subcommand parser."""

from __future__ import annotations

from typing import Callable


def build_smoke_parser(subparsers, *, cmd_smoke: Callable) -> None:
    """Attach the ``smoke`` subcommand to ``subparsers``."""
    smoke_parser = subparsers.add_parser(
        "smoke",
        help="Run read-only runtime smoke checks",
        description=(
            "Run a compact read-only runtime smoke report. Writes artifacts under /tmp "
            "by default and does not modify config, gateway, cron, or profiles."
        ),
    )
    smoke_parser.add_argument(
        "--profiles",
        default="default,cheap,lab",
        help="Comma-separated profiles for exact-string chat smokes. Default: default,cheap,lab",
    )
    smoke_parser.add_argument("--output-dir", default=None, help="Artifact directory. Default: /tmp/hermes-smoke-<timestamp>")
    smoke_parser.add_argument("--skip-chat", action="store_true", help="Skip model/provider chat smokes")
    smoke_parser.add_argument("--credits", action="store_true", help="Check OpenRouter credits if configured")
    smoke_parser.add_argument("--json", action="store_true", help="Emit JSON")
    smoke_parser.set_defaults(func=cmd_smoke)
