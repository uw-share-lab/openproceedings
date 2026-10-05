"""What a concept group's counts add to a `/search` (TASK-176; spec 04 §SearchResponse `groups`; spec 07 §E).
Run from `backend/`, on a quiet machine (other load inflates the timings):

    uv run python -m tests.bench.group_counts_report [--index DIR] [OUT]

For each query, `test_bench.search_endpoint`'s work (`search.run` with facets and highlights, a 50-hit page)
with its groups counted at `ApiConfig`'s default bounds and without them, alternated round by round, on the
synthetic 5k fixture as the API serves it and, with `--index`, on a built index directory (the real corpus: a
scratch COPY of `data/indexes/<version>`, never the served one). A first page forgets the facet memo each
round, which the counts' collections share; a later page (offset 50) reads it. Wall time, median and p95 of
ROUNDS rounds, and how each round's groups came back (counted, or why not). Writes
`docs/results/<date>-bench-group-counts.md` (or OUT). A report, not a gate: regenerate it, never edit it.
"""

from __future__ import annotations

import os
import platform
import statistics
import subprocess
import sys
import tempfile
import time
from collections import Counter
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

from openproceedings import search
from openproceedings.engine.tantivy_engine import TantivyEngine
from openproceedings.query.parser import ParseResult, parse

from tests.bench.test_bench import GROUP_FIELDS, GROUPS, TEN_GROUPS
from tests.contract.conftest import attributed, build
from tests.fixtures.corpus.synthetic_5k import records
from tests.unit.test_group_counts import wide_kept_query

REPO = Path(__file__).resolve().parents[3]
ROUNDS = 200
FIXTURE_QUERIES = [
    "(trust OR reliance) AND calibrat* AND model*",
    "trust model NOT (model NEAR/10 model*)",
    TEN_GROUPS,
]
# the real corpus's commonest kind of query: a few concept groups, and the most `/search` counts (ten
# one-word groups of common words)
REAL_QUERIES = [
    "(trust OR reliance) AND calibrat* AND model*",
    '("large language model$" OR LLM*) AND (trust* OR calibrat*) AND (benchmark* OR evaluat*)',
    "trust model NOT (model NEAR/10 model*)",
    "trust model data learning neural network training language agent task",
]


def ms(seconds: float) -> str:
    return f"{seconds * 1000:,.1f} ms"


def p95(times: list[float]) -> float:
    data = sorted(times)
    return data[min(len(data) - 1, int(0.95 * len(data)))]


def load(avg: tuple[float, float, float]) -> str:
    return " / ".join(f"{a:.1f}" for a in avg)


def outcome(found: search.Search) -> str:
    g = found.groups
    assert g is not None
    return f"{len(g.counts)} counted" if g.not_counted is None else str(g.not_counted)


def rows(engine: TantivyEngine, queries: list[str]) -> list[str]:
    out = []
    for q in queries:
        shown = q if len(q) <= 120 else f"{q.split(' NOT (')[0]} NOT (… {q.count('*')} wildcards …)"
        parsed = parse(q)
        assert parsed.effective_ast is not None, q

        def page(parsed: ParseResult, offset: int, first: bool, groups: bool) -> search.Search:
            if first:
                engine.faceted.clear()
            extra = GROUPS if groups else {}
            return search.run(engine, parsed, offset=offset, limit=50, facets=True, highlight=True, **extra)

        for label, offset, first in (("first page", 0, True), ("later page", 50, False)):
            page(
                parsed, offset, first, True
            )  # warm: compiled queries and verified clauses, as a served query's
            without: list[float] = []
            with_: list[float] = []
            seen: Counter[str] = Counter()
            for _ in range(ROUNDS):
                for groups, into in ((False, without), (True, with_)):
                    t = time.perf_counter()
                    found = page(parsed, offset, first, groups)
                    into.append(time.perf_counter() - t)
                    if groups:
                        seen[outcome(found)] += 1
            total = found.total
            how = ", ".join(f"{k} ×{n}" for k, n in seen.most_common())
            out.append(
                f"| `{shown}` | {total:,} | {label} | {ms(statistics.median(without))} | {ms(p95(without))} | "
                f"{ms(statistics.median(with_))} | {ms(p95(with_))} | {how} |"
            )
    return out


def table(engine: TantivyEngine, queries: list[str]) -> str:
    head = (
        "| Query | Matches | Page | Without counts: median | p95 | With counts: median | p95 | Groups, per round |\n"
        "|---|---|---|---|---|---|---|---|"
    )
    return "\n".join([head, *rows(engine, queries)])


def main() -> None:
    args = sys.argv[1:]
    index: Path | None = None
    if args[:1] == ["--index"]:
        index, args = Path(args[1]), args[2:]
    started_load = os.getloadavg()
    machine = (
        subprocess.run(
            ["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True, text=True, check=False
        ).stdout.strip()
        or platform.processor()
    )
    commit = subprocess.run(
        ["git", "describe", "--always", "--dirty"], cwd=REPO, capture_output=True, text=True, check=False
    ).stdout.strip()
    with tempfile.TemporaryDirectory(prefix="op-bench-groups-") as raw:
        root = Path(raw)
        built = build(list(records()), root / "snapshots", "bench", root / "indexes", attributed)
        fixture = TantivyEngine(root / "indexes" / built)
        queries = [*FIXTURE_QUERIES, wide_kept_query(fixture)]
        fixture_table = table(fixture, queries)
    real = ""
    if index is not None:
        engine = TantivyEngine(index)
        real = f"""
## The real corpus: index `{engine.index_version}`, {engine.searcher.num_docs:,} records

{table(engine, REAL_QUERIES)}
"""
    today = datetime.now(UTC).date().isoformat()
    bounds = ", ".join(f"`{field}` {GROUPS[arg]}" for arg, field in GROUP_FIELDS.items())
    report = f"""# What group counts add to a search ({today})

Regenerate with `uv run python -m tests.bench.group_counts_report --index <a copy of an index>` (from
`backend/`, on a quiet machine: other load inflates the timings); never edit by hand. TASK-176; cited by spec
04 §SearchResponse (`groups`, Cost) and spec 07 §E. A cold first page over spec 03's 100 ms p95 with its counts
is spec 03's exception "as measured", which TASK-196 decides, re-measured at a sustained 1-minute load under 5.

- Machine: {machine}, {platform.platform()}, {os.cpu_count()} CPUs; load average {load(started_load)} at the
  start and {load(os.getloadavg())} at the end (1, 5, 15 min); Python {platform.python_version()}, tantivy
  {version("tantivy")}; commit `{commit}`.
- Protocol: `search.run` with facets and highlights, a 50-hit page, as `/search` runs it
  (`tests/bench/test_bench.py::search_endpoint`), with its groups counted at `ApiConfig`'s defaults
  ({bounds}) and without them, alternated within each of {ROUNDS} rounds after one warm-up; wall time (the
  facets and the counts run on worker threads, overlapping the page). A first page forgets the facet memo
  every round, so its counts' collections are made again; a later page (offset 50) reads them from the memo.
  "Groups, per round" is how each round's groups came back: counted, or the `not_counted` reason.

## The synthetic 5k fixture, as the API serves it

The last query is ten one-word groups and one kept `NOT (… every three-letter wildcard under the cap …)`
(`tests/unit/test_group_counts.py::wide_kept_query`): over `max_counted_terms`, so `too_costly` and never
counted.

{fixture_table}
{real}"""
    out = Path(args[0]) if args else REPO / "docs" / "results" / f"{today}-bench-group-counts.md"
    out.write_text(report)
    print(out)


if __name__ == "__main__":
    main()
