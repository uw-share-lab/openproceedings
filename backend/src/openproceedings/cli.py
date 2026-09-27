"""The `op` command line. Every planned subcommand exists from M1 on; each stub names the task that
implements it (spec 08 §CLI). The CLI and the API call the same functions.

Implemented: `op ingest ris`, `op snapshot build`, `op snapshot diff` (task-022), `op index build`
(task-023), `op index parity` (task-029), `op search` (ranked, `--ids`, `--explain`, `--engine reference`;
task-024/030), `op export` (task-030), `op serve` (task-034) and `op openapi` (task-040). Results go to stdout; logs go to stderr; a refused operation exits
1 with its reason, a usage error or a stub exits 2.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import logging
import os
import secrets
import sys
import time
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

from openproceedings import __version__
from openproceedings.logs import FORMATS as LOG_FORMATS
from openproceedings.logs import LEVELS, configure_logging

FORMATS = ("ris", "csv", "bibtex", "jsonl")  # export formats (export.FORMATS; imported lazily there)
SORTS = ("relevance", "year_desc", "year_asc", "title")  # tantivy_engine.SORTS

if TYPE_CHECKING:
    from openproceedings.engine.exclusions import Excluded
    from openproceedings.engine.reference import ReferenceEngine
    from openproceedings.engine.tantivy_engine import TantivyEngine
    from openproceedings.query.parser import ParseResult

log = logging.getLogger(__name__)

# subcommand -> (help text, the Backlog task that implements it)
PLANNED: dict[str, tuple[str, str]] = {
    "record": ("save or replay a search record (spec 04)", "task-037"),
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
        "--log-format", default="json", choices=LOG_FORMATS, help="json (default) or text for reading locally"
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

    search = sub.add_parser(
        "search", help="run a query against an index: ranked hits, --ids or --explain (spec 02/03)"
    )
    search.add_argument("query")
    _index_arguments(search)
    search.add_argument(
        "--engine",
        choices=("tantivy", "reference"),
        default="tantivy",
        help="reference: the oracle over the index's snapshot (with --ids only; it has no ranking)",
    )
    search.add_argument("--sort", choices=SORTS, default="relevance")
    search.add_argument("--limit", type=int, default=20, help="ranked hits to print (default 20)")
    what = search.add_mutually_exclusive_group()
    what.add_argument("--explain", action="store_true", help="print the parse and the compiled query")
    what.add_argument("--ids", action="store_true", help="print every matching id, sorted")
    search.set_defaults(run=_search)

    export = sub.add_parser(
        "export", help="export the full matched set: ris | csv | bibtex | jsonl (spec 04)"
    )
    export.add_argument("query")
    _index_arguments(export)
    export.add_argument("--format", choices=FORMATS, required=True)
    export.add_argument("--out", type=Path, help="write to this file (default standard output)")
    export.set_defaults(run=_export)

    serve = sub.add_parser("serve", help="run the HTTP API (spec 04) over <data-dir>/indexes/<index>")
    serve.add_argument("--host", default="127.0.0.1", help="default 127.0.0.1")
    serve.add_argument("--port", type=int, default=8000, help="default 8000")
    serve.add_argument("--index", default="current", help="`current` (default) or an index_version")
    serve.add_argument(
        "--cors-origin", action="append", default=[], metavar="ORIGIN", help="an allowed origin (repeatable)"
    )
    serve.add_argument(
        "--trusted-proxy",
        action="append",
        default=[],
        metavar="ADDRESS",
        help="an address or network whose X-Forwarded-For is believed (repeatable)",
    )
    serve.add_argument("--rate-capacity", type=float, default=60.0, help="token bucket size per client")
    serve.add_argument("--rate-refill", type=float, default=1.0, help="tokens per second per client")
    serve.add_argument("--export-weight", type=float, default=10.0, help="tokens one export costs")
    serve.add_argument("--no-rate-limit", action="store_true", help="turn the rate limit off (local use)")
    serve.add_argument(
        "--log-query-text",
        action="store_true",
        help="let the log formatter keep query-text fields (a local dev instance only); no log line passes one today",
    )
    serve.set_defaults(run=_serve)

    openapi = sub.add_parser(
        "openapi",
        help="print the API's OpenAPI document, sorted and stable (`make openapi` commits it; spec 04)",
    )
    openapi.add_argument("--out", type=Path, help="write to this file (default standard output)")
    openapi.set_defaults(run=_openapi)

    for name, (help_text, task) in PLANNED.items():
        _stub(sub.add_parser(name, help=help_text, description=help_text), name, task)
    return parser


def _index_arguments(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--index",
        help="an index_version under <data-dir>/indexes (checked first) or an index directory; default current",
    )
    p.add_argument("--mode", choices=("native", "scholar"), default="native")


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
    from openproceedings.engine.index import verify_index
    from openproceedings.engine.parity import check_parity

    path = _index_path(ns)
    manifest = verify_index(path)  # before trusting anything the manifest names
    snapshot = resolve_snapshot(ns.snapshot or manifest["snapshot"], ns.data_dir / "snapshots")
    report = check_parity(path, snapshot, manifest=manifest)
    _print({"records": report.records, "terms": report.terms, "phrases": report.phrases, "differences": 0})
    return 0


def _usage(message: str) -> Exception:
    """A refusal of the user's own arguments: a UserInputError, so it logs at DEBUG (logging-standards)."""
    from openproceedings.diagnostics import DiagnosticCode, UserInputError

    return UserInputError(DiagnosticCode.API_BAD_PARAM, message)


def _parsed(ns: argparse.Namespace) -> ParseResult | None:
    """The query's parse, its diagnostics printed to stderr as user output (never logged: they quote the
    query); None when it doesn't parse."""
    from openproceedings.query.parser import parse

    result = parse(ns.query, ns.mode)
    for d in [*result.errors, *result.warnings, *result.translations]:
        print(f"{d.code}: {d.message}", file=sys.stderr)
    if result.effective_ast is None:
        log.debug("cli_refused", extra={"command": ns.command, "error": "parse"})  # user input: DEBUG at most
        return None
    return result


def _index_path(ns: argparse.Namespace) -> Path:
    from openproceedings.engine.index import IndexBuildError

    indexes = ns.data_dir / "indexes"
    name = ns.index or "current"
    # a name under <data-dir>/indexes wins; otherwise --index may be a directory path
    path = indexes / name if (indexes / name).exists() or not Path(name).is_dir() else Path(name)
    if not path.exists():
        if ns.index is None:  # `current` is set when an index is promoted (spec 08 §Deploy), not by a build
            raise _usage(
                f"no index at {path}: pass --index <index_version> (current is set when one is promoted)"
            )
        raise IndexBuildError(f"no index at {path}; build one with `op index build --snapshot …`")
    return path


def _search_run(
    ns: argparse.Namespace, started: float, index_version: str, result: ParseResult, total: int
) -> None:
    """The one INFO line per search or export: the API access line's privacy-safe fields, never the query."""
    log.info(
        "search_run",
        extra={
            "command": ns.command,
            "mode": ns.mode,
            "engine": getattr(ns, "engine", "tantivy"),
            "index_version": index_version,
            "canonical_hash": result.canonical_hash,
            "total": total,
            "ms": round((time.perf_counter() - started) * 1000),
        },
    )


def _search(ns: argparse.Namespace) -> int:
    from openproceedings.engine.tantivy_engine import TantivyEngine
    from openproceedings.search import run

    started = time.perf_counter()
    with contextlib.suppress(AttributeError, ValueError):  # UTF-8 whatever the locale, as `op export` writes
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    result = _parsed(ns)  # a bad query is reported first, whatever the index
    if result is None:
        return 1
    ast = result.effective_ast
    assert ast is not None
    if ns.engine == "reference" and not ns.ids:
        raise _usage("--engine reference needs --ids: the oracle has no ranking and no compiled query")
    if ns.limit < 0:
        raise _usage("--limit must be ≥ 0")
    path = _index_path(ns)
    engine = TantivyEngine(path)
    if ns.ids:
        ids = sorted(
            _reference(ns, path).match_ids(ast) if ns.engine == "reference" else engine.match_ids(ast)
        )
        print("\n".join(ids))
        _search_run(ns, started, engine.index_version, result, len(ids))
        return 0
    if ns.explain:
        lines = [
            f"input: {ns.query}",
            f"canonical: {result.canonical}",
            f"index_version: {engine.index_version}",
        ]
        print("\n".join([*lines, engine.explain(ast)]))
        _search_run(ns, started, engine.index_version, result, engine.page(ast, limit=0)[0])
        return 0
    found = run(engine, result, sort=ns.sort, limit=ns.limit)  # what GET /api/v1/search runs (search.py)
    for line in _report(engine, result, found.total, found.excluded, _snapshot_of(ns, path)):
        print(line)
    for rank, hit in enumerate(found.hits, 1):
        r = hit.record
        print(
            f"{rank:>4}. {hit.score:9.4f}  {hit.id}  {r['venue']} {r['year']}  {' '.join(r['title'].split())}"
        )
    _search_run(ns, started, engine.index_version, result, found.total)
    return 0


def _report(
    engine: TantivyEngine, result: ParseResult, total: int, gone: Excluded, snapshot: dict[str, Any] | None
) -> list[str]:
    """The PRISMA-ready header of a ranked search (prisma-reporting skill): when it was searched and against
    what (the index, its crawl window, the versions); a caution when the index holds only a bootstrap
    corpus, whose counts are not identification numbers (spec 01), or when its snapshot can't be found; the
    records identified within the query's own limits; those the default filters removed, ineligible (track or status) and unclassified apart; the
    screened total; then the strings that reproduce them and every wildcard's expansion, its first 10
    terms and its count (guarantee 6; every term with --explain)."""
    from datetime import UTC, datetime

    from openproceedings.query import QUERY_VERSION
    from openproceedings.query.normalize import TOKENIZER_VERSION

    ineligible = "; ".join(
        f"{f}: " + (", ".join(f"{v} {n}" for v, n in b.items() if v != "unknown") or "none")
        for f, b in (("track", gone.track), ("status", gone.status))
    )
    unclassified = gone.track["unknown"] + gone.status["unknown"]
    searched = datetime.now(UTC).strftime("%Y-%m-%dT%H:%MZ")
    window = (snapshot or {}).get("crawl_window")
    ends = (
        [e for e in (window.get(k) for k in ("from", "to")) if isinstance(e, str) and e]
        if isinstance(window, dict)
        else []
    )
    crawl = (
        "unknown (snapshot not found)"
        if snapshot is None
        else f"{ends[0][:10]} to {ends[1][:10]}"  # every fetch, not only the last (spec 04)
        if len(ends) == 2
        else str(snapshot.get("crawl_date", "unknown"))
    )
    lines = [
        f"searched {searched} · index {engine.index_version} · crawl {crawl} · tokenizer {TOKENIZER_VERSION} "
        f"· query {QUERY_VERSION}"
    ]
    sources = sorted((snapshot or {}).get("sources") or {})
    if snapshot is None:
        lines.append(
            "note: the index's snapshot is not in <data-dir>/snapshots (or its hash differs), so its sources are "
            "unknown, and so is "
            "whether these counts are PRISMA identification numbers (spec 01)"
        )
    elif sources and set(sources) <= BOOTSTRAP_SOURCES:
        lines.append(
            f"note: bootstrap corpus (sources: {', '.join(sources)}): these counts describe that corpus, "
            "not a database; they are not PRISMA identification numbers (spec 01)"
        )
    lines += [
        f"identified {total + gone.total} (within the query's own limits)",
        f"removed by default filters {gone.total}: ineligible {gone.total - unclassified} ({ineligible}), "
        f"unclassified {unclassified} (track unknown {gone.track['unknown']}, status unknown {gone.status['unknown']})",
        f"screened (total) {total}",
        f"canonical: {result.canonical}",
        f"identification: {result.identification_query or '(every record)'}",
    ]
    for (stem, op), terms in sorted(engine.expansions(result.effective_ast).items()):  # type: ignore[arg-type]
        listed = list(terms)
        shown = ", ".join(listed[:10]) + (", …; every term with --explain" if len(listed) > 10 else "")
        lines.append(f"expansion: {stem}{op} → {len(listed)} term{'' if len(listed) == 1 else 's'} ({shown})")
    return lines


BOOTSTRAP_SOURCES = {"ris"}  # an index built only from these holds an earlier search's output, not a database


def _snapshot_of(ns: argparse.Namespace, index: Path) -> dict[str, Any] | None:
    """The manifest of the snapshot an index was built from, if it's in <data-dir>/snapshots and is that
    snapshot (same hash); None otherwise (the header then says the crawl date is unknown)."""
    try:
        manifest = json.loads((index / "manifest.json").read_text(encoding="utf-8"))
        snap = json.loads(
            (ns.data_dir / "snapshots" / manifest["snapshot"] / "manifest.json").read_text(encoding="utf-8")
        )
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return (
        snap
        if isinstance(snap, dict) and snap.get("snapshot_hash") == manifest.get("snapshot_hash")
        else None
    )


def _reference(ns: argparse.Namespace, index: Path) -> ReferenceEngine:
    """The oracle over the snapshot an index was built from."""
    from openproceedings.engine.index import IndexBuildError
    from openproceedings.engine.reference import ReferenceEngine
    from openproceedings.ingest.snapshot import load_records

    # the caller opened a TantivyEngine on `index` just now, which verified every file: not hashed twice
    manifest = json.loads((index / "manifest.json").read_text(encoding="utf-8"))
    snapshot = resolve_snapshot(manifest["snapshot"], ns.data_dir / "snapshots")
    found = json.loads((snapshot / "manifest.json").read_text(encoding="utf-8"))["snapshot_hash"]
    if (
        found != manifest["snapshot_hash"]
    ):  # the same name, other contents: the oracle would answer another corpus
        raise IndexBuildError(
            f"{snapshot.name} isn't the snapshot index {manifest['index_version']} was built from"
        )
    return ReferenceEngine(load_records(snapshot).values())


def _export(ns: argparse.Namespace) -> int:
    from datetime import UTC, datetime

    from openproceedings.diagnostics import DiagnosticCode
    from openproceedings.engine.protocol import EngineInternalError
    from openproceedings.engine.tantivy_engine import TantivyEngine
    from openproceedings.export import Provenance, write

    started = time.perf_counter()
    result = _parsed(ns)
    if result is None:
        return 1
    ast = result.effective_ast
    assert ast is not None and result.canonical_hash is not None
    if ns.out is not None and ns.out.is_dir():
        raise _usage(f"--out {ns.out} is a directory; name a file")
    if ns.out is not None and not ns.out.parent.is_dir():
        raise _usage(f"--out {ns.out}: no directory {ns.out.parent}")
    engine = TantivyEngine(_index_path(ns))
    total, documents = engine.documents(ast)
    provenance = Provenance(engine.index_version, result.canonical_hash, datetime.now(UTC).date().isoformat())

    def checked(n: int) -> None:
        if n != total:
            raise EngineInternalError(DiagnosticCode.API_INTERNAL, f"exported {n} records, but {total} match")

    if ns.out is None:  # UTF-8 and untranslated newlines whatever the terminal's locale (spec 04)
        out = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", newline="", write_through=True)
        try:
            n = write(ns.format, documents, provenance, out)
        finally:
            out.detach()  # leave sys.stdout usable
        checked(n)
    else:  # a temporary file beside the target, renamed once complete and counted: never a partial file
        partial = ns.out.with_name(f".{ns.out.name}.{secrets.token_hex(6)}.partial")
        # created 0666 so the kernel applies the umask, as `> file` would; an existing file keeps its mode
        fd = os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
        try:
            if ns.out.exists():
                os.fchmod(fd, ns.out.stat().st_mode & 0o777)
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
                n = write(ns.format, documents, provenance, stream)
            checked(n)
            partial.replace(ns.out)
        finally:
            partial.unlink(missing_ok=True)
    print(f"exported {n} records ({ns.format}) · {provenance.line()}", file=sys.stderr)
    _search_run(ns, started, engine.index_version, result, total)
    return 0


def _serve(ns: argparse.Namespace) -> int:
    from pydantic import ValidationError

    from openproceedings.api.config import ApiConfig, RateLimit
    from openproceedings.api.server import serve

    try:
        config = ApiConfig(
            data_dir=ns.data_dir,
            index=ns.index,
            rate_limit=RateLimit(
                enabled=not ns.no_rate_limit,
                capacity=ns.rate_capacity,
                refill_per_second=ns.rate_refill,
                export_weight=ns.export_weight,
            ),
            cors_origins=tuple(ns.cors_origin),
            trusted_proxies=tuple(ns.trusted_proxy),
            log_query_text=ns.log_query_text,
        )
    except ValidationError as e:  # the operator's own flags: say which, as usage
        bad = sorted(
            {".".join(str(p) for p in err["loc"]) or "options" for err in e.errors(include_input=False)}
        )
        raise _usage(f"invalid serve options: {', '.join(bad)}") from None
    serve(config, ns.host, ns.port, ns.log_level, ns.log_format)
    return 0


def _openapi(ns: argparse.Namespace) -> int:
    """No index and no data directory are needed: the document comes from the routes and models alone."""
    from openproceedings.api.openapi import render

    text = render()
    if ns.out is None:
        sys.stdout.write(text)
    else:
        ns.out.write_text(text, encoding="utf-8")
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
    from openproceedings.diagnostics import InternalError, OpenProceedingsError, UserInputError
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
    except BrokenPipeError:  # the reader stopped (`op export … | head`): not a failure, and nothing to log
        # so the interpreter's final flush can't fail again (unless there is no real stdout to redirect)
        with contextlib.suppress(OSError):
            os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return 0
    except (SnapshotError, IndexBuildError, EngineError, OpenProceedingsError, ValueError, OSError) as e:
        from openproceedings.engine.parity import ParityError

        # the level by kind (logging-standards): the user's own input at DEBUG; an internal failure at ERROR
        # with its traceback; a broken guarantee (parity) at ERROR without one, since its traceback would
        # quote corpus tokens; any other refusal (a snapshot, an index, a file) at WARNING; the code, never
        # the message (messages may quote input)
        broken = isinstance(e, InternalError | ParityError)
        level = (
            logging.DEBUG if isinstance(e, UserInputError) else logging.ERROR if broken else logging.WARNING
        )
        fields: dict[str, object] = {"command": name, "error": type(e).__name__}
        if isinstance(e, OpenProceedingsError):
            fields["code"] = str(e.code)
        log.log(level, "cli_refused", extra=fields, exc_info=isinstance(e, InternalError))
        print(f"op {name}: {_reason(e)}", file=sys.stderr)
        return 1
    except Exception:  # a bug: one ERROR line with the traceback, and a clean exit status
        log.error("cli_failed", extra={"command": name}, exc_info=True)
        print(f"op {name}: internal error (see the log)", file=sys.stderr)
        return 1
    return code


def main_entry() -> None:
    """Console-script entry point."""
    sys.exit(main())
