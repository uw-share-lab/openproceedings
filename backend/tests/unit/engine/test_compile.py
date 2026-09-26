"""AST → Tantivy compilation: every table row and gotcha of the ast-compilation skill, each checked against
ReferenceEngine on a small crafted corpus (synthetic, decision-004)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from openproceedings.engine.index import build_index
from openproceedings.engine.protocol import EngineInputError
from openproceedings.engine.reference import ReferenceEngine
from openproceedings.engine.tantivy_engine import TantivyEngine
from openproceedings.ingest.record import PaperRecord
from openproceedings.query.parser import parse

from tests.unit.engine.test_index import snapshot_of
from tests.unit.ingest.test_dedup import paper

BUILT = datetime(2026, 9, 26, tzinfo=UTC)
TEXTS = {
    "Ab01": ("alpha beta", "gamma delta"),
    "Ab02": ("beta alpha", "x y z"),
    "Ab03": ("alpha x beta", "alpha x y beta"),
    "Ab04": ("alpha x y z beta", None),
    "Ab05": ("alpha", "alpha q alpha"),
    "Ab06": ("vision language models", "trust in language"),
    "Ab07": ("trustworthy trusted trusts", "trust trustx"),
    "Ab08": ("gamma", "delta gamma"),
}
CORPUS: list[PaperRecord] = [
    paper(
        k,
        t,
        abstract=a,
        year=2023 if k in ("Ab01", "Ab02") else 2024,
        venue="ICLR" if k == "Ab08" else "NeurIPS",
    )
    for k, (t, a) in TEXTS.items()
]


@pytest.fixture(scope="module")
def engines(tmp_path_factory: pytest.TempPathFactory) -> tuple[TantivyEngine, ReferenceEngine]:
    root = tmp_path_factory.mktemp("compile")
    index = build_index(snapshot_of(CORPUS, root / "snap"), root / "indexes", BUILT).path
    return TantivyEngine(index), ReferenceEngine(CORPUS)


def both(engines: tuple[TantivyEngine, ReferenceEngine], q: str) -> set[str]:
    result = parse(q)
    assert result.ast is not None, result.errors
    tantivy_ids, reference_ids = engines[0].match_ids(result.ast), engines[1].match_ids(result.ast)
    assert tantivy_ids == reference_ids, q
    return {i.rsplit(":", 1)[1] for i in tantivy_ids}


@pytest.mark.parametrize(
    ("q", "expected"),
    [
        ("alpha", {"Ab01", "Ab02", "Ab03", "Ab04", "Ab05"}),
        ("title:alpha", {"Ab01", "Ab02", "Ab03", "Ab04", "Ab05"}),
        ("abstract:alpha", {"Ab03", "Ab05"}),
        ('"alpha beta"', {"Ab01"}),
        ('"beta gamma"', set()),  # a phrase never crosses from title into abstract
        ("vision-language", {"Ab06"}),  # a term that normalizes to two tokens is a phrase
        ("alpha NEAR/0 beta", {"Ab01", "Ab02"}),  # adjacent, both orders
        ("alpha NEAR/1 beta", {"Ab01", "Ab02", "Ab03"}),
        ("alpha NEAR/2 beta", {"Ab01", "Ab02", "Ab03"}),
        ("alpha NEAR/3 beta", {"Ab01", "Ab02", "Ab03", "Ab04"}),  # n + 1 brings in three between
        ("alpha NEAR/1 alpha", {"Ab05"}),  # two distinct occurrences: `alpha q alpha`, never one alone
        ("alpha NEAR/0 alpha", set()),
        ('"alpha x" NEAR/1 beta', {"Ab03"}),  # a phrase operand takes the verified fallback
        ('"alpha x*" NEAR/2 beta', {"Ab03", "Ab04"}),
        ('"trust*" language', {"Ab06"}),
        ('"in lang*"', {"Ab06"}),  # a wildcard phrase item is verified by position
        ("trust*", {"Ab06", "Ab07"}),
        ("trust$", {"Ab06", "Ab07"}),  # the stem or one more character: trust, trusts, trustx
        ("zzz*", set()),  # an empty expansion matches nothing
        ("alpha zzz*", set()),  # and never widens an AND by being dropped
        ("alpha AND (beta OR NOT gamma)", {"Ab01", "Ab02", "Ab03", "Ab04", "Ab05"}),  # a nested NOT
        ("alpha AND (x OR NOT delta)", {"Ab02", "Ab03", "Ab04", "Ab05"}),
        ("alpha -beta", {"Ab05"}),
        ("alpha year:2023", {"Ab01", "Ab02"}),
        ("gamma venue:ICLR", {"Ab08"}),
        ("gamma -venue:ICLR", {"Ab01"}),
        ("alpha year:2023..2024", {"Ab01", "Ab02", "Ab03", "Ab04", "Ab05"}),
    ],
)
def test_rows_agree_with_the_oracle(
    engines: tuple[TantivyEngine, ReferenceEngine], q: str, expected: set[str]
) -> None:
    assert both(engines, q) == expected


def test_verified_clauses_are_reported(engines: tuple[TantivyEngine, ReferenceEngine]) -> None:
    compiled = engines[0].compile(parse('alpha NEAR/1 alpha OR "in lang*"').ast)  # type: ignore[arg-type]
    assert sorted(compiled.verified) == [
        "abstract: NEAR/1",
        "abstract: phrase",
        "title: NEAR/1",
        "title: phrase",
    ]
    plain = engines[0].compile(parse("alpha NEAR/2 beta").ast)  # type: ignore[arg-type]
    assert plain.verified == []  # distinct single terms use slop, no fallback


def test_filters_never_change_scores(engines: tuple[TantivyEngine, ReferenceEngine]) -> None:
    engine = engines[0]

    def scores(q: str) -> dict[str, float]:
        query = engine.compile(parse(q).ast).query  # type: ignore[arg-type]
        return {engine.ids[o]: s for (s, a), o in zip(engine.searcher.search(query, 50).hits,
                engine.searcher.fast_field_values("ord", [a for _, a in engine.searcher.search(query, 50).hits]), strict=True)}  # fmt: skip

    plain, filtered = scores("alpha"), scores("alpha year:2023..2024")
    assert filtered == plain and len(plain) == 5


def test_expansions_and_the_cap(
    engines: tuple[TantivyEngine, ReferenceEngine], monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, reference = engines
    w = parse("trust*").ast
    assert engine.expand(w) == reference.expand(w) == ["trust", "trusted", "trusts", "trustworthy", "trustx"]  # type: ignore[arg-type]
    import openproceedings.engine.tantivy_engine as te

    monkeypatch.setattr(te, "MAX_EXPANSIONS", 3)
    with pytest.raises(EngineInputError, match="expands to 5 terms"):
        engine.match_ids(parse("alpha OR trust*").ast)  # type: ignore[arg-type]


def test_explain_shows_the_tree_expansions_and_fallbacks(
    engines: tuple[TantivyEngine, ReferenceEngine],
) -> None:
    text = engines[0].explain(parse('alpha year:2023 "in lang*" NOT gamma').ast)  # type: ignore[arg-type]
    assert "filter year in 2023..2023 (non-scoring)" in text
    assert "title: term alpha" in text and "abstract: term alpha" in text
    assert "NOT (all documents, minus:)" in text
    assert "lang*: language" in text
    assert "verified by position: title: phrase; abstract: phrase" in text


def test_facets_agree_with_the_oracle(engines: tuple[TantivyEngine, ReferenceEngine]) -> None:
    for q in ("gamma", "gamma venue:ICLR", "alpha -year:2024", "alpha OR gamma"):
        ast = parse(q).ast
        assert engines[0].facets(ast) == engines[1].facets(ast), q  # type: ignore[arg-type]


def test_search_pages_in_id_order(engines: tuple[TantivyEngine, ReferenceEngine]) -> None:
    ast = parse("alpha").ast
    assert engines[0].search(ast, offset=1, limit=2) == engines[1].search(ast, offset=1, limit=2)  # type: ignore[arg-type]
    with pytest.raises(EngineInputError):
        engines[0].search(ast, offset=-1)  # type: ignore[arg-type]


def test_a_query_is_never_parsed_by_tantivy() -> None:
    import openproceedings.engine.compile as compile_module
    import openproceedings.engine.tantivy_engine as engine_module

    for module in (compile_module, engine_module):
        source = Path(module.__file__).read_text(encoding="utf-8")  # type: ignore[arg-type]
        assert "parse_query" not in source  # we compile our own AST, never Tantivy's query language


def test_cli_search_explain_and_ids(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from openproceedings import cli

    data = tmp_path / "data"
    index = build_index(snapshot_of(CORPUS, tmp_path / "snap"), data / "indexes", BUILT).path
    (data / "indexes" / "current").symlink_to(index.name)
    assert cli.main(["--data-dir", str(data), "search", "alpha NEAR/1 alpha", "--explain"]) == 0
    out = capsys.readouterr().out
    assert "canonical:" in out and "track:(" in out  # the default filters are what runs
    assert "verified by position: title: NEAR/1; abstract: NEAR/1" in out and index.name in out
    assert (
        cli.main(["--data-dir", str(data), "search", "alpha year:2023", "--ids", "--index", index.name]) == 0
    )
    assert capsys.readouterr().out.split() == ["op:neurips:2023:Ab01", "op:neurips:2023:Ab02"]
    assert cli.main(["--data-dir", str(data), "search", "trust NOT", "--ids"]) == 1  # a parse error
    assert "PARSE_" in capsys.readouterr().err
