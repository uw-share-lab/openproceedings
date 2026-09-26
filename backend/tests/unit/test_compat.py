"""Scholar / PoP mode (spec 02 §Compatibility input modes; decision-002; task-015, task-005)."""

from __future__ import annotations

from pathlib import Path

import pytest
from openproceedings.diagnostics import DiagnosticCode
from openproceedings.query.canonical import canonicalize, render
from openproceedings.query.compat import SOURCE_ALIASES, source_key
from openproceedings.query.parser import ParseResult, parse

FIXTURES = Path(__file__).parents[1] / "fixtures" / "queries"
C = DiagnosticCode


def protocol() -> dict[str, str]:
    lines = (FIXTURES / "trust-evals.txt").read_text().split("\n")
    return {lines[i][3:]: lines[i + 1] for i in range(len(lines) - 1) if lines[i].startswith("## ")}


def scholar(q: str) -> ParseResult:
    result = parse(q, "scholar")
    assert result.errors == [], result.errors
    return result


@pytest.mark.parametrize("name", list(protocol()))
def test_every_protocol_string_parses_in_scholar_mode(name: str) -> None:
    result = scholar(protocol()[name])
    assert result.mode == "scholar" and result.canonical is not None
    again = parse(result.canonical)  # the canonical string is native syntax
    assert again.errors == [] and again.canonical == result.canonical


def test_the_primary_string_is_pinned() -> None:
    """The review's main string (main-7-most-updated). A change here changes its canonical_hash in every
    saved record: it needs a decision record."""
    result = scholar(protocol()["main-7-most-updated"])
    assert result.canonical == (
        '(("foundation model" OR "large language model" OR llm OR "generative ai") AND '
        '(trustworthiness OR trustworthy OR trust OR "trustworthy ai") AND '
        '(benchmark OR leaderboard OR "evaluation framework") AND venue:(ICLR OR ICML OR NeurIPS) AND '
        "track:(datasets_benchmarks OR main OR position) AND status:accepted)"
    )
    assert [w.code for w in result.warnings] == [C.WARN_SOURCE_PARTIAL] * 2  # PMLR and its long name
    assert [t.code for t in result.translations] == [C.COMPAT_SOURCE_ALIAS] * 9


def test_pop_string_reads_items_as_phrases() -> None:
    """Decision-002: main-2-pop means what main-1 means, apart from its `$` wildcards."""
    pop = scholar(protocol()["main-2-pop"])
    assert pop.canonical is not None and pop.canonical.startswith(
        '(("large language model$" OR llm OR "foundation model$" OR "generative ai$" OR "vision language model$" '
        'OR vlm OR "multimodal model$" OR "ai agent$" OR "text to image model$")'
    )
    phrases = [t for t in pop.translations if t.code is C.COMPAT_POP_PHRASE]
    # 7 AI-system phrases, "trustworthy AI$", "evaluation framework$", "test suite$"
    assert len(phrases) == 10
    assert all(t.span is not None for t in pop.translations)
    assert parse(protocol()["main-2-pop"]).canonical != pop.canonical  # native mode reads it natively


PHRASING = [
    ("(a b | c)", '("a b" OR c)', 1),
    ("a b | c", '("a b" OR c)', 1),
    ("c | a b", '(c OR "a b")', 1),
    ("(a b) | c", "((a AND b) OR c)", 0),  # a group, not a `|` item
    ("a b c", "(a AND b AND c)", 0),  # no `|`: plain juxtaposition
    ("x (a b | c)", '(x AND ("a b" OR c))', 1),
    ("NOT a b | c", "((NOT a AND b) OR c)", 0),  # bounded by NOT, not by `|`: left as written
    ('"a b" | c d', '("a b" OR "c d")', 1),
    ("a OR b c", '(a OR "b c")', 1),  # uppercase OR too, not just `|`
    ("trust a b | c", '("trust a b" OR c)', 1),  # the whole run, as decision-002 states
    ("a or b | c", '((a AND "or" AND b) OR c)', 0),  # a lowercase operator word ends a run (and warns)
]


@pytest.mark.parametrize(("q", "expected", "notices"), PHRASING, ids=[q for q, *_ in PHRASING])
def test_phrase_grouping(q: str, expected: str, notices: int) -> None:
    result = parse(q, "scholar")
    assert result.errors == []
    assert result.ast is not None and render(canonicalize(result.ast)) == expected
    assert len([t for t in result.translations if t.code is C.COMPAT_POP_PHRASE]) == notices


def test_native_mode_does_not_group_or_translate() -> None:
    result = parse("(a b | c)")
    assert result.translations == [] and result.mode == "native"
    assert [e.code for e in parse("source:ICLR").errors] == [C.FIELD_COMPAT_ONLY]


SOURCES = [
    ("source:NeurIPS", "NeurIPS"),
    ("source:Neurips", "NeurIPS"),
    ('source:"Neural Information Processing Systems"', "NeurIPS"),
    ('source:"advances in neural information processing systems"', "NeurIPS"),
    ('source:"ICLR"', "ICLR"),
    ('source:"international conference on learning representations"', "ICLR"),
    ("source:ICML", "ICML"),
    ('source:"international conference on machine learning"', "ICML"),
    ("source:PMLR", "ICML"),
    ("source:”proceedings of machine learning research”", "ICML"),
    ("source:ICLR.", "ICLR"),  # matched after the token contract: punctuation and hyphens split
    ("source:neural-information-processing-systems", "NeurIPS"),
]


@pytest.mark.parametrize(("q", "venue"), SOURCES, ids=[q for q, _ in SOURCES])
def test_source_translates_to_venue(q: str, venue: str) -> None:
    result = scholar(f"trust {q}")
    assert f"venue:{venue}" in (result.canonical or "")
    [note] = [t for t in result.translations if t.code is C.COMPAT_SOURCE_ALIAS]
    assert f"`venue:{venue}`" in note.message
    value = q.removeprefix("source:")
    assert note.span == (13, 13 + len(value))  # the value itself, not `source:` ("trust " is 6, "source:" 7)
    partial = [w for w in result.warnings if w.code is C.WARN_SOURCE_PARTIAL]
    assert len(partial) == (1 if "PMLR" in q or "proceedings" in q else 0)


@pytest.mark.parametrize(
    ("q", "span"),
    [
        ("source:foo", (7, 10)),
        ('source:"neural information"', (7, 27)),
        ("source:neur*", (7, 12)),
        ("source:ICLR*", (7, 12)),
        ('source:"ICLR*"', (7, 14)),  # a wildcard inside a quoted value is not dropped
        ('source:"advances in neural information processing systems$"', (7, 59)),
    ],
)
def test_unknown_source_is_an_error_never_a_substring(q: str, span: tuple[int, int]) -> None:
    result = parse(q, "scholar")
    assert [(e.code, e.span) for e in result.errors] == [(C.FIELD_UNKNOWN_VALUE, span)]
    assert "`neurips`" in result.errors[0].message


def test_or_of_sources_collapses_to_one_venue_clause() -> None:
    result = scholar("x (source:ICLR OR source:PMLR OR source:ICML)")
    assert "venue:(ICLR OR ICML)" in (result.canonical or "")


def test_pop_dollar_notice() -> None:
    result = scholar("model$ x")
    assert [(t.code, t.span) for t in result.translations] == [(C.COMPAT_POP_DOLLAR, (0, 6))]


def test_alias_table_covers_every_corpus_export() -> None:
    names = (FIXTURES / "trust-evals-export-names.txt").read_text().split("\n")
    values = {source_key(n.removesuffix(" 2020-2024")) for n in names if n}
    assert len([n for n in names if n]) == 17
    assert values <= SOURCE_ALIASES.keys(), values - SOURCE_ALIASES.keys()


def test_intitle_hint() -> None:
    assert "`title:`" in parse("intitle:trust", "scholar").errors[0].message


def test_pop_dollar_notices_cover_phrase_items_but_not_source_values() -> None:
    pop = scholar(protocol()["main-2-pop"])
    assert len([t for t in pop.translations if t.code is C.COMPAT_POP_DOLLAR]) == 10
    assert [t.code for t in scholar("model$ source:ICLR").translations] == [
        C.COMPAT_POP_DOLLAR,
        C.COMPAT_SOURCE_ALIAS,
    ]


def test_phrase_notice_span() -> None:
    [note] = parse("(a b | c)", "scholar").translations
    assert note.span == (1, 4)


def test_source_translation_ends_with_its_clause() -> None:
    result = scholar("trust source:ICLR track:workshop")
    assert result.canonical == "(trust AND venue:ICLR AND track:workshop AND status:accepted)"


def test_a_mid_word_dollar_in_a_source_value_is_one_error() -> None:
    assert [e.code for e in parse("source:IC$LR", "scholar").errors] == [C.PARSE_WILDCARD_NOT_SUFFIX]


SCOPE = [
    ("source:ICLR OR PMLR", (15, 19)),
    ('source:ICLR OR "neural information processing systems"', (15, 54)),
]


@pytest.mark.parametrize(("q", "span"), SCOPE, ids=[q for q, _ in SCOPE])
def test_a_bare_source_name_ored_to_a_source_filter_warns(q: str, span: tuple[int, int]) -> None:
    result = scholar(q)
    assert [(w.code, w.span) for w in result.warnings] == [(C.WARN_FILTER_SCOPE, span)]
    assert "source:(" in result.warnings[0].message


def test_a_source_filter_inside_a_text_field_warns_like_venue() -> None:
    assert [w.code for w in scholar("title:(trust source:ICLR)").warnings] == [C.WARN_FILTER_SCOPE]


def test_scholar_mode_does_not_group_around_empty_words() -> None:
    assert [e.code for e in parse("a & b | c", "scholar").errors] == [C.PARSE_EMPTY_TERM]
