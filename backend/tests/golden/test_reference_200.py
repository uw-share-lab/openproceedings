"""ReferenceEngine against 44 queries on a 200-record fixture whose expected id sets were computed by an
independent evaluator (task-016 AC2; `fixtures/corpus/make_reference_200.py`)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st
from openproceedings.engine.reference import ReferenceEngine
from openproceedings.query.canonical import canonicalize, render
from openproceedings.query.parser import parse

from tests.corpus import fixture_records

CORPUS = Path(__file__).parents[1] / "fixtures" / "corpus"


RECORDS = fixture_records()
GOLDEN = json.loads((CORPUS / "reference-200-queries.json").read_text())
ENGINE = ReferenceEngine(RECORDS)


def test_fixture_size() -> None:
    assert len(RECORDS) == 200 and len(GOLDEN) == 44
    assert all(case["expected"] for case in GOLDEN), "a row expecting nothing pins nothing"


@pytest.mark.parametrize("case", GOLDEN, ids=[c["q"] for c in GOLDEN])
def test_golden(case: dict[str, object]) -> None:
    result = parse(str(case["q"]))
    assert result.ast is not None, result.errors
    assert sorted(ENGINE.match_ids(result.ast)) == case["expected"]


QUERY_PARTS = [c["q"] for c in GOLDEN]


@given(
    st.lists(st.sampled_from(QUERY_PARTS), min_size=1, max_size=4),
    st.sampled_from([" ", " OR ", " AND NOT "]),
)
def test_canonical_form_never_changes_the_match_set(parts: list[str], op: str) -> None:
    """Every canonicalisation step is meaning-preserving (review of task-013, Should 6), checked by the oracle."""
    result = parse(op.join(f"({p})" for p in parts))
    assume(result.ast is not None)
    assert result.ast is not None
    assert ENGINE.match_ids(canonicalize(result.ast)) == ENGINE.match_ids(result.ast)
    again = parse(render(canonicalize(result.ast)))
    assert again.ast is not None and ENGINE.match_ids(again.ast) == ENGINE.match_ids(result.ast)
