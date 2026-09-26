"""The query lexer (spec 02 §Grammar, §Error handling; decision-001; task-011)."""

from __future__ import annotations

import sys
import unicodedata

import pytest
from hypothesis import given
from hypothesis import strategies as st
from openproceedings.diagnostics import DiagnosticCode
from openproceedings.query import lexer
from openproceedings.query.lexer import MAX_NEAR, Kind, Lexeme, lex

C = DiagnosticCode


def _w(x: Lexeme) -> str:
    """A word as `stem` or `stem~wildcard`, so a row pins wildcard detection, not just the text."""
    return f"{x.stem}~{x.wildcard}" if x.wildcard else f"{x.stem}"


def shape(q: str) -> list[str]:
    """A compact, readable rendering of the lexemes: KIND or KIND:detail."""
    out = []
    for x in lex(q).lexemes:
        if x.kind is Kind.WORD:
            out.append(f"WORD:{_w(x)}")
        elif x.kind is Kind.PHRASE:
            out.append("PHRASE:" + "|".join(_w(p) for p in x.parts) + ("" if x.closed else "…"))
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
    ("a|-b", ["WORD:a", "OR", "NOT", "WORD:b"]),
    ('-"large model"', ["NOT", "PHRASE:large|model"]),
    ("-(a OR b)", ["NOT", "LPAREN", "WORD:a", "OR", "WORD:b", "RPAREN"]),
    ("-title:x", ["NOT", "FIELD:title", "WORD:x"]),
    ("title:-x", ["FIELD:title", "NOT", "WORD:x"]),
    ("vision-language", ["WORD:vision-language"]),
    ("x-", ["WORD:x-"]),
    ("(a -)", ["LPAREN", "WORD:a", "WORD:-", "RPAREN"]),  # `-` before `)` is not NOT (and is an error)
    ("a -|b", ["WORD:a", "WORD:-", "OR", "WORD:b"]),
    ("trust －bias", ["WORD:trust", "NOT", "WORD:bias"]),  # full-width hyphen-minus is `-` (NFKC)
    # --- parentheses, including their NFKC look-alikes
    ("(a OR b) c", ["LPAREN", "WORD:a", "OR", "WORD:b", "RPAREN", "WORD:c"]),
    ("a(b)", ["WORD:a", "LPAREN", "WORD:b", "RPAREN"]),
    ("((", ["LPAREN", "LPAREN"]),
    ("（a｜b）", ["LPAREN", "WORD:a", "OR", "WORD:b", "RPAREN"]),
    ("x⁽²⁾", ["WORD:x⁽²⁾"]),  # superscript parentheses are notation, not grouping
    # --- fields: a letter, then letters/digits/_, then a colon; names are case-insensitive
    ("title:trust", ["FIELD:title", "WORD:trust"]),
    ("Title:trust", ["FIELD:title", "WORD:trust"]),
    ("title：trust", ["FIELD:title", "WORD:trust"]),
    ("title: trust", ["FIELD:title", "WORD:trust"]),  # a space after the colon is fine
    ("abstract:(a OR b)", ["FIELD:abstract", "LPAREN", "WORD:a", "OR", "WORD:b", "RPAREN"]),
    ('title:"trust in AI"', ["FIELD:title", "PHRASE:trust|in|AI"]),
    ("venue:NeurIPS", ["FIELD:venue", "WORD:NeurIPS"]),
    ("year:2020..2026", ["FIELD:year", "RANGE:2020..2026"]),
    ("year:2024", ["FIELD:year", "WORD:2024"]),
    ("track:datasets_benchmarks", ["FIELD:track", "WORD:datasets_benchmarks"]),
    ("gpt-4:turbo", ["WORD:gpt-4:turbo"]),  # a colon after a non-field prefix is part of the word
    ("4:3", ["WORD:4:3"]),
    # --- NEAR/n
    ("trust NEAR/3 calibration", ["WORD:trust", "NEAR:3", "WORD:calibration"]),
    ("a NEAR/0 b", ["WORD:a", "NEAR:0", "WORD:b"]),
    (f"a NEAR/{MAX_NEAR} b", ["WORD:a", f"NEAR:{MAX_NEAR}", "WORD:b"]),
    ("NEAR", ["WORD:NEAR"]),
    ("near/3", ["WORD:near/3"]),
    # --- ranges
    ("2020..2026", ["RANGE:2020..2026"]),
    ("2020..", ["WORD:2020.."]),
    # --- phrases: straight, curly, low-9 and full-width double quotes; parts split on any whitespace
    ('"trust in AI"', ["PHRASE:trust|in|AI"]),
    ("“trust in AI”", ["PHRASE:trust|in|AI"]),
    ("„trust in AI“", ["PHRASE:trust|in|AI"]),
    ("＂trust in AI＂", ["PHRASE:trust|in|AI"]),
    ('"a　b"', ["PHRASE:a|b"]),
    ('"a OR b"', ["PHRASE:a|OR|b"]),
    ('"(x)"', ["PHRASE:(x)"]),
    ('""', ["PHRASE:"]),
    ('a"b c"d', ["WORD:a", "PHRASE:b|c", "WORD:d"]),
    ('"G\\"odel prize"', ['PHRASE:G\\"odel|prize']),  # an escaped quote does not close the phrase
    ('"state -of- art"', ["PHRASE:state|-of-|art"]),  # inside a phrase a leading `-` is literal
    # --- wildcards: a suffix `*` or `$`; LaTeX math and currency are not wildcards
    ("benchmark*", ["WORD:benchmark~*"]),
    ("model$", ["WORD:model~$"]),
    ("bench＊", ["WORD:bench~*"]),
    ("gpt-4*", ["WORD:gpt-4~*"]),
    ('"large language model$"', ["PHRASE:large|language|model~$"]),  # decision-001 rule 2
    ('"trust* calibrat*"', ["PHRASE:trust~*|calibrat~*"]),
    ("$\\epsilon$", ["WORD:$\\epsilon$"]),  # math, not a wildcard
    ("$\\epsilon$-DP", ["WORD:$\\epsilon$-DP"]),
    ("$a*b$", ["WORD:$a*b$"]),  # `*` inside math is not a wildcard
    ("$f(x)$-DP", ["WORD:$f(x)$-DP"]),  # math keeps its parentheses
    ("($x$)", ["LPAREN", "WORD:$x$", "RPAREN"]),
    ("US$5", ["WORD:US$5"]),  # a `$` before a digit is currency
    ("bench\\*", ["WORD:bench\\*"]),  # an escaped `*` is not a wildcard
    # --- backslash escapes keep the next character in the word; a backslash before a space does not
    ('G\\"odel', ['WORD:G\\"odel']),
    ("a\\(b", ["WORD:a\\(b"]),
    ("a\\|b", ["WORD:a\\|b"]),
    ("a\\ b", ["WORD:a\\", "WORD:b"]),
    # --- whitespace of any kind separates
    ("a b　c\td", ["WORD:a", "WORD:b", "WORD:c", "WORD:d"]),
    ("😀 trust", ["WORD:😀", "WORD:trust"]),
    ("", []),
    ("   ", []),
]


@pytest.mark.parametrize(("q", "expected"), GOLDEN, ids=[repr(q) for q, _ in GOLDEN])
def test_golden(q: str, expected: list[str]) -> None:
    assert shape(q) == expected


CLEAN = [q for q, _ in GOLDEN if q not in ("(a -)", "a -|b", '""') and not q.startswith("NEAR")]


@pytest.mark.parametrize("q", CLEAN, ids=[repr(q) for q in CLEAN])
def test_golden_inputs_raise_no_errors(q: str) -> None:
    assert lex(q).errors == ()


ERRORS: list[tuple[str, DiagnosticCode, tuple[int, int]]] = [
    # decision-001 rule 1: `$` and `*` need a stem of 3 letters or digits after normalisation
    ("a$", C.WILDCARD_STEM_TOO_SHORT, (0, 2)),
    ("ab*", C.WILDCARD_STEM_TOO_SHORT, (0, 3)),
    ("x ab*", C.WILDCARD_STEM_TOO_SHORT, (2, 5)),
    ("😀 ab*", C.WILDCARD_STEM_TOO_SHORT, (2, 5)),  # code points, not UTF-16 units
    ("*", C.WILDCARD_STEM_TOO_SHORT, (0, 1)),
    ("$", C.WILDCARD_STEM_TOO_SHORT, (0, 1)),
    ("a-b*", C.WILDCARD_STEM_TOO_SHORT, (0, 4)),
    ('"large ab*"', C.WILDCARD_STEM_TOO_SHORT, (7, 10)),
    # a `*`/`$` that is not a suffix (outside math, not currency)
    ("ben*mark", C.PARSE_WILDCARD_NOT_SUFFIX, (3, 4)),
    ("bench**", C.PARSE_WILDCARD_NOT_SUFFIX, (5, 6)),
    ("a*b*cde", C.PARSE_WILDCARD_NOT_SUFFIX, (1, 2)),  # the first one is reported
    ("b*c*", C.PARSE_WILDCARD_NOT_SUFFIX, (1, 2)),  # and the stem length is not checked on top
    ('"ben*mark x"', C.PARSE_WILDCARD_NOT_SUFFIX, (4, 5)),
    ("behavio$r", C.PARSE_WILDCARD_NOT_SUFFIX, (7, 8)),  # Web of Science's mid-word `$`
    ("model$*", C.PARSE_WILDCARD_NOT_SUFFIX, (5, 6)),
    ("model$$", C.PARSE_WILDCARD_NOT_SUFFIX, (5, 6)),
    # a wildcard must directly follow a letter or digit
    ("vision-*", C.PARSE_WILDCARD_DETACHED, (0, 8)),
    ("gpt-$", C.PARSE_WILDCARD_DETACHED, (0, 5)),
    # phrases
    ('"trust in AI', C.PARSE_UNTERMINATED_PHRASE, (0, 12)),
    ('a "', C.PARSE_UNTERMINATED_PHRASE, (2, 3)),
    # NEAR
    ("a NEAR/ b", C.PARSE_BAD_NEAR, (2, 7)),
    ("a NEAR/x b", C.PARSE_BAD_NEAR, (2, 8)),
    (f"a NEAR/{MAX_NEAR + 1} b", C.PARSE_BAD_NEAR, (2, 10)),
    ("trust NEAR calibration", C.PARSE_BAD_NEAR, (6, 10)),  # WoS's bare NEAR
    # fields
    ("foo:bar", C.FIELD_UNKNOWN, (0, 4)),
    ("intitle:trust", C.FIELD_UNKNOWN, (0, 8)),
    ("título:x", C.FIELD_UNKNOWN, (0, 7)),
    ("title2:x", C.FIELD_UNKNOWN, (0, 7)),
    ("title :trust", C.PARSE_STRAY_COLON, (6, 12)),
    # a word that starts with `-`: it would silently mean NOT or a literal hyphen
    ("a - b", C.PARSE_AMBIGUOUS_MINUS, (2, 3)),
    ("--x", C.PARSE_AMBIGUOUS_MINUS, (0, 3)),
    ("--", C.PARSE_AMBIGUOUS_MINUS, (0, 2)),
    ('"large language model"-based', C.PARSE_AMBIGUOUS_MINUS, (22, 28)),
    ("(LLM|VLM)-based", C.PARSE_AMBIGUOUS_MINUS, (9, 15)),
    ('"x"-y', C.PARSE_AMBIGUOUS_MINUS, (3, 5)),
]


@pytest.mark.parametrize(("q", "code", "span"), ERRORS, ids=[repr(q) for q, *_ in ERRORS])
def test_error_code_and_span(q: str, code: DiagnosticCode, span: tuple[int, int]) -> None:
    errors = lex(q).errors
    assert [(e.code, e.span) for e in errors] == [(code, span)]
    assert "`" in errors[0].message  # quotes the offending text and says how to fix it


def test_messages_carry_a_fix_hint() -> None:
    assert "longer stem" in lex("be*").errors[0].message
    assert "closing" in lex('"a').errors[0].message
    assert "NEAR/3" in lex("a NEAR/x b").errors[0].message
    assert "title" in lex("foo:x").errors[0].message and "venue" in lex("foo:x").errors[0].message
    assert "`vision*`" in lex("vision-*").errors[0].message


def test_long_enough_stems_are_fine() -> None:
    for q in ("gpt-4*", "vision-lang*", "naï*", "abc*", "abc$", "4o-m*", "cost$"):
        assert lex(q).errors == (), q


def test_a_bad_near_is_dropped_so_the_parser_sees_the_rest() -> None:
    assert shape("a NEAR/x b") == ["WORD:a", "WORD:b"]


def test_an_unknown_field_is_still_a_field_lexeme() -> None:
    assert shape("foo:bar") == ["FIELD:foo", "WORD:bar"]


def test_an_unterminated_phrase_runs_to_the_end_and_says_so() -> None:
    assert shape('"trust in AI') == ["PHRASE:trust|in|AI…"]


# --- warnings: only where an operator would have made sense
WARNINGS: list[tuple[str, DiagnosticCode, list[tuple[int, int]]]] = [
    ("trust or reliance", C.WARN_LOWERCASE_OPERATOR, [(6, 8)]),
    ("trust and reliance", C.WARN_LOWERCASE_OPERATOR, [(6, 9)]),
    ("trust not bias", C.WARN_LOWERCASE_OPERATOR, [(6, 9)]),
    ("(a) or b", C.WARN_LOWERCASE_OPERATOR, [(4, 6)]),
    ('"b c" or a', C.WARN_LOWERCASE_OPERATOR, [(6, 8)]),  # after a phrase
    ("2020..2021 or a", C.WARN_LOWERCASE_OPERATOR, [(11, 13)]),  # after a range
    ('a or "b c"', C.WARN_LOWERCASE_OPERATOR, [(2, 4)]),  # before a phrase
    ("a or (b)", C.WARN_LOWERCASE_OPERATOR, [(2, 4)]),  # before a group
    ("a or title:b", C.WARN_LOWERCASE_OPERATOR, [(2, 4)]),  # before a field
    ("a or -b", C.WARN_LOWERCASE_OPERATOR, [(2, 4)]),  # before NOT
    ("a or 2020..2021", C.WARN_LOWERCASE_OPERATOR, [(2, 4)]),  # before a range
    ("a NEAR/2 b near/3 c", C.WARN_LOWERCASE_OPERATOR, [(11, 17)]),
    ("or trust", C.WARN_LOWERCASE_OPERATOR, []),  # first: not between terms
    ("trust or", C.WARN_LOWERCASE_OPERATOR, []),
    ("a OR or", C.WARN_LOWERCASE_OPERATOR, []),
    ("a or OR b", C.WARN_LOWERCASE_OPERATOR, []),  # an operator follows, so it isn't between terms
    ('"a or b"', C.WARN_LOWERCASE_OPERATOR, []),  # inside a phrase it is plainly a word
    ("a oregon b", C.WARN_LOWERCASE_OPERATOR, []),
    ("trust −bias", C.WARN_LOOKALIKE_OPERATOR, [(6, 11)]),  # U+2212 minus sign
    ("trust –bias", C.WARN_LOOKALIKE_OPERATOR, [(6, 11)]),  # en dash
    ("‘trust in AI’", C.WARN_LOOKALIKE_OPERATOR, [(0, 6)]),
    ("C++ code", C.WARN_SYMBOLS_DROPPED, [(0, 3)]),
    ("F# code", C.WARN_SYMBOLS_DROPPED, [(0, 2)]),
    ('"C++ code"', C.WARN_SYMBOLS_DROPPED, []),  # phrase parts are not checked
]


@pytest.mark.parametrize(("q", "code", "spans"), WARNINGS, ids=[q for q, *_ in WARNINGS])
def test_warnings(q: str, code: DiagnosticCode, spans: list[tuple[int, int]]) -> None:
    result = lex(q)
    assert [(w.code, w.span) for w in result.warnings] == [(code, s) for s in spans]
    assert result.errors == ()


def test_warnings_say_what_to_write() -> None:
    assert "`OR`" in lex("a or b").warnings[0].message
    assert "`NEAR/3`" in lex("a near/3 b").warnings[0].message
    assert "`-bias`" in lex("a −bias").warnings[0].message
    assert "`c`" in lex("C++").warnings[0].message


def test_spans_and_text_agree() -> None:
    q = 'title:"trust in AI" OR -bench*'
    lexemes = lex(q).lexemes
    for x in lexemes:
        assert q[x.start : x.end] == x.text
    phrase = lexemes[1]
    assert [(q[p.start : p.end], p.wildcard) for p in phrase.parts] == [
        ("trust", None),
        ("in", None),
        ("AI", None),
    ]
    word = lexemes[-1]
    assert (word.text, word.stem, word.wildcard) == ("bench*", "bench", "*")


def test_non_words_carry_no_stem() -> None:
    assert [x.stem for x in lex("( title:a OR NEAR/2 2020..2021 )").lexemes if x.kind is not Kind.WORD] == [
        None
    ] * 6


def test_lexeme_and_result_are_frozen() -> None:
    result = lex("a")
    with pytest.raises(AttributeError):
        result.lexemes[0].start = 3  # type: ignore[misc]
    assert isinstance(result.lexemes, tuple) and isinstance(result.errors, tuple)


def test_nfkc_lookalike_table_is_derived_from_unicode() -> None:
    """Every character whose NFKC form is a syntax character acts as it, except the deliberate exclusions."""
    syntax = {'"': lexer.QUOTES, "(": lexer.LPARENS, ")": lexer.RPARENS, "|": lexer.PIPES, ":": lexer.COLONS}
    syntax |= {"-": lexer.MINUSES, "*": lexer.STARS, "$": lexer.DOLLARS}
    excluded = set("⁽⁾₍₎")  # super/subscript parentheses are notation
    for cp in range(sys.maxunicode + 1):
        c = chr(cp)
        target = unicodedata.normalize("NFKC", c)
        if c != target and target in syntax and c not in excluded:
            assert c in syntax[target], f"U+{cp:04X} {unicodedata.name(c, '')} should act as {target!r}"


FRAGMENTS = [
    *'ab()|-"“”\\*$:.é \U0001f600 （）－',
    *(
        "AND",
        "OR",
        "NOT",
        "NEAR/3",
        "NEAR/",
        "NEAR",
        "or",
        "and",
        "title:",
        "year:",
        "foo:",
        "2020..2024",
        "$x$",
    ),
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
