"""The query AST (spec 02 §Outputs): a pydantic discriminated union on `kind`.

Every node keeps the half-open code-point span of the input it came from, so diagnostics and the UI parse
tree point at `q`; `structure(node)` is the node without spans, for comparing meaning. Text leaves (`Term`,
`Wildcard`, `Phrase`) carry their field (`title`, `abstract`, or None for both); there is no separate
field node, and a phrase's items carry none of their own. Leaves hold normalised tokens, never raw text.
The validators make the invariants the engine relies on unrepresentable to break.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Self, get_args

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from openproceedings.vocab import STATUSES, TRACKS, VENUES

TextField = Literal["title", "abstract"]
FilterField = Literal["venue", "year", "track", "status"]  # also the canonical filter order (decision-001)
FILTER_FIELDS: tuple[FilterField, ...] = get_args(FilterField)
Span = tuple[int, int]
_TOKEN = r"^\S+$"  # a normalised token: non-empty, no whitespace
MIN_YEAR, MAX_YEAR = 1000, 9999


class _Node(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    span: Span

    @field_validator("span")
    @classmethod
    def _half_open(cls, v: Span) -> Span:
        if not 0 <= v[0] <= v[1]:
            raise ValueError(f"span must be a half-open [start, end) range, got {v}")
        return v


class Term(_Node):
    kind: Literal["term"] = "term"
    token: str = Field(pattern=_TOKEN)
    field: TextField | None = None


class Wildcard(_Node):
    """A suffix wildcard on one normalised token: `*` is zero or more characters, `$` zero or one."""

    kind: Literal["wildcard"] = "wildcard"
    stem: str = Field(pattern=_TOKEN)
    op: Literal["*", "$"]
    field: TextField | None = None


class Phrase(_Node):
    """Consecutive positions in one field. A wildcard item is expanded at its position (decision-001)."""

    kind: Literal["phrase"] = "phrase"
    items: tuple[Term | Wildcard, ...] = Field(min_length=2)
    field: TextField | None = None

    @model_validator(mode="after")
    def _items_have_no_field(self) -> Self:
        if any(i.field is not None for i in self.items):
            raise ValueError("a phrase's field is on the phrase; its items carry none")
        return self


Leaf = Term | Wildcard | Phrase


class Near(_Node):
    """Both operands within `distance` words of each other, in either order, in one field."""

    kind: Literal["near"] = "near"
    left: Leaf
    right: Leaf
    distance: int = Field(ge=0, le=100)

    @model_validator(mode="after")
    def _one_field(self) -> Self:
        if self.left.field != self.right.field:
            raise ValueError("both NEAR operands must be in the same field")
        return self

    @property
    def field(self) -> TextField | None:
        return self.left.field


class YearRange(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    lo: int = Field(ge=MIN_YEAR, le=MAX_YEAR)
    hi: int = Field(ge=MIN_YEAR, le=MAX_YEAR)

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if self.lo > self.hi:
            raise ValueError(f"year range {self.lo}..{self.hi} runs backwards")
        return self


class Filter(_Node):
    """`field:` restricted to any of `values` (a single-field OR group): YearRanges for `year`, canonical
    strings (`vocab.py`) for the others."""

    kind: Literal["filter"] = "filter"
    field: FilterField
    values: tuple[str | YearRange, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _values_match_field(self) -> Self:
        want = YearRange if self.field == "year" else str
        if not all(isinstance(v, want) for v in self.values):
            raise ValueError(f"`{self.field}` filter values must all be {want.__name__}")
        allowed = {"venue": VENUES.values(), "track": TRACKS, "status": STATUSES}.get(self.field)
        if allowed is not None and not all(v in allowed for v in self.values):
            raise ValueError(f"`{self.field}` values must be canonical vocabulary values, got {self.values}")
        return self


class Not(_Node):
    kind: Literal["not"] = "not"
    child: Node


class And(_Node):
    kind: Literal["and"] = "and"
    children: tuple[Node, ...] = Field(min_length=2)


class Or(_Node):
    kind: Literal["or"] = "or"
    children: tuple[Node, ...] = Field(min_length=2)


Node = Annotated[Term | Wildcard | Phrase | Near | Filter | Not | And | Or, Field(discriminator="kind")]

for _model in (Not, And, Or):
    _model.model_rebuild()


def _strip_spans(x: Any) -> Any:
    if isinstance(x, dict):
        return {k: _strip_spans(v) for k, v in x.items() if k != "span"}
    if isinstance(x, list | tuple):
        return [_strip_spans(v) for v in x]
    return x


def structure(n: Node) -> Any:
    """`n` as plain data without spans: two nodes mean the same query iff their structures are equal."""
    return _strip_spans(n.model_dump())
