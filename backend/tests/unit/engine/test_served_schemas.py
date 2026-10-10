"""This code serves two index schemas (decision-049): schema 4, which new indexes are built at (`abstract_kind` a
stored raw fast field: its filter and facet), and schema 3, which an existing index and the search records pinned to
it hold (no `abstract_kind`). Both index `ord`, so a verified clause names its ids as a u64 term set. On a corpus
schema 3 can hold (no OpenAlex abstract), both give the same ids, the same float scores and the same facets on their
shared fields for every query naming no `abstract_kind` (guarantee 4 for a pinned index; the record replay across
the bump is in `tests/contract/test_records.py`); schema 3 refuses a query naming it. An index of any other schema
is refused."""

from __future__ import annotations

import random
from pathlib import Path
from typing import Any

import pytest
import tantivy
from hypothesis import given, settings
from openproceedings.diagnostics import DiagnosticCode
from openproceedings.engine import index as idx
from openproceedings.engine.index import SCHEMA_VERSION, SERVED_SCHEMAS, schema
from openproceedings.engine.protocol import EngineInputError, EngineInternalError
from openproceedings.engine.tantivy_engine import SORTS, IndexUnservable, TantivyEngine, unservable
from openproceedings.query.ast import Node
from openproceedings.query.parser import parse

from tests.bench.test_bench import trust_evals
from tests.fixtures.corpus.synthetic_5k import records, vocab
from tests.golden.test_trust_evals import STRINGS
from tests.strategies import SCHEMA_3_FIELDS, engine_asts
from tests.unit.engine.test_exclusions import tantivy_of

type Pair = tuple[TantivyEngine, TantivyEngine]
MANIFEST: dict[str, Any] = {
    "index_version": "0123456789ab",
    "tokenizer_version": "2",
    "tantivy_version": "0.26.2",
    "ranking_params": {"bm25": {"b": 0.75, "k1": 1.2}},
}


@pytest.fixture(scope="module", params=["2", "3"])
def pair(tmp_path_factory: pytest.TempPathFactory, request: pytest.FixtureRequest) -> Pair:
    """The 5k corpus (no OpenAlex abstract, so schema 3 builds) indexed at schema 3 and at schema 4, at each served
    tokenizer."""
    corpus = list(records())
    old = tantivy_of(corpus, tmp_path_factory.mktemp("schema3"), "3", request.param)
    new = tantivy_of(corpus, tmp_path_factory.mktemp("schema4"), "4", request.param)
    assert old.tokenizer_version == new.tokenizer_version == request.param
    assert old.form.abstract_kind is False and new.form.abstract_kind is True
    assert old.index_version != new.index_version  # the schema is an index_version input
    return old, new


@pytest.fixture(scope="module")
def engine(pair: Pair) -> TantivyEngine:
    return pair[1]


def test_the_current_and_the_previous_schema_are_served_and_no_other() -> None:
    assert SCHEMA_VERSION == "4" and list(SERVED_SCHEMAS) == ["3", "4"]
    assert [f.abstract_kind for f in SERVED_SCHEMAS.values()] == [False, True]
    for served in SERVED_SCHEMAS:
        assert unservable({**MANIFEST, "schema_version": served}) is None
    for refused in ("1", "2", "5", None, 3, 4, [], {}, ["4"]):
        why = unservable({**MANIFEST, "schema_version": refused})
        assert why is not None and why[0] == "schema_version_mismatch" and "build a new index" in why[1]
    with pytest.raises(ValueError, match="not one this code builds"):
        schema("2")


def test_only_schema_4_stores_abstract_kind(pair: Pair) -> None:
    old, new = pair
    assert (old.filter_fields, new.filter_fields) == (SCHEMA_3_FIELDS, (*SCHEMA_3_FIELDS, "abstract_kind"))
    assert "abstract_kind" in new.searcher.doc(new.hits(tantivy.Query.all_query())[0]).to_dict()
    assert "abstract_kind" not in old.searcher.doc(old.hits(tantivy.Query.all_query())[0]).to_dict()


def outcome(engine: TantivyEngine, ast: Node, sort: str = "relevance") -> Any:
    try:
        return engine.ranked(ast, sort)
    except EngineInputError as e:
        return ("refused", e.code)


def shared_facets(new: TantivyEngine, old: TantivyEngine, ast: Node) -> None:
    assert {k: v for k, v in new.facets(ast).items() if k in old.filter_fields} == old.facets(ast)


@pytest.mark.parametrize("name", [n for n in STRINGS if STRINGS[n].strip()])
def test_each_trust_evals_string_ranks_the_same_on_both_schemas(pair: Pair, name: str) -> None:
    old, new = pair
    parsed = trust_evals(name)
    assert parsed.effective_ast is not None
    for sort in SORTS:  # the whole order: ids and exact float scores
        assert outcome(new, parsed.effective_ast, sort) == outcome(old, parsed.effective_ast, sort)
    shared_facets(new, old, parsed.effective_ast)


# every tree the differential suite draws but `abstract_kind:`, on both schemas: no per-example deadline (two
# engines per example)
@settings(max_examples=150, deadline=None)
@given(engine_asts(vocab(), fields=SCHEMA_3_FIELDS))
def test_generated_trees_rank_the_same_on_both_schemas(pair: Pair, ast: Node) -> None:
    old, new = pair
    ranked = outcome(old, ast)
    assert outcome(new, ast) == ranked
    if isinstance(ranked, list):
        shared_facets(new, old, ast)


@pytest.mark.parametrize(
    "q",
    [
        "abstract:(2 NEAR/10 age*)",  # the candidates that failed, excluded (TASK-076)
        '"trust trust*"',  # the ids that held
        "abstract:(trust* NEAR/100 the)",  # no id set: every candidate holds it
        '"large language model$" OR "AI agent$"',
    ],
)
def test_each_verified_form_ranks_the_same_on_both_schemas(pair: Pair, q: str) -> None:
    old, new = pair
    ast = parse(q).ast
    assert ast is not None
    assert new.ranked(ast) == old.ranked(ast) and new.ranked(ast)


def test_schema_3_refuses_what_schema_4_answers(pair: Pair) -> None:
    old, new = pair
    ast = parse("trust abstract_kind:(official OR none)").effective_ast
    assert ast is not None
    with pytest.raises(EngineInputError) as refused:
        old.ranked(ast)
    assert refused.value.code == DiagnosticCode.FIELD_NOT_INDEXED
    answered = new.ranked(ast)
    assert isinstance(answered, list) and answered
    plain = parse("trust").effective_ast
    assert plain is not None
    assert answered == new.ranked(plain)  # every 5k record is official or none


def test_ord_is_indexed(engine: TantivyEngine) -> None:
    query = tantivy.Query.term_set_query(engine.index.schema, "ord", [0, 1])
    assert engine._count(query) == 2
    with pytest.raises(ValueError, match="not one this code builds"):
        schema("1")


def test_an_index_whose_manifest_claims_an_indexed_ord_it_lacks_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A manifest naming schema 3 over files that don't index `ord` is refused when the engine opens it, not
    query by query."""

    def without_ord(version: str | None = None) -> tantivy.Schema:
        """Schema 3's field set with `ord` a fast column only (as the retired schema 2 had it)."""
        b = tantivy.SchemaBuilder()
        b.add_text_field("id", stored=True, tokenizer_name="raw")
        for field in idx.TEXT:
            b.add_text_field(field, stored=True, tokenizer_name=idx.ANALYZER, index_option="position")
        for field in SERVED_SCHEMAS["3"].facets:
            b.add_text_field(field, stored=True, fast=True, tokenizer_name="raw")
        b.add_unsigned_field("year", stored=True, indexed=True, fast=True)
        b.add_unsigned_field("ord", stored=False, indexed=False, fast=True)
        b.add_unsigned_field("title_rank", stored=False, indexed=False, fast=True)
        b.add_bytes_field("record", stored=True, indexed=False)
        return b.build()

    monkeypatch.setattr(idx, "schema", without_ord)
    with pytest.raises(IndexUnservable, match="isn't indexed") as refused:
        tantivy_of(list(records())[:50], tmp_path, "3")  # builds, then opens the index as the API would
    assert refused.value.reason == "schema_version_mismatch"


def test_the_ord_term_set_names_exactly_the_given_ids(engine: TantivyEngine) -> None:
    rng = random.Random(7)
    for size in (1, 2, 50, 1_000):
        ids = rng.sample(engine.ids, size)
        assert engine.ids_of(engine.id_set(ids)) == frozenset(ids)
    with pytest.raises(EngineInternalError):
        engine.id_set(["op:neurips:1900:NotAnId"])


def test_the_ordinal_table_is_lazy_reused_and_resettable(engine: TantivyEngine) -> None:
    engine._ords = None
    ids = engine.ids[:50]
    first = engine.id_set(ids)
    table = engine._ords
    assert table is not None and len(table) == len(engine.ids)
    assert engine.ids_of(first) == frozenset(ids)
    assert engine.ids_of(engine.id_set(ids)) == frozenset(ids)
    assert engine._ords is table
    engine._ords = None
    assert engine.ids_of(engine.id_set(ids)) == frozenset(ids)
    assert engine._ords is not table


@pytest.mark.parametrize("which", [0, 1], ids=["schema3", "schema4"])
def test_filter_values_equal_display_for_every_combo_field(pair: Pair, which: int) -> None:
    """`filter_values` reads the value bitmaps, never a stored document: each held id's values are exactly what
    `display` shows for every `combo` field; an absent id is left out; no ids, nothing."""
    engine = pair[which]
    ids = random.Random(11).sample(engine.ids, 50)
    absent = "op:neurips:1900:NotAnId"
    got = engine.filter_values([*ids, absent])
    shown = engine.display(ids)
    assert set(got) == set(ids)
    assert got == {i: {f: shown[i][f] for f in engine.combo} for i in ids}
    assert set(engine.combo) == (
        {"venue", "year", "track", "status"} | ({"abstract_kind"} if which else set())
    )
    assert engine.filter_values([]) == {} and engine.filter_values([absent]) == {}


def test_a_document_with_no_value_in_a_field_omits_that_field(
    engine: TantivyEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A field none of whose value bitmaps holds the document (it has no value there) is left out of that id's
    values, never a `StopIteration`."""
    i = engine.ids[0]
    bit = 1 << engine._ord_table()[i]
    masks = engine._value_masks()
    track = engine.combo.index("track")
    cleared = tuple(
        tuple((v, m & ~bit) for v, m in values) if n == track else values for n, values in enumerate(masks)
    )
    monkeypatch.setattr(engine, "_masks", cleared)
    got = engine.filter_values([i])
    assert set(got[i]) == set(engine.combo) - {"track"}
