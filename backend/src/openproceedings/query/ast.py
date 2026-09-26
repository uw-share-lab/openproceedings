"""The query AST (spec 02 §Outputs): a pydantic discriminated union on `kind`.

Every node keeps the half-open code-point span of the input it came from, so diagnostics and the UI parse
tree point at `q`. Text leaves carry their field (`title`, `abstract`, or None for both); there is no
separate field node. Leaves hold normalised tokens (`normalize.py`), never raw text.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

TextField = Literal["title", "abstract"]
FilterField = Literal["venue", "year", "track", "status", "source"]
Span = tuple[int, int]


class _Node(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    span: Span


class Term(_Node):
    kind: Literal["term"] = "term"
    token: str = Field(min_length=1)
    field: TextField | None = None


class Wildcard(_Node):
    """A suffix wildcard on one normalised token: `*` is zero or more characters, `$` zero or one."""

    kind: Literal["wildcard"] = "wildcard"
    stem: str = Field(min_length=1)
    op: Literal["*", "$"]
    field: TextField | None = None


class Phrase(_Node):
    """Consecutive positions in one field. A wildcard item is expanded at its position (decision-001)."""

    kind: Literal["phrase"] = "phrase"
    items: tuple[Term | Wildcard, ...] = Field(min_length=2)


class Near(_Node):
    """Both operands within `distance` words of each other, in either order, in one field."""

    kind: Literal["near"] = "near"
    left: Term | Wildcard | Phrase
    right: Term | Wildcard | Phrase
    distance: int = Field(ge=0)


class YearRange(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    lo: int
    hi: int


class Filter(_Node):
    """`field:` restricted to any of `values` (a single-field OR group). `year` values are YearRanges."""

    kind: Literal["filter"] = "filter"
    field: FilterField
    values: tuple[str | YearRange, ...] = Field(min_length=1)


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
Leaf = Term | Wildcard | Phrase

for _model in (Not, And, Or):
    _model.model_rebuild()
