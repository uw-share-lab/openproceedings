"""The query parser (spec 02 §Grammar, §Error handling; decision-001; task-012)."""

from __future__ import annotations

from typing import Literal

import pytest
from hypothesis import given
from hypothesis import strategies as st
from openproceedings.diagnostics import DiagnosticCode, by_position, clip
from openproceedings.query.ast import And, Filter, Near, Node, Not, Or, Phrase, Term, Wildcard, YearRange
from openproceedings.query.canonical import canonicalize, render
from openproceedings.query.parser import MAX_DEPTH, MAX_PER_CODE, MAX_QUERY_LENGTH, parse


def show(n: Node) -> str:
    """S-expression rendering: text leaves as `field:token`, groups as `(OP …)`."""
    if isinstance(n, Term):
        return f"{n.field + ':' if n.field else ''}{n.token}"
    if isinstance(n, Wildcard):
        return f"{n.field + ':' if n.field else ''}{n.stem}{n.op}"
    if isinstance(n, Phrase):
        return f'{n.field + ":" if n.field else ""}"' + " ".join(show(i) for i in n.items) + '"'
    if isinstance(n, Near):
        return f"(NEAR/{n.distance} {show(n.left)} {show(n.right)})"
    if isinstance(n, Not):
        return f"(NOT {show(n.child)})"
    if isinstance(n, And | Or):
        return f"({'AND' if isinstance(n, And) else 'OR'} {' '.join(show(c) for c in n.children)})"
    assert isinstance(n, Filter)
    vals = [v if isinstance(v, str) else (str(v.lo) if v.lo == v.hi else f"{v.lo}..{v.hi}") for v in n.values]
    return f"{n.field}:{'|'.join(vals)}"


def parsed(q: str) -> str:
    result = parse(q)
    assert result.errors == [], result.errors
    assert result.ast is not None
    return show(result.ast)


GOLDEN: list[tuple[str, str]] = [
    ("trust", "trust"),
    ("Trust", "trust"),
    ("trust calibration", "(AND trust calibration)"),
    ("trust AND calibration", "(AND trust calibration)"),
    ("a b c", "(AND a b c)"),
    ("a OR b OR c", "(OR a b c)"),
    ("a | b", "(OR a b)"),
    ("(a OR b) c", "(AND (OR a b) c)"),
    ("a (b OR c)", "(AND a (OR b c))"),
    ("((a))", "a"),
    ("a -b", "(AND a (NOT b))"),
    ("a NOT b", "(AND a (NOT b))"),
    ("NOT a b", "(AND (NOT a) b)"),
    ("a NOT (b OR c)", "(AND a (NOT (OR b c)))"),
    ("a NOT NOT b", "(AND a (NOT (NOT b)))"),
    # precedence: NOT > AND > OR (the mixed cases also warn; see below)
    ("a b OR c", "(OR (AND a b) c)"),
    ("a OR b c", "(OR a (AND b c))"),
    ("a AND b OR c AND d", "(OR (AND a b) (AND c d))"),
    # words that normalise to several tokens are phrases; wildcards (decision-001)
    ("vision-language", '"vision language"'),
    ("GPT-4o", '"gpt 4o"'),
    ("benchmark*", "benchmark*"),
    ("model$", "model$"),
    ("gpt-4*", '"gpt 4*"'),
    ('"large language model$"', '"large language model$"'),
    ('"trust in AI"', '"trust in ai"'),
    ('"trust"', "trust"),
    ('"trust - AI"', '"trust ai"'),
    ("$\\epsilon$-DP", '"ε dp"'),
    # text fields push down to the leaves
    ("title:trust", "title:trust"),
    ("title:(a OR b)", "(OR title:a title:b)"),
    ('abstract:"trust in AI"', 'abstract:"trust in ai"'),
    ("title:vision-language", 'title:"vision language"'),
    ("title:bench*", "title:bench*"),
    ("title:(a NOT b)", "(AND title:a (NOT title:b))"),
    # NEAR/n
    ("a NEAR/3 b", "(NEAR/3 a b)"),
    ('"trust in" NEAR/5 calibrat*', '(NEAR/5 "trust in" calibrat*)'),
    ("title:(a NEAR/3 b)", "(NEAR/3 title:a title:b)"),
    ("x a NEAR/3 b", "(AND x (NEAR/3 a b))"),
    ("a NEAR/3 b OR c", "(OR (NEAR/3 a b) c)"),
    # filters
    ("venue:neurips", "venue:NeurIPS"),
    ("venue:(ICLR OR NeurIPS)", "venue:ICLR|NeurIPS"),
    ("venue:(ICLR | icml)", "venue:ICLR|ICML"),
    ("year:2024", "year:2024"),
    ("year:2020..2024", "year:2020..2024"),
    ("year:(2019 OR 2021..2023)", "year:2019|2021..2023"),
    ("track:Workshop", "track:workshop"),
    ("status:accepted", "status:accepted"),
    ("venue:ICLR", "venue:ICLR"),
    ("trust NOT track:workshop", "(AND trust (NOT track:workshop))"),
    ("year:2024..2024", "year:2024"),
    ("year:1000", "year:1000"),
    ("year:²⁰²⁴", "year:2024"),  # NFKC, like every other look-alike (M1 gate)
    ("year:２０２４", "year:2024"),
    ("venue:ＩＣＬＲ", "venue:ICLR"),
    ("venue:İCLR", "venue:ICLR"),
    ("track:ＭＡＩＮ", "track:main"),
    ("NOT NOT a", "(NOT (NOT a))"),  # positive: not all-negative
    ("a OR NOT NOT b", "(OR a (NOT (NOT b)))"),
    ("a NEAR/3 (b)", "(NEAR/3 a b)"),  # a one-word group counts as a word
    ("title: trust", "title:trust"),
    ("title:(trust venue:ICLR)", "(AND title:trust venue:ICLR)"),
    # lowercase operators are words
    ("trust and calibration", "(AND trust and calibration)"),
]


@pytest.mark.parametrize(("q", "expected"), GOLDEN, ids=[q for q, _ in GOLDEN])
def test_golden(q: str, expected: str) -> None:
    assert parsed(q) == expected


def test_decision_001_wildcard_phrases_have_the_wildcard_last() -> None:
    ast = parse("gpt-4*").ast
    assert isinstance(ast, Phrase)
    assert [type(i) for i in ast.items] == [Term, Wildcard]
    assert (ast.items[0].token, ast.items[1].stem, ast.items[1].op) == ("gpt", "4", "*")  # type: ignore[union-attr]
    ast = parse('"large language model$"').ast
    assert isinstance(ast, Phrase) and isinstance(ast.items[-1], Wildcard)
    assert (ast.items[-1].stem, ast.items[-1].op) == ("model", "$")


def test_year_values_are_ranges() -> None:
    ast = parse("year:(2019 OR 2021..2023)").ast
    assert isinstance(ast, Filter) and ast.values == (
        YearRange(lo=2019, hi=2019),
        YearRange(lo=2021, hi=2023),
    )


# Every mixed AND/OR case: (q, mode, [(span, reading)]), one pair per WARN_MIXED_AND_OR in span order. The
# reading is the diagnostic's `reading` field (TASK-099): the text at the span as it was read, which the
# editor's "Load with parentheses" splices over the span.
LONG_OR = " OR ".join(
    f"term{i:02d}" for i in range(24)
)  # > 120 code points: the message clips, `reading` doesn't
MIXED: list[tuple[str, Literal["native", "scholar"], list[tuple[tuple[int, int], str]]]] = [
    ("a b OR c", "native", [((0, 8), "(a b) OR c")]),
    ("a OR b c", "native", [((0, 8), "a OR (b c)")]),
    ("a AND b OR c", "native", [((0, 12), "(a AND b) OR c")]),
    ("x (a b OR c)", "native", [((3, 11), "(a b) OR c")]),  # on the level that mixes, inside the parentheses
    ("a | b c", "native", [((0, 7), "a OR (b c)")]),  # `|` is read as OR
    ("a b\nOR  c", "native", [((0, 9), "(a b) OR c")]),  # the separator is written ` OR `, whatever was typed
    ("a b OR c OR d e", "native", [((0, 15), "(a b) OR c OR (d e)")]),
    ("a NEAR/1 b OR c d", "native", [((0, 17), "a NEAR/1 b OR (c d)")]),  # NEAR is not an AND group
    ("-a b OR c", "native", [((0, 9), "(-a b) OR c")]),
    ("title:a b OR c", "native", [((0, 14), "(title:a b) OR c")]),
    ("title:(a b OR c)", "native", [((7, 15), "(a b) OR c")]),
    ("𝐱 a OR b c", "native", [((0, 10), "(𝐱 a) OR (b c)")]),  # code points: the astral letter is one
    (
        "x (a b OR c) OR y z",
        "native",
        [
            ((0, 19), "(x (a b OR c)) OR (y z)"),
            ((3, 11), "(a b) OR c"),
        ],  # the outer level quotes the inner as typed
    ),
    (f"z {LONG_OR}", "native", [((0, len(LONG_OR) + 2), f"(z term00) OR {LONG_OR[len('term00 OR ') :]}")]),
    ("a AND b OR c", "scholar", [((0, 12), "(a AND b) OR c")]),
    ("trust OR reliance AND calibration", "scholar", [((0, 33), "trust OR (reliance AND calibration)")]),
]


@pytest.mark.parametrize(("q", "mode", "want"), MIXED, ids=[f"{m}:{q[:30]}" for q, m, _ in MIXED])
def test_mixed_and_or_warns_with_its_reading(
    q: str, mode: Literal["native", "scholar"], want: list[tuple[tuple[int, int], str]]
) -> None:
    result = parse(q, mode)
    mixed = sorted(
        (w for w in result.warnings if w.code is DiagnosticCode.WARN_MIXED_AND_OR),
        key=lambda w: w.span or (0, 0),
    )
    assert [(w.span, w.reading) for w in mixed] == want
    assert all("parenthes" in w.message for w in mixed)
    # every other diagnostic has no reading (the model enforces it; this pins what the parser sends)
    assert all(
        d.reading is None for d in result.errors + result.translations + result.warnings if d not in mixed
    )
    for w in mixed:
        assert w.span is not None and w.reading is not None
        loaded = q[: w.span[0]] + w.reading + q[w.span[1] :]
        after = parse(loaded, mode)
        assert after.canonical == result.canonical  # loading the reading never changes what is searched
        assert sum(x.code is DiagnosticCode.WARN_MIXED_AND_OR for x in after.warnings) == len(mixed) - 1


# TASK-140: a mixed level that raised an error while parsing has no faithful reading, so `reading` is null and
# the message quotes the level as typed, not a reading (it once quoted `(a b) OR c` for `a b OR () OR c`,
# silently dropping the failed branch). The span is the whole level, the failed part included.
# (q, mode, level span, the error that part raises)
NO_READING = (
    "`{}` mixes AND and OR without parentheses, and it has errors — fix them first, then add parentheses to "
    "choose how it groups (AND binds tighter than OR)."
)
SCHOLAR_NOTE = " Google Scholar binds OR tighter, so it would have grouped this the other way."
FAILED: list[tuple[str, Literal["native", "scholar"], tuple[int, int], DiagnosticCode]] = [
    ("a b OR () OR c", "native", (0, 14), DiagnosticCode.PARSE_EMPTY_GROUP),
    ('a b OR "" OR c', "native", (0, 14), DiagnosticCode.PARSE_EMPTY_TERM),
    ("a b OR - OR c", "native", (0, 13), DiagnosticCode.PARSE_AMBIGUOUS_MINUS),
    ("a b OR NOT OR c", "native", (0, 15), DiagnosticCode.PARSE_EXPECTED_TERM),
    ("a b OR title: OR c", "native", (0, 18), DiagnosticCode.PARSE_EXPECTED_TERM),
    ("() OR a b", "native", (0, 9), DiagnosticCode.PARSE_EMPTY_GROUP),  # the failed branch first
    # the error inside an AND group's branch: its node's span can stop short of the failed part, so a reading
    # would drop it (`a b () OR c` → `(a b) OR c`, `a b OR c ()` → `(a b) OR (c)`)
    ("a b () OR c", "native", (0, 11), DiagnosticCode.PARSE_EMPTY_GROUP),
    ("a b OR c ()", "native", (0, 11), DiagnosticCode.PARSE_EMPTY_GROUP),
    ("a () b OR c", "native", (0, 11), DiagnosticCode.PARSE_EMPTY_GROUP),
    # a trailing OR is part of the level
    ("a b OR c OR", "native", (0, 11), DiagnosticCode.PARSE_EXPECTED_TERM),
    ("a AND b OR () OR c", "scholar", (0, 18), DiagnosticCode.PARSE_EMPTY_GROUP),
]


@pytest.mark.parametrize(("q", "mode", "span", "error"), FAILED, ids=[f"{m}:{q}" for q, m, _, _ in FAILED])
def test_a_mixed_level_with_errors_quotes_itself_not_a_reading(
    q: str, mode: Literal["native", "scholar"], span: tuple[int, int], error: DiagnosticCode
) -> None:
    result = parse(q, mode)
    assert [e.code for e in result.errors] == [error]
    [w] = [w for w in result.warnings if w.code is DiagnosticCode.WARN_MIXED_AND_OR]
    want = NO_READING.format(q[slice(*span)]) + (SCHOLAR_NOTE if mode == "scholar" else "")
    assert (w.span, w.reading, w.message) == (span, None, want)


def test_nested_levels_with_errors_quote_themselves() -> None:
    """Each level quotes its own text, so the outer and inner warnings read differently."""
    q = "a b OR (c d OR ())"
    mixed = sorted(
        (w for w in parse(q).warnings if w.code is DiagnosticCode.WARN_MIXED_AND_OR), key=by_position
    )
    assert [(w.span, w.reading, w.message) for w in mixed] == [
        ((0, 18), None, NO_READING.format(q)),
        ((8, 17), None, NO_READING.format("c d OR ()")),
    ]


def test_a_long_level_with_errors_is_clipped_like_a_reading() -> None:
    q = f"z {LONG_OR} OR ()"
    [w] = [w for w in parse(q).warnings if w.code is DiagnosticCode.WARN_MIXED_AND_OR]
    assert (w.span, w.reading, w.message) == ((0, len(q)), None, NO_READING.format(clip(q, 120)))


def test_an_error_outside_the_level_keeps_its_reading() -> None:
    """Only an error inside the level withholds the reading: `a b OR c)`'s stray `)` is not part of it."""
    result = parse("a b OR c)")
    assert [e.code for e in result.errors] == [DiagnosticCode.PARSE_UNBALANCED_PAREN]
    [w] = result.warnings
    assert (w.span, w.reading) == ((0, 8), "(a b) OR c")


def test_the_summary_past_the_per_code_cap_has_no_reading() -> None:
    """22 mixed levels: 20 warnings with their readings, then "… and 2 more like these." with none (it stands
    for two levels). The validator allows a null reading on WARN_MIXED_AND_OR, so this parses (it used to 500)."""
    q = " ".join(f"(a{i} b{i} OR c{i})" for i in range(22))
    mixed = [w for w in parse(q).warnings if w.code is DiagnosticCode.WARN_MIXED_AND_OR]
    assert len(mixed) == MAX_PER_CODE + 1
    assert all(w.reading == f"(a{i} b{i}) OR c{i}" for i, w in enumerate(mixed[:MAX_PER_CODE]))
    assert (mixed[-1].message, mixed[-1].reading) == ("… and 2 more like these.", None)


def test_the_message_clips_a_long_reading_but_the_field_does_not() -> None:
    [w] = parse(f"z {LONG_OR}").warnings
    assert w.reading is not None and len(w.reading) > 120
    assert w.reading not in w.message and "…`" in w.message


# TASK-141: query text quoted in a message is one line of visible characters (diagnostics.clip): whitespace runs
# are one space, and a backtick or an invisible character is written as its escape, so a backtick in the query
# can't end the message's quoting early. The span still points at exactly what was typed.
# (q, code, span, message)
QUOTED: list[tuple[str, DiagnosticCode, tuple[int, int], str]] = [
    (
        "a b OR `c`",
        DiagnosticCode.WARN_MIXED_AND_OR,
        (0, 10),
        "AND binds tighter than OR, so this is read as `(a b) OR \\x60c\\x60` — add parentheses if you meant "
        "something else.",
    ),
    (
        "a b OR `c`",
        DiagnosticCode.WARN_LOOKALIKE_OPERATOR,
        (7, 10),
        '`\\x60c\\x60` starts with a single quote, which does not make a phrase — use double quotes: `"…"`.',
    ),
    ("a b\tOR () OR c", DiagnosticCode.WARN_MIXED_AND_OR, (0, 14), NO_READING.format("a b OR () OR c")),
    (
        "x\u2028y OR z w",
        DiagnosticCode.WARN_MIXED_AND_OR,
        (0, 10),
        (
            "AND binds tighter than OR, so this is read as `(x y) OR (z w)` — add parentheses if you meant something "
            "else."
        ),
    ),
    (
        "a b OR c\u202ed",
        DiagnosticCode.WARN_MIXED_AND_OR,
        (0, 10),
        (
            "AND binds tighter than OR, so this is read as `(a b) OR c\\u202ed` — add parentheses if you meant "
            "something else."
        ),
    ),
    (
        "(a\nb",
        DiagnosticCode.PARSE_UNBALANCED_PAREN,
        (0, 1),
        "`(a b` has no closing parenthesis — add `)` where the group ends.",
    ),
    (
        '"trust\x00 in\nmodels',
        DiagnosticCode.PARSE_UNTERMINATED_PHRASE,
        (0, 17),
        'The phrase starting `"trust\\x00 in models` has no closing quote — add a closing `"`.',
    ),
    (
        "venue:IC\x07LR",
        DiagnosticCode.FIELD_UNKNOWN_VALUE,
        (6, 11),
        "`IC\\x07LR` is not a venue (values take no wildcards or quotes) — use one of `NeurIPS`, `ICLR`, `ICML`, `AAAI`, `AIES`, `FAccT`, `IASEAI`.",
    ),
    (
        "trust NEAR/x`y b",
        DiagnosticCode.PARSE_BAD_NEAR,
        (6, 14),
        "`NEAR/x\\x60y` needs a whole-number distance up to 100 — write e.g. `NEAR/3` (at most 3 words apart).",
    ),
]


# A fix hint is text to type back, so it quotes the query only when `clip` shows it as typed: a hint with an
# escape in it (`-foo\x60bar`) would search something else if copied. Then the hint says what to do instead.
HINTS: list[tuple[str, DiagnosticCode, tuple[int, int], str]] = [
    (
        "trust \u2212foo`bar",
        DiagnosticCode.WARN_LOOKALIKE_OPERATOR,
        (6, 14),
        "`\u2212foo\\x60bar` starts with `\u2212`, which is not an operator, so the word is searched — to exclude it, "
        "type an ASCII hyphen `-` in its place.",
    ),
    (
        "trust \u2212foo\u200bbar",
        DiagnosticCode.WARN_LOOKALIKE_OPERATOR,
        (6, 14),
        "`\u2212foo\\u200bbar` starts with `\u2212`, which is not an operator, so the word is searched — to exclude "
        "it, type an ASCII hyphen `-` in its place.",
    ),
    (
        "trust \u2212foo",
        DiagnosticCode.WARN_LOOKALIKE_OPERATOR,
        (6, 10),
        "`\u2212foo` starts with `\u2212`, which is not an operator, so the word is searched — to exclude it, type an "
        "ASCII hyphen: `-foo`.",
    ),
    (
        "trust \xacfoo`bar",
        DiagnosticCode.WARN_LOOKALIKE_OPERATOR,
        (6, 14),
        "`\xac` in `\xacfoo\\x60bar` is searched as the word `neg`, not NOT — to exclude, type `-` in place of `\xac`.",
    ),
    (
        "trust \xacfoo",
        DiagnosticCode.WARN_LOOKALIKE_OPERATOR,
        (6, 10),
        "`\xac` in `\xacfoo` is searched as the word `neg`, not NOT — to exclude, write `-foo`.",
    ),
    (
        "trust vis`ion-*",
        DiagnosticCode.PARSE_WILDCARD_DETACHED,
        (6, 15),
        "The `*` in `vis\\x60ion-*` follows `-`, not a letter or digit, so it would match any word starting `ion` — "
        "put it straight after the stem.",
    ),
    (
        "trust vision-*",
        DiagnosticCode.PARSE_WILDCARD_DETACHED,
        (6, 14),
        "The `*` in `vision-*` follows `-`, not a letter or digit, so it would match any word starting `vision` — put "
        "it straight after the stem, e.g. `vision*`.",
    ),
]
QUOTED += HINTS


@pytest.mark.parametrize(
    ("q", "code", "span", "message"), QUOTED, ids=[ascii(q) + c for q, c, _, _ in QUOTED]
)
def test_quoted_query_text_is_one_line_that_a_backtick_cannot_break(
    q: str, code: DiagnosticCode, span: tuple[int, int], message: str
) -> None:
    result = parse(q)
    found = [(d.span, d.message) for d in result.errors + result.warnings if d.code is code]
    assert (span, message) in found, found
    assert message.count("`") % 2 == 0


def test_mixed_warning_shows_the_reading() -> None:
    assert parse("a b OR c").warnings[0].message == (
        "AND binds tighter than OR, so this is read as `(a b) OR c` — add parentheses if you meant something else."
    )
    assert parse("a AND b OR c", "scholar").warnings[0].message.endswith(SCHOLAR_NOTE)
    assert "`a OR (b c)`" in parse("a OR b c").warnings[0].message


SCOPE = [
    ("year:2023 OR 2024", [(13, 17)]),
    ("venue:ICLR OR NeurIPS", [(14, 21)]),
    ("(venue:ICLR OR icml) trust", [(15, 19)]),
    ("venue:ICLR OR trust", []),
    ("year:2023 OR (trust 2024)", []),  # only a bare branch is flagged
    ("2024 OR trust", []),  # no filter in the OR
    ("year:2023 OR (2024)", [(14, 18)]),  # a parenthesised value too
    ("(venue:ICLR OR year:2023 OR 2024)", [(28, 32)]),  # any filter field in the OR, not just the first
]


def test_filter_inside_a_text_field_warns() -> None:
    result = parse("title:(trust venue:ICLR)")
    assert [(w.code, w.span) for w in result.warnings] == [(DiagnosticCode.WARN_FILTER_SCOPE, (13, 19))]


@pytest.mark.parametrize(("q", "spans"), SCOPE, ids=[q for q, _ in SCOPE])
def test_filter_scope_warning(q: str, spans: list[tuple[int, int]]) -> None:
    result = parse(q)
    assert result.errors == []
    got = [w.span for w in result.warnings if w.code is DiagnosticCode.WARN_FILTER_SCOPE]
    assert got == spans
    if spans:
        assert (
            ":(… OR" in next(w for w in result.warnings if w.code is DiagnosticCode.WARN_FILTER_SCOPE).message
        )


@pytest.mark.parametrize("q", ["a OR b OR c", "(a b) OR c", "a (b OR c)", "a b c", "a NEAR/3 b OR c"])
def test_unmixed_levels_do_not_warn(q: str) -> None:
    assert parse(q).warnings == []


def test_lexer_warnings_come_through() -> None:
    assert [w.code for w in parse("trust or calibration").warnings] == [
        DiagnosticCode.WARN_LOWERCASE_OPERATOR
    ]


ERRORS: list[tuple[str, DiagnosticCode, tuple[int, int]]] = [
    ("", DiagnosticCode.PARSE_EXPECTED_TERM, (0, 0)),
    ("   ", DiagnosticCode.PARSE_EXPECTED_TERM, (0, 3)),
    ("(a", DiagnosticCode.PARSE_UNBALANCED_PAREN, (0, 1)),
    ("a)", DiagnosticCode.PARSE_UNBALANCED_PAREN, (1, 2)),
    ("(a OR (b)", DiagnosticCode.PARSE_UNBALANCED_PAREN, (0, 1)),
    ("()", DiagnosticCode.PARSE_EMPTY_GROUP, (0, 2)),
    ("a ( ) b", DiagnosticCode.PARSE_EMPTY_GROUP, (2, 5)),
    ("a OR", DiagnosticCode.PARSE_EXPECTED_TERM, (2, 4)),
    ("OR a", DiagnosticCode.PARSE_EXPECTED_TERM, (0, 2)),
    ("a AND", DiagnosticCode.PARSE_EXPECTED_TERM, (2, 5)),
    ("a AND AND b", DiagnosticCode.PARSE_EXPECTED_TERM, (2, 5)),
    ("a OR AND b", DiagnosticCode.PARSE_EXPECTED_TERM, (2, 4)),  # one mistake, one error
    ("a OR OR b", DiagnosticCode.PARSE_EXPECTED_TERM, (2, 4)),
    ("a AND OR", DiagnosticCode.PARSE_EXPECTED_TERM, (2, 5)),
    ("(a OR )", DiagnosticCode.PARSE_EXPECTED_TERM, (3, 5)),
    ("a NOT", DiagnosticCode.PARSE_EXPECTED_TERM, (2, 5)),
    ("title:", DiagnosticCode.PARSE_EXPECTED_TERM, (0, 6)),
    ("title:NOT a", DiagnosticCode.PARSE_EXPECTED_TERM, (0, 6)),
    ("2020..2024", DiagnosticCode.PARSE_EXPECTED_TERM, (0, 10)),
    ("NOT a", DiagnosticCode.PARSE_ALL_NEGATIVE, (0, 5)),
    ("-a -b", DiagnosticCode.PARSE_ALL_NEGATIVE, (0, 5)),
    ("a OR NOT b", DiagnosticCode.PARSE_ALL_NEGATIVE, (0, 10)),
    ("NOT venue:ICLR", DiagnosticCode.PARSE_ALL_NEGATIVE, (0, 14)),
    ("year:2026..2020", DiagnosticCode.FIELD_RANGE_INVERTED, (5, 15)),
    ("track:foo", DiagnosticCode.FIELD_UNKNOWN_VALUE, (6, 9)),
    ("venue:NIPS", DiagnosticCode.FIELD_UNKNOWN_VALUE, (6, 10)),
    ("status:accept*", DiagnosticCode.FIELD_UNKNOWN_VALUE, (7, 14)),
    ("year:abc", DiagnosticCode.FIELD_UNKNOWN_VALUE, (5, 8)),
    ("venue:(ICLR AND ICML)", DiagnosticCode.FIELD_FILTER_SYNTAX, (12, 15)),
    ("track:(main OR foo)", DiagnosticCode.FIELD_UNKNOWN_VALUE, (15, 18)),
    ("venue:(ICLR ICML)", DiagnosticCode.FIELD_FILTER_SYNTAX, (12, 16)),
    ("venue:(NOT ICLR)", DiagnosticCode.FIELD_FILTER_SYNTAX, (7, 10)),
    ("venue:()", DiagnosticCode.PARSE_EMPTY_GROUP, (6, 8)),
    ("venue:(ICLR", DiagnosticCode.PARSE_UNBALANCED_PAREN, (6, 7)),
    ("title:(abstract:x)", DiagnosticCode.PARSE_NESTED_FIELD, (7, 16)),
    ("a - b", DiagnosticCode.PARSE_AMBIGUOUS_MINUS, (2, 3)),  # the lexer's; the parser adds nothing
    ("a &", DiagnosticCode.PARSE_EMPTY_TERM, (2, 3)),
    ("title:--", DiagnosticCode.PARSE_AMBIGUOUS_MINUS, (6, 8)),
    ("title:title:a", DiagnosticCode.PARSE_EXPECTED_TERM, (0, 6)),
    ("AND", DiagnosticCode.PARSE_EXPECTED_TERM, (0, 3)),  # one error, not one per loop that sees it
    ("|", DiagnosticCode.PARSE_EXPECTED_TERM, (0, 1)),
    ("AND b", DiagnosticCode.PARSE_EXPECTED_TERM, (0, 3)),
    ("() NEAR/3 a", DiagnosticCode.PARSE_EMPTY_GROUP, (0, 2)),  # the operand's error, not a NEAR one too
    ("a NEAR/3 ()", DiagnosticCode.PARSE_EMPTY_GROUP, (9, 11)),
    ("a NEAR/3 --", DiagnosticCode.PARSE_AMBIGUOUS_MINUS, (9, 11)),
    ("-- NEAR/3 a", DiagnosticCode.PARSE_AMBIGUOUS_MINUS, (0, 2)),
    ("a NEAR/3 b NEAR/2 c NEAR/1 d", DiagnosticCode.PARSE_BAD_NEAR, (11, 17)),
    ("a NEAR/3 NOT b", DiagnosticCode.PARSE_BAD_NEAR, (2, 8)),
    ("NOT ab*", DiagnosticCode.WILDCARD_STEM_TOO_SHORT, (4, 7)),
    ("NOT NOT NOT a", DiagnosticCode.PARSE_ALL_NEGATIVE, (0, 13)),
    ("venue:(bogus) x", DiagnosticCode.FIELD_UNKNOWN_VALUE, (7, 12)),
    (
        '"*"',
        DiagnosticCode.WILDCARD_STEM_TOO_SHORT,
        (1, 2),
    ),  # one error for an empty phrase  # no ALL_NEGATIVE on top of a lexer error
    ("year:0", DiagnosticCode.FIELD_UNKNOWN_VALUE, (5, 6)),
    ("year:2020..99999999999999999999", DiagnosticCode.FIELD_UNKNOWN_VALUE, (5, 31)),
    ("year:2020-2026", DiagnosticCode.FIELD_UNKNOWN_VALUE, (5, 14)),
    ("source:PMLR", DiagnosticCode.FIELD_COMPAT_ONLY, (0, 7)),
    ('source:"neural information processing systems"', DiagnosticCode.FIELD_COMPAT_ONLY, (0, 7)),
    ("source:(PMLR OR NeurIPS) trust", DiagnosticCode.FIELD_COMPAT_ONLY, (0, 7)),
    ("source:2020..2021", DiagnosticCode.FIELD_COMPAT_ONLY, (0, 7)),  # its value is not a second mistake
    ("track:ab*", DiagnosticCode.WILDCARD_STEM_TOO_SHORT, (6, 9)),  # one error for the value, not two
    ('a ""', DiagnosticCode.PARSE_EMPTY_TERM, (2, 4)),
    ("NEAR/3 a", DiagnosticCode.PARSE_BAD_NEAR, (0, 6)),
    ("a NEAR/3", DiagnosticCode.PARSE_BAD_NEAR, (2, 8)),
    ("(a OR b) NEAR/3 c", DiagnosticCode.PARSE_BAD_NEAR, (9, 15)),
    ("a NEAR/3 (b OR c)", DiagnosticCode.PARSE_BAD_NEAR, (2, 8)),
    ("title:a NEAR/3 b", DiagnosticCode.PARSE_BAD_NEAR, (8, 14)),
    ("a NEAR/3 b NEAR/2 c", DiagnosticCode.PARSE_BAD_NEAR, (11, 17)),
    ("a ab*", DiagnosticCode.WILDCARD_STEM_TOO_SHORT, (2, 5)),  # from the lexer
    ("foo:bar", DiagnosticCode.FIELD_UNKNOWN, (0, 4)),
]


@pytest.mark.parametrize(("q", "code", "span"), ERRORS, ids=[q or "<empty>" for q, *_ in ERRORS])
def test_error_code_and_span(q: str, code: DiagnosticCode, span: tuple[int, int]) -> None:
    result = parse(q)
    assert [(e.code, e.span) for e in result.errors] == [(code, span)]
    assert result.ast is None  # non-empty errors ⇒ nothing to search


def test_unknown_field_chains_do_not_recurse() -> None:
    result = parse("x:" * 999 + "a")  # just under the length cap
    assert {e.code for e in result.errors} == {DiagnosticCode.FIELD_UNKNOWN}


def test_resync_after_a_stray_paren_reports_later_errors() -> None:
    assert [(e.code, e.span) for e in parse("a ) b OR").errors] == [
        (DiagnosticCode.PARSE_UNBALANCED_PAREN, (2, 3)),
        (DiagnosticCode.PARSE_EXPECTED_TERM, (6, 8)),
    ]


def test_separate_mistakes_are_each_reported() -> None:
    assert [e.code for e in parse("source:(PMLR").errors] == [
        DiagnosticCode.FIELD_COMPAT_ONLY,
        DiagnosticCode.PARSE_UNBALANCED_PAREN,
    ]
    assert [e.code for e in parse("title:venue:foo").errors] == [
        DiagnosticCode.PARSE_EXPECTED_TERM,
        DiagnosticCode.FIELD_UNKNOWN_VALUE,
    ]


def test_two_empty_phrases_around_near_give_two_errors_and_no_near_error() -> None:
    assert [e.code for e in parse('"" NEAR/3 ""').errors] == [DiagnosticCode.PARSE_EMPTY_TERM] * 2


def test_too_deep_is_an_error_not_a_crash() -> None:
    q = "(" * (MAX_DEPTH + 1) + "a" + ")" * (MAX_DEPTH + 1)
    result = parse(q)
    assert [e.code for e in result.errors] == [DiagnosticCode.PARSE_TOO_DEEP]
    assert parsed("(" * MAX_DEPTH + "a" + ")" * MAX_DEPTH) == "a"
    assert [e.code for e in parse("NOT " * 450 + "a").errors] == [DiagnosticCode.PARSE_TOO_DEEP]


def test_several_errors_are_all_reported_sorted_by_position() -> None:
    result = parse("track:foo (a OR")
    assert [(e.code, e.span) for e in result.errors] == [
        (DiagnosticCode.FIELD_UNKNOWN_VALUE, (6, 9)),
        (DiagnosticCode.PARSE_UNBALANCED_PAREN, (10, 11)),
        (DiagnosticCode.PARSE_EXPECTED_TERM, (13, 15)),
    ]


def test_unknown_values_list_the_valid_ones() -> None:
    assert "datasets_benchmarks" in parse("track:foo").errors[0].message
    assert "NeurIPS" in parse("venue:NIPS").errors[0].message


def test_collapsed_and_inner_spans() -> None:
    assert parse('"trust"').ast.span == (0, 7)  # type: ignore[union-attr]
    ast = parse("gpt-4*").ast
    assert isinstance(ast, Phrase) and ast.items[1].span == (4, 6)
    ast = parse("title:vision-language").ast
    assert isinstance(ast, Phrase) and ast.field == "title" and all(i.field is None for i in ast.items)


def test_spans_include_parentheses_and_field_prefixes() -> None:
    q = "x title:(a OR b)"
    ast = parse(q).ast
    assert isinstance(ast, And)
    assert q[slice(*ast.children[1].span)] == "title:(a OR b)"
    assert q[slice(*ast.span)] == q


QUERYISH = st.lists(
    st.sampled_from(
        [
            *'ab()|-" *$:',
            "AND",
            "OR",
            "NOT",
            "NEAR/3",
            "title:",
            "venue:",
            "year:",
            "2020..2024",
            "ICLR",
            "vision-x",
            "x:",
            "source:",
            "track:",
            "main",
            "--",
            "2024",
        ]
    ),
    max_size=25,
).map(" ".join)


@given(st.one_of(st.text(max_size=40), QUERYISH))
def test_random_input_never_raises(q: str) -> None:
    result = parse(q)
    assert (result.ast is None) == bool(result.errors)
    for d in result.errors + result.warnings:
        assert d.span is not None and 0 <= d.span[0] <= d.span[1] <= len(q)
    if result.ast is not None:
        assert 0 <= result.ast.span[0] <= result.ast.span[1] <= len(q)


BIG = [
    ("a NEAR/" + "9" * 50 + " b", DiagnosticCode.PARSE_BAD_NEAR),
    ("a NEAR/" + "0" * 50 + "3 b", None),  # leading zeros are not significant: NEAR/3
    ("year:1.." + "9" * 50, DiagnosticCode.FIELD_UNKNOWN_VALUE),
    ("year:" + "9" * 50, DiagnosticCode.FIELD_UNKNOWN_VALUE),
    ("1.." + "9" * 50, DiagnosticCode.PARSE_EXPECTED_TERM),
]


@pytest.mark.parametrize(("q", "code"), BIG, ids=[q[:12] for q, _ in BIG])
def test_long_digit_runs_are_diagnostics_never_exceptions(q: str, code: DiagnosticCode | None) -> None:
    assert [e.code for e in parse(q).errors] == ([code] if code else [])


def test_a_long_bare_number_next_to_a_year_filter_is_quoted_not_converted() -> None:
    result = parse("year:2020 OR " + "9" * 50)
    assert result.canonical is not None and '"' + "9" * 50 + '"' not in result.canonical  # not a year value


def test_the_length_cap_is_checked_before_any_work() -> None:
    result = parse("w " * 1001)
    assert [(e.code, e.span) for e in result.errors] == [(DiagnosticCode.PARSE_TOO_LONG, (2000, 2002))]
    assert parse("w " * 1000).errors == []


def test_diagnostics_are_capped_per_code() -> None:
    result = parse("C++ " * 50)
    symbols = [w for w in result.warnings if w.code is DiagnosticCode.WARN_SYMBOLS_DROPPED]
    assert len(symbols) == 21 and symbols[-1].message == "… and 30 more like these."
    assert all(len(d.message) < 200 for d in result.warnings)


def test_messages_quote_at_most_40_characters_of_input() -> None:
    """Every message template, fed a long word, stays bounded (spec 02: no diagnostic grows with the input)."""
    w = "x" * 600
    inputs = [
        "trust −" + w,
        w + "(s)",
        "ab-" + w + "-*",
        w + "* " + w,
        "foo" + w + ":x",
        "a " + w + "$b",
        '"' + w,
        "a NEAR/" + w,
        "a " + w[:3] + "*",
        "track:" + w,
        "venue:" + w,
        "year:" + w,
        "(" + w,
        w + ")",
        "C++" + w,
        "a " + w + " OR b c",
        "and " + w + " or x",
        ":" + w,
        "--" + w,
        '"a"' + w,
        w + '"a"',
        "1.." + w,
        "title:(abstract:" + w + ")",
        "source:" + w,
    ]
    # the longest message has a fixed text (the `source:` list) around one clipped quote of the input: its length
    # with a two-character input quoted, minus those two characters, plus the clip's width, bounds every message
    probe = next(
        d for d in parse("source:qq", "scholar").errors if d.code is DiagnosticCode.FIELD_UNKNOWN_VALUE
    )
    bound = len(probe.message) - len("qq") + len(clip("x" * 1000))
    for q in inputs:
        for mode in ("native", "scholar"):
            result = parse(q[:2000], mode)  # type: ignore[arg-type]
            for d in result.errors + result.warnings + result.translations:
                assert len(d.message) <= bound, (q[:20], d.code, len(d.message), bound)


def test_parsing_is_linear_in_the_query_length() -> None:
    import time

    def cost(q: str) -> float:
        best = float("inf")
        for _ in range(3):
            start = time.thread_time()  # CPU time: other load on a shared runner doesn't count
            parse(q)
            best = min(best, time.thread_time() - start)
        return best

    for unit in (
        "w ",
        "$x ",
        "$a b ",
        "a. b ",
        "a(b)",
        "a|",
        ")a",
    ):  # every lexer-side shape found; `\\((`-like shapes stay out of this ratio check until task-070
        # makes the tokenizer's LaTeX scan linear (they flake under load); the absolute bound below pins the cache
        n = 2000 // len(unit) - 1
        small, large = cost(unit * (n // 5)), cost(unit * n)  # 5x the input
        assert large < small * 15 + 0.01, (unit, small, large)  # quadratic would be ~25x
    for q in ('"' + "$x " * 666 + '"', "a " * 999, "\\((" * 666):  # the last was 11.8 s without run caching
        start = time.perf_counter()
        parse(q, "scholar")
        assert time.perf_counter() - start < 0.5, q[:10]  # was 11 s before the M1 gate fix


def test_a_malformed_filter_group_is_skipped_as_a_whole() -> None:
    result = parse("venue:(iclr (x)) trust")
    assert [e.code for e in result.errors] == [DiagnosticCode.FIELD_FILTER_SYNTAX]
    assert (
        parse("venue:(iclr (x)) trust NOT").errors[-1].code is DiagnosticCode.PARSE_EXPECTED_TERM
    )  # parsing went on


def test_m1_gate_mutant_rows() -> None:
    """Each row kills a mutant that survived the M1 gate's QA pass (P5, P6, P7, C9b, D6)."""
    [mixed] = [w for w in parse("a NEAR/1 b OR c d").warnings if w.code is DiagnosticCode.WARN_MIXED_AND_OR]
    assert "`a NEAR/1 b OR (c d)`" in mixed.message  # the NEAR span covers both operands
    assert mixed.reading == "a NEAR/1 b OR (c d)"
    assert DiagnosticCode.WARN_FILTER_SCOPE not in [w.code for w in parse("year:2023 OR title:2024").warnings]
    assert DiagnosticCode.WARN_FILTER_SCOPE not in [w.code for w in parse("year:2023 OR (2024 -)").warnings]
    tree = parse("year:2020 OR 5").ast
    assert tree is not None and "(year:2020 OR 5)" in render(canonicalize(tree))  # 5 is no year: unquoted
    partial = parse("trust track:main")  # a partial track set is the user's own limit, never the default
    assert partial.defaults == ["status"]
    assert partial.identification_query == "(trust AND track:main)"


def test_a_year_is_at_most_four_digits_alone_or_in_a_range() -> None:
    assert [e.code for e in parse("year:02024").errors] == [DiagnosticCode.FIELD_UNKNOWN_VALUE]
    assert [e.code for e in parse("year:00002020..2024").errors] == [DiagnosticCode.FIELD_UNKNOWN_VALUE]


# A wildcard must directly follow a letter or digit, judged on the folded pieces (spec 02; decision-008
# replaced task-075's raw-character `reach` rule): `abcd⒈*` is `abcd1.*`, so it is detached like `abcd1.*`,
# and a U+0338 on the `.` changes nothing. The message names the piece, and the raw text it came from.
@pytest.mark.parametrize(
    ("q", "piece", "hint"),
    [
        ("abcd⒈*", "`.` (from `⒈`)", "`abcd1*`"),  # DIGIT ONE FULL STOP: `1.`, last piece `.`
        ("abcd⒈̸*", "`.` (from `⒈̸`)", "`abcd1*`"),  # the slash on the `.` folds away
        ("abcd⑴*", "`)` (from `⑴`)", '`"abcd 1*"`'),  # PARENTHESIZED DIGIT ONE: `(1)`, last piece `)`
        ("abcd⑴̸*", "`)` (from `⑴̸`)", '`"abcd 1*"`'),
        ('"trust abcd⒈̸*"', "`.` (from `⒈̸`)", "`abcd1*`"),
        ("abcd1.*", "`.`", "`abcd1*`"),  # the look-alike's NFKC spelling: the same verdict
        ("abc．*", "`.` (from `．`)", "`abc*`"),  # FULLWIDTH FULL STOP
        ("vision-*", "`-`", "`vision*`"),
        # a whole-character tail on a multi-token stem: cut as written, not rebuilt from the tokens
        ("trust-model-*", "`-`", "`trust-model*`"),
        ('"x trust-model-*"', "`-`", "`trust-model*`"),
        # inside a phrase the hint is the phrase's words, not a phrase nested in it (`"x "y 1*""`)
        ('"x y⑴*"', "`)` (from `⑴`)", "`y 1*`"),
        ('"x abcd⑴*"', "`)` (from `⑴`)", "`abcd 1*`"),
        # cutting the stem as written would leave the math unclosed (`abcd$\alpha*`: PARSE_WILDCARD_NOT_SUFFIX)
        (r"abcd$\alpha$*", "`$`", '`"abcd α*"`'),
        ("abcd$x$*", "`$`", '`"abcd x*"`'),
        ('"trust abcd$x$*"', "`$`", "`abcd x*`"),
    ],
    ids=ascii,
)
def test_wildcard_after_a_non_word_piece_is_detached(q: str, piece: str, hint: str) -> None:
    [error] = parse(q).errors
    assert error.code is DiagnosticCode.PARSE_WILDCARD_DETACHED
    assert f"follows {piece}, not a letter or digit" in error.message and f"e.g. {hint}." in error.message
    # the hint is valid in place of the word: on its own, or as the last words of the phrase it sits in
    fixed = hint.strip("`") if not q.startswith('"') else f'{q.rsplit(" ", 1)[0]} {hint.strip("`")}"'
    assert parse(fixed).errors == [], fixed


# M3a gate round 2 (exactness-guardian): a mark after the separator (a vowel sign, alone no word) must not
# hide the separator the wildcard follows. Each was accepted as the bare stem (`vision*`) at 30756ce.
@pytest.mark.parametrize(
    "q",
    ["vision-ަ*", "abcd-\u0ce2*", "abcd-ि*", "abcd-ิ*", "abcd.ெ*", '"trust vision.ަ*"', "calibrat-ྜྷ*"],
    ids=ascii,
)
def test_a_lone_mark_after_a_separator_leaves_the_wildcard_detached(q: str) -> None:
    assert [e.code for e in parse(q).errors] == [DiagnosticCode.PARSE_WILDCARD_DETACHED]


@pytest.mark.parametrize(
    ("q", "tree"),
    [
        ("abcd½*", '"abcd1 2*"'),  # VULGAR FRACTION ONE HALF: `1⁄2`, last piece `2`
        ("abcd½̸*", '"abcd1 2*"'),  # the slash on the `2` folds away (a digit's mark)
        ("abcd≠ͅ*", '"abcd neq ι*"'),  # U+0345 after neq folds to `ι`, a letter, the last piece
        ("abcde\u0301*", "abcde*"),  # a decomposed accent is no piece: it folds away
        ("bench\\-*", "bench*"),  # `\-` is markup that joins the word, not a piece
    ],
    ids=ascii,
)
def test_wildcard_after_a_word_piece_is_attached(q: str, tree: str) -> None:
    result = parse(q)
    assert result.errors == []
    assert result.ast is not None and render(canonicalize(result.ast)) == tree


# decision-008: the canonical string is what a search record keeps and replay re-parses, so a query whose
# canonical string is over the cap is refused, even though the input itself fits
def test_a_query_whose_canonical_form_is_over_the_cap_is_too_long() -> None:
    words = [f"w{i:04d}" for i in range(300)]
    q = " ".join(words)  # 1,799 code points; juxtaposition prints as ` AND `, and the defaults are added
    canonical = (
        "("
        + " AND ".join(words)
        + " AND track:(datasets_benchmarks OR main OR position) AND status:accepted)"
    )
    result = parse(q)
    assert len(q) == 1_799 and result.ast is None and result.canonical is None
    [error] = result.errors
    assert error.code is DiagnosticCode.PARSE_TOO_LONG and error.span == (0, len(q))
    over = f"{len(canonical) - MAX_QUERY_LENGTH:,} over the limit of {MAX_QUERY_LENGTH:,}"
    assert f"is {len(canonical):,} characters, {over}" in error.message
    assert "each space between words becomes ` AND `" in error.message
    assert "field:" not in error.message  # no field group: not blamed (M3a round 3)
    defaults = " AND track:(datasets_benchmarks OR main OR position) AND status:accepted"
    assert f"the default filters add {len(defaults)}" in error.message


def test_a_canonical_overflow_names_only_the_causes_its_query_has() -> None:
    """A plain OR list has no implicit AND and no field group: neither is named (the defaults still are);
    a `field:(…)` group is named, and juxtaposition inside one counts as an implicit AND."""
    ored = " OR ".join(f"w{i:04d}" for i in range(217))  # 1,949 code points
    [error] = parse(ored).errors
    assert error.code is DiagnosticCode.PARSE_TOO_LONG, parse(ored).canonical
    assert "` AND `" not in error.message and "field:" not in error.message
    assert "the default filters add" in error.message
    grouped = "title:(" + " OR ".join(f"w{i:04d}" for i in range(200)) + ") track:main status:accepted"
    [error] = parse(grouped).errors
    assert error.code is DiagnosticCode.PARSE_TOO_LONG
    assert "a `field:(…)` group repeats `field:` on every term" in error.message
    assert "each space between words becomes ` AND `" in error.message  # `) track:main` side by side
    assert "default filters add" not in error.message


def test_the_length_cap_message_groups_thousands() -> None:
    [error] = parse("x" * 2_966).errors
    assert error.message.startswith("The query is 2,966 characters long; the limit is 2,000")


def test_a_canonical_overflow_with_typed_filters_does_not_blame_the_defaults() -> None:
    q = " ".join(f"w{i:04d}" for i in range(300)) + " track:main status:accepted"
    [error] = parse(q).errors
    assert error.code is DiagnosticCode.PARSE_TOO_LONG and "default filters add" not in error.message


def test_a_canonical_string_exactly_at_the_cap_is_accepted() -> None:
    clauses = " AND track:main AND status:accepted)"
    at_cap = "(" + "x" * (MAX_QUERY_LENGTH - 1 - len(clauses)) + clauses
    assert len(at_cap) == MAX_QUERY_LENGTH and parse(at_cap).canonical == at_cap
    over = "trust " + at_cap[: -len(clauses)] + " AND status:accepted)"  # canonical: 2,001 code points
    assert len(over) <= MAX_QUERY_LENGTH
    result = parse(over)
    assert [e.code for e in result.errors] == [DiagnosticCode.PARSE_TOO_LONG], len(result.canonical or "")


# The seven registry rewrites from docs/design/2026-09-27-copy-deck.md §2 (TASK-093), pinned verbatim with
# their codes and spans: wording may change, codes and spans may not (error-diagnostics).
_NEGATED = (
    "Every part of this query is negated (`NOT …`), so it would match almost everything — add something to "
)
_COLON = " starts with a colon, so no field is named — a field name must touch its colon, e.g. `title:trust`."
_UNCLOSED = " has no closing parenthesis — add `)` where the group ends."
COPY_DECK_REWRITES: list[tuple[str, str, DiagnosticCode, tuple[int, int], str]] = [
    (
        "(trust OR reliance",
        "native",
        DiagnosticCode.PARSE_UNBALANCED_PAREN,
        (0, 1),
        "`(trust OR reliance`" + _UNCLOSED,
    ),
    ("a (b", "native", DiagnosticCode.PARSE_UNBALANCED_PAREN, (2, 3), "`(b`" + _UNCLOSED),
    ("venue:(ICLR OR", "native", DiagnosticCode.PARSE_UNBALANCED_PAREN, (6, 7), "`(ICLR OR`" + _UNCLOSED),
    (
        "NOT workshop",
        "native",
        DiagnosticCode.PARSE_ALL_NEGATIVE,
        (0, 12),
        _NEGATED + "search for, e.g. `trust NOT bias`.",
    ),
    (
        "(" * 70 + "x",
        "native",
        DiagnosticCode.PARSE_TOO_DEEP,
        (MAX_DEPTH, MAX_DEPTH + 1),
        f"The query nests groups or `NOT`s more than {MAX_DEPTH} deep here — remove a level of parentheses or a "
        "`NOT`.",
    ),
    ("trust : model", "native", DiagnosticCode.PARSE_STRAY_COLON, (6, 7), "`: model`" + _COLON),
    ("trust :model", "native", DiagnosticCode.PARSE_STRAY_COLON, (6, 12), "`:model`" + _COLON),
    ("trust :", "native", DiagnosticCode.PARSE_STRAY_COLON, (6, 7), "`:`" + _COLON),
    (
        "x" * 2_001,
        "native",
        DiagnosticCode.PARSE_TOO_LONG,
        (2_000, 2_001),
        "The query is 2,001 characters long; the limit is 2,000 — shorten it, e.g. replace a list of word forms "
        "with one wildcard.",
    ),
    (
        "venue:(ICLR AND ICML)",
        "native",
        DiagnosticCode.FIELD_FILTER_SYNTAX,
        (12, 15),
        "`venue:(…)` takes values joined by OR, e.g. `venue:(ICLR OR ICML)`.",
    ),
    (
        "year:(2020 AND 2021)",
        "native",
        DiagnosticCode.FIELD_FILTER_SYNTAX,
        (11, 14),
        "`year:(…)` takes values joined by OR, e.g. `year:(2020 OR 2024..2026)`.",
    ),
    (
        "track:(main x)",
        "native",
        DiagnosticCode.FIELD_FILTER_SYNTAX,
        (12, 13),
        "`track:(…)` takes values joined by OR, e.g. `track:(main OR position)`.",
    ),
    (
        "status:(accepted x)",
        "native",
        DiagnosticCode.FIELD_FILTER_SYNTAX,
        (17, 18),
        "`status:(…)` takes values joined by OR, e.g. `status:(accepted OR withdrawn)`.",
    ),
    (
        "source:(ICLR AND PMLR)",
        "scholar",
        DiagnosticCode.FIELD_FILTER_SYNTAX,
        (13, 16),
        "`source:(…)` takes values joined by OR, e.g. `source:(ICLR OR ICML)`.",
    ),
    (
        "大语言模型",
        "native",
        DiagnosticCode.WARN_CJK_RUN,
        (0, 5),
        "`大语言模型`: Chinese, Japanese and Korean text is not split into words, so this matches only the exact "
        "run — `大语言模型*` also finds longer runs that start with it.",
    ),
]


@pytest.mark.parametrize(("q", "mode", "code", "span", "message"), COPY_DECK_REWRITES)
def test_the_copy_deck_rewrites_are_the_registry_text(
    q: str, mode: Literal["native", "scholar"], code: DiagnosticCode, span: tuple[int, int], message: str
) -> None:
    result = parse(q, mode=mode)
    found = [(d.code, d.span, d.message) for d in (*result.errors, *result.warnings) if d.code is code]
    assert found == [(code, span, message)]


def test_a_canonical_overflow_suggests_shortening_not_splitting() -> None:
    [error] = parse(" ".join(f"w{i:04d}" for i in range(300))).errors
    assert error.code is DiagnosticCode.PARSE_TOO_LONG
    assert error.message.endswith(" Shorten it, e.g. replace a list of word forms with one wildcard.")
    assert "several searches" not in error.message


# A filter value glued to a following `(` is refused like a glued word, whatever the value (spec 02 §Grammar,
# decision-028, TASK-158): `year:2020..2022(x)` once parsed as `x AND year:2020..2022` while `year:2021(x)` was
# refused. A `)` glued to a following field prefix still parses: a field name ends at its `:`, so nothing is
# split, and a facet click splices `field:(…)` straight after a `)` (`…)(source:ICLR OR …)`, the Trust-Evals
# strings)
_P = DiagnosticCode.PARSE_PAREN_TOUCHES_WORD
_V = DiagnosticCode.FIELD_UNKNOWN_VALUE
GLUED_CLAUSES: list[tuple[str, str | list[tuple[DiagnosticCode, tuple[int, int]]]]] = [
    ("year:2020..2022(x)", [(_P, (5, 16))]),
    ("year:2021(x)", [(_P, (5, 10))]),
    ("venue:iclr(x)", [(_P, (6, 11))]),
    ("track:main(x)", [(_P, (6, 11))]),
    ("title:y(x)", [(_P, (6, 8))]),
    ("(x)year:2020..2022", "(AND x year:2020..2022)"),
    ("(x)year:2021", "(AND x year:2021)"),
    ("(x)venue:iclr", "(AND x venue:ICLR)"),
    ("(x)title:y", "(AND x title:y)"),
    ("(x)track:main", "(AND x track:main)"),
    # an invalid year value is reported on the value, and on the glued `(` too where there is one (TASK-158 #3)
    ("year:..2022(x)", [(_V, (5, 11)), (_P, (5, 12))]),
    ("year:2020..(x)", [(_V, (5, 11)), (_P, (5, 12))]),
    ("(x)year:..2022", [(_V, (8, 14))]),
    # a value glued inside its filter group is one mistake, not also a malformed group
    ("year:(2021(x))", [(_P, (6, 11))]),
    ("year:(2020..2022(x))", [(_P, (6, 17))]),
]


@pytest.mark.parametrize(("q", "outcome"), GLUED_CLAUSES, ids=[q for q, _ in GLUED_CLAUSES])
@pytest.mark.parametrize("mode", ["native", "scholar"])
def test_a_parenthesis_glued_to_a_filter_clause(
    q: str, outcome: str | list[tuple[DiagnosticCode, tuple[int, int]]], mode: Literal["native", "scholar"]
) -> None:
    result = parse(q, mode)
    if isinstance(outcome, str):
        assert result.errors == [] and result.ast is not None
        assert show(result.ast) == outcome
    else:
        assert [(e.code, e.span) for e in result.errors] == outcome
        assert result.ast is None


@pytest.mark.parametrize(
    "q", ["year:2020..2022 (x)", "year:2021 (x)", "venue:iclr (x)", "(x)year:2020..2022"]
)
def test_a_spaced_or_accepted_glued_clause_has_a_canonical_string_that_replays(q: str) -> None:
    """The message's fix parses; and no canonical string writes a value before `(` (clauses and groups are
    joined by ` AND `), so every saved record's canonical string re-parses unchanged (decision-028)."""
    result = parse(q)
    assert result.errors == [] and result.canonical is not None
    again = parse(result.canonical)
    assert again.errors == [] and again.canonical == result.canonical


@pytest.mark.parametrize("mode", ["native", "scholar"])
def test_a_glued_source_value_is_still_checked_as_a_value(mode: Literal["native", "scholar"]) -> None:
    """`source:` (Scholar mode) goes through its own value check, which a glued `(` doesn't silence."""
    errors = [(e.code, e.span) for e in parse("source:foo(x)", mode).errors]
    if mode == "scholar":
        assert errors == [(_V, (7, 10)), (_P, (7, 11))]
        assert [(e.code, e.span) for e in parse("(x)source:foo", mode).errors] == [(_V, (10, 13))]
    else:
        assert errors == [(DiagnosticCode.FIELD_COMPAT_ONLY, (0, 7)), (_P, (7, 11))]


def test_a_group_whose_first_token_is_no_value_keeps_both_errors() -> None:
    """Only a glued value's closing check is deduplicated (TASK-158 review): a field name where a group's first
    value goes is an unknown field and a malformed group, as before."""
    assert [(e.code, e.span) for e in parse("year:(xtitle:").errors] == [
        (DiagnosticCode.FIELD_UNKNOWN, (6, 13)),
        (DiagnosticCode.FIELD_FILTER_SYNTAX, (6, 13)),
    ]


def test_a_glued_word_error_still_stops_a_second_error_on_the_word() -> None:
    """Only a filter value's own check looks past the glue error; `~` (no letters) is said once."""
    assert [(e.code, e.span) for e in parse("~(x)").errors] == [(_P, (0, 2))]


def test_a_glued_value_message_says_where_the_space_goes() -> None:
    message = parse("year:2020..2022(x)").errors[0].message
    assert message == (
        "`2020..2022(`: a parenthesis touching a `year:` value would be read as AND — if you meant "
        "`year:2020..2022 AND (…)`, put a space before the `(`; for several values write a group, "
        "`year:(2020..2022 OR …)`."
    )
    assert "`venue:iclr AND (…)`" in parse("venue:iclr(x)").errors[0].message  # the field as written
    # inside its group a space would leave a malformed group, so the fix is to close it
    assert parse("year:(2021 OR 2022(x))").errors[0].message == (
        "`2022(`: a parenthesis touching a `year:` value would be read as AND, and a `year:(…)` group takes only "
        "values joined by OR (`year:(… OR …)`) — end the group with `)` before the `(`."
    )
    # a negated value gets no rewrite that would drop its `-`; a NOT further back is not this value's
    # a value that clip would change (whitespace, an escape, a cut) is not quoted in the fix: one visible line
    for q in ('venue:"a\nb"(x)', 'venue:"a\tb"(x)'):
        message = next(e.message for e in parse(q).errors if e.code is _P)
        assert "\n" not in message and "\t" not in message, q
        assert message.endswith(
            "— put a space before the `(`; for several values write a group, `venue:(… OR …)`."
        )
    # nor does a `source:` value, whose rewrite native mode would refuse (FIELD_COMPAT_ONLY)
    for q in ("-year:2021(x)", "year:-2021(x)", "source:neurips(x)"):
        message = next(e.message for e in parse(q).errors if e.code is _P)
        field = q.lstrip("-").split(":")[0]
        assert message.endswith(
            f"— put a space before the `(`; for several values write a group, `{field}:(… OR …)`."
        ), q
    assert "`year:2021 AND (…)`" in parse("NOT a year:2021(x)").errors[0].message
    # a text word, a text field's word and a word after `)` keep the plural hint
    for q in ("model(s)", "trust model(s)", "title:model(s)", "(a)b"):
        assert "`model$`" in parse(q).errors[0].message, q
    bare = [
        e.message for e in parse("2020..2022(x)").errors if e.code is DiagnosticCode.PARSE_PAREN_TOUCHES_WORD
    ]
    assert len(bare) == 1 and "`model(s)`" in bare[0]  # a bare range is no field's value


def test_a_group_glued_to_a_group_is_not_this_rule() -> None:
    """No value is split by `)(`, so the rule doesn't cover it (decision-028)."""
    assert parsed("year:(2020..2022)(x)") == "(AND year:2020..2022 x)"
    assert parsed("(a)(b)") == "(AND a b)"


def test_an_open_year_range_value_is_refused_without_a_text_warning() -> None:
    """`..2022` as a filter value is FIELD_UNKNOWN_VALUE only, not also read as a search word (TASK-158 #4);
    as a text term it still warns that the dots are dropped."""
    for q in ("year:..2022", "year: ..2022", "year:(2021 OR ..2022)"):
        result = parse(q)
        assert [e.code for e in result.errors] == [DiagnosticCode.FIELD_UNKNOWN_VALUE], q
        assert result.warnings == [], q
    assert [w.code for w in parse("..2022").warnings] == [DiagnosticCode.WARN_SYMBOLS_DROPPED]
    assert [w.code for w in parse("title:..2022").warnings] == [DiagnosticCode.WARN_SYMBOLS_DROPPED]
