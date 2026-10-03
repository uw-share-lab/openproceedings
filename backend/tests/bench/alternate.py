"""Old and new tokenizer, alternated round by round in one process, so load on a shared machine weighs on both
alike (TASK-088; the method of `docs/results/2026-09-27-search-overlap.md`). Run from `backend/`, on an
existing index (never one under `data/` that this writes to: it only reads):

    git show <base>:backend/src/openproceedings/query/normalize.py > <scratch>/old_normalize.py
    uv run python -m tests.bench.alternate search INDEX <scratch>/old_normalize.py [ROUNDS]
    uv run python -m tests.bench.alternate tokenize INDEX <scratch>/old_normalize.py [ROUNDS]
    uv run python -m tests.bench.alternate columns INDEX

- `search`: every Trust-Evals string's `/search` first page (`test_bench.search_endpoint`, the facet memo
  cleared each round), with the highlighter's `tokenize` set to the old or the new one before each round,
  the order flipping every round; the two whole `Search` results are compared with `==` first. Prints wall
  and CPU (process time, every thread) p50 and p95 per tokenizer, in milliseconds.
- `tokenize`: the tokenizer alone over the titles and abstracts of 3,000 records drawn at random (seed 1), and
  over those of them that leave the whole-text ASCII path; median CPU per round.
- `columns`: `report_80k`'s three `/search` columns (first page and a later page as wall p95, the first page's
  CPU per request) with the live code, on an existing index such as the real corpus's.
Prints the 1-minute load average at the start and end of each. A report, not a gate.
"""

from __future__ import annotations

import importlib.util
import os
import random
import statistics
import sys
import time
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

from openproceedings.engine import highlight
from openproceedings.engine.tantivy_engine import TantivyEngine
from openproceedings.query import normalize

from tests.bench.report_80k import ENDPOINT_ROUNDS, cpu_timed, ms, p95, timed
from tests.bench.test_bench import search_endpoint, trust_evals
from tests.golden.test_trust_evals import STRINGS


def old_module(path: str) -> ModuleType:
    """`normalize.py` at the base commit, loaded as a module of its own (its helpers too, not the live ones)."""
    spec = importlib.util.spec_from_file_location("old_normalize", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["old_normalize"] = module  # dataclasses look their module up while it executes
    spec.loader.exec_module(module)
    return module


def pct(xs: list[float], q: float) -> float:
    s = sorted(xs)
    return s[min(len(s) - 1, int(q * len(s)))]


def interleaved(
    rounds: int, fs: dict[str, Callable[[], object]], before: Callable[[str], None] = lambda _: None
) -> tuple[dict[str, list[float]], dict[str, list[float]]]:
    """Wall and CPU times of each of `fs`, one call each per round, the order flipping every round."""
    wall: dict[str, list[float]] = {k: [] for k in fs}
    cpu: dict[str, list[float]] = {k: [] for k in fs}
    names = list(fs)
    for r in range(rounds):
        for name in names if r % 2 == 0 else names[::-1]:
            before(name)
            t, c = time.perf_counter(), time.process_time()
            fs[name]()
            wall[name].append(time.perf_counter() - t)
            cpu[name].append(time.process_time() - c)
    return wall, cpu


def search(engine: TantivyEngine, old: ModuleType, rounds: int) -> None:
    tokenizers = {"old": old.tokenize, "new": normalize.tokenize}

    def use(name: str) -> None:
        highlight.tokenize = tokenizers[name]  # type: ignore[assignment]

    print("| String | Wall p50: old | new | Wall p95: old | new | CPU p50: old | new | CPU p95: old | new |")
    print("|---|---|---|---|---|---|---|---|---|")
    for name in STRINGS:
        parsed = trust_evals(name)
        results = {}
        for which in tokenizers:
            use(which)
            for _ in range(3):  # warm: compiled queries, verified clauses
                search_endpoint(engine, parsed)
            results[which] = search_endpoint(engine, parsed)
        assert results["old"] == results["new"], name
        page = {k: (lambda parsed=parsed: search_endpoint(engine, parsed)) for k in tokenizers}
        wall, cpu = interleaved(rounds, page, use)
        cells = [
            ms(f(d[k]))
            for d in (wall, cpu)
            for f in (statistics.median, lambda x: pct(x, 0.95))
            for k in tokenizers
        ]
        print(f"| {name} | " + " | ".join(cells) + " |", flush=True)
    highlight.tokenize = normalize.tokenize


def tokenize(engine: TantivyEngine, index: Path, old: ModuleType, rounds: int) -> None:
    ids = (index / "ids.txt").read_text().split()
    random.Random(1).shuffle(ids)
    shown = engine.display(ids[:3_000])
    texts = [t for d in shown.values() for t in (d.get("title") or "", d.get("abstract") or "")]
    looped = [t for t in texts if not normalize._plain_ascii(t)]
    assert [[(t.text, t.start, t.end, t.op) for t in old.tokenize(x)] for x in texts] == [
        [(t.text, t.start, t.end, t.op) for t in normalize.tokenize(x)] for x in texts
    ]
    print("| Texts | Count | Old (median CPU) | New | Ratio |")
    print("|---|---|---|---|---|")
    for label, group in (("every text", texts), ("texts off the whole-text ASCII path", looped)):
        fs = {
            "old": lambda group=group: [old.tokenize(t) for t in group],
            "new": lambda group=group: [normalize.tokenize(t) for t in group],
        }
        _wall, cpu = interleaved(rounds, fs)  # type: ignore[arg-type]
        a, b = statistics.median(cpu["old"]), statistics.median(cpu["new"])
        print(f"| {label} | {len(group):,} | {ms(a)} | {ms(b)} | {b / a:.0%} |", flush=True)


def columns(engine: TantivyEngine) -> None:
    print(
        "| String | Matches | first page: p95 wall | a later page: p95 wall | first page: CPU per request |"
    )
    print("|---|---|---|---|---|")
    for name in STRINGS:
        parsed = trust_evals(name)
        search_endpoint(engine, parsed)
        search_endpoint(engine, parsed)
        first = p95(timed(lambda: search_endpoint(engine, parsed), ENDPOINT_ROUNDS))  # noqa: B023
        later = p95(timed(lambda: search_endpoint(engine, parsed, 50, first=False), ENDPOINT_ROUNDS))  # noqa: B023
        cpu = cpu_timed(lambda: search_endpoint(engine, parsed), ENDPOINT_ROUNDS)  # noqa: B023
        total = engine.search(parsed.effective_ast, limit=0).total  # type: ignore[arg-type]
        print(f"| {name} | {total:,} | {ms(first)} | {ms(later)} | {ms(sum(cpu) / len(cpu))} |", flush=True)


def main() -> None:
    mode, index = sys.argv[1], Path(sys.argv[2])
    engine = TantivyEngine(index)
    print(f"load at start: {os.getloadavg()[0]:.1f}", flush=True)
    if mode == "search":
        search(engine, old_module(sys.argv[3]), int(sys.argv[4]) if len(sys.argv) > 4 else 200)
    elif mode == "tokenize":
        tokenize(engine, index, old_module(sys.argv[3]), int(sys.argv[4]) if len(sys.argv) > 4 else 30)
    elif mode == "columns":
        columns(engine)
    else:
        sys.exit(f"unknown mode {mode!r}: search, tokenize or columns")
    print(f"load at end: {os.getloadavg()[0]:.1f}")


if __name__ == "__main__":
    main()
