"""Shared Hypothesis strategies for the query language (property-testing skill; task-017).

`asts()` builds valid trees directly (every node type: terms, wildcards, phrases with wildcard items,
NEAR, filters, NOT, AND, OR), so properties reach shapes that string generators rarely produce.
`queries()` builds query strings. Both draw from VOCABULARY, a small corpus-like token set that includes
the awkward cases: operator words, filter values, digits, marks kept by the tokenizer, CJK.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from hypothesis import strategies as st
from openproceedings.query.ast import (
    And,
    Filter,
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
from openproceedings.query.normalize import normalize
from openproceedings.vocab import STATUSES, TRACKS

_ROWS = [
    json.loads(line)
    for line in (Path(__file__).parent / "fixtures" / "corpus" / "reference-200.jsonl")
    .read_text()
    .splitlines()
]
_FIELD_TOKENS = [normalize(r[f] or "") for r in _ROWS for f in ("title", "abstract")]


def _fixture_vocabulary() -> list[str]:
    """The real term dictionary of the 200-record fixture, so generated queries hit documents."""
    return sorted({t for tokens in _FIELD_TOKENS for t in tokens})


# consecutive tokens that really occur in one field, so phrases and NEAR operands match something
NGRAMS = sorted(
    {tuple(ts[i : i + k]) for ts in _FIELD_TOKENS for k in (2, 3) for i in range(len(ts) - k + 1)}
)
# real strict prefixes (`benchmar*`, `relian*`) as well as whole words
PREFIXES = sorted({t[:n] for t in _fixture_vocabulary() if len(t) >= 5 for n in range(3, len(t))})


VOCABULARY = [
    *_fixture_vocabulary(),
    *("trust", "trustworthy", "calibration", "benchmark", "benchmarks", "model", "models", "reliance"),
    *("human", "vision", "language", "large", "llm", "llms", "gpt", "4o", "ai", "agent", "safety"),
    *("and", "or", "not", "near", "the", "of"),  # operator words and stopwords are ordinary tokens
    *("neurips", "iclr", "main", "workshop", "accepted", "2024", "2021"),  # filter values as text
    *("naive", "信頼性", "ป่า", "が"),
]
STEMS = [w for w in VOCABULARY if len(w) >= 3] + PREFIXES
SPAN = (0, 0)
FIELDS: list[TextField | None] = [None, "title", "abstract"]


@dataclass(frozen=True)
class Vocab:
    """What trees are drawn from: terms (the rare ones, df 1-3, drawn a third of the time), wildcard stems
    (one in twenty from `wide`, stems past the 200-term cap, so refusals are exercised), and n-grams that
    occur (so phrases and NEAR match)."""

    terms: tuple[str, ...]
    stems: tuple[str, ...]
    ngrams: tuple[tuple[str, ...], ...]
    rare: tuple[str, ...] = ()
    wide: tuple[str, ...] = ()

    def term(self) -> st.SearchStrategy[str]:
        return _mixed(self.terms, self.rare, 3)

    def stem(self) -> st.SearchStrategy[str]:
        return _mixed(self.stems, self.wide, 20)


def _mixed(common: tuple[str, ...], special: tuple[str, ...], one_in: int) -> st.SearchStrategy[str]:
    if not special:
        return st.sampled_from(common)
    return st.integers(0, one_in - 1).flatmap(lambda k: st.sampled_from(special if k == 0 else common))


FIXTURE = Vocab(tuple(VOCABULARY), tuple(STEMS), tuple(NGRAMS))


def _term(token: str, field: TextField | None = None) -> Term:
    return Term(span=SPAN, token=token, field=field)


def _wildcard(stem: str, op: str, field: TextField | None = None) -> Wildcard:
    return Wildcard(span=SPAN, stem=stem, op="*" if op == "*" else "$", field=field)


@st.composite
def leaves(
    draw: st.DrawFn, field: TextField | None = None, vocab: Vocab = FIXTURE
) -> Term | Wildcard | Phrase:
    kind = draw(st.sampled_from(["term", "wildcard", "phrase", "phrase"]))
    if kind == "term":
        return _term(draw(vocab.term()), field)
    if kind == "wildcard":
        return _wildcard(draw(vocab.stem()), draw(st.sampled_from("*$")), field)
    words = list(
        draw(st.one_of(st.sampled_from(vocab.ngrams), st.lists(vocab.term(), min_size=2, max_size=4)))
    )
    items: list[Term | Wildcard] = [_term(w) for w in words]
    if draw(st.booleans()):  # a wildcard item, at any position (decision-001)
        i = draw(st.integers(0, len(items) - 1))
        items[i] = _wildcard(draw(vocab.stem()), draw(st.sampled_from("*$")))
    return Phrase(span=SPAN, items=tuple(items), field=field)


@st.composite
def filters(draw: st.DrawFn) -> Filter:
    field = draw(st.sampled_from(["venue", "year", "track", "status"]))
    if field == "year":
        values: list[str | YearRange] = [
            YearRange(lo=lo, hi=lo + span)
            for lo, span in draw(
                st.lists(st.tuples(st.integers(2018, 2026), st.integers(0, 3)), min_size=1, max_size=3)
            )
        ]
    else:
        pool = {
            "venue": ["NeurIPS", "ICLR", "ICML"],
            "track": list(TRACKS),
            "status": list(STATUSES),
        }[field]
        values = list(draw(st.lists(st.sampled_from(pool), min_size=1, max_size=3)))
    return Filter(span=SPAN, field=field, values=tuple(values))  # type: ignore[arg-type]


@st.composite
def _node(draw: st.DrawFn, depth: int, vocab: Vocab = FIXTURE) -> Node:
    options = ["leaf", "near", "filter"] + (["not", "and", "or"] if depth < 3 else [])
    kind = draw(st.sampled_from(options))
    if kind == "leaf":
        return draw(leaves(draw(st.sampled_from(FIELDS)), vocab))
    if kind == "near":
        field = draw(st.sampled_from(FIELDS))
        return Near(
            span=SPAN,
            left=draw(leaves(field, vocab)),
            right=draw(leaves(field, vocab)),
            distance=draw(st.integers(0, 5)),
        )
    if kind == "filter":
        return draw(filters())
    if kind == "not":
        return Not(span=SPAN, child=draw(_node(depth + 1, vocab)))
    children = tuple(draw(st.lists(_node(depth + 1, vocab), min_size=2, max_size=3)))
    return And(span=SPAN, children=children) if kind == "and" else Or(span=SPAN, children=children)


@st.composite
def negative_asts(draw: st.DrawFn, vocab: Vocab = FIXTURE) -> Node:
    """A tree with no positive part (NOT x, or an OR with a negated branch): must be PARSE_ALL_NEGATIVE."""
    negated = Not(span=SPAN, child=draw(_node(1, vocab)))
    if draw(st.booleans()):
        return negated
    return Or(span=SPAN, children=(draw(_node(1, vocab)), negated))


def engine_asts(vocab: Vocab = FIXTURE) -> st.SearchStrategy[Node]:
    """Any tree an engine may be handed: parser-valid ones, and bare or all-negative ones the parser would
    refuse (an engine takes any AST; spec 03 §Two engines, one contract)."""
    return st.one_of(asts(vocab), _node(0, vocab), negative_asts(vocab))


@st.composite
def asts(draw: st.DrawFn, vocab: Vocab = FIXTURE) -> Node:
    """A valid tree with a positive part (a term ANDed in front), so its canonical string parses."""
    anchor = _term(draw(vocab.term()))
    return And(span=SPAN, children=(anchor, draw(_node(0, vocab))))


WORDS = st.sampled_from(
    ["trust", "Calibration", "vision-language", "gpt-4*", "model$", "bench*", "naïve", "GPT-4o", "x"]
)
PHRASES = st.lists(WORDS, min_size=1, max_size=4).map(lambda ws: '"' + " ".join(ws) + '"')
FILTER_STRINGS = st.sampled_from(
    ["venue:ICLR", "venue:(neurips OR ICML)", "year:2024", "year:2019..2021", "track:main", "status:accepted"]
)


@st.composite
def queries(draw: st.DrawFn, depth: int = 0) -> str:
    """Query strings: words, phrases, fielded terms, filters, NOT, NEAR, and nested AND/OR groups."""
    leaf = st.one_of(
        WORDS,
        PHRASES,
        FILTER_STRINGS,
        WORDS.map(lambda w: f"title:{w}"),
        PHRASES.map(lambda p: f"abstract:{p}"),
    )
    if depth >= 3 or draw(st.booleans()):
        return draw(leaf)
    parts = draw(st.lists(queries(depth + 1), min_size=2, max_size=4))
    body = draw(st.sampled_from([" ", " AND ", " OR ", " | "])).join(parts)
    if draw(st.booleans()):
        body = f"({body})"
    if draw(st.integers(0, 4)) == 0:
        body = f"trust NOT {body}"
    if draw(st.integers(0, 5)) == 0:
        body = f"{body} x NEAR/2 y"
    return body
