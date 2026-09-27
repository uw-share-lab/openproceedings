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


# Near the 2,000-code-point cap: whatever the parser accepts there must have a canonical string that is
# itself an accepted query (decision-008), however much the canonical form adds (defaults, ANDs, prefixes)
NEAR_CAP_PARTS = st.one_of(
    queries(),
    st.integers(0, 99_999).map(lambda i: f"w{i}"),  # distinct words, so deduplication doesn't shrink it
    st.integers(0, 99_999).map(lambda i: f"title:(t{i} OR u{i})"),  # a prefix per leaf in canonical form
    st.sampled_from(["gpt-4*", "abcd⒈", "abcd½*", "(a b) OR c", "track:main", "status:accepted"]),
)


@st.composite
def near_cap_queries(draw: st.DrawFn, low: int = 1_500, high: int = 2_000) -> str:
    """A query of `low`..`high` code points: parts joined by one separator, cut back to fit."""
    target = draw(st.integers(low, high))
    sep = draw(st.sampled_from([" ", " OR ", " AND ", " | "]))
    parts: list[str] = []
    size = 0
    while size < target:
        part = draw(NEAR_CAP_PARTS)
        parts.append(part)
        size += len(part) + len(sep)
    while len(parts) > 1 and len(sep.join(parts)) > high:
        parts.pop()
    return sep.join(parts)


# Filter-clause queries (spec 02 §Filter clauses): every clause shape a facet click may meet (bare, grouped, an
# OR of one field's filters, parenthesised, negated), mixed with words and groups, joined with and without
# spaces so a clause can be followed directly by a group (`track:(main OR workshop)(x OR y)`), and sometimes
# padded toward the 2,000-code-point cap or nested toward the depth limit.
CLAUSE_VALUES: dict[str, tuple[str, ...]] = {
    "venue": ("ICLR", "ICML", "NeurIPS"),
    "track": tuple(TRACKS),
    "status": tuple(STATUSES),
}
CLAUSE_WORDS = st.sampled_from(
    [
        "trust",
        "llm",
        "calibrat*",
        '"language model"',
        "title:agents",
        "abstract:(a OR b)",
        "x",
        "model$",
        "(x OR y)",
    ]
)


@st.composite
def filter_clause_strings(draw: st.DrawFn) -> str:
    field = draw(st.sampled_from(["venue", "track", "status", "year", "track", "status"]))
    if field == "year":
        return draw(st.sampled_from(["year:2021", "year:2020..2022", "year:(2019 OR 2023..2024)"]))
    pool = CLAUSE_VALUES[field]
    values = draw(st.lists(st.sampled_from(pool), min_size=1, max_size=min(3, len(pool)), unique=True))
    if field == "venue" and draw(st.integers(0, 3)) == 0:
        values = [v.lower() for v in values]
    shape = draw(st.sampled_from(["bare", "bare", "grouped", "or", "paren"]))
    if shape == "or" and len(values) > 1:
        return "(" + " OR ".join(f"{field}:{v}" for v in values) + ")"
    if shape == "paren":
        return f"({field}:{values[0]})"
    if shape == "grouped" or len(values) > 1:
        return f"{field}:({' OR '.join(values)})"
    return f"{field}:{values[0]}"


@st.composite
def clause_queries(draw: st.DrawFn, depth: int = 0) -> str:
    """A query built from filter clauses and words (see above)."""
    atom = draw(st.one_of(filter_clause_strings(), filter_clause_strings(), CLAUSE_WORDS))
    atom = draw(st.sampled_from(["", "", "", "", "-", "NOT ", "NOT NOT "])) + atom
    if depth >= 2 or draw(st.booleans()):
        body = atom
    else:
        parts = draw(st.lists(clause_queries(depth + 1), min_size=2, max_size=4))
        body = draw(st.sampled_from([" ", " ", " AND ", " OR ", ""])).join(parts)
        if depth > 0 and draw(st.booleans()):
            body = f"({body})"
    if depth == 0:
        pad = draw(st.integers(0, 19))
        if pad == 0:  # toward the cap: distinct words, so nothing deduplicates
            body += "".join(f" w{i}" for i in range(draw(st.integers(330, 400))))
        elif pad == 1:  # toward the depth limit
            deep = draw(st.integers(58, 64))
            body = "(" * deep + body + ")" * deep
    return body
