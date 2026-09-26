"""The query lexer (spec 02 §Grammar, §Error handling; decision-001; task-011)."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st
from openproceedings.diagnostics import DiagnosticCode
from openproceedings.query.lexer import Kind, Lexeme, lex


def shape(q: str) -> list[str]:
    """A compact, readable rendering of the lexemes: KIND or KIND:detail."""
    out = []
    for x in lex(q).lexemes:
        if x.kind is Kind.WORD:
            out.append(f"WORD:{x.stem}{x.wildcard or ''}")
        elif x.kind is Kind.PHRASE:
            out.append("PHRASE:" + "|".join(f"{p.stem}{p.wildcard or ''}" for p in x.parts))
        elif x.kind is Kind.FIELD:
            out.append(f"FIELD:{x.field}")
        elif x.kind is Kind.NEAR:
            out.append(f"NEAR:{x.near}")
        elif x.kind is Kind.RANGE:
            assert x.range is not None
            out.append(f"RANGE:{x.range[0]}..{x.range[1]}")
        else:
            out.append(x.kind.value)
    return out


GOLDEN: list[tuple[str, list[str]]] = [
    # --- operators are uppercase only; juxtaposition is left to the parser
    ("trust AND calibration", ["WORD:trust", "AND", "WORD:calibration"]),
    ("trust OR reliance", ["WORD:trust", "OR", "WORD:reliance"]),
    ("trust | reliance", ["WORD:trust", "OR", "WORD:reliance"]),
    ("trust|reliance", ["WORD:trust", "OR", "WORD:reliance"]),
    ("NOT bias", ["NOT", "WORD:bias"]),
    ("trust calibration", ["WORD:trust", "WORD:calibration"]),
    ("trust and calibration", ["WORD:trust", "WORD:and", "WORD:calibration"]),
    ("Or", ["WORD:Or"]),
    ("ANDROID", ["WORD:ANDROID"]),
    # --- `-` negates only at the start of a primary
    ("trust -bias", ["WORD:trust", "NOT", "WORD:bias"]),
    ("-bias", ["NOT", "WORD:bias"]),
    ("(-bias)", ["LPAREN", "NOT", "WORD:bias", "RPAREN"]),
    ('-"large model"', ["NOT", "PHRASE:large|model"]),
    ("-(a OR b)", ["NOT", "LPAREN", "WORD:a", "OR", "WORD:b", "RPAREN"]),
    ("-title:x", ["NOT", "FIELD:title", "WORD:x"]),
    ("--x", ["NOT", "WORD:-x"]),  # one negation; the rest is a word
    ("vision-language", ["WORD:vision-language"]),
    (
        "a - b",
        ["WORD:a", "WORD:-", "WORD:b"],
    ),  # a lone `-` is a word (it normalises to nothing: parser error)
    ("x-", ["WORD:x-"]),
    # --- parentheses
    ("(a OR b) c", ["LPAREN", "WORD:a", "OR", "WORD:b", "RPAREN", "WORD:c"]),
    ("a(b)", ["WORD:a", "LPAREN", "WORD:b", "RPAREN"]),
    ("((", ["LPAREN", "LPAREN"]),
    # --- fields: letters then a colon at the start of a primary; names are case-insensitive
    ("title:trust", ["FIELD:title", "WORD:trust"]),
    ("Title:trust", ["FIELD:title", "WORD:trust"]),
    ("abstract:(a OR b)", ["FIELD:abstract", "LPAREN", "WORD:a", "OR", "WORD:b", "RPAREN"]),
    ('title:"trust in AI"', ["FIELD:title", "PHRASE:trust|in|AI"]),
    ("venue:NeurIPS", ["FIELD:venue", "WORD:NeurIPS"]),
    ("year:2020..2026", ["FIELD:year", "RANGE:2020..2026"]),
    ("year:2024", ["FIELD:year", "WORD:2024"]),
    ("track:datasets_benchmarks", ["FIELD:track", "WORD:datasets_benchmarks"]),
    ("gpt-4:turbo", ["WORD:gpt-4:turbo"]),  # a colon after a non-letter is part of the word
    ("4:3", ["WORD:4:3"]),
    # --- NEAR/n
    ("trust NEAR/3 calibration", ["WORD:trust", "NEAR:3", "WORD:calibration"]),
    ("a NEAR/0 b", ["WORD:a", "NEAR:0", "WORD:b"]),
    ("NEAR", ["WORD:NEAR"]),
    ("near/3", ["WORD:near/3"]),
    # --- ranges
    ("2020..2026", ["RANGE:2020..2026"]),
    ("2020..", ["WORD:2020.."]),
    # --- phrases: straight or curly quotes; parts split on whitespace; operators inside are literal
    ('"trust in AI"', ["PHRASE:trust|in|AI"]),
    ("“trust in AI”", ["PHRASE:trust|in|AI"]),
    ('"a OR b"', ["PHRASE:a|OR|b"]),
    ('"(x)"', ["PHRASE:(x)"]),
    ('""', ["PHRASE:"]),
    ('a"b c"d', ["WORD:a", "PHRASE:b|c", "WORD:d"]),
    ('"G\\"odel prize"', ['PHRASE:G\\"odel|prize']),  # an escaped quote does not close the phrase
    # --- wildcards: a suffix `*` or `$`; `$` inside LaTeX math is not a wildcard
    ("benchmark*", ["WORD:benchmark*"]),
    ("model$", ["WORD:model$"]),
    ("gpt-4*", ["WORD:gpt-4*"]),
    ('"large language model$"', ["PHRASE:large|language|model$"]),  # decision-001 rule 2
    ('"trust* calibrat*"', ["PHRASE:trust*|calibrat*"]),
    ("$\\epsilon$", ["WORD:$\\epsilon$"]),  # an even number of `$`: math, not a wildcard
    ("$\\epsilon$-DP", ["WORD:$\\epsilon$-DP"]),
    ("$x$abc$", ["WORD:$x$abc$"]),  # odd: the last `$` is a wildcard on the stem `$x$abc`
    ("bench\\*", ["WORD:bench\\*"]),  # an escaped `*` is not a wildcard
    # --- backslash escapes keep the next character in the word
    ('G\\"odel', ['WORD:G\\"odel']),
    ("a\\(b", ["WORD:a\\(b"]),
    ("a\\|b", ["WORD:a\\|b"]),
    # --- whitespace of any kind separates
    ("a b　c\td", ["WORD:a", "WORD:b", "WORD:c", "WORD:d"]),
    ("", []),
    ("   ", []),
]


@pytest.mark.parametrize(("q", "expected"), GOLDEN, ids=[repr(q) for q, _ in GOLDEN])
def test_golden(q: str, expected: list[str]) -> None:
    assert shape(q) == expected


@pytest.mark.parametrize(
    "q",
    [q for q, _ in GOLDEN if not any(s in q for s in ("*", "NEAR/", '"', "“"))],
)
def test_golden_inputs_without_errors_have_none(q: str) -> None:
    assert lex(q).errors == []


ERRORS: list[tuple[str, DiagnosticCode, tuple[int, int]]] = [
    # decision-001 rule 1: `$` and `*` need a stem of 3 letters or digits after normalisation
    ("a$", DiagnosticCode.WILDCARD_STEM_TOO_SHORT, (0, 2)),
    ("ab*", DiagnosticCode.WILDCARD_STEM_TOO_SHORT, (0, 3)),
    ("x ab*", DiagnosticCode.WILDCARD_STEM_TOO_SHORT, (2, 5)),
    ("*", DiagnosticCode.WILDCARD_STEM_TOO_SHORT, (0, 1)),
    ("--*", DiagnosticCode.WILDCARD_STEM_TOO_SHORT, (1, 3)),
    ("a-b*", DiagnosticCode.WILDCARD_STEM_TOO_SHORT, (0, 4)),
    ('"large ab*"', DiagnosticCode.WILDCARD_STEM_TOO_SHORT, (7, 10)),
    ("ben*mark", DiagnosticCode.PARSE_WILDCARD_NOT_SUFFIX, (3, 4)),
    ("bench**", DiagnosticCode.PARSE_WILDCARD_NOT_SUFFIX, (5, 6)),
    ('"ben*mark x"', DiagnosticCode.PARSE_WILDCARD_NOT_SUFFIX, (4, 5)),
    ('"trust in AI', DiagnosticCode.PARSE_UNTERMINATED_PHRASE, (0, 12)),
    ('a "', DiagnosticCode.PARSE_UNTERMINATED_PHRASE, (2, 3)),
    ("a NEAR/ b", DiagnosticCode.PARSE_BAD_NEAR, (2, 7)),
    ("a NEAR/x b", DiagnosticCode.PARSE_BAD_NEAR, (2, 8)),
    ("foo:bar", DiagnosticCode.FIELD_UNKNOWN, (0, 4)),
    ("intitle:trust", DiagnosticCode.FIELD_UNKNOWN, (0, 8)),
]


@pytest.mark.parametrize(("q", "code", "span"), ERRORS, ids=[repr(q) for q, *_ in ERRORS])
def test_error_code_and_span(q: str, code: DiagnosticCode, span: tuple[int, int]) -> None:
    errors = lex(q).errors
    assert [(e.code, e.span) for e in errors] == [(code, span)]
    assert "`" in errors[0].message  # quotes the offending text and says how to fix it


def test_messages_carry_a_fix_hint() -> None:
    assert "bench*" in lex("be*").errors[0].message or "longer stem" in lex("be*").errors[0].message
    assert "closing" in lex('"a').errors[0].message
    assert "NEAR/3" in lex("a NEAR/x b").errors[0].message
    assert "title" in lex("foo:x").errors[0].message and "venue" in lex("foo:x").errors[0].message


def test_long_enough_stems_are_fine() -> None:
    for q in ("gpt-4*", "vision-lang*", "naï*", "abc*", "abc$", "4o-m*"):
        assert lex(q).errors == [], q


def test_a_bad_near_is_dropped_so_the_parser_sees_the_rest() -> None:
    assert shape("a NEAR/x b") == ["WORD:a", "WORD:b"]


def test_an_unknown_field_is_still_a_field_lexeme() -> None:
    assert shape("foo:bar") == ["FIELD:foo", "WORD:bar"]


def test_an_unterminated_phrase_runs_to_the_end() -> None:
    assert shape('"trust in AI') == ["PHRASE:trust|in|AI"]


# --- WARN_LOWERCASE_OPERATOR: only where an operator would have made sense, i.e. between terms
LOWERCASE = [
    ("trust or reliance", [(6, 8)]),
    ("trust and reliance", [(6, 9)]),
    ("trust not bias", [(6, 9)]),
    ("(a) or b", [(4, 6)]),
    ('a or "b c"', [(2, 4)]),
    ("a NEAR/2 b near/3 c", [(11, 17)]),
    ("or trust", []),  # first: not between terms
    ("trust or", []),
    ("a OR or", []),
    ('"a or b"', []),  # inside a phrase it is plainly a word
    ("a oregon b", []),
]


@pytest.mark.parametrize(("q", "spans"), LOWERCASE, ids=[q for q, _ in LOWERCASE])
def test_lowercase_operator_warning(q: str, spans: list[tuple[int, int]]) -> None:
    result = lex(q)
    assert [(w.code, w.span) for w in result.warnings] == [
        (DiagnosticCode.WARN_LOWERCASE_OPERATOR, s) for s in spans
    ]
    assert result.errors == []


def test_lowercase_warning_says_what_to_write() -> None:
    assert "`OR`" in lex("a or b").warnings[0].message
    assert "`NEAR/3`" in lex("a near/3 b").warnings[0].message


def test_spans_and_text_agree() -> None:
    q = 'title:"trust in AI" OR -bench*'
    for x in lex(q).lexemes:
        assert q[x.start : x.end] == x.text
    phrase = lex(q).lexemes[1]
    assert [(q[p.start : p.end], p.wildcard) for p in phrase.parts] == [
        ("trust", None),
        ("in", None),
        ("AI", None),
    ]
    word = lex(q).lexemes[-1]
    assert (word.text, word.stem, word.wildcard) == ("bench*", "bench", "*")


def test_lexeme_is_frozen() -> None:
    x = lex("a").lexemes[0]
    with pytest.raises(AttributeError):
        x.start = 3  # type: ignore[misc]
    assert isinstance(x, Lexeme)


FRAGMENTS = [
    *'ab()|-"“”\\*$:.é \U0001f600 ',
    *("AND", "OR", "NOT", "NEAR/3", "NEAR/", "or", "and", "title:", "year:", "foo:", "2020..2024"),
]
QUERYISH = st.lists(st.sampled_from(FRAGMENTS), max_size=20).map("".join)


@given(st.one_of(st.text(max_size=40), QUERYISH))
def test_random_input_never_raises_and_spans_are_sound(q: str) -> None:
    result = lex(q)  # never raises: bad input is a diagnostic
    prev_end = 0
    covered: set[int] = set()
    for x in result.lexemes:
        assert prev_end <= x.start <= x.end <= len(q)
        assert q[x.start : x.end] == x.text
        prev_end = x.end
        covered.update(range(x.start, x.end))
        for p in x.parts:
            assert x.start <= p.start <= p.end <= x.end and q[p.start : p.end] == p.text
    for d in result.errors + result.warnings:
        assert d.span is not None and d.span[1] <= len(q)
        covered.update(range(*d.span))
    # every visible character belongs to some lexeme or to an error that explains it
    assert all(i in covered for i, c in enumerate(q) if not c.isspace())
