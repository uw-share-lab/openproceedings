"""The `op` command line. Every planned subcommand exists from M1 on; each stub names the task that
implements it (spec 08 §CLI). The CLI and the API call the same functions.

Implemented: `op ingest ris`, `op snapshot build`, `op snapshot diff` (task-022), `op index build`
(task-023), `op search --explain / --ids` (task-024; ranked output and export are task-030). Results go to stdout as
JSON; logs go to stderr; a refused operation exits 1 with its reason, a usage error or a stub exits 2.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

from openproceedings import __version__
from openproceedings.logs import FORMATS, LEVELS, configure_logging

log = logging.getLogger(__name__)

# subcommand -> (help text, the Backlog task that implements it)
PLANNED: dict[str, tuple[str, str]] = {
    "export": ("export the full matched set: ris | csv | bibtex | jsonl (spec 04)", "task-030"),
    "serve": ("run the HTTP API (spec 04)", "task-034"),
    "record": ("save or replay a search record (spec 04)", "task-037"),
    "openapi": ("print the OpenAPI schema for the frontend codegen (spec 04)", "task-040"),
    "embed": ("build SPECTER2 embeddings for the current index (spec 06)", "task-058"),
    "eval": ("evaluation reports: scholar | coverage | audit | near-miss (spec 07)", "task-054"),
}
# `op ingest <source>` sources still to come -> the task that implements them
PLANNED_SOURCES: dict[str, str] = {"openreview": "task-050", "proceedings": "task-052"}


def default_data_dir() -> Path:
    """`$OP_DATA_DIR`, else the repository's `data/` (found from this package's location, so the command
    works from any directory), else `./data`."""
    if env := os.environ.get("OP_DATA_DIR"):
        return Path(env)
    for parent in Path(__file__).resolve().parents:
        if (parent / "backend").is_dir() and (parent / "pyproject.toml").is_file():
            return parent / "data"
    return Path("data")


def _stub(p: argparse.ArgumentParser, name: str, task: str) -> None:
    p.add_argument("args", nargs=argparse.REMAINDER, help=argparse.SUPPRESS)
    p.set_defaults(stub=(name, task))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="op", description="openproceedings command line")
    parser.add_argument("--version", action="version", version=f"op {__version__}")
    parser.add_argument("--log-level", default="INFO", type=str.upper, choices=LEVELS, help="default INFO")
    parser.add_argument(
        "--log-format", default="json", choices=FORMATS, help="json (default) or text for reading locally"
    )
    parser.add_argument(
        "--data-dir", type=Path, help="default $OP_DATA_DIR, else the repository's data/ (gitignored)"
    )
    sub = parser.add_subparsers(dest="command", metavar="<command>")

    ingest = sub.add_parser(
        "ingest", help="fetch sources into the cache: ris | openreview | proceedings (spec 01)"
    )
    sources = ingest.add_subparsers(dest="source", metavar="<source>", required=True)
    ris = sources.add_parser(
        "ris", help="cache scholarmend outputs (mended.ris + the resolved.json beside it)"
    )
    ris.add_argument("files", nargs="+", type=Path, metavar="mended.ris")
    ris.set_defaults(run=_ingest_ris)
    for name, task in PLANNED_SOURCES.items():
        _stub(sources.add_parser(name, help=f"planned in {task}"), f"ingest {name}", task)

    snapshot = sub.add_parser("snapshot", help="build or diff immutable corpus snapshots (spec 01)")
    actions = snapshot.add_subparsers(dest="action", metavar="<action>", required=True)
    b = actions.add_parser("build", help="import the cache, dedup, write a new immutable snapshot (offline)")
    b.add_argument("--from", dest="cache", type=Path, help="cache directory (default <data-dir>/cache)")
    b.add_argument("--out", type=Path, help="snapshots directory (default <data-dir>/snapshots)")
    b.set_defaults(run=_snapshot_build)
    d = actions.add_parser("diff", help="ids added, removed and changed between two snapshots")
    d.add_argument("a", type=Path)
    d.add_argument("b", type=Path)
    d.set_defaults(run=_snapshot_diff)

    index = sub.add_parser("index", help="build an immutable index from a snapshot (spec 03)")
    index_actions = index.add_subparsers(dest="action", metavar="<action>", required=True)
    ib = index_actions.add_parser(
        "build", help="build data/indexes/<index_version>/ from a snapshot (offline)"
    )
    ib.add_argument(
        "--snapshot", required=True, help="a snapshot directory, its name, or a snapshot_hash prefix"
    )
    ib.add_argument("--out", type=Path, help="indexes directory (default <data-dir>/indexes)")
    ib.set_defaults(run=_index_build)
    ip = index_actions.add_parser(
        "parity", help="check an index holds normalize()'s tokens for every record of its snapshot (local)"
    )
    ip.add_argument("--index", required=True, help="an index name under <data-dir>/indexes, or its directory")
    ip.add_argument("--snapshot", help="its snapshot (default: the one its manifest names)")
    ip.set_defaults(run=_index_parity)
    _stub(index_actions.add_parser("retire", help="planned in task-065"), "index retire", "task-065")

    search = sub.add_parser("search", help="run a query against an index: --explain, --ids (spec 02/03)")
    search.add_argument("query")
    search.add_argument(
        "--index",
        help="an index_version under <data-dir>/indexes (checked first) or an index directory; default current",
    )
    search.add_argument("--mode", choices=("native", "scholar"), default="native")
    what = search.add_mutually_exclusive_group(required=True)
    what.add_argument("--explain", action="store_true", help="print the parse and the compiled query")
    what.add_argument("--ids", action="store_true", help="print the sorted matching ids")
    search.set_defaults(run=_search)

    for name, (help_text, task) in PLANNED.items():
        _stub(sub.add_parser(name, help=help_text, description=help_text), name, task)
    return parser


def _print(value: object) -> None:
    print(json.dumps(value, indent=1, sort_keys=True, ensure_ascii=False))


def _ingest_ris(ns: argparse.Namespace) -> int:
    from openproceedings.ingest.snapshot import ingest_ris

    reports = ingest_ris(ns.files, ns.data_dir / "cache")
    _print([r.to_manifest() for r in reports])
    return 0


def _snapshot_build(ns: argparse.Namespace) -> int:
    from openproceedings.ingest.snapshot import build

    result = build(ns.cache or ns.data_dir / "cache", ns.out or ns.data_dir / "snapshots")
    _print({"path": str(result.path), "snapshot_hash": result.snapshot_hash, "created": result.created})
    return 0


def resolve_snapshot(spec: str, snapshots: Path) -> Path:
    """A snapshot from a path, a directory name under `snapshots`, or a unique snapshot_hash prefix."""
    from openproceedings.ingest.snapshot import SnapshotError

    if Path(spec).is_dir():
        return Path(spec)
    if (snapshots / spec).is_dir():
        return snapshots / spec
    found = []
    for d in sorted(snapshots.glob("*")) if snapshots.is_dir() else []:
        if d.name.startswith("."):
            continue  # a `.tmp-` leftover or the lock file: never a snapshot
        try:
            if json.loads((d / "manifest.json").read_text(encoding="utf-8"))["snapshot_hash"].startswith(
                spec
            ):
                found.append(d)
        except (OSError, ValueError, KeyError, TypeError):
            continue
    if len(found) != 1:
        raise SnapshotError(f"{'no' if not found else 'more than one'} snapshot matches {spec!r}")
    return found[0]


def _index_build(ns: argparse.Namespace) -> int:
    from openproceedings.engine.index import build_index

    snapshot = resolve_snapshot(ns.snapshot, ns.data_dir / "snapshots")
    result = build_index(snapshot, ns.out or ns.data_dir / "indexes")
    _print({"path": str(result.path), "index_version": result.index_version, "created": result.created})
    return 0


def _index_parity(ns: argparse.Namespace) -> int:
    from openproceedings.engine.index import IndexBuildError
    from openproceedings.engine.parity import check_parity

    indexes = ns.data_dir / "indexes"
    path = indexes / ns.index if (indexes / ns.index).exists() else Path(ns.index)
    if not path.is_dir():
        raise IndexBuildError(f"no index at {path}")
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    snapshot = resolve_snapshot(ns.snapshot or manifest["snapshot"], ns.data_dir / "snapshots")
    report = check_parity(path, snapshot)
    _print({"records": report.records, "terms": report.terms, "differences": 0})
    return 0


def _search(ns: argparse.Namespace) -> int:
    from openproceedings.engine.index import IndexBuildError
    from openproceedings.engine.tantivy_engine import TantivyEngine
    from openproceedings.query.parser import parse

    result = parse(ns.query, ns.mode)  # a bad query is reported first, whatever the index
    lines = [f"input: {ns.query}"]
    lines += [f"{d.code}: {d.message}" for d in [*result.errors, *result.warnings]]
    lines += [f"{t.code}: {t.message}" for t in result.translations]
    if result.effective_ast is None:
        log.warning("cli_refused", extra={"command": "search", "error": "parse"})
        print("\n".join(lines), file=sys.stderr)
        return 1
    indexes = ns.data_dir / "indexes"
    name = ns.index or "current"
    # a name under <data-dir>/indexes wins; otherwise --index may be a directory path
    path = indexes / name if (indexes / name).exists() or not Path(name).is_dir() else Path(name)
    if not path.exists():
        raise IndexBuildError(f"no index at {path}; build one with `op index build --snapshot …`")
    engine = TantivyEngine(path)
    if ns.ids:
        print("\n".join(sorted(engine.match_ids(result.effective_ast))))
        return 0
    lines += [f"canonical: {result.canonical}", f"index_version: {engine.index_version}"]
    print("\n".join([*lines, engine.explain(result.effective_ast)]))
    return 0


def _snapshot_diff(ns: argparse.Namespace) -> int:
    from openproceedings.ingest.snapshot import diff

    _print(diff(ns.a, ns.b))
    return 0


def _stub_tail_holds(args: list[str], ns: argparse.Namespace, extra: list[str]) -> bool:
    """A stub takes any future arguments, but only after its own name (`op search --x`, not
    `op --x search` or `op ingest --x openreview`); a real command takes none it doesn't declare."""
    if not hasattr(ns, "stub"):
        return False
    k = -1
    for word in ns.stub[0].split():  # e.g. "ingest openreview": find each word in turn
        k = args.index(word, k + 1)
    return not Counter(extra) - Counter(args[k + 1 :])


def _reason(e: Exception) -> str:
    """A refusal's one-line reason, never record text: our errors name a file and a record index; a
    pydantic error quotes its input, so only its error types are shown; an OS error its kind and path."""
    from pydantic import ValidationError

    if isinstance(e, ValidationError):
        kinds = sorted({str(err["type"]) for err in e.errors(include_input=False)})
        return f"invalid record ({', '.join(kinds)})"
    if isinstance(e, OSError):
        return f"{type(e).__name__}: {e.strerror or e}" + (
            f" ({Path(e.filename).name})" if e.filename else ""
        )
    return str(e)


def main(argv: Sequence[str] | None = None) -> int:
    from openproceedings.engine.index import IndexBuildError
    from openproceedings.engine.protocol import EngineError
    from openproceedings.ingest.snapshot import SnapshotError

    parser = build_parser()
    args = list(sys.argv[1:] if argv is None else argv)
    ns, extra = parser.parse_known_args(args)
    if extra and not _stub_tail_holds(args, ns, extra):
        parser.error(f"unrecognized arguments: {' '.join(extra)}")
    ns.data_dir = ns.data_dir or default_data_dir()
    configure_logging(ns.log_level, ns.log_format)
    if ns.command is None:
        parser.print_help(sys.stderr)
        return 2
    if hasattr(ns, "stub"):
        name, task = ns.stub
        print(
            f"op {name}: not implemented yet — planned in {task} (backlog task view {task})", file=sys.stderr
        )
        return 2
    name = " ".join(filter(None, (ns.command, getattr(ns, "source", None), getattr(ns, "action", None))))
    try:
        code: int = ns.run(ns)
    except (SnapshotError, IndexBuildError, EngineError, ValueError, OSError) as e:
        reason = _reason(e)
        log.warning("cli_refused", extra={"command": name, "error": type(e).__name__})
        print(f"op {name}: {reason}", file=sys.stderr)
        return 1
    return code


def main_entry() -> None:
    """Console-script entry point."""
    sys.exit(main())
