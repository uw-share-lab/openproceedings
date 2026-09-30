"""The `op` command line. Every planned subcommand exists from M1 on; each stub names the task that
implements it (spec 08 §CLI). The CLI and the API call the same functions.

Implemented: `op ingest ris`, `op ingest openreview` (API v2, task-050; API v1, task-051),
`op ingest iclr|neurips|pmlr` (TASK-096, task-052/053), `op snapshot build`, `op snapshot diff` (task-022), `op index build`
(task-023), `op index parity` (task-029), `op search` (ranked, `--ids`, `--explain`, `--engine reference`;
task-024/030), `op export` (task-030), `op serve` (task-034), `op openapi` (task-040) and `op record save` /
`op record replay` (task-083). Results go to stdout; logs go to stderr; a refused operation exits 1 with its
reason, a usage error or a stub exits 2, and `op record replay` exits 3 on a `mismatch` (`EXIT_MISMATCH`).
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import logging
import math
import os
import re
import secrets
import sys
import time
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

from openproceedings import __version__
from openproceedings.logs import FORMATS as LOG_FORMATS
from openproceedings.logs import LEVELS, configure_logging, elapsed_ms
from openproceedings.vocab import bootstrap_only

FORMATS = ("ris", "csv", "bibtex", "jsonl")  # export formats (export.FORMATS; imported lazily there)
SORTS = ("relevance", "year_desc", "year_asc", "title")  # tantivy_engine.SORTS

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from pydantic import ValidationError

    from openproceedings.api.models import ReplayInfo
    from openproceedings.engine.exclusions import Excluded
    from openproceedings.engine.reference import ReferenceEngine
    from openproceedings.engine.tantivy_engine import TantivyEngine
    from openproceedings.eval.coverage_report import RecordCell
    from openproceedings.official_counts import OfficialTable
    from openproceedings.query.parser import ParseResult
    from openproceedings.records import RecordStore, SearchRecord

log = logging.getLogger(__name__)

# subcommand -> (help text, the Backlog task that implements it)
PLANNED: dict[str, tuple[str, str]] = {
    "embed": (
        "build SPECTER2 embeddings for the current index (spec 06; deferred to phase 2, decision-017)",
        "task-058",
    ),
}
# `op eval <report>` reports still to come -> the task that implements them (coverage: TASK-054)
PLANNED_EVALS: dict[str, str] = {"scholar": "task-056", "audit": "task-055", "near-miss": "task-061"}
# `op record replay`'s exit status on a `mismatch` (spec 08 §Error handling): a broken guarantee 4, which a
# script must tell apart from a refusal (1), a usage error (2) and drift (0)
EXIT_MISMATCH = 3
# `op ingest <source>` sources still to come -> the task that implements them
PLANNED_SOURCES: dict[str, str] = {}  # none left: ris, openreview, neurips and pmlr are all implemented
# tasks deferred to phase 2 with the semantic layer (spec 06, decision-017): their stubs say so
DEFERRED_TASKS: frozenset[str] = frozenset({"task-058", "task-061"})
MIN_DELAY = 0.5  # seconds between requests to a proceedings host: never faster (politeness)


def default_data_dir() -> Path:
    """`$OP_DATA_DIR`, else the repository's `data/` (found from this package's location, so the command
    works from any directory), else `./data`."""
    if env := os.environ.get("OP_DATA_DIR"):
        return Path(env)
    for parent in Path(__file__).resolve().parents:
        if (parent / "backend").is_dir() and (parent / "pyproject.toml").is_file():
            return parent / "data"
    return Path("data")


def _stub_status(task: str) -> str:
    """How a stub names its task: planned, or deferred to phase 2 with the semantic layer (decision-017)."""
    return "deferred to phase 2 (decision-017)" if task in DEFERRED_TASKS else f"planned in {task}"


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
        "ingest", help="fetch sources into the cache: ris | iclr | neurips | pmlr | openreview (spec 01)"
    )
    sources = ingest.add_subparsers(dest="source", metavar="<source>", required=True)
    ris = sources.add_parser(
        "ris", help="cache scholarmend outputs (mended.ris + the resolved.json beside it)"
    )
    ris.add_argument("files", nargs="+", type=Path, metavar="mended.ris")
    ris.set_defaults(run=_ingest_ris)
    orv = sources.add_parser(
        "openreview",
        help="crawl OpenReview venue-years into <data-dir>/cache/openreview: API v2 (ICLR 2024+, NeurIPS 2023+, "
        "ICML 2023+) or v1 (ICLR 2013-2023, NeurIPS 2021-2022), picked by year; credentials "
        "OPENREVIEW_USERNAME/OPENREVIEW_PASSWORD from .env",
    )
    orv.add_argument("--venue", required=True, choices=("ICLR", "NeurIPS", "ICML"))
    orv.add_argument("--years", "--year", dest="years", required=True, type=_years, metavar="YYYY[-YYYY]")
    mode = orv.add_mutually_exclusive_group()
    mode.add_argument("--offline", action="store_true", help="replay the cache only; a miss is refused")
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="no network, no writes: report what is cached and what would be fetched",
    )
    mode.add_argument(
        "--refresh", action="store_true", help="fetch every response again (overwrites the cache)"
    )
    orv.set_defaults(run=_ingest_openreview)
    for name, about in (
        ("iclr", "ICLR 2014-2016 accepted-paper archive pages (iclr.cc)"),
        ("neurips", "NeurIPS proceedings years (proceedings.neurips.cc; 2021 adds the D&B host)"),
        ("pmlr", "ICML years from PMLR (the volume in ingest/pmlr_volumes.toml)"),
    ):
        crawl = sources.add_parser(name, help=f"crawl {about} into <data-dir>/cache/{name}")
        crawl.add_argument(
            "--year", dest="years", action="append", required=True, type=_years, metavar="YYYY[-YYYY]",
            help="a year or an inclusive range; repeatable",
        )  # fmt: skip
        crawl.add_argument(
            "--dry-run",
            action="store_true",
            help="read only the index pages; report what a crawl would fetch",
        )
        crawl.add_argument("--offline", action="store_true", help="use the page cache only (no network)")
        crawl.add_argument(
            "--refresh", action="store_true", help="re-fetch the index pages (a newly published year)"
        )
        crawl.add_argument(
            "--delay",
            type=float,
            default=1.0,
            help=f"seconds between requests (default 1, at least {MIN_DELAY})",
        )
        crawl.set_defaults(run=_ingest_crawl)
    for name, task in PLANNED_SOURCES.items():
        _stub(sources.add_parser(name, help=_stub_status(task)), f"ingest {name}", task)

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

    record = sub.add_parser(
        "record", help="save or replay a search record: reproduced | drifted | mismatch (spec 04)"
    )
    record_actions = record.add_subparsers(dest="action", metavar="<action>", required=True)
    rs = record_actions.add_parser(
        "save", help="freeze a search as a search record in <data-dir>/records (what POST /records writes)"
    )
    rs.add_argument("query")
    rs.add_argument("--index", help="`current` (default) or an index_version under <data-dir>/indexes")
    rs.add_argument("--mode", choices=("native", "scholar"), default="native")
    rs.add_argument("--json", action="store_true", help="print the stored record (without its ids) as JSON")
    rs.set_defaults(run=_record_save)
    rr = record_actions.add_parser(
        "replay",
        help="replay a search record (what GET /records/{id} runs); exit 0 reproduced or drifted, "
        f"{EXIT_MISMATCH} mismatch",
    )
    rr.add_argument("record_id", metavar="id")
    rr.add_argument(
        "--index",
        help="the index to replay on when the record's own index_version isn't here: `current` (default) or "
        "an index_version",
    )
    rr.add_argument("--json", action="store_true", help="print GET /records/{id}'s replay block as JSON")
    rr.set_defaults(run=_record_replay)

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
        "--max-verified-clauses",
        type=int,
        default=16,
        help="position-verified clauses one query may have (default 16, a backstop; decision-010); with the rate limit on, times each clause's cost it must fit the smaller bucket",
    )
    serve.add_argument(
        "--max-verification-seconds",
        type=float,
        default=30.0,
        help="wall time one query's position checks may take before a 503 API_BUSY (default 30; decision-010)",
    )
    serve.add_argument(
        "--max-verification-candidates",
        type=int,
        default=300_000,
        help="documents one query's position checks may read (default 300000, the cost bound; decision-010)",
    )
    serve.add_argument(
        "--docs",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="serve Swagger UI at /api/v1/docs (it loads from a CDN); default on for a loopback --host only",
    )
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

    ev = sub.add_parser("eval", help="evaluation reports: coverage | scholar | audit | near-miss (spec 07)")
    reports = ev.add_subparsers(dest="report", required=True, metavar="REPORT")
    cov = reports.add_parser(
        "coverage",
        help="write docs/results/<date>-coverage.md: indexed vs official accepted counts and the M4 gate "
        "(spec 07 §C)",
    )
    cov.add_argument("--index", help="`current` (default) or an index_version under <data-dir>/indexes")
    cov.add_argument(
        "--out", type=Path, help="the report's directory (default the repository's docs/results)"
    )
    cov.add_argument("--date", help="the report's date, YYYY-MM-DD (default today, UTC)")
    cov.add_argument(
        "--check", action="store_true", help="exit 1 when the M4 gate fails or an accepted exception is stale"
    )
    cov.set_defaults(run=_eval_coverage)
    for name, task in PLANNED_EVALS.items():
        _stub(reports.add_parser(name, help=_stub_status(task)), f"eval {name}", task)

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


def _years(text: str) -> list[int]:
    """`2013` or `2013-2024` (inclusive) as years; argparse reports an ArgumentTypeError as a usage error."""
    m = re.fullmatch(r"([0-9]{4})(?:-([0-9]{4}))?", text)
    if m is None:
        raise argparse.ArgumentTypeError(f"not a year or a YYYY-YYYY range: {text!r}")
    lo, hi = int(m.group(1)), int(m.group(2) or m.group(1))
    if hi < lo:
        raise argparse.ArgumentTypeError(f"an empty range: {text!r}")
    return list(range(lo, hi + 1))


def _ingest_openreview(ns: argparse.Namespace) -> int:
    """Each year goes to the API that holds it (`openreview_v1.api_for`): v1 years through their per-year
    adapters, v2 years through the v2 crawler. The whole request is refused before anything is fetched if a
    year is on neither. Reports are printed in year order."""
    from openproceedings.ingest.sources import openreview_v1, openreview_v2
    from openproceedings.ingest.sources.openreview_client import OpenReviewClient, env_credentials

    apis = {y: openreview_v1.api_for(ns.venue, y) for y in ns.years}
    cache = ns.data_dir / "cache"
    offline = ns.offline or ns.dry_run
    creds = None if offline else env_credentials()  # never read for a run that can't fetch
    reports: dict[int, dict[str, Any]] = {}
    if v1_years := [y for y in ns.years if apis[y] == "v1"]:
        v1 = openreview_v1.make_client(cache, credentials=creds, offline=offline, refresh=ns.refresh)
        for r1 in openreview_v1.ingest(v1, cache, ns.venue, v1_years, dry_run=ns.dry_run):
            reports[r1.year] = r1.to_manifest()
    if v2_years := [y for y in ns.years if apis[y] == "v2"]:
        v2 = OpenReviewClient(
            openreview_v2.http_dir(cache), credentials=creds, offline=offline, refresh=ns.refresh
        )
        for r2 in openreview_v2.ingest(v2, cache, ns.venue, v2_years, dry_run=ns.dry_run):
            reports[r2.year] = r2.to_manifest()
    _print([reports[y] for y in sorted(reports)])
    return 0


def _ingest_crawl(ns: argparse.Namespace) -> int:
    from openproceedings.ingest.sources.crawl import ingest_iclr, ingest_neurips, ingest_pmlr

    if not math.isfinite(ns.delay):
        raise _usage("--delay must be finite")
    if ns.delay < MIN_DELAY:
        raise _usage(f"--delay must be at least {MIN_DELAY} seconds (politeness)")
    if ns.dry_run and ns.offline:
        raise _usage("--dry-run and --offline don't combine: a dry run reads the live index pages")
    run = {"iclr": ingest_iclr, "neurips": ingest_neurips, "pmlr": ingest_pmlr}[ns.source]
    years = sorted({y for chunk in ns.years for y in chunk})
    _print(
        run(years, ns.data_dir / "cache", offline=ns.offline, dry_run=ns.dry_run, refresh=ns.refresh,
            min_interval=ns.delay)
    )  # fmt: skip
    return 0


def _snapshot_build(ns: argparse.Namespace) -> int:
    from openproceedings.ingest.snapshot import build

    result = build(ns.cache or ns.data_dir / "cache", ns.out or ns.data_dir / "snapshots")
    _print({"path": str(result.path), "snapshot_hash": result.snapshot_hash, "created": result.created,
            "unexpected_statuses": [u.to_json() for u in result.unexpected_statuses]})  # fmt: skip
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


def _command(ns: argparse.Namespace) -> str:
    """The full command name a log line carries (`record save`, `index build`, `search`)."""
    return " ".join(filter(None, (ns.command, getattr(ns, "source", None), getattr(ns, "action", None))))


def _parsed(ns: argparse.Namespace) -> ParseResult | None:
    """The query's parse, its diagnostics printed to stderr as user output (never logged: they quote the
    query); None when it doesn't parse."""
    from openproceedings.query.parser import parse

    result = parse(ns.query, ns.mode)
    for d in [*result.errors, *result.warnings, *result.translations]:
        print(f"{d.code}: {d.message}", file=sys.stderr)
    if result.effective_ast is None:
        log.debug(
            "cli_refused", extra={"command": _command(ns), "error": "parse"}
        )  # user input: DEBUG at most
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
            "ms": elapsed_ms(started),
        },
    )


def _repo_root() -> Path | None:
    for parent in Path(__file__).resolve().parents:
        if (parent / "backend").is_dir() and (parent / "pyproject.toml").is_file():
            return parent
    return None


def _official_table() -> OfficialTable:
    """The official counts `op eval coverage` gates on (a seam: tests gate on a small table)."""
    from openproceedings.official_counts import OFFICIAL_ACCEPTED

    return OFFICIAL_ACCEPTED


def _eval_coverage(ns: argparse.Namespace) -> int:
    """`op eval coverage` (TASK-054): the dated coverage report, from what `GET /coverage` serves for the index."""
    import hashlib
    from datetime import UTC, date, datetime

    from openproceedings.api.coverage import compute
    from openproceedings.api.state import snapshot_records
    from openproceedings.engine.tantivy_engine import TantivyEngine
    from openproceedings.eval.coverage_report import (
        Meta,
        failing_summary,
        gate,
        load_cause_file,
        load_unresolved,
        missing_decisions,
        render,
        stale_causes,
        stale_exceptions,
        write,
    )  # fmt: skip

    started = time.perf_counter()
    try:
        day = date.fromisoformat(ns.date) if ns.date else datetime.now(UTC).date()
    except ValueError:
        raise _usage(f"--date must be YYYY-MM-DD, not {ns.date!r}") from None
    root = _repo_root()
    if root is None:  # --out moves only the report: the official counts and causes are read from the checkout
        raise _usage(
            "run from a checkout: the report reads docs/results/coverage-sources.md and coverage-causes.toml"
        )
    results = root / "docs" / "results"
    out = ns.out or results
    path = _index_path(ns)
    engine = TantivyEngine(path)
    records = snapshot_records(ns.data_dir, path, engine.index_version)  # verified, as the server loads it
    coverage = compute(engine, records).model_dump(mode="json")
    sources, causes_file = results / "coverage-sources.md", results / "coverage-causes.toml"
    # a malformed causes file is a ValueError: refused before anything is written
    causes, exceptions = load_cause_file(causes_file)
    if missing := missing_decisions(exceptions, root / "backlog" / "decisions"):
        raise ValueError(f"{causes_file}: no decision record for {', '.join(missing)} in backlog/decisions")

    # an exception's paper in the snapshot the index was built from
    def locate(rid: str) -> RecordCell | None:
        r = records.get(rid)
        return None if r is None else (r.venue, r.year, r.track, r.status)

    official = _official_table()
    unresolved = load_unresolved(records.path.parent, records.manifest)  # conflicts.csv, hash-checked
    meta = Meta(
        date=day,
        index_version=engine.index_version,
        sources_sha256=hashlib.sha256(sources.read_bytes()).hexdigest(),
        causes_sha256=hashlib.sha256(causes_file.read_bytes()).hexdigest() if causes_file.is_file() else None,
        command=f"op eval coverage --index {engine.index_version} --date {day.isoformat()}",
    )
    text = render(
        coverage,
        records.manifest,
        meta,
        official=official,
        causes=causes,
        exceptions=exceptions,
        locate=locate,
        unresolved=unresolved,
    )
    written, replaced = write(text, out, day)
    verdict = gate(coverage, official, exceptions, locate)
    stale, stale_ex = stale_causes(causes, verdict), stale_exceptions(exceptions, verdict)
    log.info("coverage_report_written", extra={
        "index_version": engine.index_version, "gated": verdict.gated, "passing": verdict.passing,
        "gaps": verdict.gaps, "unclassified": sum(k not in causes for k, _ in verdict.failing),
        "accepted_exceptions": len(verdict.accepted), "stale_causes": len(stale),
        "stale_exceptions": len(stale_ex), "unresolved": len(unresolved), "replaced": replaced, "ms": elapsed_ms(started),
    })  # fmt: skip
    print(f"wrote {written}", file=sys.stderr)
    state = "PASS" if verdict.passed else "FAIL"
    print(f"M4 gate: {state}: {verdict.passing} of {verdict.gated} gated cells within ±1%, "
          f"{len(verdict.accepted)} owner-accepted exception(s)", file=sys.stderr)  # fmt: skip
    for line in failing_summary(verdict):
        print(f"  {line}", file=sys.stderr)
    for v, y, t in verdict.accepted:  # never silent: each accepted exception is named on every run
        print(f"  {v} {y} {t} (accepted exception, {exceptions[(v, y, t)].decision})", file=sys.stderr)
    for v, y, t in stale:
        print(f"coverage-causes.toml: [{v} {y} {t}] is not failing; remove its note", file=sys.stderr)
    for v, y, t in stale_ex:
        print(
            f"coverage-causes.toml: [{v} {y} {t}.accepted] is not failing; remove the exception",
            file=sys.stderr,
        )
    if ns.check and stale_ex:  # a stale exception fails --check, as a gate failure does
        print(f"--check: {len(stale_ex)} stale accepted exception(s)", file=sys.stderr)
    return 1 if ns.check and (not verdict.passed or stale_ex) else 0


def _search(ns: argparse.Namespace) -> int:
    from openproceedings.engine.tantivy_engine import TantivyEngine
    from openproceedings.search import run

    started = time.perf_counter()
    _utf8_stdout()
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


def _utf8_stdout() -> None:
    with contextlib.suppress(AttributeError, ValueError):  # UTF-8 whatever the locale, as `op export` writes
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]


def _removed_line(removed: int, track: Mapping[str, int], status: Mapping[str, int]) -> str:
    """Those the default filters removed, ineligible (track or status) and unclassified apart (03's
    exclusion accounting; a search's header and a record's summary)."""
    from openproceedings.engine.exclusions import unclassified_total

    ineligible = "; ".join(
        f"{f}: " + (", ".join(f"{v} {n}" for v, n in b.items() if v != "unknown") or "none")
        for f, b in (("track", track), ("status", status))
    )
    unclassified = unclassified_total(track, status)
    return (
        f"removed by default filters {removed}: ineligible {removed - unclassified} ({ineligible}), "
        f"unclassified {unclassified} (track unknown {track['unknown']}, status unknown {status['unknown']})"
    )


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

    from openproceedings.engine.exclusions import identified_total
    from openproceedings.query import QUERY_VERSION
    from openproceedings.query.normalize import TOKENIZER_VERSION

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
    elif bootstrap_only(sources):
        lines.append(
            f"note: bootstrap corpus (sources: {', '.join(sources)}): these counts describe that corpus, "
            "not a database; they are not PRISMA identification numbers (spec 01)"
        )
    lines += [
        f"identified {identified_total(total, gone.total)} (within the query's own limits)",
        _removed_line(gone.total, gone.track, gone.status),
        f"screened (total) {total}",
        f"canonical: {result.canonical}",
        f"identification: {result.identification_query or '(every record)'}",
    ]
    for (stem, op), terms in sorted(engine.expansions(result.effective_ast).items()):  # type: ignore[arg-type]
        listed = list(terms)
        shown = ", ".join(listed[:10]) + (", …; every term with --explain" if len(listed) > 10 else "")
        lines.append(f"expansion: {stem}{op} → {len(listed)} term{'' if len(listed) == 1 else 's'} ({shown})")
    return lines


def _snapshot_of(ns: argparse.Namespace, index: Path) -> dict[str, Any] | None:
    """The manifest of the snapshot an index was built from, by the one rule (`indexed_snapshot`: a plain
    directory name under <data-dir>/snapshots whose manifest names the index's snapshot_hash); None otherwise
    (the header then says the crawl date is unknown)."""
    from openproceedings.ingest.snapshot import SnapshotError, indexed_snapshot

    try:
        manifest = json.loads((index / "manifest.json").read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            return None
        _path, snap = indexed_snapshot(ns.data_dir, manifest)
    except (OSError, ValueError, SnapshotError):
        return None
    return snap


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
    from openproceedings.engine.tantivy_engine import TantivyEngine
    from openproceedings.export import Provenance, check_count, utc_date, write

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
    provenance = Provenance(engine.index_version, result.canonical_hash, utc_date())

    if ns.out is None:  # UTF-8 and untranslated newlines whatever the terminal's locale (spec 04)
        out = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", newline="", write_through=True)
        try:
            n = write(ns.format, documents, provenance, out)
        finally:
            out.detach()  # leave sys.stdout usable
        check_count(n, total)
    else:  # a temporary file beside the target, renamed once complete and counted: never a partial file
        partial = ns.out.with_name(f".{ns.out.name}.{secrets.token_hex(6)}.partial")
        # created 0666 so the kernel applies the umask, as `> file` would; an existing file keeps its mode
        fd = os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
        try:
            if ns.out.exists():
                os.fchmod(fd, ns.out.stat().st_mode & 0o777)
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
                n = write(ns.format, documents, provenance, stream)
            check_count(n, total)
            partial.replace(ns.out)
        finally:
            partial.unlink(missing_ok=True)
    print(f"exported {n} records ({ns.format}) · {provenance.line()}", file=sys.stderr)
    _search_run(ns, started, engine.index_version, result, total)
    return 0


# --- op record save / op record replay (task-083; spec 04 §Search records) --------------------------------
# The same functions as POST /records and GET /records/{id}: `records.freeze` + `RecordStore.insert`, and
# `records.replay`. What the CLI leaves out is the API's serving policy only: the rate limit and save
# ceilings, and the verified-clause cap and candidate ceiling that withhold a replay (decision-010). The
# operator runs these on their own machine, as `op search` runs any query, so a replay is never withheld and
# its `refused` is only ever a canonical that no longer runs. The store's size cap and free-space floor
# (ApiConfig's defaults) apply: they protect the data volume, not the server.
def _selected_index(ns: argparse.Namespace, name: str, hint: str) -> TantivyEngine:
    """The engine of index `name` (`current` or an index_version) under <data-dir>/indexes, by the API's
    selection rule (`api.state.index_path`; never `resolve_snapshot`, never an arbitrary directory): a
    record pins an index_version that a replay must find by name. A directory not named for the index it
    holds is refused too, since a replay could never find it again."""
    from openproceedings.api.state import IndexSelectionError, index_path
    from openproceedings.engine.tantivy_engine import TantivyEngine

    try:
        path = index_path(ns.data_dir, name)
    except IndexSelectionError as e:
        raise _usage(f"{e.args[0]}; {hint}") from None
    engine = TantivyEngine(path)
    if engine.index_version != path.name:
        raise _usage(f"indexes/{path.name} holds index {engine.index_version}, not one named for it; {hint}")
    return engine


def _record_store(data_dir: Path) -> RecordStore:
    """`<data-dir>/records/records.sqlite` with the API's default size cap and free-space floor."""
    from openproceedings.api.config import ApiConfig
    from openproceedings.records import RECORDS_DIR, RecordStore

    limits = ApiConfig.model_fields
    return RecordStore(
        data_dir / RECORDS_DIR,
        max_bytes=limits["records_max_bytes"].default,
        min_free_bytes=limits["records_min_free_bytes"].default,
    )


def _record_lines(record: SearchRecord) -> list[str]:
    """What a methods section quotes from a record (prisma-reporting skill): the versions, when it was
    searched and what the dates of the corpus are, the counts, `ids_hash` and the strings that reproduce it."""
    from openproceedings.engine.exclusions import identified_total

    window = record.crawl_dates.get("*")
    kind = (record.crawl_dates_kind or {}).get("*")
    label = {"scholar_query_dates": "Scholar searches run", "mixed": "crawl and Scholar searches"}.get(
        kind or "", "crawl"
    )
    dates = f"{window.from_[:10]} to {window.to[:10]}" if window is not None else "unknown"
    lines = [
        f"searched {record.searched_at} · index {record.index_version} · tokenizer {record.tokenizer_version} "
        f"· query {record.query_version}",
        f"{label} {dates} · sources {', '.join(record.sources) if record.sources is not None else 'not recorded'}",
    ]
    if record.identification_citable is False:
        lines.append(
            "note: bootstrap corpus: these counts describe that corpus, not a database; they are not PRISMA "
            "identification numbers (spec 01)"
        )
    elif record.identification_citable is None:
        lines.append("note: this record doesn't say whether its counts are PRISMA identification numbers")
    ex = record.excluded
    lines += [
        f"identified {identified_total(record.total, ex.total)} (within the query's own limits)",
        _removed_line(ex.total, ex.track, ex.status),
        f"screened (total) {record.total}",
        f"ids_hash {record.ids_hash}",
        f"canonical: {record.canonical}",
        f"identification: {record.identification_query or '(every record)'}",
    ]
    return lines


def _record_save(ns: argparse.Namespace) -> int:
    from openproceedings.api.records import RECORD_PAGE
    from openproceedings.records import freeze

    started = time.perf_counter()
    _utf8_stdout()
    result = _parsed(ns)  # refused as POST /records refuses it (the parse checks the length cap first)
    if result is None:
        return 1
    engine = _selected_index(
        ns, ns.index or "current", "pass --index current or an index_version under <data-dir>/indexes"
    )
    fields, found = freeze(engine, result, ns.query, ns.data_dir)
    record = _record_store(ns.data_dir).insert(fields, found.ids)
    page = RECORD_PAGE.format(record_id=record.record_id)
    log.info(
        "record_saved",
        extra={
            "record_id": record.record_id,
            "mode": ns.mode,
            "index_version": record.index_version,
            "query_version": record.query_version,
            "canonical_hash": record.canonical_hash,
            "total": record.total,
            "ms": elapsed_ms(started),
        },
    )
    if ns.json:
        _print({**record.model_dump(mode="json", exclude={"ids"}), "page": page})
    else:
        print("\n".join([f"saved record {record.record_id} · page {page}", *_record_lines(record)]))
    withheld = _withheld_by_default(engine, result)
    if withheld is not None:
        print(
            f"note: a default-configured API instance refuses this query ({withheld}: over its limits on slow "
            f"position checks). It would not have saved it, and it withholds this record's replay: `drifted`, "
            f"`refused: {withheld}`, no counts. `op record replay` runs it.",
            file=sys.stderr,
        )
    return 0


def _withheld_by_default(engine: TantivyEngine, result: ParseResult) -> str | None:
    """The code a default-configured API instance withholds this query's replay with (`api.deps.admit_replay`
    under ApiConfig's default `max_verified_clauses` and `max_verification_candidates`), or None: the CLI
    runs every replay, but a record saved here is meant to be replayed through the API too."""
    from openproceedings.api.config import ApiConfig
    from openproceedings.diagnostics import DiagnosticCode
    from openproceedings.engine.compile import verified_clauses
    from openproceedings.search import expanded

    ast = result.effective_ast
    clauses = verified_clauses(ast)
    if ast is None or not clauses:
        return None
    limits = ApiConfig.model_fields
    if len(clauses) > limits["max_verified_clauses"].default:
        return str(DiagnosticCode.API_TOO_MANY_VERIFIED_CLAUSES)
    expanded(engine, ast)  # as `api.deps.verification_candidates`: the search already ran, so within the cap
    if sum(n for _c, _f, n in engine.candidates(ast)) > limits["max_verification_candidates"].default:
        return str(DiagnosticCode.API_QUERY_TOO_COSTLY)
    return None


def _pinned_loader(data_dir: Path) -> Callable[[str], TantivyEngine | None]:
    """`api.state.open_pinned` (the rule `IndexState.pinned` serves, without the server's cache, open slot and
    verification gate), each version opened (and re-hashed) at most once per command."""
    from openproceedings.api.state import open_pinned
    from openproceedings.engine.tantivy_engine import TantivyEngine

    opened: dict[str, TantivyEngine | None] = {}

    def load(version: str) -> TantivyEngine | None:
        if version not in opened:
            opened[version] = open_pinned(data_dir, version, TantivyEngine).engine
        return opened[version]

    return load


def _record_replay(ns: argparse.Namespace) -> int:
    from openproceedings.api.records import replay_info
    from openproceedings.diagnostics import DiagnosticCode, UserInputError
    from openproceedings.engine.compile import verified_clauses
    from openproceedings.query.parser import parse
    from openproceedings.records import replay, valid_record_id

    started = time.perf_counter()
    _utf8_stdout()
    if not valid_record_id(ns.record_id):  # never a path: the id is not repeated back
        raise _usage("a record id is 12 characters from A–Z, a–z, 0–9, `-` and `_`")
    record = _record_store(ns.data_dir).get(ns.record_id)  # a read never creates the store
    if record is None:
        raise UserInputError(
            DiagnosticCode.API_RECORD_NOT_FOUND, "no search record with that id in <data-dir>/records"
        )
    pinned = _pinned_loader(ns.data_dir)
    # the record's own index when it is here (then --index and `current` aren't opened at all), else the
    # one to replay on: a drift report against it
    served = pinned(record.index_version) or _selected_index(
        ns,
        ns.index or "current",
        f"the record's own index {record.index_version} isn't here either: pass --index <index_version> to "
        "replay it on another",
    )
    parsed = parse(record.canonical, "native")  # never `input`: translations that changed can't alter it
    result = replay(record, served, pinned, ns.data_dir, parsed=parsed)  # no `admit`: never withheld here
    ast = parsed.effective_ast
    info = replay_info(result, len(verified_clauses(ast)) if ast is not None else None)
    if ns.json:
        _print(
            {
                "record_id": record.record_id,
                "recorded_index_version": record.index_version,
                **info.model_dump(mode="json"),
            }
        )
    else:
        print("\n".join(_replay_lines(record, info)))
    log.info(
        "record_replayed",
        extra={
            "record_id": record.record_id,
            "status": info.status,
            "index_version": info.index_version,
            "recorded_index_version": record.index_version,
            "canonical_hash": record.canonical_hash,
            "query_version": info.query_version,
            "total": info.total,
            "added_total": info.added_total,
            "removed_total": info.removed_total,
            "refused": str(info.refused) if info.refused is not None else None,
            "ms": elapsed_ms(started),
        },
    )
    return EXIT_MISMATCH if info.status == "mismatch" else 0


def _replay_lines(record: SearchRecord, info: ReplayInfo) -> list[str]:
    """A replay for reading: the status, what was recorded and what ran, each changed input, the diff's
    counts (`+0 / −0` said, not hidden), and "do not cite" on a mismatch."""
    lines = [
        f"record {record.record_id}: {info.status}",
        f"recorded on index {record.index_version} · query {record.query_version} · searched "
        f"{record.searched_at} · total {record.total} · ids_hash {record.ids_hash}",
    ]
    ran = f"replayed on index {info.index_version} · query {info.query_version}"
    if info.refused is not None:
        lines.append(f"{ran} · not run: {info.refused} (nothing was compared)")
    else:
        lines.append(f"{ran} · total {info.total} · ids_hash {info.ids_hash}")
    for c in info.changed:
        recorded, current = (
            v if isinstance(v, str) else json.dumps(v, sort_keys=True) for v in (c.recorded, c.current)
        )
        lines.append(f"changed: {c.input} ({c.kind}) {recorded} → {current}")
    if info.added_total is not None and info.removed_total is not None:
        same = " (membership-identical)" if info.membership_identical else ""
        lines.append(f"added +{info.added_total} · removed −{info.removed_total}{same}")
    if info.status == "mismatch":
        lines.append(
            f"mismatch: do not cite this record (ids match: {info.ids_match}, excluded match: "
            f"{info.excluded_match}); API_REPLAY_MISMATCH is logged for the maintainers"
        )
    return lines


def _serve(ns: argparse.Namespace) -> int:
    import ipaddress

    from pydantic import ValidationError

    from openproceedings.api.config import ApiConfig, RateLimit
    from openproceedings.api.server import serve

    try:
        loopback = ns.host == "localhost" or ipaddress.ip_address(ns.host).is_loopback
    except ValueError:  # a host name
        loopback = False
    if ns.no_rate_limit and not loopback:
        raise _usage(
            "--no-rate-limit is for a local instance only: with a non-loopback --host, anyone who can reach "
            "it could run unbounded exports"
        )
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
            max_verified_clauses=ns.max_verified_clauses,
            max_verification_candidates=ns.max_verification_candidates,
            max_verification_seconds=ns.max_verification_seconds,
            serve_docs=loopback if ns.docs is None else ns.docs,
        )
    except ValidationError as e:  # the operator's own flags: say which and why, as usage
        raise _usage(f"invalid serve options: {serve_errors(e)}") from None
    serve(config, ns.host, ns.port, ns.log_level, ns.log_format)
    return 0


def serve_errors(e: ValidationError) -> str:
    """Each of the operator's bad serve options with the validator's own explanation (never the input, which
    pydantic would quote): `trusted_proxies.0: Value error, trusted proxy 0.0.0.0/0 is wider than /8 …`."""
    return "; ".join(
        f"{'.'.join(str(p) for p in err['loc']) or 'options'}: {err['msg']}"
        for err in e.errors(include_input=False, include_url=False)
    )


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
    from openproceedings.ingest.sources.http import FetchError, SourceError

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
            f"op {name}: not implemented yet — {_stub_status(task)}; see `backlog task view {task}`",
            file=sys.stderr,
        )
        return 2
    name = _command(ns)
    try:
        code: int = ns.run(ns)
    except BrokenPipeError:  # the reader stopped (`op export … | head`): not a failure, and nothing to log
        # so the interpreter's final flush can't fail again (unless there is no real stdout to redirect)
        with contextlib.suppress(OSError):
            os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return 0
    except (
        SnapshotError, IndexBuildError, EngineError, OpenProceedingsError, SourceError, ValueError, OSError,
    ) as e:  # fmt: skip
        from openproceedings.engine.parity import ParityError

        # the level by kind (logging-standards): the user's own input at DEBUG; an internal failure at ERROR
        # with its traceback; a broken guarantee (parity) at ERROR without one, since its traceback would
        # quote corpus tokens; an aborted crawl (a fetch that failed) at ERROR, since a person must re-run it;
        # any other refusal (a snapshot, an index, a file, a volume) at WARNING; the code or reason, never the
        # message (messages may quote input)
        broken = isinstance(e, InternalError | ParityError | FetchError)
        level = (
            logging.DEBUG if isinstance(e, UserInputError) else logging.ERROR if broken else logging.WARNING
        )
        fields: dict[str, object] = {"command": name, "error": type(e).__name__}
        if isinstance(e, OpenProceedingsError):
            fields["code"] = str(e.code)
        if isinstance(e, SourceError | SnapshotError):
            fields["reason"] = e.reason
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
