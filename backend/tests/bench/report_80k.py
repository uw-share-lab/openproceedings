"""The ~80k-corpus benchmark report (spec 03 §Performance budgets; spec 07 §E; task-031). Run from the repo
root, on a quiet machine:

    uv run python -m tests.bench.report_80k            (from backend/)

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
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SIZE = 80_000
ROUNDS = 20
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


def main() -> None:
    from openproceedings.engine.exclusions import excluded
    from openproceedings.engine.index import build_index
    from openproceedings.engine.protocol import EngineInputError
    from openproceedings.engine.tantivy_engine import TantivyEngine
    from openproceedings.query.parser import parse

    from tests.bench.test_bench import widest_stem
    from tests.fixtures.corpus.synthetic_5k import records
    from tests.golden.test_trust_evals import STRINGS
    from tests.unit.engine.test_exclusions import BUILT, DedupResult, as_paper, render

    started = time.perf_counter()
    corpus = records(SIZE, (120, 250))
    generated = time.perf_counter() - started
    root = Path(tempfile.mkdtemp(prefix="op-bench-"))
    snap = root / "snap"
    snap.mkdir()
    papers = tuple(sorted((as_paper(r) for r in corpus), key=lambda p: p.id))
    for name, data in render(DedupResult(papers, (), ()), [], BUILT).items():
        (snap / name).write_bytes(data)
    t = time.perf_counter()
    built = build_index(snap, root / "indexes", BUILT)
    build_s = time.perf_counter() - t
    size = sum(f.stat().st_size for f in built.path.rglob("*") if f.is_file())
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1 if sys.platform == "darwin" else 1 / 1024)
    engine = TantivyEngine(built.path)

    rows = []
    for name in STRINGS:
        result = parse(STRINGS[name], "scholar")
        ast = result.effective_ast
        assert ast is not None

        def exclusion_run(ast: object = ast, result: object = result) -> None:
            engine.verified.clear()
            excluded(engine, result, len(engine.match_ids(ast)))  # type: ignore[arg-type]

        engine.verified.clear()
        cold = timed(lambda ast=ast: engine.search(ast, limit=50), rounds=1)[0]  # type: ignore[misc]
        warm = p95(timed(lambda ast=ast: engine.search(ast, limit=50)))  # type: ignore[misc]
        exclusions = p95(timed(exclusion_run))
        total = engine.search(ast, limit=0).total
        rows.append(f"| {name} | {total:,} | {ms(cold)} | {ms(warm)} | {ms(exclusions)} |")

    from openproceedings.query.ast import Wildcard

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
        t = time.perf_counter()
        total = len(engine.match_ids(ast))
        verified.append(f"| `{q}` | {total:,} | {ms(time.perf_counter() - t)} |")

    commit = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], cwd=REPO, capture_output=True, text=True
    ).stdout.strip()
    today = datetime.now(UTC).date().isoformat()
    report = f"""# Benchmarks on a synthetic ~80k corpus ({today})

Regenerate with `uv run python -m tests.bench.report_80k` (from `backend/`); never edit by hand. Budgets are
spec 03 §Performance budgets. Verified clauses are exempt from the `match_ids` budget (spec 03), so they
are reported, not gated.

- Machine: {platform.platform()}, {platform.machine()}, {os.cpu_count()} CPUs; Python {platform.python_version()},
  tantivy {version("tantivy")}; commit `{commit}`; index `{built.index_version}`.
- Corpus: `tests/fixtures/corpus/synthetic_5k.records({SIZE}, (120, 250))`, {len(corpus):,} records (generated in
  {generated:.1f} s): the differential corpus's generator with abstracts of 120-250 words.

## Build (budget: under 2 min, under 500 MB)

| Build time | Index size | Peak memory (this process) |
|---|---|---|
| {build_s:.1f} s | {size / 1e6:,.0f} MB | {peak / 1e6:,.0f} MB |

## Trust-Evals protocol strings, Scholar mode ({ROUNDS} rounds each; budgets: 100 ms, 300 ms)

Cold is the first run after the verified-clause cache is cleared; warm is the p95 of the {ROUNDS} runs after it
(the cache an engine keeps). `main-2-pop` holds wildcard phrases (`model$`), which take the position-verified
path spec 03 exempts, so its cold numbers are the exception's, not a budget miss.

| String | Matches | Search, first 50 hits: cold | Search: p95 warm | `match_ids` + exclusions: p95 cold |
|---|---|---|---|---|
{chr(10).join(rows)}

## Wildcard expansion (budget: 50 ms for up to 200 terms)

| Stem | Terms | p95 |
|---|---|---|
| `{stem}*` | {n} | {ms(p95(timed(expand_wide)))} |
| `co*` (past the cap: refused) | {sum(1 for f in ("title", "abstract") for _ in engine.searcher.terms_with_prefix(f, "co"))} (both fields) | {ms(p95(timed(expand_past)))} |

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
