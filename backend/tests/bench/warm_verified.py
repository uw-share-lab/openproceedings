"""Warm searches with a verified clause's old and new id set, alternated round by round in one process (TASK-076),
so load on a shared machine weighs on both alike. Run from `backend/`, on an existing index (it only reads it):

    uv run python -m tests.bench.warm_verified INDEX [ROUNDS]

Two engines over the index: one compiles as before TASK-076 (a verified clause always names the ids that hold
it), one as now (it names the candidates that don't, when they are fewer). For every Trust-Evals string each
engine searches once cold (verifying its clauses), the two whole orders are compared with `==` (ids and exact
float scores), then `search(limit=50)` is timed ROUNDS times on each (200 by default), the order flipping
every round: wall p50, p95 and p99, and CPU (process time) p50 and p99, in milliseconds (a wall
spike with no CPU spike is the machine, not the search). Prints the 1-minute load
average at the start and end. A report, not a gate.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from openproceedings.engine.tantivy_engine import TantivyEngine

from tests.bench.report_80k import ms, quantile
from tests.bench.test_bench import trust_evals
from tests.golden.test_trust_evals import STRINGS


def main() -> None:
    index = Path(sys.argv[1])
    rounds = int(sys.argv[2]) if len(sys.argv) > 2 else 200
    engines = {"old": TantivyEngine(index), "new": TantivyEngine(index)}
    engines["old"].ids_of = None  # type: ignore[assignment,method-assign]  # compile's `members`: the old form
    print(f"load at start: {os.getloadavg()[0]:.1f}", flush=True)
    print(
        "| String | Matches | Wall p50: old | new | Wall p95: old | new | Wall p99: old | new | CPU p50: old | new | CPU p99: old | new |"
    )
    print("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for name in STRINGS:
        ast = trust_evals(name).effective_ast
        assert ast is not None
        assert engines["old"].ranked(ast) == engines["new"].ranked(ast), name
        wall: dict[str, list[float]] = {"old": [], "new": []}
        cpu: dict[str, list[float]] = {"old": [], "new": []}
        for r in range(rounds):
            for which in ("old", "new") if r % 2 == 0 else ("new", "old"):
                t, c = time.perf_counter(), time.process_time()
                engines[which].search(ast, limit=50)
                wall[which].append(time.perf_counter() - t)
                cpu[which].append(time.process_time() - c)
        total = engines["new"].search(ast, limit=0).total
        cells = [
            ms(quantile(d[k], q))
            for d, q in ((wall, 0.5), (wall, 0.95), (wall, 0.99), (cpu, 0.5), (cpu, 0.99))
            for k in wall
        ]
        print(f"| {name} | {total:,} | " + " | ".join(cells) + " |", flush=True)
    print(f"load at end: {os.getloadavg()[0]:.1f}")


if __name__ == "__main__":
    main()
