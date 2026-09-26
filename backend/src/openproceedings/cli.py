"""The `op` command line. Every planned subcommand exists from M1 on; each stub names the task that
implements it (spec 08 §CLI). The CLI and the API call the same functions."""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence

from openproceedings import __version__
from openproceedings.logs import FORMATS, LEVELS, configure_logging

log = logging.getLogger(__name__)

# subcommand -> (help text, the Backlog task that implements it)
PLANNED: dict[str, tuple[str, str]] = {
    "ingest": ("fetch sources: openreview | proceedings | ris (spec 01)", "task-019"),
    "snapshot": ("build or diff immutable corpus snapshots (spec 01)", "task-022"),
    "index": ("build or retire an immutable index (spec 03)", "task-023"),
    "search": ("run a query; --explain, --engine tantivy|reference (spec 02/03)", "task-030"),
    "export": ("export the full matched set: ris | csv | bibtex | jsonl (spec 04)", "task-030"),
    "serve": ("run the HTTP API (spec 04)", "task-034"),
    "record": ("save or replay a search record (spec 04)", "task-037"),
    "openapi": ("print the OpenAPI schema for the frontend codegen (spec 04)", "task-040"),
    "embed": ("build SPECTER2 embeddings for the current index (spec 06)", "task-058"),
    "eval": ("evaluation reports: scholar | coverage | audit | near-miss (spec 07)", "task-054"),
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="op", description="openproceedings command line")
    parser.add_argument("--version", action="version", version=f"op {__version__}")
    parser.add_argument("--log-level", default="INFO", type=str.upper, choices=LEVELS, help="default INFO")
    parser.add_argument(
        "--log-format", default="json", choices=FORMATS, help="json (default) or text for reading locally"
    )
    sub = parser.add_subparsers(dest="command", metavar="<command>")
    for name, (help_text, _task) in PLANNED.items():
        p = sub.add_parser(name, help=help_text, description=help_text)
        p.add_argument("args", nargs=argparse.REMAINDER, help=argparse.SUPPRESS)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    ns = parser.parse_args(argv)
    configure_logging(ns.log_level, ns.log_format)
    if ns.command is None:
        parser.print_help(sys.stderr)
        return 2
    _help, task = PLANNED[ns.command]
    print(
        f"op {ns.command}: not implemented yet — planned in {task} (backlog task view {task})",
        file=sys.stderr,
    )
    return 2


def main_entry() -> None:
    """Console-script entry point."""
    sys.exit(main())
