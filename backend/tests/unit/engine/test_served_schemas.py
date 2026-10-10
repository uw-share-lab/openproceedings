"""This code serves one index schema, 3 (`ord` indexed, so a verified clause names its ids as a u64 term set). Schema 2
was retired once no record pinned a schema-2 index (decision-049 milestone C); an index of any other schema is
refused. The two-schema comparisons return when a schema 4 is served beside 3."""

from __future__ import annotations

import random
from pathlib import Path
from typing import Any

import pytest
import tantivy
from openproceedings.engine import index as idx
from openproceedings.engine.index import SCHEMA_VERSION, SERVED_SCHEMAS, schema
from openproceedings.engine.protocol import EngineInternalError
from openproceedings.engine.tantivy_engine import IndexUnservable, TantivyEngine, unservable

from tests.fixtures.corpus.synthetic_5k import records
from tests.unit.engine.test_exclusions import tantivy_of

MANIFEST: dict[str, Any] = {
    "index_version": "0123456789ab",
    "tokenizer_version": "2",
    "tantivy_version": "0.26.2",
    "ranking_params": {"bm25": {"b": 0.75, "k1": 1.2}},
}


@pytest.fixture(scope="module", params=["2", "3"])
def engine(tmp_path_factory: pytest.TempPathFactory, request: pytest.FixtureRequest) -> TantivyEngine:
    """The 5k corpus indexed at schema 3, at each served tokenizer."""
    built = tantivy_of(list(records()), tmp_path_factory.mktemp("schema3"), "3", request.param)
    assert built.tokenizer_version == request.param
    return built


def test_only_schema_3_is_served_once_schema_2_is_retired() -> None:
    """Schema 2 retired (index-versioning skill §Two served schemas): no record pinned a schema-2 index."""
    assert SCHEMA_VERSION == "3" and list(SERVED_SCHEMAS) == ["3"]
    assert unservable({**MANIFEST, "schema_version": "3"}) is None
    for refused in ("1", "2", "4", None, 3, [], {}, ["3"]):
        why = unservable({**MANIFEST, "schema_version": refused})
        assert why is not None and why[0] == "schema_version_mismatch" and "build a new index" in why[1]
    with pytest.raises(ValueError, match="not one this code builds"):
        schema("2")


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
        for field in idx.FACETS:
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
