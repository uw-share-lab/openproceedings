"""Default filters, WARN_NESTED_FILTER and identification_query (spec 02 §Default filters; task-014)."""

from __future__ import annotations

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st
from openproceedings.diagnostics import DiagnosticCode
from openproceedings.query.defaults import DEFAULT_CLAUSES
from openproceedings.query.parser import ParseResult, parse

TRACK = "track:(datasets_benchmarks OR main OR position)"
STATUS = "status:accepted"


def ok(q: str) -> ParseResult:
    result = parse(q)
    assert result.errors == [], result.errors
    return result


GOLDEN: list[tuple[str, str, str, list[str]]] = [
    # q, canonical, identification_query, defaults
    ("trust", f"(trust AND {TRACK} AND {STATUS})", "trust", ["track", "status"]),
    (
        "trust calibration",
        f"(trust AND calibration AND {TRACK} AND {STATUS})",
        "(trust AND calibration)",
        ["track", "status"],
    ),
    ("a OR b", f"((a OR b) AND {TRACK} AND {STATUS})", "(a OR b)", ["track", "status"]),
    (
        "trust venue:ICLR",
        f"(trust AND venue:ICLR AND {TRACK} AND {STATUS})",
        "(trust AND venue:ICLR)",
        ["track", "status"],
    ),
    # a user-written track or status limit replaces that default and is part of the search
    (
        "trust track:workshop",
        f"(trust AND track:workshop AND {STATUS})",
        "(trust AND track:workshop)",
        ["status"],
    ),
    (
        "trust status:rejected",
        f"(trust AND {TRACK} AND status:rejected)",
        "(trust AND status:rejected)",
        ["track"],
    ),
    (
        "trust NOT track:workshop",
        f"(trust AND NOT track:workshop AND {STATUS})",
        "(trust AND NOT track:workshop)",
        ["status"],
    ),
    (
        "trust track:(main OR workshop) status:(accepted OR rejected)",
        "(trust AND track:(main OR workshop) AND status:(accepted OR rejected))",
        "(trust AND track:(main OR workshop) AND status:(accepted OR rejected))",
        [],
    ),
    # recognised by content: typed, reordered, or split into a single-field OR, it is still the default
    (f"trust {TRACK}", f"(trust AND {TRACK} AND {STATUS})", "trust", ["track", "status"]),
    (
        "trust track:(position OR Main OR datasets_benchmarks)",
        f"(trust AND {TRACK} AND {STATUS})",
        "trust",
        ["track", "status"],
    ),
    (
        "trust (track:main OR track:position OR track:datasets_benchmarks)",
        f"(trust AND {TRACK} AND {STATUS})",
        "trust",
        ["track", "status"],
    ),
    (
        "(trust status:accepted) calibration",
        f"(trust AND calibration AND {TRACK} AND {STATUS})",
        "(trust AND calibration)",
        ["track", "status"],
    ),
    # a default-equal clause next to another clause of its field is the user's own (the parser would not add it)
    (
        f"trust track:workshop {TRACK}",
        f"(trust AND {TRACK} AND track:workshop AND {STATUS})",
        f"(trust AND {TRACK} AND track:workshop)",
        ["status"],
    ),
    # if the only positive clause was a default, identification is all-negative: a set the engine can count,
    # but not a query that parses on its own (records reproduce it by replaying `canonical`)
    (
        "status:accepted NOT track:workshop",
        "(NOT track:workshop AND status:accepted)",
        "NOT track:workshop",
        ["status"],
    ),
    # a query of nothing but defaults identifies the whole corpus
    (STATUS, f"({TRACK} AND {STATUS})", "", ["track", "status"]),
]


@pytest.mark.parametrize(("q", "canonical", "identification", "defaults"), GOLDEN, ids=[g[0] for g in GOLDEN])
def test_golden(q: str, canonical: str, identification: str, defaults: list[str]) -> None:
    result = ok(q)
    assert (result.canonical, result.identification_query, result.defaults) == (
        canonical,
        identification,
        defaults,
    )


@pytest.mark.parametrize("q", [g[0] for g in GOLDEN])
def test_replaying_the_canonical_string_changes_nothing(q: str) -> None:
    first = ok(q)
    assert first.canonical is not None
    again = ok(first.canonical)
    assert (again.canonical, again.canonical_hash, again.identification_query, again.defaults) == (
        first.canonical,
        first.canonical_hash,
        first.identification_query,
        first.defaults,
    )


def test_toggle_workshops_off_and_on() -> None:
    """The UI toggle edits the same clause: including workshops writes a non-default set, which is then the
    user's limit (no `track` default, and it stays in identification_query); restoring the set restores
    the default exactly."""
    base = ok("trust")
    assert base.canonical is not None
    included = ok(
        base.canonical.replace(TRACK, "track:(datasets_benchmarks OR main OR position OR workshop)")
    )
    assert included.defaults == ["status"]
    assert (
        included.identification_query
        == "(trust AND track:(datasets_benchmarks OR main OR position OR workshop))"
    )
    assert included.canonical is not None
    restored = ok(
        included.canonical.replace("track:(datasets_benchmarks OR main OR position OR workshop)", TRACK)
    )
    assert (
        restored.canonical,
        restored.canonical_hash,
        restored.identification_query,
        restored.defaults,
    ) == (
        base.canonical,
        base.canonical_hash,
        base.identification_query,
        base.defaults,
    )


NESTED = [
    ("(track:workshop AND x) OR y", "track", (1, 15)),
    ("x OR status:rejected", "status", (5, 20)),
    ("trust NOT (track:workshop OR x)", "track", (11, 25)),
    (
        "trust (trust OR track:main)",
        "track",
        (16, 26),
    ),  # Hypothesis counterexample (task-017), kept as golden
    (f"trust {TRACK} (x OR track:workshop)", "track", (60, 74)),  # a typed default keeps the warning
]


@pytest.mark.parametrize(("q", "field", "span"), NESTED, ids=[q for q, *_ in NESTED])
def test_nested_filters_keep_the_default_and_warn(q: str, field: str, span: tuple[int, int]) -> None:
    result = ok(q)
    assert field in result.defaults
    nested = [w for w in result.warnings if w.code is DiagnosticCode.WARN_NESTED_FILTER]
    assert [w.span for w in nested] == [span]
    assert f"top-level `{field}:`" in nested[0].message
    assert result.canonical is not None  # a replay keeps the warning
    assert [w.code for w in ok(result.canonical).warnings].count(DiagnosticCode.WARN_NESTED_FILTER) == 1


def test_a_top_level_clause_silences_the_nested_warning() -> None:
    result = ok("track:workshop ((track:main AND x) OR y)")
    assert result.defaults == ["status"]
    assert [w.code for w in result.warnings] == []


def test_the_typed_tree_is_unchanged_and_the_effective_tree_carries_the_defaults() -> None:
    result = ok("trust")
    assert result.ast is not None and result.ast.kind == "term"
    assert result.effective_ast is not None and result.effective_ast.kind == "and"
    assert [c.kind for c in result.effective_ast.children] == ["term", "filter", "filter"]  # type: ignore[union-attr]


def test_errors_have_no_defaults() -> None:
    result = parse("a OR")
    assert (result.effective_ast, result.identification_query, result.defaults) == (None, None, [])


def test_default_clauses_match_the_skill() -> None:
    assert {f: v for f, v in DEFAULT_CLAUSES.items()} == {
        "track": ("datasets_benchmarks", "main", "position"),
        "status": ("accepted",),
    }


WORDS = st.sampled_from(
    ["trust", "calibration", "vision-language", "bench*", '"trust in ai"', "venue:ICLR", "year:2024"]
)
LIMITS = st.sampled_from(
    [
        "",
        TRACK,
        STATUS,
        "track:workshop",
        "status:rejected",
        "NOT track:workshop",
        "track:(main OR position OR datasets_benchmarks)",
    ]
)


@given(st.lists(st.one_of(WORDS, LIMITS), min_size=1, max_size=5).map(" ".join))
def test_defaults_are_idempotent(q: str) -> None:
    first = parse(q)
    assume(not first.errors and first.canonical is not None)
    again = ok(first.canonical)
    assert (again.canonical, again.identification_query, again.defaults) == (
        first.canonical,
        first.identification_query,
        first.defaults,
    )
    ident = parse(first.identification_query or "")
    if not ident.errors:  # re-parsing it re-adds exactly the defaults that were removed
        assert ident.canonical == first.canonical
    else:  # empty (only defaults) or all-negative (the only positive clause was a default)
        assert first.identification_query == "" or [e.code for e in ident.errors] == [
            DiagnosticCode.PARSE_ALL_NEGATIVE
        ]


def test_every_nested_clause_warns() -> None:
    result = ok("trust (x OR track:workshop) (y OR track:main)")
    assert [w.span for w in result.warnings if w.code is DiagnosticCode.WARN_NESTED_FILTER] == [
        (12, 26),
        (34, 44),
    ]


def test_inserted_defaults_point_at_the_end_of_the_input() -> None:
    result = ok("trust")
    assert result.effective_ast is not None
    assert [c.span for c in result.effective_ast.children[1:]] == [(5, 5), (5, 5)]  # type: ignore[union-attr]


def test_identification_ast_is_the_set_without_defaults() -> None:
    assert ok("trust").identification_ast == ok("trust").ast
    assert ok("status:accepted").identification_ast is None  # every record
    negative = ok("status:accepted NOT track:workshop").identification_ast
    assert negative is not None and negative.kind == "not"  # usable even though the string won't parse
