"""`abstract_kind:` (spec 02; decision-049): a filter, never text (guarantee 2), no default, the same rule in the
oracle and the index; a schema-3 index refuses it as input (422), never as an internal error."""

from pathlib import Path

import pytest
from openproceedings.diagnostics import DiagnosticCode, http_status
from openproceedings.engine.protocol import EngineInputError
from openproceedings.engine.reference import ReferenceEngine
from openproceedings.query.ast import FILTER_FIELDS
from openproceedings.query.parser import parse

from tests.corpus import Rec
from tests.unit.engine.test_exclusions import tantivy_of

# no text holds the word `openalex`, so the text test can only match a kind as text
RECS = [
    Rec("op:aaai:1990:dblp-A90", "Trust in planning", "Filled text.", venue="AAAI", year=1990,
        abstract_kind="openalex"),
    Rec("op:aaai:2020:ojs-1", "Trust in search", "Official text.", venue="AAAI", year=2020),
    Rec("op:aaai:2021:ojs-2", "Trust in games", None, venue="AAAI", year=2021),
]  # fmt: skip


def test_the_field_is_last_in_the_canonical_order() -> None:
    assert FILTER_FIELDS[-1] == "abstract_kind"


def test_a_record_s_kind_defaults_from_its_abstract() -> None:
    assert [r.abstract_kind for r in RECS] == ["openalex", "official", "none"]


@pytest.mark.parametrize(("q", "ids"), [
    ("trust abstract_kind:openalex", {"op:aaai:1990:dblp-A90"}),
    ("trust abstract_kind:(official OR none)", {"op:aaai:2020:ojs-1", "op:aaai:2021:ojs-2"}),
    ("trust NOT abstract_kind:none", {"op:aaai:1990:dblp-A90", "op:aaai:2020:ojs-1"}),
    ("trust abstract_kind:OPENALEX", {"op:aaai:1990:dblp-A90"}),  # values are case-blind, as venue's
])  # fmt: skip
def test_the_oracle_filters_by_kind(q: str, ids: set[str]) -> None:
    ast = parse(q).ast
    assert ast is not None and ReferenceEngine(RECS).match_ids(ast) == ids


def test_a_kind_is_never_matched_as_text() -> None:  # guarantee 2: the word `openalex` alone matches no kind
    ast = parse("openalex").ast
    assert ast is not None and ReferenceEngine(RECS).match_ids(ast) == frozenset()


def test_an_unknown_value_is_refused_naming_the_values() -> None:
    result = parse("trust abstract_kind:crossref")
    (err,) = result.errors
    assert err.code == DiagnosticCode.FIELD_UNKNOWN_VALUE and "`openalex`" in err.message


def test_no_default_applies() -> None:
    result = parse("trust")
    assert "abstract_kind" not in (result.canonical or "") and "abstract_kind" not in result.defaults


def test_the_canonical_form_puts_it_after_status() -> None:
    assert parse("abstract_kind:(none OR official) trust").canonical == (
        "(trust AND track:(datasets_benchmarks OR main OR position) AND status:accepted"
        " AND abstract_kind:(none OR official))"
    )


def test_existing_canonicals_are_unchanged() -> None:  # no QUERY_VERSION bump (Planner decision)
    assert parse("trust venue:ICLR year:2024").canonical == (
        "(trust AND venue:ICLR AND year:2024 AND track:(datasets_benchmarks OR main OR position)"
        " AND status:accepted)"
    )


# `source:` still means venue; abstract_kind follows it
def test_scholar_s_source_alias_is_untouched() -> None:
    assert parse("trust source:ICLR", "scholar").canonical == (
        "(trust AND venue:ICLR AND track:(datasets_benchmarks OR main OR position) AND status:accepted)"
    )
    assert parse("trust source:ICLR abstract_kind:official", "scholar").canonical == (
        "(trust AND venue:ICLR AND track:(datasets_benchmarks OR main OR position) AND status:accepted"
        " AND abstract_kind:official)"
    )


def test_a_schema_3_engine_refuses_abstract_kind_on_every_entry_point(tmp_path: Path) -> None:
    engine = tantivy_of(RECS[1:], tmp_path, "3")  # no OpenAlex record: a schema-3 build refuses one (Task 4)
    assert "abstract_kind" not in engine.filter_fields
    ast = parse("trust abstract_kind:openalex").effective_ast
    assert ast is not None
    for call in (lambda: engine.compile(ast), lambda: engine.facets(ast), lambda: engine.counts([ast]),
                 lambda: engine.match_ids(ast), lambda: engine.candidates(ast)):  # fmt: skip
        with pytest.raises(EngineInputError) as refused:
            call()
        assert refused.value.code == DiagnosticCode.FIELD_NOT_INDEXED
        assert "schema 4" in str(refused.value) and engine.index_version in str(refused.value)
    assert http_status(DiagnosticCode.FIELD_NOT_INDEXED) == 422


def test_a_schema_3_engine_still_serves_a_query_without_it(tmp_path: Path) -> None:
    engine = tantivy_of(RECS[1:], tmp_path, "3")
    ast = parse("trust venue:AAAI").effective_ast
    assert ast is not None
    engine.admit(ast)  # nothing to refuse
    assert len(engine.match_ids(ast)) == 2 and set(engine.facets(ast)) == set(engine.filter_fields)
