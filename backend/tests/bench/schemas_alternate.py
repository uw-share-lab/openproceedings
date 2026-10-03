"""Warm searches on a schema-2 index and a schema-3 index of the same snapshot, alternated round by round in one
process (TASK-167), so load on a shared machine weighs on both alike. Run from `backend/`, on two existing
indexes (it only reads them; build the schema-3 one into a scratch directory, never into `data/indexes`):

    uv run python -m tests.bench.schemas_alternate OLD_INDEX NEW_INDEX [ROUNDS]

A verified clause names its ids as a term set on the text `id` in a schema-2 index, and on the indexed `ord`
in a schema-3 one. For every Trust-Evals string each engine searches once cold (verifying its clauses), the
two whole orders are compared with `==` (ids and exact float scores, every sort) and so are the facets and
the exclusion counts, then `search(limit=50)` is timed ROUNDS times on each (200 by default), the order
flipping every round: wall p50, p95 and p99 and CPU (process time) p50 and p99, in milliseconds. Prints the
1-minute load average at the start and end. A report, not a gate.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from openproceedings.engine.exclusions import excluded
from openproceedings.engine.index import verify_index
from openproceedings.engine.tantivy_engine import SORTS, TantivyEngine

from tests.bench.report_80k import ms, quantile
from tests.bench.test_bench import trust_evals
from tests.golden.test_trust_evals import STRINGS


def verify_pair_inputs(old: Path, new: Path) -> None:
    """Refuse a comparison that changes anything besides the schema, using verified manifests."""
    manifests = (verify_index(old), verify_index(new))
    for field in ("snapshot_hash", "tokenizer_version", "ranking_params", "tantivy_version"):
        assert manifests[0][field] == manifests[1][field], f"schema comparison requires identical {field}"


def main() -> None:
    verify_pair_inputs(Path(sys.argv[1]), Path(sys.argv[2]))
    engines = {"schema 2": TantivyEngine(Path(sys.argv[1])), "schema 3": TantivyEngine(Path(sys.argv[2]))}
    rounds = int(sys.argv[3]) if len(sys.argv) > 3 else 200
    old, new = engines.values()
    assert (old.ord_indexed, new.ord_indexed) == (False, True), "pass a schema-2 index, then a schema-3 one"
    assert old.ids == new.ids, "the two indexes must hold the same snapshot"
    print(f"load at start: {os.getloadavg()[0]:.1f}", flush=True)
    print(
        "| String | Matches | Wall p50: schema 2 | 3 | Wall p95: 2 | 3 | Wall p99: 2 | 3 | CPU p50: 2 | 3 "
        "| CPU p99: 2 | 3 |"
    )
    print("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for name in STRINGS:
        parsed = trust_evals(name)
        ast = parsed.effective_ast
        assert ast is not None
        for sort in SORTS:
            assert old.ranked(ast, sort) == new.ranked(ast, sort), (name, sort)
        assert old.facets(ast) == new.facets(ast), name
        total = len(new.match_ids(ast))
        assert excluded(old, parsed, total) == excluded(new, parsed, total), name
        wall: dict[str, list[float]] = {k: [] for k in engines}
        cpu: dict[str, list[float]] = {k: [] for k in engines}
        for r in range(rounds):
            for which in tuple(engines) if r % 2 == 0 else tuple(reversed(engines)):
                t, c = time.perf_counter(), time.process_time()
                engines[which].search(ast, limit=50)
                wall[which].append(time.perf_counter() - t)
                cpu[which].append(time.process_time() - c)
        cells = [
            ms(quantile(d[k], q))
            for d, q in ((wall, 0.5), (wall, 0.95), (wall, 0.99), (cpu, 0.5), (cpu, 0.99))
            for k in engines
        ]
        print(f"| {name} | {total:,} | " + " | ".join(cells) + " |", flush=True)
    print(f"load at end: {os.getloadavg()[0]:.1f}")


if __name__ == "__main__":
    main()
