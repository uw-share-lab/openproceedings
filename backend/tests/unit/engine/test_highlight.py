"""Highlights from the AST (spec 03 §Highlights, spec 04 span units): half-open code-point spans over the raw
field, exactly what matched and nothing else. The highlighter's own verdict is checked against
ReferenceEngine on every fixture record for every golden query, so it can't light a record it wouldn't match."""

from __future__ import annotations

import json
from itertools import pairwise
from pathlib import Path

import pytest
from openproceedings.engine.highlight import _Highlighter, highlights
from openproceedings.engine.reference import ReferenceEngine
from openproceedings.query.normalize import normalize, tokenize
from openproceedings.query.parser import parse

from tests.corpus import Rec, fixture_records

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
        lit_ = highlights(ast, r, expansions)
        if r.id not in matched:
            assert lit_ == {"title": [], "abstract": []}
        for f, v in lit_.items():
            text = getattr(r, f) or ""
            assert all(0 <= s < e <= len(text) for s, e in v) and v == sorted(v)
            assert all(a[1] <= b[0] for a, b in pairwise(v))  # merged: never overlapping
            for s, e in v:
                assert normalize(text[s:e])  # every span covers at least one real token


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
