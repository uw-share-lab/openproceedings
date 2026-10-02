"""Exclusion accounting through the facet combos and through the default fields only, alternated round by round
in one process (TASK-166), so load on a shared machine weighs on both alike. Run from `backend/`, on an
existing index (it only reads it), or on the synthetic 5k fixture with `5k`:

    uv run python -m tests.bench.exclusions_alternate INDEX|5k [ROUNDS]

For every Trust-Evals string (and, with `5k`, test_bench's broad query) the two paths' `Excluded` are compared
with `==` first; then `match_ids` + `excluded` is timed ROUNDS times each (200 by default), the order flipping
every round, warm (the facet memo holds each path's combos, as on a later page or a repeated save) and cold
(the facet memo cleared before each call; the compiled and verified memos stay warm, so the aggregation is what
is timed). `facets` is the combos over every facet field, as a search with facets reads them (and as every
search did before TASK-166); `defaults` aggregates only track and status, what a search without facets now
runs. Wall p50 and p95 and CPU (process time) p50, in milliseconds, and the number of combos each path reads.
Prints the 1-minute load average at the start and end. A report, not a gate.
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from functools import partial
from pathlib import Path

from openproceedings.engine.exclusions import ORDER, Excluded, excluded
from openproceedings.engine.tantivy_engine import COMBO, TantivyEngine
from openproceedings.query.ast import Node
from openproceedings.query.parser import ParseResult, parse

from tests.bench.report_80k import ms, quantile
from tests.bench.test_bench import BROAD, trust_evals
from tests.golden.test_trust_evals import STRINGS

PATHS = {"facets": COMBO, "defaults": ORDER}


def engine_of(arg: str) -> TantivyEngine:
    if arg != "5k":
        return TantivyEngine(Path(arg))
    from tests.fixtures.corpus.synthetic_5k import records
    from tests.unit.engine.test_exclusions import tantivy_of

    return tantivy_of(list(records()), Path(tempfile.mkdtemp(prefix="op-excl-")))


def accounting(engine: TantivyEngine, parsed: ParseResult, ast: Node, over: tuple[str, ...]) -> Excluded:
    """`match_ids` + exclusion accounting with the combos aggregated over `over`."""
    return excluded(engine, parsed, len(engine.match_ids(ast)), facets=partial(engine.facets, over=over))


def main() -> None:
    engine = engine_of(sys.argv[1])
    rounds = int(sys.argv[2]) if len(sys.argv) > 2 else 200
    queries: dict[str, ParseResult] = {name: trust_evals(name) for name in STRINGS}
    if sys.argv[1] == "5k":
        queries["broad (test_bench)"] = parse(BROAD)
    print(f"load at start: {os.getloadavg()[0]:.1f}", flush=True)
    print(
        "| String | Combos: facets | defaults | Warm p50: facets | defaults | Warm p95: facets | defaults "
        "| Warm CPU p50: facets | defaults | Cold p50: facets | defaults | Cold p95: facets | defaults |"
    )
    print("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for name, parsed in queries.items():
        ast = parsed.effective_ast
        assert ast is not None
        runs = {k: partial(accounting, engine, parsed, ast, over) for k, over in PATHS.items()}
        engine.faceted.clear()
        assert runs["facets"]() == runs["defaults"](), name
        held = {key.split("\x00")[0]: len(v) for key, v in engine.faceted.items()}  # one base per path here
        combos = {k: held.get(",".join(over), 0) for k, over in PATHS.items()}
        cells: list[str] = [str(combos["facets"]), str(combos["defaults"])]
        warm: dict[str, list[float]] = {k: [] for k in PATHS}
        cpu: dict[str, list[float]] = {k: [] for k in PATHS}
        cold: dict[str, list[float]] = {k: [] for k in PATHS}
        for r in range(rounds):
            for which in tuple(PATHS) if r % 2 == 0 else tuple(reversed(PATHS)):
                t, c = time.perf_counter(), time.process_time()
                runs[which]()
                warm[which].append(time.perf_counter() - t)
                cpu[which].append(time.process_time() - c)
        for r in range(rounds):
            for which in tuple(PATHS) if r % 2 == 0 else tuple(reversed(PATHS)):
                engine.faceted.clear()
                t = time.perf_counter()
                runs[which]()
                cold[which].append(time.perf_counter() - t)
        for d, q in ((warm, 0.5), (warm, 0.95), (cpu, 0.5), (cold, 0.5), (cold, 0.95)):
            cells += [ms(quantile(d[k], q)) for k in PATHS]
        print(f"| {name} | " + " | ".join(cells) + " |", flush=True)
    print(f"load at end: {os.getloadavg()[0]:.1f}")


if __name__ == "__main__":
    main()
