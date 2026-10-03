"""In-index verified-id construction and collection (TASK-167).

From backend/: uv run python -m tests.bench.id_sets OLD_INDEX NEW_INDEX [ROUNDS]
Both indexes are read-only and must contain the same snapshot. Compile main-2-pop
once to obtain its verified abstract AI-agent clause. Alternate text and ordinal
forms each round. Construction is timed without a collection; collection reuses
one constructed query. Whole-tree compile timings retain verified/expansion memos,
clear the compiled memo, and reset the ordinal table only for first-use compiles;
compile memo hits retain all memos. First-use ordinal construction resets the lazy table each
round; subsequent construction retains it. Retained table memory counts dict and
integer values, excluding the existing id strings. No RSS claim is made.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from openproceedings.engine.tantivy_engine import TantivyEngine
from openproceedings.query.ast import Phrase, Wildcard
from pydantic import TypeAdapter

from tests.bench.report_80k import ms, quantile
from tests.bench.test_bench import trust_evals


def main() -> None:
    old, new = (TantivyEngine(Path(p)) for p in sys.argv[1:3])
    rounds = int(sys.argv[3]) if len(sys.argv) > 3 else 100
    assert rounds > 0
    assert not old.ord_indexed and new.ord_indexed
    assert old.ids == new.ids
    ast = trust_evals("main-2-pop").effective_ast
    assert ast is not None
    clauses = old.compile(ast).ids
    pick = []
    for (field, clause), ids in clauses.items():
        node = TypeAdapter(Phrase).validate_json(clause)
        if (
            field == "abstract"
            and node.items[0].model_dump().get("token") == "ai"
            and any(isinstance(i, Wildcard) and i.stem == "agent" for i in node.items)
        ):
            pick = ids
            break
    assert pick, "the snapshot must contain the abstract AI-agent wildcard clause"
    engines = {"text": old, "ordinal": new}
    queries = {k: e.id_set(pick) for k, e in engines.items()}
    for k, e in engines.items():
        assert e.ids_of(queries[k]) == frozenset(pick)
    times: dict[str, list[float]] = {
        k: []
        for k in (
            "text construction",
            "ordinal first construction",
            "ordinal subsequent construction",
            "text collection",
            "ordinal collection",
        )
    }
    print(f"load at start: {os.getloadavg()[0]:.1f}", flush=True)
    for r in range(rounds):
        for k in tuple(engines) if r % 2 == 0 else tuple(reversed(engines)):
            e = engines[k]
            if k == "ordinal":
                e._ords = None
                t = time.process_time()
                e.id_set(pick)
                times["ordinal first construction"].append(time.process_time() - t)
            t = time.process_time()
            e.id_set(pick)
            times[f"{k} {'subsequent ' if k == 'ordinal' else ''}construction"].append(
                time.process_time() - t
            )
            t = time.process_time()
            e.searcher.search(queries[k], 1, count=True)
            times[f"{k} collection"].append(time.process_time() - t)
    new.compile(ast)  # verified clauses/expansions warm for the isolated compile comparison
    compile_times: dict[str, list[float]] = {
        "tree compile, table first use": [],
        "tree compile, table retained": [],
        "tree compile memo hit": [],
    }
    for _ in range(rounds):
        for phase in compile_times:
            if phase != "tree compile memo hit":
                new.compiled.clear()
            if phase == "tree compile, table first use":
                new._ords = None
            t = time.process_time()
            new.compile(ast)
            compile_times[phase].append(time.process_time() - t)
    times.update(compile_times)
    print(
        f"indexes: {old.index_version} / {new.index_version}; records: {len(new.ids):,}; verified ids: {len(pick):,}; rounds: {rounds}"
    )
    print("| Phase | CPU p50 | CPU p95 |\n|---|---|---|")
    for k, values in times.items():
        print(f"| {k} | {ms(quantile(values, 0.5))} | {ms(quantile(values, 0.95))} |")
    assert new._ords is not None
    memory = sys.getsizeof(new._ords) + sum(sys.getsizeof(v) for v in new._ords.values())
    print(f"retained ordinal table: {memory:,} bytes (dict + integer values; existing id strings excluded)")
    print(f"load at end: {os.getloadavg()[0]:.1f}")


if __name__ == "__main__":
    main()
