"""What a position-verified clause's id filter costs per search, and what the forms that could replace it would
cost (TASK-167). Run from `backend/`, on an existing index (it only reads it; the u64 comparison builds a
throwaway index of its own in a temporary directory):

    uv run python -m tests.bench.verified_forms INDEX [ROUNDS]

For each verified clause of `main-2-pop` (field, clause), warm, the median over ROUNDS (50 by default) of
one collection of: its candidate query alone; the form the engine compiles (`Compiler.exact`: the candidates
narrowed by the verified ids, or less the failures when they are fewer); and the candidates AND a
constant-0 `regex_phrase_query` of the clause (each wildcard item an alternation of its expansions, the
only form tantivy-py 0.26 offers that resolves no id list), with whether that form matched exactly the
verified ids. Then a term set of 20,752 values (the `"AI agent$"` abstract clause's ids on the synthetic 80k)
over 80,000 documents, on a raw-text id like the index's and on an indexed u64 (what a schema change could
add). Prints the 1-minute load average at the start and end. A report, not a gate.
"""

from __future__ import annotations

import os
import random
import re
import sys
import tempfile
import time
from pathlib import Path
from typing import cast

import tantivy
from openproceedings.engine.compile import Compiler
from openproceedings.engine.tantivy_engine import TantivyEngine
from openproceedings.query.ast import Node, Phrase, Term, TextField
from pydantic import TypeAdapter

from tests.bench.test_bench import trust_evals

IDS = 20_752  # the synthetic 80k's `"AI agent$"` abstract clause
DOCS = 80_000


def median_ms(searcher: tantivy.Searcher, query: tantivy.Query, rounds: int) -> float:
    times = []
    for _ in range(rounds):
        t = time.perf_counter()
        searcher.search(query, 1, count=True)
        times.append(time.perf_counter() - t)
    return sorted(times)[len(times) // 2] * 1000


def clauses(engine: TantivyEngine, rounds: int) -> None:
    ast = trust_evals("main-2-pop").effective_ast
    assert ast is not None
    compiled = engine.compile(ast)
    compiler = Compiler(
        engine.index.schema, engine.expansions(ast), engine.read, count=engine._count, members=engine.ids_of
    )
    nodes: TypeAdapter[Node] = TypeAdapter(Node)
    print(
        "| Field | Clause | Verified | Candidates | Candidates alone | As compiled | Regex phrase | Same ids |"
    )
    print("|---|---|---|---|---|---|---|---|")
    for (name, clause), ids in compiled.ids.items():
        field = cast(TextField, name)
        n = nodes.validate_json(clause)
        assert isinstance(n, Phrase)
        candidates = compiler.candidates(n, field)
        if not ids:
            continue  # compiled to an empty query: nothing to resolve
        words: list[str | tuple[int, str]] = [
            re.escape(i.token)
            if isinstance(i, Term)
            else "(?:" + "|".join(re.escape(t) for t in compiler.expansions[(i.stem, i.op)]) + ")"
            for i in n.items
        ]
        phrase = tantivy.Query.regex_phrase_query(engine.index.schema, field, words, 0)
        regex = tantivy.Query.boolean_query(
            [
                (tantivy.Occur.Must, candidates),
                (tantivy.Occur.Must, tantivy.Query.const_score_query(phrase, 0.0)),
            ]
        )
        exact = compiler.exact(candidates, ids)
        text = " ".join(i.token if isinstance(i, Term) else i.stem + i.op for i in n.items)
        cells = [median_ms(engine.searcher, q, rounds) for q in (candidates, exact, regex)]
        print(
            f'| {field} | `"{text}"` | {len(ids):,} | {engine._count(candidates):,} | '
            + " | ".join(f"{c:.1f} ms" for c in cells)
            + f" | {engine.ids_of(regex) == frozenset(ids)} |",
            flush=True,
        )


def term_sets(rounds: int) -> None:
    builder = tantivy.SchemaBuilder()
    builder.add_text_field("id", tokenizer_name="raw")
    builder.add_unsigned_field("ord", indexed=True)
    schema = builder.build()
    with tempfile.TemporaryDirectory(prefix="op-forms-") as d:
        index = tantivy.Index(schema, path=d)
        writer = index.writer(heap_size=200_000_000, num_threads=1)
        ids = [f"op:neurips:2024:{i:08x}abcdef" for i in range(DOCS)]  # ids of a realistic length
        for o, i in enumerate(ids):
            doc = tantivy.Document()
            doc.add_text("id", i)
            doc.add_unsigned("ord", o)
            writer.add_document(doc)
        writer.commit()
        writer.wait_merging_threads()
        index.reload()
        searcher = index.searcher()
        pick = sorted(random.Random(1).sample(range(DOCS), IDS))
        for label, query in (
            ("raw-text id (as built)", tantivy.Query.term_set_query(schema, "id", [ids[o] for o in pick])),
            ("indexed u64 ord (a schema change)", tantivy.Query.term_set_query(schema, "ord", pick)),
        ):
            assert searcher.search(query, 1, count=True).count == IDS  # type: ignore[attr-defined]
            print(f"- term set of {IDS:,} on a {label}: {median_ms(searcher, query, rounds):.1f} ms")


def main() -> None:
    engine = TantivyEngine(Path(sys.argv[1]))
    rounds = int(sys.argv[2]) if len(sys.argv) > 2 else 50
    print(f"load at start: {os.getloadavg()[0]:.1f}", flush=True)
    clauses(engine, rounds)
    term_sets(rounds)
    print(f"load at end: {os.getloadavg()[0]:.1f}")


if __name__ == "__main__":
    main()
