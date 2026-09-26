"""Highlights from the AST (spec 03 §Highlights, spec 04 span units): half-open code-point spans over the raw
field, exactly what matched and nothing else. The highlighter's own verdict is checked against
ReferenceEngine on every fixture record for every golden query, so it can't light a record it wouldn't match."""

from __future__ import annotations

import json
from itertools import pairwise
from pathlib import Path

import pytest
from hypothesis import given, settings
from openproceedings.engine.highlight import _Highlighter, highlights
from openproceedings.engine.protocol import EngineInternalError
from openproceedings.engine.reference import ReferenceEngine
from openproceedings.query.ast import Near, Node, Not, Phrase, Term, Wildcard
from openproceedings.query.normalize import tokenize
from openproceedings.query.parser import parse

from tests.corpus import Rec, fixture_records
from tests.strategies import asts

RECORDS = fixture_records()
REFERENCE = ReferenceEngine(RECORDS)
GOLDEN = json.loads(
    (Path(__file__).parents[2] / "fixtures" / "corpus" / "reference-200-queries.json").read_text()
)


def lit(q: str, *records: Rec) -> dict[str, list[tuple[int, int]]]:
    ast = parse(q).ast
    assert ast is not None
    engine = ReferenceEngine(records)
    return highlights(ast, records[0], engine.expansions(ast))  # type: ignore[return-value]


def raw(record: Rec, spans: dict[str, list[tuple[int, int]]]) -> dict[str, list[str]]:
    return {f: [(getattr(record, f) or "")[s:e] for s, e in v] for f, v in spans.items()}


@pytest.mark.parametrize("case", GOLDEN, ids=[c["q"] for c in GOLDEN])
def test_the_highlighter_matches_exactly_what_the_oracle_matches(case: dict[str, object]) -> None:
    ast = parse(str(case["q"])).ast
    assert ast is not None
    expansions = REFERENCE.expansions(ast)
    matched = REFERENCE.match_ids(ast)
    for r in RECORDS:
        tokens = {f: tokenize(getattr(r, f) or "") for f in ("title", "abstract")}
        verdict, _spans = _Highlighter(r, tokens, expansions).node(ast)  # type: ignore[arg-type]
        assert verdict == (r.id in matched), (case["q"], r.id)
        if r.id not in matched:
            with pytest.raises(EngineInternalError):  # an engine hit the AST doesn't match: never silent
                highlights(ast, r, expansions)
            continue
        for f, v in highlights(ast, r, expansions).items():
            text = getattr(r, f) or ""
            assert all(0 <= s < e <= len(text) for s, e in v) and v == sorted(v)
            assert all(a[1] <= b[0] for a, b in pairwise(v))  # merged: never overlapping


def rec(title: str, abstract: str | None = None, **kw: object) -> Rec:
    return Rec("fx:001", title, abstract, **kw)  # type: ignore[arg-type]


def test_an_astral_plane_title_is_counted_in_code_points() -> None:
    r = rec("😀 𝐓rust in 𝔸I")  # an emoji and two NFKC-mapped mathematical letters: all astral
    got = lit("trust ai", r)
    assert got["title"] == [(2, 7), (11, 13)]  # code points; UTF-16 would be (3, 9) and (14, 18)
    assert raw(r, got)["title"] == ["𝐓rust", "𝔸I"]


def test_a_phrase_is_one_span_per_occurrence() -> None:
    r = rec("t", "We study trust  in AI, then trust in ai again; trust alone.")
    assert raw(r, lit('"trust in ai"', r))["abstract"] == ["trust  in AI", "trust in ai"]


def test_only_expanded_terms_light_up() -> None:
    r = rec("Trustworthy distrust of trusted trust", None)
    assert raw(r, lit("trust*", r))["title"] == ["Trustworthy", "trusted", "trust"]
    assert raw(r, lit("trust$", r))["title"] == ["trust"]  # `$` is one more character or none


def test_a_branch_that_did_not_match_lights_nothing() -> None:
    r = rec("trust and model", None, year=2024)
    assert raw(r, lit("(trust year:2023) OR model", r))["title"] == ["model"]
    assert raw(r, lit("model NOT (trust calibration)", r))["title"] == ["model"]  # a true NOT lights nothing
    assert raw(r, lit("model OR (trust calibration)", r))["title"] == ["model"]


def test_near_lights_only_occurrences_in_a_pair() -> None:
    r = rec("t", "trust ai; x x x x trust x x x x ai")
    assert lit("trust NEAR/1 ai", r)["abstract"] == [(0, 5), (6, 8)]
    r2 = rec("t", "ai x trust")  # either order
    assert raw(r2, lit("trust NEAR/1 ai", r2))["abstract"] == ["ai", "trust"]


def test_a_fielded_term_lights_only_its_field() -> None:
    r = rec("trust", "trust")
    assert lit("title:trust", r) == {"title": [(0, 5)], "abstract": []}
    assert lit("trust", r) == {"title": [(0, 5)], "abstract": [(0, 5)]}


def test_overlaps_merge_but_neighbours_stay_apart() -> None:
    r = rec("trust in ai", None)
    assert lit('"trust in" OR ai OR trust', r)["title"] == [(0, 8), (9, 11)]


def test_latex_math_lights_its_raw_source() -> None:
    r = rec("t", "An $\\alpha$-divergence bound, $x \\le y$")
    assert raw(r, lit("α", r))["abstract"] == [
        "alpha"
    ]  # a command's span is its name (tokenize's offset map)
    assert raw(r, lit("leq", r))["abstract"] == ["le"]


def allowed(n: Node, expansions: dict[tuple[str, str], frozenset[str]]) -> set[str]:
    """Every token some positive leaf of `n` can match (NOT subtrees and filters light nothing)."""
    if isinstance(n, Term):
        return {n.token}
    if isinstance(n, Wildcard):
        return set(expansions[(n.stem, n.op)])
    if isinstance(n, Phrase):
        return set().union(*(allowed(i, expansions) for i in n.items))
    if isinstance(n, Near):
        return allowed(n.left, expansions) | allowed(n.right, expansions)
    if isinstance(n, Not):
        return set()
    return set().union(*(allowed(c, expansions) for c in getattr(n, "children", ())))


@settings(deadline=None)
@given(asts())
def test_every_lit_token_is_one_a_positive_leaf_can_match(ast: Node) -> None:
    # independent of the evaluation: spans start and end on token boundaries, and every token inside one is
    # a term, an expansion or a phrase item of the query, outside any NOT
    expansions = REFERENCE.expansions(ast)
    ok = allowed(ast, expansions)
    matched = REFERENCE.match_ids(ast)
    for r in RECORDS:
        if r.id not in matched:
            continue
        for f, spans in highlights(ast, r, expansions).items():
            tokens = tokenize(getattr(r, f) or "")
            starts, ends = {t.start for t in tokens}, {t.end for t in tokens}
            for s, e in spans:
                assert s in starts and e in ends, (f, s, e)
                inside = [t.text for t in tokens if s <= t.start and t.end <= e]
                assert inside and all(t in ok for t in inside), (f, inside)


def test_phrase_items_and_near_operands_light_exactly() -> None:
    r = rec("t", "trusting in the ai and trusted in ai")
    assert raw(r, lit('"tru* in" NEAR/1 ai', r))["abstract"] == ["trusting in", "ai", "trusted in", "ai"]
    assert raw(r, lit('"trust* in" ai', r))["abstract"] == ["trusting in", "ai", "trusted in", "ai"]
    assert raw(r, lit('"trusted in" NEAR/0 ai', r))["abstract"] == ["trusted in", "ai"]


def test_a_fielded_near_lights_only_its_field() -> None:
    r = rec("trust ai", "trust ai")
    assert lit("title:(trust NEAR/1 ai)", r) == {"title": [(0, 5), (6, 8)], "abstract": []}


def test_touching_operator_tokens_stay_apart() -> None:
    r = rec("5×3", None)
    assert lit("5 times", r)["title"] == [(0, 1), (1, 2)]


def test_near_over_a_long_field_is_not_quadratic() -> None:
    import time

    r = rec("t", "trust ai " * 1_500)
    best = float("inf")
    for _ in range(3):  # best of 3: one busy moment on a shared runner isn't a regression
        t = time.perf_counter()
        got = lit("trust NEAR/100 ai", r)["abstract"]
        best = min(best, time.perf_counter() - t)
    assert len(got) == 3_000 and best < 1.0  # every pair checked took ~13 s


TOKENS = {r.id: {f: tokenize(getattr(r, f) or "") for f in ("title", "abstract")} for r in RECORDS}


def covered(ast: Node, r: Rec, expansions: dict[tuple[str, str], frozenset[str]]) -> dict[str, set[int]]:
    """The code points `ast` lights in each field of `r` (tokens cached per record)."""
    _m, spans = _Highlighter(r, TOKENS[r.id], expansions).node(ast)  # type: ignore[arg-type]
    return {f: {i for s, e in spans.get(f, set()) for i in range(s, e)} for f in ("title", "abstract")}  # type: ignore[call-overload]


@settings(deadline=None)
@given(asts(), asts())
def test_an_or_lights_exactly_its_matching_branches_and_an_and_all_of_them(a: Node, b: Node) -> None:
    # compositional, from the oracle's verdicts: OR lights the union over the branches that match (so an
    # unmatched branch lights nothing), AND the union over both
    from openproceedings.query.ast import And, Or

    branches = [(c, REFERENCE.match_ids(c)) for c in (a, b)]
    for combined in (Or(span=(0, 0), children=(a, b)), And(span=(0, 0), children=(a, b))):
        expansions = REFERENCE.expansions(combined)
        matched = REFERENCE.match_ids(combined)
        for r in RECORDS:
            if r.id not in matched:
                continue
            want: dict[str, set[int]] = {"title": set(), "abstract": set()}
            for c, ids in branches:
                if r.id in ids:
                    for f, points in covered(c, r, expansions).items():
                        want[f] |= points
            assert covered(combined, r, expansions) == want, (r.id, combined.kind)
