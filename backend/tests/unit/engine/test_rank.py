"""Field-weighted BM25 and deterministic ordering (field-weighted-bm25 skill; spec 03 §Ranking): hand-computed
scores on a tiny corpus, determinism across builds, stable pages, id tie-breaks, and filters and NOT that
never reorder. ReferenceEngine doesn't rank, so these compare Tantivy runs with each other and with
arithmetic (decision-004: synthetic records)."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from pathlib import Path

import pytest
from openproceedings.engine.index import build_index
from openproceedings.engine.protocol import EngineInputError
from openproceedings.engine.tantivy_engine import SORTS, TantivyEngine
from openproceedings.ingest.record import PaperRecord
from openproceedings.query.parser import parse

from tests.unit.engine.test_index import snapshot_of
from tests.unit.ingest.test_dedup import paper

BUILT = datetime(2026, 9, 26, tzinfo=UTC)
K1, B = 1.2, 0.75


def engine_of(records: list[PaperRecord], root: Path) -> TantivyEngine:
    return TantivyEngine(build_index(snapshot_of(records, root / "snap"), root / "indexes", BUILT).path)


def ranked(engine: TantivyEngine, q: str, sort: str = "relevance") -> list[tuple[str, float]]:
    return engine.ranked(parse(q).ast, sort)  # type: ignore[arg-type]


def bm25(tf: int, dl: int, avgdl: float, n: int, docs: int) -> float:
    idf = math.log(1 + (docs - n + 0.5) / (n + 0.5))
    return idf * tf * (K1 + 1) / (tf + K1 * (1 - B + B * dl / avgdl))


def test_scores_are_hand_computed_field_weighted_bm25(tmp_path: Path) -> None:
    # titles only: "a b" (2 tokens), "a c d" (3), "e" (1); avgdl 2, `a` in 2 of 3 documents
    records = [paper("Aa01", "a b"), paper("Aa02", "a c d"), paper("Aa03", "e")]
    engine = engine_of(records, tmp_path)
    scores = dict(ranked(engine, "a"))
    assert scores["op:neurips:2024:Aa01"] == pytest.approx(
        2.0 * bm25(1, 2, 2.0, 2, 3), rel=1e-4
    )  # title weight 2
    assert scores["op:neurips:2024:Aa02"] == pytest.approx(2.0 * bm25(1, 3, 2.0, 2, 3), rel=1e-4)


def test_the_title_weighs_twice_the_abstract(tmp_path: Path) -> None:
    # the same text in both fields gives both fields the same statistics
    records = [
        paper(f"Bb{i:02d}", t, abstract=t) for i, t in enumerate(["trust in ai", "trust", "calibration"])
    ]
    engine = engine_of(records, tmp_path)
    title, abstract = dict(ranked(engine, "title:trust")), dict(ranked(engine, "abstract:trust"))
    assert title.keys() == abstract.keys() and all(
        title[i] == pytest.approx(2 * abstract[i], rel=1e-6) for i in title
    )
    both = dict(ranked(engine, "trust"))
    assert all(both[i] == pytest.approx(title[i] + abstract[i], rel=1e-6) for i in both)  # a sum over fields


CORPUS = [
    paper("Cc01", "Trust calibration", abstract="trust in models", year=2023),
    paper("Cc02", "trust", abstract="a survey of trust", year=2024),
    paper("Cc03", "Calibration survey", abstract="trust and calibration", year=2022),
    paper("Cc04", "banana", abstract="trust", year=2024),
    paper("Cc05", "banana", abstract="trust", year=2024),  # identical to Cc04: a tie broken by id
    paper("Cc06", "apple", abstract="trust trust", year=2023),
]
QUERIES = ["trust", "trust -survey", "trust calibration", "trust OR banana", "trust year:2023..2024"]


@pytest.fixture(scope="module")
def two(tmp_path_factory: pytest.TempPathFactory) -> tuple[TantivyEngine, TantivyEngine]:
    return engine_of(CORPUS, tmp_path_factory.mktemp("one")), engine_of(
        CORPUS, tmp_path_factory.mktemp("two")
    )


@pytest.mark.parametrize("sort", SORTS)
@pytest.mark.parametrize("q", QUERIES)
def test_same_query_and_index_give_identical_order_and_scores(
    two: tuple[TantivyEngine, TantivyEngine], q: str, sort: str
) -> None:
    a, b = two
    assert ranked(a, q, sort) == ranked(b, q, sort)  # exact floats, two separate builds


@pytest.mark.parametrize("sort", SORTS)
@pytest.mark.parametrize("q", QUERIES)
def test_pages_cover_the_match_set_exactly(
    two: tuple[TantivyEngine, TantivyEngine], q: str, sort: str
) -> None:
    engine = two[0]
    ast = parse(q).ast
    pages = []
    for offset in range(0, 8, 2):
        page = engine.search(ast, sort=sort, offset=offset, limit=2)  # type: ignore[arg-type]
        assert page.total == len(engine.match_ids(ast))  # type: ignore[arg-type]
        pages += page.ids
    assert len(pages) == len(set(pages)) and set(pages) == engine.match_ids(ast)  # type: ignore[arg-type]
    assert pages == [i for i, _ in ranked(engine, q, sort)]


def test_ties_break_by_id(two: tuple[TantivyEngine, TantivyEngine]) -> None:
    order = [i for i, _ in ranked(two[0], "banana")]
    assert order == ["op:neurips:2024:Cc04", "op:neurips:2024:Cc05"]


def test_filters_and_negations_never_reorder_or_rescore(two: tuple[TantivyEngine, TantivyEngine]) -> None:
    engine = two[0]
    plain = ranked(engine, "trust")
    for q in ("trust year:2023..2024", "trust -survey", "trust -venue:ICLR"):
        kept = ranked(engine, q)
        remaining = [(i, s) for i, s in plain if i in {k for k, _ in kept}]
        assert [i for i, _ in kept] == [i for i, _ in remaining]
        assert [s for _, s in kept] == pytest.approx([s for _, s in remaining], rel=1e-9)


def test_sort_keys(two: tuple[TantivyEngine, TantivyEngine]) -> None:
    engine = two[0]
    by_year = [i[-4:] for i, _ in ranked(engine, "trust", "year_desc")]
    assert by_year == ["Cc02", "Cc04", "Cc05", "Cc01", "Cc06", "Cc03"]  # 2024s, 2023s, 2022, each by id
    assert [i[-4:] for i, _ in ranked(engine, "trust", "year_asc")] == [
        "Cc03",
        "Cc01",
        "Cc06",
        "Cc02",
        "Cc04",
        "Cc05",
    ]
    # casefolded display title, then id: apple, banana, banana, calibration survey, trust, trust calibration
    assert [i[-4:] for i, _ in ranked(engine, "trust", "title")] == [
        "Cc06",
        "Cc04",
        "Cc05",
        "Cc03",
        "Cc02",
        "Cc01",
    ]
    relevance = ranked(engine, "trust")
    assert [s for _, s in relevance] == sorted((s for _, s in relevance), reverse=True)


def test_an_unknown_sort_is_a_bad_parameter(two: tuple[TantivyEngine, TantivyEngine]) -> None:
    with pytest.raises(EngineInputError, match="sort must be one of"):
        ranked(two[0], "trust", "citations")
    with pytest.raises(EngineInputError, match="task-059"):
        ranked(two[0], "trust", "semantic")


def test_an_empty_match_set_ranks_as_empty(two: tuple[TantivyEngine, TantivyEngine]) -> None:
    assert ranked(two[0], "zebra") == [] and two[0].search(parse("zebra").ast).total == 0  # type: ignore[arg-type]


def test_order_never_depends_on_tantivys_hit_order(tmp_path: Path) -> None:
    engine = engine_of(CORPUS, tmp_path)
    expected = {sort: ranked(engine, "trust OR banana", sort) for sort in SORTS}
    real = engine.searcher

    class Reversed:  # Tantivy returning its hits in another order (e.g. another segment layout)
        def __getattr__(self, name: str) -> object:
            return getattr(real, name)

        def search(self, *a: object, **kw: object) -> object:
            result = real.search(*a, **kw)
            return type("R", (), {"hits": list(reversed(result.hits)), "count": result.count})()

    engine.searcher = Reversed()  # type: ignore[assignment]
    assert {sort: ranked(engine, "trust OR banana", sort) for sort in SORTS} == expected
