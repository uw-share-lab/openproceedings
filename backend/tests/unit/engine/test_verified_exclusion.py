"""A verified clause names whichever of its id lists is shorter (TASK-076): the ids that hold it, matched by a
term set beside its candidate query, or the candidates that don't, excluded from it. The candidates are a
superset of the verified ids, so either form matches exactly the verified ids, and the exclusion adds no score
where the term set added 0.0: the scores are the same floats. Tantivy re-resolves an id term set on every
search, so a clause most of whose candidates hold it was the warm search's main cost (`main-2-pop`).

Every case runs on both served schemas (TASK-167): a schema-3 index names the ids as a u64 term set on `ord`
(`TantivyEngine.id_set`), a schema-2 one as a term set on the text `id`, with the same matches and scores."""

from __future__ import annotations

import pytest
import tantivy
from hypothesis import given, settings
from openproceedings.engine.compile import Compiler
from openproceedings.engine.index import SERVED_SCHEMAS
from openproceedings.engine.protocol import EngineInputError
from openproceedings.engine.reference import ReferenceEngine
from openproceedings.engine.tantivy_engine import TantivyEngine, _ord
from openproceedings.query.ast import Node
from openproceedings.query.parser import parse

from tests.corpus import Rec
from tests.fixtures.corpus.synthetic_5k import records, vocab
from tests.golden.test_tantivy_200 import as_paper
from tests.strategies import engine_asts
from tests.unit.engine.test_exclusions import tantivy_of

TEXTS = {
    "Ac01": "large language models",
    "Ac02": "large language model",
    "Ac03": "language large model",  # a candidate of the phrase below that doesn't hold it
    "Ac04": "a large language modeling study",
    "Ac05": "small models",
}
CORPUS = [
    Rec(id=f"fx:{k}", title=t, abstract=None, venue="NeurIPS", year=2024, track="main", status="accepted")
    for k, t in TEXTS.items()
]


@pytest.fixture(scope="module", params=list(SERVED_SCHEMAS))
def small(tmp_path_factory: pytest.TempPathFactory, request: pytest.FixtureRequest) -> TantivyEngine:
    engine = tantivy_of(CORPUS, tmp_path_factory.mktemp("exclusion"), request.param)
    assert engine.ord_indexed == (request.param != "2")
    return engine


@pytest.fixture(scope="module", params=list(SERVED_SCHEMAS))
def synthetic(tmp_path_factory: pytest.TempPathFactory, request: pytest.FixtureRequest) -> TantivyEngine:
    return tantivy_of(list(records()), tmp_path_factory.mktemp("exclusion-5k"), request.param)


def id_sets(engine: TantivyEngine, q: str, monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """The id lists `q`'s compile puts in Tantivy term sets, compiled afresh."""
    seen: list[list[str]] = []
    real = engine.id_set

    def spy(ids: list[str]) -> tantivy.Query:
        seen.append(sorted(i.rsplit(":", 1)[1] for i in ids))
        return real(ids)

    monkeypatch.setattr(engine, "id_set", spy)
    engine.verified.clear()
    engine.compiled.clear()
    ast = parse(q).ast
    assert ast is not None
    engine.compile(ast)
    return seen


def test_a_clause_most_candidates_hold_names_the_candidates_that_dont(
    small: TantivyEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    # title: four candidates hold large, language and model*; three hold the phrase, Ac03 doesn't
    assert id_sets(small, '"large language model*"', monkeypatch) == [["FxAc03"]]


def test_a_clause_few_candidates_hold_names_the_ids_that_do(
    small: TantivyEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    # title: large and model* in Ac01-Ac04; only Ac03 has them adjacent, in that order
    assert id_sets(small, '"large model*"', monkeypatch) == [["FxAc03"]]


def test_a_clause_every_candidate_holds_needs_no_id_set(
    small: TantivyEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert id_sets(small, '"small model*"', monkeypatch) == []


@pytest.mark.parametrize(
    "q",
    [
        '"large language model*"',
        '"large model*"',
        '"small model*"',
        '"lang* large"',
        # the exclusion form inside a tree: under AND, OR and NOT, and beside an unverified clause
        '"large language model*" AND NOT small',
        '"large language model*" OR small',
        'study AND NOT "large language model*"',
        'title:"large language model*" AND large',
        '("large language model*" OR "large model*") AND model*',
    ],
)
def test_each_form_matches_and_scores_as_the_term_set_did(small: TantivyEngine, q: str) -> None:
    ast = parse(q).ast
    assert ast is not None
    assert {i for i, _ in collected(small, ast, members=True)} == ReferenceEngine(
        [as_paper(r) for r in CORPUS]
    ).match_ids(ast)
    assert collected(small, ast, members=True) == collected(small, ast, members=False)


def collected(engine: TantivyEngine, ast: Node, *, members: bool) -> list[tuple[str, float]]:
    """Every match of `ast` and its exact score, compiled afresh with the exclusion form allowed or not."""
    compiled = Compiler(
        engine.index.schema,
        engine.expansions(ast),
        engine.read,
        weights=engine.ranking["field_weights"],
        count=engine._count,
        members=engine.ids_of if members else None,
        id_query=engine.id_set,
    ).compile(ast)
    hits = engine.searcher.search(compiled.query, max(1, engine.searcher.num_docs)).hits
    ords = engine.searcher.fast_field_values("ord", [address for _score, address in hits])
    return sorted((engine.ids[_ord(o)], score) for (score, _address), o in zip(hits, ords, strict=True))


# every tree the differential suite draws, on the 5k corpus: the same ids and the same float scores either way
@settings(deadline=None)
@given(engine_asts(vocab()))
def test_generated_trees_match_and_score_the_same_either_way(synthetic: TantivyEngine, ast: Node) -> None:
    try:
        expected = collected(synthetic, ast, members=False)
    except EngineInputError as refused:  # an over-cap wildcard: refused the same way either way
        with pytest.raises(type(refused)):
            collected(synthetic, ast, members=True)
        return
    assert collected(synthetic, ast, members=True) == expected


# drawn trees rarely reach a clause most of whose candidates hold it, so each form also has 5k cases of its own
@pytest.mark.parametrize(
    ("q", "form"),
    [
        ("abstract:(2 NEAR/10 age*)", "failed"),  # 94 candidates, 69 hold it
        ("abstract:(trust* NEAR/100 the)", "none"),  # 950 candidates, every one holds it
        ('"trust trust*"', "ids"),  # title 16 of 318, abstract 70 of 1,479
        ("(abstract:(2 NEAR/10 age*) OR trust) AND NOT abstract:(trust* NEAR/100 the)", "failed"),
    ],
)
def test_each_form_on_the_5k_corpus(
    synthetic: TantivyEngine, monkeypatch: pytest.MonkeyPatch, q: str, form: str
) -> None:
    sets = id_sets(synthetic, q, monkeypatch)
    ast = parse(q).ast
    assert ast is not None
    holding = synthetic.compile(ast).ids.values()
    if form == "failed":  # a set, and shorter than the ids that held
        assert sets and min(map(len, sets)) < max(map(len, holding))
        assert not any(sorted(i.rsplit(":", 1)[1] for i in ids) in sets for ids in holding if ids)
    elif form == "none":
        assert sets == []
    else:
        assert sets == [sorted(i.rsplit(":", 1)[1] for i in ids) for ids in holding if ids]
    assert collected(synthetic, ast, members=True) == collected(synthetic, ast, members=False)
