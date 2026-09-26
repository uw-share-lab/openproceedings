"""The query parser (spec 02 §Grammar, §Error handling; decision-001; task-012)."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st
from openproceedings.diagnostics import DiagnosticCode
from openproceedings.query.ast import And, Filter, Near, Node, Not, Or, Phrase, Term, Wildcard, YearRange
from openproceedings.query.canonical import canonicalize, render
from openproceedings.query.parser import MAX_DEPTH, parse


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
    ("$\\epsilon$-DP", '"epsilon dp"'),
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


MIXED = [
    ("a b OR c", (0, 8)),
    ("a OR b c", (0, 8)),
    ("a AND b OR c", (0, 12)),
    ("x (a b OR c)", (3, 11)),  # the warning is on the level that mixes, inside the parentheses
]


@pytest.mark.parametrize(("q", "span"), MIXED, ids=[q for q, _ in MIXED])
def test_mixed_and_or_warns(q: str, span: tuple[int, int]) -> None:
    result = parse(q)
    assert [(w.code, w.span) for w in result.warnings] == [(DiagnosticCode.WARN_MIXED_AND_OR, span)]
    assert "parenthes" in result.warnings[0].message


def test_mixed_warning_shows_the_reading() -> None:
    assert "`(a b) OR c`" in parse("a b OR c").warnings[0].message
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
    for q in inputs:
        for mode in ("native", "scholar"):
            result = parse(q[:2000], mode)  # type: ignore[arg-type]
            for d in result.errors + result.warnings + result.translations:
                assert len(d.message) < 500, (
                    q[:20],
                    d.code,
                    len(d.message),
                )  # longest fixed text: the source list


def test_parsing_is_linear_in_the_query_length() -> None:
    import time

    def cost(q: str) -> float:
        best = float("inf")
        for _ in range(3):
            start = time.perf_counter()
            parse(q)
            best = min(best, time.perf_counter() - start)
        return best

    for unit in ("w ", "$x ", "$a b ", "a. b ", "a(b)", "a|", ")a"):  # incl. space-free runs
        n = 2000 // len(unit) - 1
        small, large = cost(unit * (n // 5)), cost(unit * n)  # 5x the input
        assert large < small * 15 + 0.01, (unit, small, large)  # quadratic would be ~25x
    for q in ('"' + "$x " * 666 + '"', "a " * 999):
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
