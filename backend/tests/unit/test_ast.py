"""AST invariants (spec 02 §Outputs): what the engine relies on cannot be constructed wrongly."""

from __future__ import annotations

import pytest
from openproceedings.query.ast import Filter, Near, Phrase, Term, Wildcard, YearRange, structure
from pydantic import ValidationError

S = (0, 1)


@pytest.mark.parametrize(
    "build",
    [
        lambda: Term(span=(5, 1), token="a"),  # backwards span
        lambda: Term(span=(-1, 1), token="a"),
        lambda: Term(span=S, token=""),
        lambda: Term(span=S, token="a b"),  # a token never contains whitespace
        lambda: Wildcard(span=S, stem="", op="*"),
        lambda: Phrase(span=S, items=(Term(span=S, token="a"),)),  # one item is a Term, not a Phrase
        lambda: Phrase(span=S, items=(Term(span=S, token="a", field="title"), Term(span=S, token="b"))),
        lambda: Near(
            span=S, left=Term(span=S, token="a", field="title"), right=Term(span=S, token="b"), distance=1
        ),
        lambda: Near(span=S, left=Term(span=S, token="a"), right=Term(span=S, token="b"), distance=101),
        lambda: YearRange(lo=2024, hi=2020),
        lambda: YearRange(lo=0, hi=2020),
        lambda: YearRange(lo=2020, hi=10000),
        lambda: Filter(span=S, field="venue", values=(YearRange(lo=2020, hi=2021),)),
        lambda: Filter(span=S, field="year", values=("ICLR",)),
        lambda: Filter(span=S, field="source", values=("PMLR",)),  # type: ignore[arg-type]  # Scholar-only
        lambda: Filter(span=S, field="venue", values=()),
    ],
)
def test_invalid_nodes_cannot_be_built(build: object) -> None:
    with pytest.raises(ValidationError):
        build()  # type: ignore[operator]


def test_structure_ignores_spans_only() -> None:
    a = Term(span=(0, 5), token="trust", field="title")
    assert structure(a) == structure(Term(span=(9, 14), token="trust", field="title"))
    assert structure(a) != structure(Term(span=(0, 5), token="trust"))
    assert "span" not in str(
        structure(Phrase(span=S, items=(Term(span=S, token="a"), Wildcard(span=S, stem="b", op="$"))))
    )


def test_near_reports_its_field() -> None:
    near = Near(
        span=S,
        left=Term(span=S, token="a", field="abstract"),
        right=Term(span=S, token="b", field="abstract"),
        distance=2,
    )
    assert near.field == "abstract"
