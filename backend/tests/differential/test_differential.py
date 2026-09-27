"""TantivyEngine == ReferenceEngine on the synthetic 5k corpus (spec 07 §A; differential-tester agent;
task-028). The oracle is the definition of correct, so every generated tree must give the same match set,
the same wildcard expansions (or the same refusal), the same disjunctive facets, the same `total` for every
sort (and, for `year_asc`, the (year, id) order), and, for trees that parse, the same exclusion counts as a
brute-force count. Trees draw on the corpus's own term dictionary (`synthetic_5k.vocab()`), rare terms
weighted up. 2,000 examples under the `ci` profile; 50,000 nightly with task-057.

Saving a counterexample: every failure message ends with `regression: <the shrunk AST as JSON>`. Add
`{"ast": <that JSON>, "note": "<what broke>"}` to `differential-regressions.json`, which
`test_saved_regressions_still_agree` replays on every run (all-negative trees included, which no query
string can express).
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from openproceedings.engine.exclusions import excluded
from openproceedings.engine.protocol import FACET_FIELDS, EngineInputError
from openproceedings.engine.reference import ReferenceEngine, _conjuncts, _own_field
from openproceedings.engine.tantivy_engine import SORTS, TantivyEngine
from openproceedings.query.ast import Node, Wildcard
from openproceedings.query.canonical import canonicalize, render
from openproceedings.query.defaults import DEFAULT_CLAUSES
from openproceedings.query.parser import ParseResult, parse
from pydantic import TypeAdapter

from tests.fixtures.corpus.synthetic_5k import records, vocab
from tests.golden.test_tantivy_200 import as_paper
from tests.strategies import engine_asts
from tests.unit.engine.test_exclusions import tantivy_of

REGRESSIONS = Path(__file__).parent / "differential-regressions.json"
NODE: TypeAdapter[Node] = TypeAdapter(Node)
RECORDS = list(records())
BACK = {as_paper(r).id: r.id for r in RECORDS}
BY_ID = {r.id: r for r in RECORDS}
CORPUS_HASH = "c401aedfa0b5149d"


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
        assert got_json == json.dumps(brute_excluded(reference, parsed, got, ast)), q


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


@settings(deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large])
@given(ast=engine_asts(vocab()))
def test_tantivy_agrees_with_the_oracle(engines: tuple[ReferenceEngine, TantivyEngine], ast: Node) -> None:
    agree(engines, ast)


def test_saved_regressions_still_agree(engines: tuple[ReferenceEngine, TantivyEngine]) -> None:
    cases = json.loads(REGRESSIONS.read_text())
    assert cases, "the regression file holds at least the seeded hard cases"
    for case in cases:
        agree(engines, NODE.validate_python(case["ast"]))


def test_the_corpus_covers_every_filter_combination() -> None:
    from openproceedings.vocab import STATUSES, TRACKS

    from tests.fixtures.corpus.synthetic_5k import VENUES, YEARS

    seen = {(r.venue, r.year, r.track, r.status) for r in RECORDS}
    corpus = json.dumps([dataclasses.asdict(r) for r in RECORDS], ensure_ascii=False)
    # pinned: a change here (to the generator, the golden fixture's n-grams or normalize()) is deliberate,
    # and saved regressions must be re-checked against the new corpus
    assert hashlib.sha256(corpus.encode()).hexdigest()[:16] == CORPUS_HASH
    assert len(seen) == len(VENUES) * len(YEARS) * len(TRACKS) * len(STATUSES)
    assert len(RECORDS) == 5_000 and any(r.abstract is None for r in RECORDS)
