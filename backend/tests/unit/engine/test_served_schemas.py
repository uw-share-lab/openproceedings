"""This code serves two index schemas (TASK-167): schema 3, which new indexes are built at (`ord` indexed, so a
verified clause names its ids as a u64 term set), and schema 2, which an existing index and the search records
pinned to it hold (a term set on the text `id`). Both give the same ids and the same float scores for every
query (guarantee 4 for a pinned index; the record replay across the bump is in
`tests/contract/test_records.py`). An index of any other schema is still refused."""

from __future__ import annotations

import random
from typing import Any

import pytest
import tantivy
from hypothesis import given, settings
from openproceedings.engine.index import SCHEMA_VERSION, SERVED_SCHEMAS, schema
from openproceedings.engine.protocol import EngineInputError, EngineInternalError
from openproceedings.engine.tantivy_engine import SORTS, TantivyEngine, unservable
from openproceedings.query.ast import Node
from openproceedings.query.parser import parse

from tests.bench.test_bench import trust_evals
from tests.fixtures.corpus.synthetic_5k import records, vocab
from tests.golden.test_trust_evals import STRINGS
from tests.strategies import engine_asts
from tests.unit.engine.test_exclusions import tantivy_of

type Pair = tuple[TantivyEngine, TantivyEngine]
MANIFEST: dict[str, Any] = {
    "index_version": "0123456789ab",
    "tokenizer_version": "2",
    "tantivy_version": "0.26.2",
    "ranking_params": {"bm25": {"b": 0.75, "k1": 1.2}},
}


@pytest.fixture(scope="module")
def pair(tmp_path_factory: pytest.TempPathFactory) -> Pair:
    """The 5k corpus indexed at schema 2 and at schema 3."""
    corpus = list(records())
    old = tantivy_of(corpus, tmp_path_factory.mktemp("schema2"), "2")
    new = tantivy_of(corpus, tmp_path_factory.mktemp("schema3"))
    assert (old.ord_indexed, new.ord_indexed) == (False, True)
    assert old.index_version != new.index_version  # the schema is an index_version input
    return old, new


def test_the_current_and_the_previous_schema_are_served_and_no_other() -> None:
    assert SCHEMA_VERSION == "3" and list(SERVED_SCHEMAS) == ["2", "3"]
    assert [f.ord_indexed for f in SERVED_SCHEMAS.values()] == [False, True]
    for served in SERVED_SCHEMAS:
        assert unservable({**MANIFEST, "schema_version": served}) is None
    for refused in ("1", "4", None, 3, [], {}, ["3"]):
        why = unservable({**MANIFEST, "schema_version": refused})
        assert why is not None and why[0] == "schema_version_mismatch" and "build a new index" in why[1]


def test_only_schema_3_indexes_ord(pair: Pair) -> None:
    old, new = pair
    query = tantivy.Query.term_set_query(new.index.schema, "ord", [0, 1])
    assert new._count(query) == 2
    with pytest.raises(ValueError, match="not indexed"):
        old._count(tantivy.Query.term_set_query(old.index.schema, "ord", [0, 1]))
    with pytest.raises(ValueError, match="not one this code builds"):
        schema("1")


def outcome(engine: TantivyEngine, ast: Node, sort: str = "relevance") -> Any:
    try:
        return engine.ranked(ast, sort)
    except EngineInputError as e:
        return ("refused", e.code)


@pytest.mark.parametrize("name", [n for n in STRINGS if STRINGS[n].strip()])
def test_each_trust_evals_string_ranks_the_same_on_both_schemas(pair: Pair, name: str) -> None:
    old, new = pair
    parsed = trust_evals(name)
    assert parsed.effective_ast is not None
    for sort in SORTS:  # the whole order: ids and exact float scores
        assert outcome(new, parsed.effective_ast, sort) == outcome(old, parsed.effective_ast, sort)
    assert new.facets(parsed.effective_ast) == old.facets(parsed.effective_ast)


# every tree the differential suite draws, on both schemas: no per-example deadline (two engines per example)
@settings(max_examples=150, deadline=None)
@given(engine_asts(vocab()))
def test_generated_trees_rank_the_same_on_both_schemas(pair: Pair, ast: Node) -> None:
    old, new = pair
    assert outcome(new, ast) == outcome(old, ast)


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


def test_the_ord_term_set_names_exactly_the_given_ids(pair: Pair) -> None:
    _old, new = pair
    rng = random.Random(7)
    for size in (1, 2, 50, 1_000):
        ids = rng.sample(new.ids, size)
        assert new.ids_of(new.id_set(ids)) == frozenset(ids)
    with pytest.raises(EngineInternalError):
        new.id_set(["op:neurips:1900:NotAnId"])
