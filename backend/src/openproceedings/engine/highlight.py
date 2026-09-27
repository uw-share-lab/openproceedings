"""Highlights from the AST (spec 03 §Highlights, spec 04 span units; task-027).

For one record the query matched, the spans of exactly what matched it, per text field: half-open
`[start, end)` ranges of Unicode code points over the raw stored title or abstract, from `tokenize`'s offset
map (never over normalised text, whose lengths NFKC can change). Never from a snippet generator.

What counts as "what matched" (the evaluation is written out here, and a test checks its verdict against
ReferenceEngine's on every record):
- a term or an expanded wildcard term: each token it matches, in the fields it searches;
- a phrase: one span per occurrence, from its first token's start to its last token's end;
- NEAR: each operand occurrence that is part of a pair within the distance, and nothing between them;
- AND: its children's spans; OR: the spans of the children that matched, so a branch that didn't match
  lights nothing; NOT and filters: nothing (they match by absence or by metadata, not by text).
Overlapping spans are merged; touching ones stay apart (an operator token touches its neighbours: `5×3`).
A LaTeX math command's span is its name without the backslash (`$\\alpha$` lights `alpha`), and accent
markup that opens a word is in the word's span (`\\"{O}del` lights all of it), as tokenize's offsets give.
"""

from __future__ import annotations

from bisect import bisect_left
from collections.abc import Iterable

from openproceedings.diagnostics import DiagnosticCode
from openproceedings.engine.protocol import EngineInternalError, Expansions, Searchable
from openproceedings.query.ast import (
    And,
    Filter,
    Leaf,
    Near,
    Node,
    Not,
    Or,
    Phrase,
    Term,
    TextField,
    Wildcard,
    YearRange,
)
from openproceedings.query.normalize import Token, tokenize
from openproceedings.vocab import TEXT_FIELDS

Spans = dict[TextField, set[tuple[int, int]]]


def highlights(
    ast: Node, record: Searchable, expansions: Expansions
) -> dict[TextField, list[tuple[int, int]]]:
    """Each text field's highlight spans for `record`, one of the engine's hits: sorted, every field present,
    possibly empty. `expansions` are the engine's (`Engine.expansions(ast)`). A hit this evaluation doesn't
    match means the engine and the AST disagree: an internal error, never silently empty highlights."""
    tokens = {f: tokenize(_text(record, f)) for f in TEXT_FIELDS}
    matched, spans = _Highlighter(record, tokens, expansions).node(ast)
    if not matched:
        raise EngineInternalError(
            DiagnosticCode.API_INTERNAL, "a hit the query doesn't match: engine disagreement"
        )
    return {f: _merged(spans.get(f, set())) for f in TEXT_FIELDS}


class _Highlighter:
    def __init__(
        self, record: Searchable, tokens: dict[TextField, list[Token]], expansions: Expansions
    ) -> None:
        self.record = record
        self.tokens = tokens
        self.expansions = expansions

    def node(self, n: Node) -> tuple[bool, Spans]:
        """Whether `n` matches the record, and the spans that make it match. A node that doesn't match has no
        spans, whatever its kind: that one rule is why an AND with a missing child, or an OR branch that
        didn't match, lights nothing."""
        matched, spans = self.evaluate(n)
        return matched, spans if matched else {}

    def evaluate(self, n: Node) -> tuple[bool, Spans]:
        if isinstance(n, And | Or):
            results = [self.node(c) for c in n.children]
            verdict = all if isinstance(n, And) else any
            return verdict(m for m, _ in results), _union(s for _, s in results)
        if isinstance(n, Not):
            return not self.node(n.child)[0], {}
        if isinstance(n, Filter):
            return self.filter(n), {}
        if isinstance(n, Near):
            return self.near(n)
        spans: Spans = {}
        for f in _fields(n.field):
            found = {self.span(f, a, b) for a, b in self.occurrences(f, n)}
            if found:
                spans[f] = found
        return bool(spans), spans

    def occurrences(self, f: TextField, leaf: Leaf) -> list[tuple[int, int]]:
        """Half-open token-index ranges in field `f` where `leaf` occurs."""
        items: tuple[Term | Wildcard, ...] = leaf.items if isinstance(leaf, Phrase) else (leaf,)
        allowed = [{i.token} if isinstance(i, Term) else set(self.expansions[(i.stem, i.op)]) for i in items]
        texts = [t.text for t in self.tokens[f]]
        k = len(items)
        return [
            (s, s + k) for s in range(len(texts) - k + 1) if all(texts[s + j] in allowed[j] for j in range(k))
        ]

    def near(self, n: Near) -> tuple[bool, Spans]:
        spans: Spans = {}
        for f in _fields(n.field):
            lefts, rights = self.occurrences(f, n.left), self.occurrences(f, n.right)
            found = {self.span(f, *a) for a in _paired(lefts, rights, n.distance)}
            found |= {self.span(f, *b) for b in _paired(rights, lefts, n.distance)}
            if found:
                spans[f] = found
        return bool(spans), spans

    def span(self, f: TextField, first: int, stop: int) -> tuple[int, int]:
        """Raw code-point span of tokens `first` … `stop - 1` of field `f`."""
        return self.tokens[f][first].start, self.tokens[f][stop - 1].end

    def filter(self, n: Filter) -> bool:
        if n.field == "year":
            return any(isinstance(v, YearRange) and v.lo <= self.record.year <= v.hi for v in n.values)
        return str(getattr(self.record, n.field)) in n.values


def _paired(xs: list[tuple[int, int]], ys: list[tuple[int, int]], distance: int) -> list[tuple[int, int]]:
    """The occurrences in `xs` with a partner in `ys`: not overlapping, at most `distance` tokens between
    them, in either order (ReferenceEngine's NEAR). A binary search per occurrence, so a long field full of
    both operands costs O(n log n), never a check of every pair."""
    starts, ends = sorted(y[0] for y in ys), sorted(y[1] for y in ys)

    def some(values: list[int], lo: int, hi: int) -> bool:
        k = bisect_left(values, lo)
        return k < len(values) and values[k] <= hi

    # y after x: y starts in [x.end, x.end + d]; y before x: y ends in [x.start - d, x.start]
    return [x for x in xs if some(starts, x[1], x[1] + distance) or some(ends, x[0] - distance, x[0])]


def _text(record: Searchable, f: TextField) -> str:
    return (record.title if f == "title" else record.abstract) or ""


def _fields(field: TextField | None) -> tuple[TextField, ...]:
    return (field,) if field else TEXT_FIELDS


def _union(parts: Iterable[Spans]) -> Spans:
    out: Spans = {}
    for spans in parts:
        for f, s in spans.items():
            out.setdefault(f, set()).update(s)
    return out


def _merged(spans: set[tuple[int, int]]) -> list[tuple[int, int]]:
    """Sorted, with overlapping spans (a term inside a phrase that also matched) merged into one. Spans that
    only touch stay apart: `5×3` is three tokens with no separator, and `5 times` lights two."""
    out: list[tuple[int, int]] = []
    for s, e in sorted(spans):
        if out and s < out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], e))
        else:
            out.append((s, e))
    return out
