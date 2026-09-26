"""TantivyEngine == ReferenceEngine on the synthetic 5k corpus (spec 07 §A; differential-tester agent;
task-028). The oracle is the definition of correct, so every generated tree must give the same match set,
the same wildcard expansions (or the same refusal), the same disjunctive facets, and the same `total` for
every sort. 2,000 examples under the `ci` profile, 50,000 nightly.

A counterexample is shrunk by Hypothesis, then saved to `differential-regressions.json` (its AST as JSON
and a note), which `test_saved_regressions_still_agree` replays on every run.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from openproceedings.engine.protocol import FACET_FIELDS, EngineInputError
from openproceedings.engine.reference import ReferenceEngine, _conjuncts, _own_field
from openproceedings.engine.tantivy_engine import SORTS, TantivyEngine
from openproceedings.query.ast import Node, Wildcard
from openproceedings.query.canonical import render
from pydantic import TypeAdapter

from tests.fixtures.corpus.synthetic_5k import records
from tests.golden.test_tantivy_200 import as_paper
from tests.strategies import engine_asts
from tests.unit.engine.test_exclusions import tantivy_of

REGRESSIONS = Path(__file__).parent / "differential-regressions.json"
NODE: TypeAdapter[Node] = TypeAdapter(Node)
RECORDS = list(records())
BACK = {as_paper(r).id: r.id for r in RECORDS}
BY_ID = {r.id: r for r in RECORDS}


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
    q = render(ast)
    for w in wildcards(ast):
        assert outcome(reference.expand, w) == outcome(tantivy.expand, w), (q, w)
    expected = outcome(reference.match_ids, ast)
    got = outcome(tantivy.match_ids, ast)
    if isinstance(got, frozenset):
        got = frozenset(BACK[i] for i in got)
        only_t, only_r = sorted(got - expected)[:5], sorted(expected - got)[:5]  # type: ignore[operator]
        assert got == expected, f"{q}\nonly in tantivy: {only_t}\nonly in reference: {only_r}"
        assert expected_facets(reference, ast, got) == tantivy.facets(ast), q
        for sort in SORTS:
            assert tantivy.search(ast, sort=sort, limit=0).total == len(got), (q, sort)
    else:
        assert got == expected, q  # both refused, with the same code


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
@given(ast=engine_asts())
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
    assert len(seen) == len(VENUES) * len(YEARS) * len(TRACKS) * len(STATUSES)
    assert len(RECORDS) == 5_000 and any(r.abstract is None for r in RECORDS)
