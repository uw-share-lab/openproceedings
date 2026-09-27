"""The ~80k-corpus benchmark report (spec 03 §Performance budgets; spec 07 §E; task-031). Run from
`backend/`, on a quiet machine (other load inflates the timings):

    uv run python -m tests.bench.report_80k

It generates the synthetic corpus at 80,000 records with abstracts of realistic length (120-250 words; the
same generator as the 5k differential corpus, so anyone can reproduce it), builds the index, and writes
`docs/results/<date>-bench.md`: build time, size and peak memory; p95 of a 50-hit search and of `match_ids`
with exclusion accounting for every Trust-Evals protocol string; the widest expansion under the cap and one
past it; and the position-verified cases spec 03 exempts (stopword NEAR, wildcard phrases), timed cold.
A report, not a gate: regenerate it with this command, never edit it by hand.
"""

from __future__ import annotations

import contextlib
import os
import platform
import resource
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
SIZE = 80_000
ROUNDS = 40  # cold rounds (match_ids + exclusions): each clears the verified-clause cache
WARM_ROUNDS = 200  # warm searches are cheap, and a p95 over fewer swings with one slow round
VERIFIED = [
    "the NEAR/5 the",
    '"the*" NEAR/5 model',
    '"of the" NEAR/3 model*',
    '"a model*"',
    '"large language model$"',
    "trust NEAR/0 trust",
]


def p95(times: list[float]) -> float:
    data = sorted(times)
    return data[min(len(data) - 1, int(0.95 * len(data)))]


def timed(f: object, rounds: int = ROUNDS) -> list[float]:
    out = []
    for _ in range(rounds):
        t = time.perf_counter()
        f()  # type: ignore[operator]
        out.append(time.perf_counter() - t)
    return out


def ms(seconds: float) -> str:
    return f"{seconds * 1000:,.1f} ms"


BUILD = (
    "import sys; from datetime import UTC, datetime; from pathlib import Path; "
    "from openproceedings.engine.index import build_index; "
    "print(build_index(Path(sys.argv[1]), Path(sys.argv[2]), datetime(2026, 9, 26, tzinfo=UTC)).path)"
)


def main() -> None:
    from tests.fixtures.corpus.synthetic_5k import records

    started = time.perf_counter()
    corpus = records(SIZE, (120, 250))
    generated = time.perf_counter() - started
    root = Path(tempfile.mkdtemp(prefix="op-bench-"))
    try:
        _report(corpus, generated, root)
    finally:
        _remove(root)


def _remove(root: Path) -> None:
    """Delete the scratch corpus and index (an index is sealed read-only, so unseal it first)."""
    for folder, _dirs, _files in os.walk(root):
        Path(folder).chmod(0o755)
    shutil.rmtree(root)


def _report(corpus: tuple[Any, ...], generated: float, root: Path) -> None:
    from openproceedings.engine.compile import FIELDS
    from openproceedings.engine.exclusions import excluded
    from openproceedings.engine.protocol import EngineInputError
    from openproceedings.engine.tantivy_engine import TantivyEngine
    from openproceedings.query.ast import Wildcard
    from openproceedings.query.parser import parse

    from tests.bench.test_bench import widest_stem
    from tests.golden.test_trust_evals import STRINGS
    from tests.unit.engine.test_exclusions import BUILT, DedupResult, as_paper, render

    snap = root / "snap"
    snap.mkdir()
    papers = tuple(sorted((as_paper(r) for r in corpus), key=lambda p: p.id))
    for name, data in render(DedupResult(papers, (), ()), [], BUILT).items():
        (snap / name).write_bytes(data)
    t = time.perf_counter()
    # the build in a process of its own, as `op index build` runs it, so its peak memory is its own
    run = subprocess.run(
        [sys.executable, "-c", BUILD, str(snap), str(root / "indexes")], capture_output=True, text=True
    )
    if run.returncode != 0:
        sys.exit(f"the build failed:\n{run.stderr}")
    built = Path(run.stdout.splitlines()[-1])
    build_s = time.perf_counter() - t
    rss = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    peak = rss if sys.platform == "darwin" else rss * 1024  # bytes on macOS, KiB on Linux
    size = sum(f.stat().st_size for f in built.rglob("*") if f.is_file())
    engine = TantivyEngine(built)

    rows = []
    for name in STRINGS:
        result = parse(STRINGS[name], "scholar")
        ast = result.effective_ast
        assert ast is not None

        def exclusion_run(ast: object = ast, result: object = result) -> None:
            engine.verified.clear()
            engine.compiled.clear()  # the compiled query holds verified results too
            engine.expanded.clear()
            excluded(engine, result, len(engine.match_ids(ast)))  # type: ignore[arg-type]

        engine.verified.clear()
        engine.compiled.clear()  # the compiled query holds verified results too
        engine.expanded.clear()
        cold = timed(lambda ast=ast: engine.search(ast, limit=50), rounds=1)[0]  # type: ignore[misc]
        warm = p95(timed(lambda ast=ast: engine.search(ast, limit=50), WARM_ROUNDS))  # type: ignore[misc]
        exclusions = p95(timed(exclusion_run))
        total = engine.search(ast, limit=0).total
        rows.append(f"| {name} | {total:,} | {ms(cold)} | {ms(warm)} | {ms(exclusions)} |")

    stem, n = widest_stem(engine)
    wide = Wildcard(span=(0, 0), stem=stem, op="*")

    def expand_wide() -> None:
        engine.expanded.clear()
        engine.expand(wide)

    past = Wildcard(span=(0, 0), stem="co", op="*")

    def expand_past() -> None:
        engine.expanded.clear()
        with contextlib.suppress(EngineInputError):  # refused: past the cap
            engine.expand(past)

    verified = []
    for q in VERIFIED:
        ast = parse(q).effective_ast
        assert ast is not None
        engine.verified.clear()
        engine.compiled.clear()  # the compiled query holds verified results too
        engine.expanded.clear()
        t = time.perf_counter()
        total = len(engine.match_ids(ast))
        verified.append(f"| `{q}` | {total:,} | {ms(time.perf_counter() - t)} |")

    commit = subprocess.run(
        ["git", "describe", "--always", "--dirty"], cwd=REPO, capture_output=True, text=True
    ).stdout.strip()
    today = datetime.now(UTC).date().isoformat()
    report = f"""# Benchmarks on a synthetic ~80k corpus ({today})

Regenerate with `uv run python -m tests.bench.report_80k` (from `backend/`, on a quiet machine: other load
inflates the timings); never edit by hand. Budgets are
spec 03 §Performance budgets. Position-verified clauses are exempt from the search and `match_ids` budgets
when cold (spec 03), so they are reported, not gated.

- Machine: {platform.platform()}, {platform.machine()}, {os.cpu_count()} CPUs; Python {platform.python_version()},
  tantivy {version("tantivy")}; commit `{commit}`; index `{built.name}`.
- Corpus: `tests/fixtures/corpus/synthetic_5k.records({SIZE}, (120, 250))`, {len(corpus):,} records (generated in
  {generated:.1f} s): the differential corpus's generator with abstracts of 120-250 words.

## Build (budget: under 2 min, under 500 MB)

| Build time | Index size | Peak memory: the largest single process (the build; its ~65 MB workers are not summed) |
|---|---|---|
| {build_s:.1f} s | {size / 1e6:,.0f} MB | {peak / 1e6:,.0f} MB |

## Trust-Evals protocol strings, Scholar mode (budgets: 100 ms, 300 ms)

Cold is the first run after every cache is cleared (verified clauses, expansions, compiled queries); warm is the
p95 of the {WARM_ROUNDS} runs after it, with the caches an engine keeps; the exclusions column is the p95 of
{ROUNDS} runs, each clearing every cache first. `main-2-pop` holds wildcard phrases (`model$`), which take the position-verified path spec 03 exempts, so
its cold numbers are the exception's, not a budget miss (its warm headroom is task-076).

| String | Matches | Search, first 50 hits: cold | Search: p95 warm | `match_ids` + exclusions: p95 cold |
|---|---|---|---|---|
{chr(10).join(rows)}

## Wildcard expansion (budget: 50 ms for up to 200 terms)

| Stem | Terms | p95 |
|---|---|---|
| `{stem}*` | {n} | {ms(p95(timed(expand_wide)))} |
| `co*` (past the cap: refused) | {len({t for f in FIELDS for t, _df in engine.searcher.terms_with_prefix(f, "co")})} distinct | {ms(p95(timed(expand_past)))} |

## Position-verified clauses (the spec 03 exception; one cold run each)

| Query | Matches | `match_ids` |
|---|---|---|
{chr(10).join(verified)}
"""
    out = REPO / "docs" / "results" / f"{today}-bench.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report)
    print(out)


if __name__ == "__main__":
    main()
