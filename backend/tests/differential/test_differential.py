"""TantivyEngine == ReferenceEngine on the synthetic 5k corpus (spec 07 §A; differential-tester agent;
task-028). The oracle is the definition of correct, so every generated tree must give the same match set,
the same wildcard expansions (or the same refusal), the same disjunctive facets, the same `total` for every
sort (and, for `year_asc`, the (year, id) order), and, for trees that parse, the same exclusion counts as a
brute-force count, through the facet combos and through the default fields alone (a search without facets,
TASK-166). And each concept group's counts, alone and the query without it, are the oracle's
(`test_group_counts_agree_with_the_oracle`, TASK-176). The engine is built at the current SCHEMA_VERSION; the previous schema a pinned index may hold is
held to the oracle in `tests/unit/engine/test_served_schemas.py` (TASK-167). Trees draw on the corpus's own term dictionary (`synthetic_5k.vocab()`), rare terms
weighted up, and stems at the 200-expansion cap's edge (`cap_records()`, 20 records added to the corpus the
engines search, 5,020 in all, both parts hash-pinned: `qca*` expands to 199 terms, `qcb*` to 200, `qcc*` to 201
and is refused; TASK-057). 200 examples per PR (`pr` profile); 50,000 in total in the nightly workflow's own
`differential` job (`nightly`: 8 independent runs of 6,250, each with its own seed; TASK-057).

Saving a counterexample: every failure message ends with `regression: <the shrunk AST as JSON>`. Add
`{"ast": <that JSON>, "note": "<what broke>"}` to `differential-regressions.json`, which
`test_saved_regressions_still_agree` replays on every run (all-negative trees included, which no query
string can express).
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
from functools import partial
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from openproceedings.diagnostics import DiagnosticCode
from openproceedings.engine.exclusions import ORDER, excluded
from openproceedings.engine.protocol import FACET_FIELDS, MAX_EXPANSIONS, EngineInputError
from openproceedings.engine.reference import ReferenceEngine, _conjuncts, _own_field
from openproceedings.engine.tantivy_engine import SORTS, TantivyEngine
from openproceedings.query.ast import And, Node, Not, Wildcard
from openproceedings.query.canonical import canonicalize, render
from openproceedings.query.defaults import DEFAULT_CLAUSES
from openproceedings.query.groups import split
from openproceedings.query.parser import ParseResult, parse
from pydantic import TypeAdapter

from tests.corpus import Rec
from tests.fixtures.corpus.synthetic_5k import CAP_STEMS, cap_records, cap_vocab, records
from tests.golden.test_tantivy_200 import as_paper
from tests.strategies import SPAN, engine_asts, filters
from tests.unit.engine.test_exclusions import tantivy_of

REGRESSIONS = Path(__file__).parent / "differential-regressions.json"
NODE: TypeAdapter[Node] = TypeAdapter(Node)
RECORDS = [*records(), *cap_records()]
BACK = {as_paper(r).id: r.id for r in RECORDS}
BY_ID = {r.id: r for r in RECORDS}
CORPUS_HASH = "c401aedfa0b5149d"
CAP_HASH = "ef8e7afc95483953"  # the 20 cap-edge records the engines also search
REFUSED = ("refused", DiagnosticCode.WILDCARD_TOO_MANY_EXPANSIONS)


@pytest.fixture(scope="module")
def engines(tmp_path_factory: pytest.TempPathFactory) -> tuple[ReferenceEngine, TantivyEngine]:
    return ReferenceEngine(RECORDS), tantivy_of(RECORDS, tmp_path_factory.mktemp("differential"))


def outcome(f: object, *args: object) -> object:
    """A call's result, or the diagnostic code it refused with: both engines must refuse alike."""
    try:
        return f(*args)  # type: ignore[operator]
    except EngineInputError as e:
        return ("refused", e.code)


def wildcards(n: object) -> list[Wildcard]:
    if isinstance(n, Wildcard):
        return [n]
    kids = [getattr(n, a) for a in ("child", "left", "right") if hasattr(n, a)]
    kids += list(getattr(n, "children", ())) + list(getattr(n, "items", ()))
    return [w for k in kids for w in wildcards(k)]


def agree(engines: tuple[ReferenceEngine, TantivyEngine], ast: Node) -> None:
    reference, tantivy = engines
    q = f"{render(ast)}\nregression: {NODE.dump_json(ast).decode()}"
    for w in wildcards(ast):
        assert outcome(reference.expand, w) == outcome(tantivy.expand, w), q
    expected = outcome(reference.match_ids, ast)
    got = outcome(tantivy.match_ids, ast)
    if not isinstance(got, frozenset):
        assert got == expected, q  # both refused, with the same code
        return
    got = frozenset(BACK[i] for i in got)
    only_t, only_r = sorted(got - expected)[:5], sorted(expected - got)[:5]  # type: ignore[operator]
    assert got == expected, f"only in tantivy: {only_t}\nonly in reference: {only_r}\n{q}"
    assert expected_facets(reference, ast, got) == tantivy.facets(ast), q
    for sort in SORTS:
        assert tantivy.search(ast, sort=sort, limit=0).total == len(got), (sort, q)
    page = [BACK[i] for i in tantivy.search(ast, sort="year_asc", limit=len(got)).ids]
    keyed = [(BY_ID[i].year, as_paper(BY_ID[i]).id) for i in page]
    assert set(page) == got and keyed == sorted(keyed), q
    parsed = parse(render(ast))
    if parsed.effective_ast is not None:  # a tree the parser accepts: its exclusion counts agree too
        total = len(tantivy.match_ids(parsed.effective_ast))
        got_json = json.dumps(excluded(tantivy, parsed, total).to_json())  # order-sensitive: spec 04 pins it
        expected_json = json.dumps(brute_excluded(reference, parsed, got, ast))
        assert got_json == expected_json, q
        # what a search without facets counts (`search.run`: the default fields only, TASK-166)
        narrow = excluded(tantivy, parsed, total, facets=partial(tantivy.facets, over=ORDER))
        assert json.dumps(narrow.to_json()) == expected_json, q


def brute_excluded(
    reference: ReferenceEngine, parsed: ParseResult, own: frozenset[str], tree: Node
) -> dict[str, object]:
    """Exclusion counts record by record, independent of exclusions.py. Identified: the oracle's set for the
    identification tree (the tree's own set, already known, when that is just the canonical tree). Matched:
    the identified records that pass every default filter. Each identified record not matched is bucketed by
    the first default, track then status, it fails. It trusts `parse()` for `identification_ast` and
    `defaults` (defaults.py has its own tests); what it checks is the engines' bucketing, and the bucket order
    spec 04 pins (by count, ties by name, `unknown` last)."""
    ast = parsed.identification_ast
    if ast is None:
        identified = set(BY_ID)
    elif parsed.identification_query == render(canonicalize(tree)):
        identified = set(own)
    else:
        identified = set(reference.match_ids(ast))
    buckets: dict[str, dict[str, int]] = {"track": {}, "status": {}}
    for i in identified:
        r = BY_ID[i]
        failed = [
            f for f in ("track", "status") if f in parsed.defaults and getattr(r, f) not in DEFAULT_CLAUSES[f]
        ]
        if failed:
            value = getattr(r, failed[0])
            buckets[failed[0]][value] = buckets[failed[0]].get(value, 0) + 1
    shaped = {
        f: {
            **{v: n for v, n in sorted(b.items(), key=lambda kv: (-kv[1], kv[0])) if v != "unknown"},
            "unknown": b.get("unknown", 0),
        }
        for f, b in buckets.items()
    }
    return {"total": sum(sum(b.values()) for b in buckets.values()), **shaped}


def expected_facets(
    reference: ReferenceEngine, ast: Node, matched: frozenset[str]
) -> dict[str, dict[str, int]]:
    """The oracle's disjunctive facets. A field with no top-level conjunct of its own is counted over the
    match set, which is already known; only the others need the oracle's own pass (one per field)."""
    own = {_own_field(c) for c in _conjuncts(ast)}
    out = reference.facets(ast, tuple(f for f in FACET_FIELDS if f in own))
    for f in FACET_FIELDS:
        if f not in own:
            counts: dict[str, int] = {}
            for i in matched:
                value = str(getattr(BY_ID[i], f))
                counts[value] = counts.get(value, 0) + 1
            out[f] = dict(sorted(counts.items()))
    return out


# The nightly `differential` job splits the profile's examples across parallel jobs (TASK-057): with
# OP_DIFFERENTIAL_SHARDS=n, each job runs 1/n of them under its own `--hypothesis-seed`.
SHARDS = int(os.environ.get("OP_DIFFERENTIAL_SHARDS", "1"))
assert SHARDS >= 1, "OP_DIFFERENTIAL_SHARDS is a positive count of jobs"


# the oracle over 5k records, every sort and the facets per example: no per-example deadline
@settings(deadline=None, max_examples=max(1, settings().max_examples // SHARDS))
@given(ast=engine_asts(cap_vocab()))
def test_tantivy_agrees_with_the_oracle(engines: tuple[ReferenceEngine, TantivyEngine], ast: Node) -> None:
    agree(engines, ast)


def test_saved_regressions_still_agree(engines: tuple[ReferenceEngine, TantivyEngine]) -> None:
    cases = json.loads(REGRESSIONS.read_text())
    assert cases, "the regression file holds at least the seeded hard cases"
    for case in cases:
        agree(engines, NODE.validate_python(case["ast"]))


def test_the_cap_stems_sit_at_the_cap(engines: tuple[ReferenceEngine, TantivyEngine]) -> None:
    for engine in engines:
        for stem, n in CAP_STEMS.items():
            got = outcome(engine.expand, Wildcard(span=(0, 0), stem=stem, op="*"))
            assert (len(got) if isinstance(got, list) else got) == (n if n <= MAX_EXPANSIONS else REFUSED), (
                stem
            )
            # `$`: the stem's 26 words one letter longer
            assert len(engine.expand(Wildcard(span=(0, 0), stem=stem, op="$"))) == 26, stem
        assert outcome(engine.expand, Wildcard(span=(0, 0), stem="qc", op="*")) == REFUSED


def test_the_corpus_covers_every_filter_combination() -> None:
    from openproceedings.vocab import STATUSES, TRACKS

    from tests.fixtures.corpus.synthetic_5k import VENUES, YEARS

    corpus_5k = records()
    seen = {(r.venue, r.year, r.track, r.status) for r in corpus_5k}

    def digest(rs: tuple[Rec, ...]) -> str:
        return hashlib.sha256(
            json.dumps([dataclasses.asdict(r) for r in rs], ensure_ascii=False).encode()
        ).hexdigest()

    # pinned: a change here (to the generator, the golden fixture's n-grams, normalize() or the cap records) is
    # deliberate, and saved regressions must be re-checked against the new corpus
    assert digest(corpus_5k)[:16] == CORPUS_HASH
    assert digest(cap_records())[:16] == CAP_HASH
    assert len(seen) == len(VENUES) * len(YEARS) * len(TRACKS) * len(STATUSES)
    assert len(corpus_5k) == 5_000 and any(r.abstract is None for r in corpus_5k)


# --- each concept group's counts (TASK-176): `TantivyEngine.counts` against the oracle's match sets -----------------
@st.composite
def grouped_asts(draw: st.DrawFn) -> Node:
    """An AND of several trees (each a concept group, a leave-out or a filter clause) and extra top-level
    filters: the queries whose groups `search.run` counts (as `tests/unit/test_group_counts.py` draws them,
    here over the cap-edge vocabulary too)."""
    parts: list[Node] = draw(st.lists(engine_asts(cap_vocab()), min_size=1, max_size=4))
    parts += [
        Not(span=SPAN, child=f) if draw(st.booleans()) else f for f in draw(st.lists(filters(), max_size=3))
    ]
    return parts[0] if len(parts) == 1 else And(span=SPAN, children=tuple(draw(st.permutations(parts))))


# up to nine trees through the oracle per example: no per-example deadline; sharded as the agreement property
@settings(deadline=None, max_examples=max(1, settings().max_examples // SHARDS))
@given(tree=grouped_asts())
def test_group_counts_agree_with_the_oracle(
    engines: tuple[ReferenceEngine, TantivyEngine], tree: Node
) -> None:
    """The query, each group alone and the query without each, counted in one `counts` call (shared conjuncts,
    as `search.run` asks) and one at a time with `count`: each the oracle's `len(match_ids)`, or the same
    refusal. Run at the profile's examples (ci 2,000, nightly 50,000), unlike the unit property's pinned few."""
    reference, tantivy = engines
    tantivy.faceted.clear()  # a fresh collection as often as a memoised one
    ast = canonicalize(tree)
    found = split(ast)
    trees = [ast, *map(found.alone, found.groups[:4])]
    if len(found.groups) >= 2:
        trees += map(found.without, found.groups[:4])
    q = f"{render(ast)}\nregression: {NODE.dump_json(ast).decode()}"
    expected = [outcome(lambda n: len(reference.match_ids(n)), t) for t in trees]
    assert [outcome(tantivy.count, t) for t in trees] == expected, q
    if all(isinstance(e, int) for e in expected):
        assert outcome(tantivy.counts, trees) == expected, q
    else:  # one refused tree refuses the call, with the first refusal's code
        assert outcome(tantivy.counts, trees) == next(e for e in expected if not isinstance(e, int)), q
