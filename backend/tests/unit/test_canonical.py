"""Canonical form and canonical_hash (spec 02 §Outputs; decision-001 rule 5; task-013)."""

from __future__ import annotations

import hashlib

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st
from openproceedings.query import QUERY_VERSION
from openproceedings.query.ast import structure
from openproceedings.query.canonical import canonical_hash, canonicalize, render
from openproceedings.query.normalize import TOKENIZER_VERSION
from openproceedings.query.parser import parse


def canon(q: str) -> str:
    """The canonical form of the tree as typed (default filters are task-014's, in test_defaults.py)."""
    result = parse(q)
    assert result.errors == [], result.errors
    assert result.ast is not None
    return render(canonicalize(result.ast))


GOLDEN: list[tuple[str, str]] = [
    ("trust", "trust"),
    ("Trust", "trust"),
    ("trust calibration", "(trust AND calibration)"),
    ("a b c", "(a AND b AND c)"),
    ("(a b) c", "(a AND b AND c)"),  # AND is flattened
    ("a (b c)", "(a AND b AND c)"),
    ("a | b OR c", "(a OR b OR c)"),
    ("(a OR b) OR c", "(a OR b OR c)"),
    ("a b OR c", "((a AND b) OR c)"),
    ("a -b", "(a AND NOT b)"),
    ("NOT (a OR b) c", "(NOT (a OR b) AND c)"),
    ("a NOT NOT b", "(a AND NOT NOT b)"),
    ("vision-language", '"vision language"'),
    ('"trust in AI"', '"trust in ai"'),
    ('"trust"', "trust"),
    ("benchmark*", "benchmark*"),
    ("model$", "model$"),
    ('"large language model$"', '"large language model$"'),
    ('"trust* calibration"', '"trust* calibration"'),
    # a short last stem is hyphen-joined to what precedes it, so the canonical string re-parses (decision-001)
    ("gpt-4*", '"gpt-4*"'),
    ("a-b-c*", '"a-b-c*"'),
    ('"use gpt-4o*"', '"use gpt-4o*"'),
    ('"x gpt-4* y"', '"x gpt-4* y"'),
    ("title:(a OR b)", "(title:a OR title:b)"),
    ('abstract:"trust in AI"', 'abstract:"trust in ai"'),
    ("title:gpt-4*", 'title:"gpt-4*"'),
    ("a NEAR/3 b", "(a NEAR/3 b)"),
    ("title:(a NEAR/3 b)", "(title:a NEAR/3 title:b)"),
    # filters: after the text, ordered venue, year, track, status, then others alphabetically; values sorted
    (
        "status:accepted track:main year:2024 venue:ICLR trust",
        "(trust AND venue:ICLR AND year:2024 AND track:main AND status:accepted)",
    ),
    ("venue:(NeurIPS OR ICLR)", "venue:(ICLR OR NeurIPS)"),
    ("venue:(icml | ICLR | ICML)", "venue:(ICLR OR ICML)"),  # deduplicated
    ("year:(2024 OR 2019..2021)", "year:(2019..2021 OR 2024)"),
    ("track:(workshop OR main)", "track:(main OR workshop)"),
    ("trust NOT track:workshop venue:ICLR", "(trust AND venue:ICLR AND NOT track:workshop)"),
    ("trust track:main NOT track:workshop", "(trust AND track:main AND NOT track:workshop)"),
    (
        "(venue:ICML OR venue:ICLR) trust",
        "(trust AND venue:(ICLR OR ICML))",
    ),  # a single-field OR group merges
    ("(venue:ICLR OR track:main) trust", "((venue:ICLR OR track:main) AND trust)"),  # mixed fields: untouched
    ("(a venue:ICLR) OR b", "((a AND venue:ICLR) OR b)"),  # filters sort within every AND
    # a lone token spelling a lowercase operator is quoted, so the canonical string raises no warning
    ('trust "and" calibration', '(trust AND "and" AND calibration)'),
    ('"or"', '"or"'),
    ('"trust and safety"', '"trust and safety"'),
    ("NOT NOT a b", "(NOT NOT a AND b)"),
]


@pytest.mark.parametrize(("q", "expected"), GOLDEN, ids=[q for q, _ in GOLDEN])
def test_golden(q: str, expected: str) -> None:
    assert canon(q) == expected


@pytest.mark.parametrize("q", [q for q, _ in GOLDEN])
def test_golden_canonical_is_a_fixed_point(q: str) -> None:
    c = canon(q)
    assert canon(c) == c


def test_errors_have_no_canonical() -> None:
    result = parse("a OR")
    assert (result.canonical, result.canonical_hash) == (None, None)


def test_hash_is_sha256_of_canonical_and_tokenizer_version() -> None:
    c = parse("trust calibration").canonical
    assert c is not None
    expected = hashlib.sha256(f"{c}\x00{TOKENIZER_VERSION}".encode()).hexdigest()
    assert canonical_hash(c) == expected == parse("trust calibration").canonical_hash
    assert canonical_hash("a1") != canonical_hash("a")  # the separator keeps (canonical, version) unambiguous


def test_equivalent_queries_hash_equal() -> None:
    same = ["trust venue:ICLR", "venue:iclr Trust", "(trust) AND venue:(ICLR)", "Trust  AND  venue:ICLR"]
    assert len({parse(q).canonical_hash for q in same}) == 1


def test_canonical_strings_reparse_without_warnings() -> None:
    for q in ('trust "and" calibration', '"or" x', "a b c"):
        assert parse(canon(q)).warnings == []


def test_query_version_is_defined() -> None:
    assert QUERY_VERSION == "1"


@pytest.mark.parametrize("q", [q for q, _ in GOLDEN])
def test_ast_to_string_to_ast_is_the_identity(q: str) -> None:
    ast = parse(q).ast
    assert ast is not None
    normal = canonicalize(ast)
    again = parse(render(normal)).ast
    assert again is not None
    assert structure(canonicalize(again)) == structure(normal)


WORDS = st.sampled_from(
    [
        "trust",
        "Calibration",
        "vision-language",
        "gpt-4*",
        "model$",
        "bench*",
        "naïve",
        "GPT-4o",
        "a-b-c*",
        "LLM",
        "x",
    ]
)
PHRASES = st.lists(WORDS, min_size=1, max_size=4).map(lambda ws: '"' + " ".join(ws) + '"')
FILTERS = st.sampled_from(
    [
        "venue:ICLR",
        "venue:(neurips OR ICML)",
        "year:2024",
        "year:2019..2021",
        "track:main",
        "status:accepted",
        "track:(workshop OR main)",
    ]
)


@st.composite
def queries(draw: st.DrawFn, depth: int = 0) -> str:
    leaf = st.one_of(
        WORDS, PHRASES, FILTERS, WORDS.map(lambda w: f"title:{w}"), PHRASES.map(lambda p: f"abstract:{p}")
    )
    if depth >= 3 or draw(st.booleans()):
        return draw(leaf)
    parts = draw(st.lists(queries(depth + 1), min_size=2, max_size=4))
    op = draw(st.sampled_from([" ", " AND ", " OR ", " | "]))
    body = op.join(parts)
    if draw(st.booleans()):
        body = f"({body})"
    if draw(st.integers(0, 4)) == 0:
        body = f"trust NOT {body}"
    if draw(st.integers(0, 5)) == 0:
        body = f"{body} x NEAR/2 y"
    return body


@given(queries())
def test_canonical_is_idempotent(q: str) -> None:
    result = parse(q)
    assume(not result.errors)
    assert result.canonical is not None
    again = parse(result.canonical)
    assert again.errors == [], (q, result.canonical, again.errors)
    assert again.canonical == result.canonical
    assert again.canonical_hash == result.canonical_hash


@given(st.one_of(st.text(max_size=40), queries()))
def test_canonical_of_any_valid_input_reparses_to_the_same_tree(q: str) -> None:
    result = parse(q)
    assume(result.ast is not None)
    assert result.canonical is not None
    again = parse(result.canonical)
    assert again.effective_ast is not None and result.effective_ast is not None, (
        q,
        result.canonical,
        again.errors,
    )
    assert structure(again.effective_ast) == structure(result.effective_ast)
