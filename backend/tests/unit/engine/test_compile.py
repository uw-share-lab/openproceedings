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
        ('"alpha x" NEAR/0 beta', {"Ab03"}),  # adjacent after the phrase: alpha x | beta
        ('beta NEAR/0 "x y"', {"Ab03"}),  # adjacent before: alpha x y | beta in the abstract (x y beta)
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


@pytest.mark.parametrize(("cap", "refused"), [(5, False), (4, True)])
def test_the_cap_is_inclusive_on_both_engines(
    engines: tuple[TantivyEngine, ReferenceEngine], monkeypatch: pytest.MonkeyPatch, cap: int, refused: bool
) -> None:
    # `trust*` expands to exactly 5 terms: at a cap of 5 it's allowed, at 4 it's refused (spec 02: more than
    # the cap is an error, never the cap itself)
    import openproceedings.engine.reference as ref
    import openproceedings.engine.tantivy_engine as te

    monkeypatch.setattr(te, "MAX_EXPANSIONS", cap)
    monkeypatch.setattr(ref, "MAX_EXPANSIONS", cap)
    w = parse("trust*").ast
    engines[0].expanded.clear()  # the memo from earlier tests would skip the check being tested
    try:
        for engine in engines:
            if refused:
                with pytest.raises(EngineInputError, match="expands to 5 terms"):
                    engine.expand(w)  # type: ignore[arg-type]
            else:
                assert len(engine.expand(w)) == 5  # type: ignore[arg-type]
    finally:  # what was memoised under the patched cap must not leak into later tests
        engines[0].expanded.clear()
        engines[0].compiled.clear()


def test_near_reversed_counts_the_tokens_between_exactly(tmp_path: Path) -> None:
    # `beta x y alpha`: alpha NEAR/2 beta holds (two tokens between, in reverse order), NEAR/1 doesn't
    records = [paper("Rv01", "beta x y alpha"), paper("Rv02", "unrelated")]
    tantivy = TantivyEngine(build_index(snapshot_of(records, tmp_path / "s"), tmp_path / "i", BUILT).path)
    reference = ReferenceEngine(records)
    for q, expected in (("alpha NEAR/2 beta", {"Rv01"}), ("alpha NEAR/1 beta", set())):
        ast = parse(q).ast
        got = {i.rsplit(":", 1)[1] for i in tantivy.match_ids(ast)}  # type: ignore[arg-type]
        assert got == {i.rsplit(":", 1)[1] for i in reference.match_ids(ast)} == expected, q  # type: ignore[arg-type]


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
    for q in ("gamma", "gamma venue:ICLR", "alpha -year:2024", "alpha OR gamma", "(gamma venue:ICLR) delta"):
        result = parse(q)
        for ast in (result.ast, result.effective_ast):  # as typed, and with the default filters the API runs
            assert engines[0].facets(ast) == engines[1].facets(ast), q  # type: ignore[arg-type]
    # a nested AND is flattened: the venue filter inside it is still venue's own conjunct
    assert engines[0].facets(parse("(gamma venue:ICLR) delta").ast)["venue"] == {"ICLR": 1, "NeurIPS": 1}  # type: ignore[arg-type]


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


def scores(engine: TantivyEngine, q: str) -> dict[str, float]:
    query = engine.compile(parse(q).ast).query  # type: ignore[arg-type]
    hits = engine.searcher.search(query, 50).hits
    ords = engine.searcher.fast_field_values("ord", [a for _, a in hits])
    return {engine.ids[o]: s for (s, _), o in zip(hits, ords, strict=True)}  # type: ignore[index]


def test_not_adds_no_score(engines: tuple[TantivyEngine, ReferenceEngine]) -> None:
    assert scores(engines[0], "alpha -zeta") == scores(engines[0], "alpha")
    # under an OR, a NOT branch that matches must add nothing either (Ab05: alpha, no beta, no gamma)
    ab05 = next(i for i in engines[0].ids if i.endswith("Ab05"))
    assert scores(engines[0], "alpha AND (gamma OR NOT beta)")[ab05] == scores(engines[0], "alpha")[ab05]


def test_each_wildcard_expansion_scores_as_its_own_term(
    engines: tuple[TantivyEngine, ReferenceEngine],
) -> None:
    # a wildcard scores exactly as the explicit OR of its expansions, never a flat constant per match
    explicit = "trust OR trusted OR trusts OR trustworthy OR trustx"
    assert scores(engines[0], "trust*") == pytest.approx(scores(engines[0], explicit), rel=1e-6)


def test_a_verified_clause_scores_each_item_once(engines: tuple[TantivyEngine, ReferenceEngine]) -> None:
    ab05 = next(i for i in engines[0].ids if i.endswith("Ab05"))
    near = scores(engines[0], "alpha NEAR/1 alpha")[ab05]  # verified in the abstract only
    assert near == pytest.approx(
        scores(engines[0], "abstract:alpha")[ab05], rel=1e-6
    )  # alpha counted once, the id check adds 0


def test_cli_search_refuses_an_over_cap_wildcard(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    import openproceedings.engine.tantivy_engine as te
    from openproceedings import cli

    index = build_index(snapshot_of(CORPUS, tmp_path / "snap"), tmp_path / "indexes", BUILT).path
    monkeypatch.setattr(te, "MAX_EXPANSIONS", 3)
    for what in ("--ids", "--explain"):
        assert cli.main(["--data-dir", str(tmp_path), "search", "trust*", what, "--index", index.name]) == 1
        err = capsys.readouterr().err
        assert "WILDCARD_TOO_MANY_EXPANSIONS" in err and "Traceback" not in err
    assert cli.main(["--data-dir", str(tmp_path / "empty"), "search", "trust", "--ids"]) == 1
    assert "pass --index" in capsys.readouterr().err  # `current` is set by promotion, not by a build


def test_distinct_items_are_each_scored_once(engines: tuple[TantivyEngine, ReferenceEngine]) -> None:
    engine = engines[0]
    ab03 = next(i for i in engine.ids if i.endswith("Ab03"))
    # verified in both fields: alpha, x and beta each count once per field, as the plain AND does
    assert scores(engine, '"alpha x" NEAR/1 beta')[ab03] == pytest.approx(
        scores(engine, "alpha x beta")[ab03], rel=1e-6
    )
    ab07 = next(i for i in engine.ids if i.endswith("Ab07"))
    # `trust` implies `trust*`, so the candidate holds `trust` once (abstract "trust trustx")
    assert scores(engine, '"trust trust*"')[ab07] == pytest.approx(
        scores(engine, "abstract:trust")[ab07], rel=1e-6
    )


def test_facets_verify_each_clause_once_per_field(tmp_path: Path) -> None:
    engine = TantivyEngine(
        build_index(snapshot_of(CORPUS, tmp_path / "snap"), tmp_path / "indexes", BUILT).path
    )
    reads = []
    real = engine.read

    def counting(query: object, field: str) -> object:
        reads.append(field)
        return real(query, field)  # type: ignore[arg-type]

    engine.read = counting  # type: ignore[method-assign]
    engine.facets(parse("alpha NEAR/1 alpha").effective_ast)  # type: ignore[arg-type]  # default filters: 4 fields
    assert sorted(reads) == ["abstract", "title"]  # not once per facet field


def test_cli_search_index_precedence_and_errors(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from openproceedings import cli

    data = tmp_path / "data"
    index = build_index(snapshot_of(CORPUS, tmp_path / "snap"), data / "indexes", BUILT).path
    monkeypatch.chdir(tmp_path)
    (tmp_path / index.name).mkdir()  # a same-named local directory never shadows the data dir's index
    assert cli.main(["--data-dir", str(data), "search", "alpha", "--ids", "--index", index.name]) == 0
    assert len(capsys.readouterr().out.split()) == 5
    assert cli.main(["--data-dir", str(tmp_path / "none"), "search", "trust NOT", "--ids"]) == 1
    assert "PARSE_" in capsys.readouterr().err  # the query's error first, whatever the index
    assert cli.main(["--data-dir", str(tmp_path / "none"), "search", "trust", "--ids"]) == 1
    assert "pass --index" in capsys.readouterr().err  # a usage error: the log line is at DEBUG
    assert (
        cli.main(["--data-dir", str(tmp_path / "none"), "search", "trust", "--ids", "--index", "nosuch"]) == 1
    )
    err = capsys.readouterr().err
    assert "cli_refused" in err and "op index build" in err  # a named index that isn't there


@pytest.mark.parametrize(
    "q",
    [
        "alpha beta gamma delta",  # AND of four
        "alpha OR beta OR gamma OR delta OR x",  # OR of five
        "alpha beta gamma OR x y z",
        "trust* alpha beta",  # a wildcard expansion beside a three-way AND
        "alpha year:2020..2026 venue:(ICLR OR NeurIPS OR ICML)",
        '"alpha x" "x y" beta',  # verified candidates in a three-way AND
    ],
)
def test_no_compiled_boolean_has_more_than_two_clauses(
    engines: tuple[TantivyEngine, ReferenceEngine], monkeypatch: pytest.MonkeyPatch, q: str
) -> None:
    # a flat Boolean of three or more clauses sums scores in a layout-dependent order (compile.combine)
    import openproceedings.engine.compile as comp
    import tantivy

    sizes: list[int] = []

    class Query:
        def __getattr__(self, name: str) -> object:
            return getattr(tantivy.Query, name)

        def boolean_query(self, clauses: list[tuple[tantivy.Occur, tantivy.Query]]) -> tantivy.Query:
            sizes.append(len(clauses))
            return tantivy.Query.boolean_query(clauses)

    class Tantivy:
        def __getattr__(self, name: str) -> object:
            return Query() if name == "Query" else getattr(tantivy, name)

    monkeypatch.setattr(comp, "tantivy", Tantivy())
    engines[0].verified.clear()
    engines[0].compiled.clear()  # compile afresh, through the patched module
    before = set(both(engines, q))
    assert sizes and max(sizes) == 2, sizes
    monkeypatch.undo()
    assert both(engines, q) == before


def test_combine_refuses_an_empty_list() -> None:
    import tantivy
    from openproceedings.engine.compile import combine

    with pytest.raises(ValueError, match="at least one"):
        combine(tantivy.Occur.Should, [])


def test_an_over_cap_wildcard_is_refused_every_time_and_keeps_only_its_count(tmp_path: Path) -> None:
    records = [paper(f"Cc{i:03d}", f"trust{i:03d}") for i in range(210)]
    engine = TantivyEngine(build_index(snapshot_of(records, tmp_path / "s"), tmp_path / "i", BUILT).path)
    w = parse("trust*").ast
    for _ in range(3):  # the first call fills the cache; the later ones read it
        with pytest.raises(EngineInputError, match="expands to 210 terms"):
            engine.expand(w)  # type: ignore[arg-type]
    assert engine.expanded[("trust", "*")] == 210  # a count, not 210 terms
    small = parse("trust00*").ast
    got = engine.expand(small)  # type: ignore[arg-type]
    got.append("mutated")
    assert engine.expand(small) == [f"trust{i:03d}" for i in range(10)]  # the caller gets a copy


def test_an_over_cap_message_clips_the_quoted_stem(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Spec 02: user text quoted in a message is clipped to 40 characters, so it never grows with the input."""
    import openproceedings.engine.tantivy_engine as te

    stem = "trust" + "x" * 95
    records = [paper(f"Cc{i:03d}", f"{stem}{i}") for i in range(3)]
    engine = TantivyEngine(build_index(snapshot_of(records, tmp_path / "s"), tmp_path / "i", BUILT).path)
    monkeypatch.setattr(te, "MAX_EXPANSIONS", 1)
    with pytest.raises(EngineInputError) as e:
        engine.expand(parse(f"{stem}*").ast)  # type: ignore[arg-type]
    quoted = e.value.message.split("`")[1]
    assert len(quoted) == 40 and quoted.endswith("…") and stem[:10] in quoted


def test_a_tree_compiles_once_per_engine(engines: tuple[TantivyEngine, ReferenceEngine]) -> None:
    engine = engines[0]
    ast = parse("alpha OR trust*").ast
    first = engine.compile(ast)  # type: ignore[arg-type]
    again = engine.compile(ast)  # type: ignore[arg-type]
    assert again.query is first.query and again.explain == first.explain  # the memo, not a recompile
    explain, verified = list(first.explain), list(first.verified)
    again.explain.append("changed")  # a caller's copy: never what the next caller gets
    again.verified.append(again.verified[0] if again.verified else None)  # type: ignore[arg-type]
    fresh = engine.compile(ast)  # type: ignore[arg-type]
    assert fresh.explain == explain and fresh.verified == verified
    assert again.explain is not first.explain and again.verified is not first.verified
    assert engine.compile(parse("alpha OR beta").ast).query is not first.query  # type: ignore[arg-type]
