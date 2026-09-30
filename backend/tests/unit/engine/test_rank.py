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
        assert [s for _, s in kept] == [s for _, s in remaining]  # exact floats: never re-scored


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
    with pytest.raises(EngineInputError, match="deferred to phase 2 \\(decision-017\\)"):
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


# --- review rows (task-025, 2026-09-26) ----------------------------------------------------------------------


def repeated(n: int) -> list[PaperRecord]:
    """Identical texts far apart in id order, among other texts."""
    texts = [("trust model agent", "language evaluation benchmark"), ("model language", "trust agent"),
             ("benchmark", "evaluation of trust")]  # fmt: skip
    return [paper(f"Rr{i:04d}", *texts[i % 3][:1], abstract=texts[i % 3][1]) for i in range(n)]


@pytest.mark.parametrize(
    "q",
    [
        "trust OR model OR agent",
        "model OR language OR evaluation OR benchmark OR agent",
        "trust* OR mod*",
        "trust agent model",
    ],
)
def test_segment_layout_never_changes_scores_or_order(tmp_path: Path, q: str) -> None:
    one = TantivyEngine(build_index(snapshot_of(repeated(60), tmp_path / "s1"), tmp_path / "one", BUILT).path)
    many = TantivyEngine(
        build_index(snapshot_of(repeated(60), tmp_path / "s2"), tmp_path / "many", BUILT, commit_every=7).path
    )
    assert many.searcher.num_segments > 1
    a, b = ranked(one, q), ranked(many, q)
    assert a == b  # exact order and exact floats, whatever the segments
    by_text: dict[int, set[float]] = {}
    for i, s in a:
        by_text.setdefault(int(i[-4:]) % 3, set()).add(s)
    assert all(len(v) == 1 for v in by_text.values())  # identical texts score identically, so ids break ties


@pytest.mark.parametrize("q", ["w OR x OR y OR z", "x OR y OR z OR w", "z OR y OR x OR w"])
def test_identical_texts_score_equally_across_union_windows(tmp_path: Path, q: str) -> None:
    # Tantivy's union scores 4,096 documents at a time and drops a finished term's scorer by swapping the last
    # one into its place, so a flat union of ≥3 clauses adds in a new order after `w` runs out: identical texts
    # before and after that 4,096 boundary differ by an ulp. Balanced binary trees (`combine`) never reorder.
    n = 4_300
    texts = [" ".join(["x"] * (1 + g % 3) + ["y"] * (1 + g % 5) + ["z"] * (1 + g % 7) + ["pad"] * (g % 11))
             for g in range(40)]  # fmt: skip

    def text(i: int) -> str:
        return texts[i] if i < 40 else texts[i - (n - 40)] if i >= n - 40 else "w" if i == 45 else "filler"

    engine = engine_of([paper(f"Uu{i:05d}", "t", abstract=text(i)) for i in range(n)], tmp_path)
    by_text: dict[str, set[float]] = {}
    for i, s in ranked(engine, q):
        if i[-5:] != "00045":
            by_text.setdefault(text(int(i[-5:])), set()).add(s)
    assert len(by_text) == 40
    assert all(len(v) == 1 for v in by_text.values())


def test_an_index_from_other_versions_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import openproceedings.engine.index as idx
    from openproceedings.engine.protocol import EngineError

    for name, value in (("SCHEMA_VERSION", "1"), ("TOKENIZER_VERSION", "1")):
        with monkeypatch.context() as m:
            m.setattr(idx, name, value)
            path = build_index(snapshot_of(CORPUS, tmp_path / name), tmp_path / f"i-{name}", BUILT).path
        with pytest.raises(EngineError, match="build a new index"):
            TantivyEngine(path)
    with monkeypatch.context() as m:
        m.setattr(idx, "version", lambda _name: "0.0.1")  # an index built by another Tantivy
        path = build_index(snapshot_of(CORPUS, tmp_path / "tv"), tmp_path / "i-tv", BUILT).path
    with pytest.raises(EngineError, match=r"tantivy_version 0\.0\.1"):
        TantivyEngine(path)
    with monkeypatch.context() as m:
        m.setattr(idx, "RANKING_PARAMS", {**idx.RANKING_PARAMS, "bm25": {"b": 0.75, "k1": 1.3}})
        path = build_index(snapshot_of(CORPUS, tmp_path / "bm25"), tmp_path / "i-bm25", BUILT).path
    with pytest.raises(EngineError, match="Tantivy applies"):
        TantivyEngine(path)


def test_weights_come_from_the_index_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import openproceedings.engine.index as idx

    records = [
        paper(f"Bb{i:02d}", t, abstract=t) for i, t in enumerate(["trust in ai", "trust", "calibration"])
    ]
    with monkeypatch.context() as m:
        m.setattr(
            idx, "RANKING_PARAMS", {**idx.RANKING_PARAMS, "field_weights": {"abstract": 1.0, "title": 3.0}}
        )
        path = build_index(snapshot_of(records, tmp_path / "s"), tmp_path / "i", BUILT).path
    engine = TantivyEngine(path)  # the module constant is back to 2.0: the index's own 3.0 must win
    title, abstract = dict(ranked(engine, "title:trust")), dict(ranked(engine, "abstract:trust"))
    assert all(title[i] == pytest.approx(3 * abstract[i], rel=1e-6) for i in title)


def test_every_match_is_ranked_however_many(tmp_path: Path) -> None:
    engine = engine_of([paper(f"Mm{i:05d}", "trust", abstract="x") for i in range(1_100)], tmp_path)
    assert (
        len(ranked(engine, "trust")) == 1_100
        and engine.search(parse("trust").ast, offset=1_090).total == 1_100
    )  # type: ignore[arg-type]
    assert len(engine.search(parse("trust").ast, offset=1_090).ids) == 10  # type: ignore[arg-type]


def test_title_sort_normalizes_before_casefolding(tmp_path: Path) -> None:
    records = [paper("Tt01", "strassf"), paper("Tt02", "Straße z"),  # casefold: strasse z < strassf
               paper("Tt03", "Zebra"), paper("Tt04", "E\u0301cole"), paper("Tt05", "\u00c9cole")]  # fmt: skip
    engine = engine_of(records, tmp_path)
    order = [i[-4:] for i, _ in engine.ranked(parse("strassf OR z OR zebra OR ecole").ast, "title")]  # type: ignore[arg-type]
    # casefold puts `strasse z` before `strassf`; NFKC makes both Écoles `école` (after `z` in code points),
    # side by side and in id order
    assert order == ["Tt02", "Tt01", "Tt03", "Tt04", "Tt05"]


def test_the_title_pass_reads_lines_as_the_validating_pass_does(tmp_path: Path) -> None:
    import hashlib
    import json

    from openproceedings.ingest.snapshot import SnapshotError

    snap = snapshot_of(CORPUS, tmp_path / "s")
    data = (snap / "records.jsonl").read_bytes().replace(b'{"', b'{\r"', 1)  # a CR between JSON tokens
    (snap / "records.jsonl").write_bytes(data)
    manifest = json.loads((snap / "manifest.json").read_text())
    (snap / "manifest.json").write_text(
        json.dumps({**manifest, "snapshot_hash": hashlib.sha256(data).hexdigest()})
    )
    assert len(ranked(TantivyEngine(build_index(snap, tmp_path / "i", BUILT).path), "trust")) == 6
    bad = snapshot_of(CORPUS, tmp_path / "b")
    (bad / "records.jsonl").write_bytes(
        (bad / "records.jsonl").read_bytes().replace(b"trust", b"tr\xffst", 1)
    )
    with pytest.raises(SnapshotError):  # invalid UTF-8: a clean refusal, never a raw decode error
        build_index(bad, tmp_path / "ib", BUILT)


def test_the_installed_tantivy_is_the_one_bm25_was_confirmed_on() -> None:
    from importlib.metadata import version

    from openproceedings.engine.tantivy_engine import TANTIVY_PINNED

    # k1/b are Tantivy's constants, checked by hand on this version: an upgrade re-checks them
    assert version("tantivy") == TANTIVY_PINNED
