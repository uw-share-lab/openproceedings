"""Tokenizer parity (spec 03 §Tokenizer, spec 07 §A; task-029): a built index holds exactly normalize()'s
tokens: stored text through its analyzer, positions read back by phrase, and the term dictionary in both
directions. On the synthetic 5k corpus here (LaTeX, NFKC forms, marks, CJK, astral characters); on the real
corpus locally, never in CI."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path

import pytest
from openproceedings.cli import main
from openproceedings.engine import index as index_module
from openproceedings.engine import parity
from openproceedings.engine.index import build_index, open_index
from openproceedings.engine.parity import ParityError, check_parity
from openproceedings.query.normalize import normalize

from tests.corpus import fixture_records
from tests.fixtures.corpus.synthetic_5k import records
from tests.unit.engine.test_exclusions import tantivy_of


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    root = tmp_path_factory.mktemp("parity")
    engine = tantivy_of(list(records()), root)
    return root / "indexes" / engine.index_version, root / "snap"


def test_the_index_holds_normalize_tokens_for_every_record(built: tuple[Path, Path]) -> None:
    report = check_parity(*built, workers=1)
    fields = [normalize(getattr(r, f) or "") for r in records() for f in ("title", "abstract")]
    distinct = {
        (f, t) for r in records() for f in ("title", "abstract") for t in normalize(getattr(r, f) or "")
    }
    assert (report.records, report.terms, report.phrases) == (
        5_000,
        len(distinct),
        sum(len(t) >= 2 for t in fields),
    )


def test_a_multi_segment_index_passes_too(tmp_path: Path) -> None:
    from openproceedings.ingest.dedup import DedupResult

    from tests.unit.engine.test_exclusions import BUILT, as_paper, render

    snap = tmp_path / "snap"
    snap.mkdir()
    papers = tuple(sorted((as_paper(r) for r in fixture_records()[:60]), key=lambda p: p.id))
    for name, data in render(DedupResult(papers, (), ()), [], BUILT).items():
        (snap / name).write_bytes(data)
    path = build_index(snap, tmp_path / "indexes", BUILT, commit_every=7).path
    assert open_index(path).searcher().num_segments > 1
    assert check_parity(path, snap, workers=1).records == 60


def test_a_token_that_differs_names_the_first_record_field_and_token(
    built: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    title = next(r.title for r in records() if r.id == "fx:0003")

    def skewed(text: str) -> list[str]:
        tokens = normalize(text)
        return [*tokens[:1], "zzz", *tokens[2:]] if text == title else tokens

    monkeypatch.setattr(index_module, "normalize", skewed)  # what the check normalizes with, in-process
    with pytest.raises(
        ParityError, match=r"Fx0003: title token 1: the index has '.+', normalize\(\) gives 'zzz'"
    ):
        check_parity(*built, workers=1)


def test_a_shorter_side_is_named_as_nothing() -> None:
    with pytest.raises(
        ParityError, match=r"x: title token 2: the index has nothing, normalize\(\) gives 'c'"
    ):
        parity._first_difference("x", "title", ["a", "b"], ["a", "b", "c"])
    with pytest.raises(ParityError, match=r"token 1: the index has 'b', normalize\(\) gives nothing"):
        parity._first_difference("x", "title", ["a", "b"], ["a"])


def test_tokens_out_of_position_are_caught(built: tuple[Path, Path]) -> None:
    index, _snap = built
    tantivy_index = open_index(index)
    searcher = tantivy_index.searcher()
    r = next(r for r in records() if len(set(normalize(r.title))) >= 3)
    rid = "op:" + r.venue.lower() + f":{r.year}:Fx{r.id[3:]}"
    tokens = normalize(r.title)
    parity._positions(tantivy_index, searcher, rid, "title", tokens)  # as indexed: found
    with pytest.raises(ParityError, match="aren't at consecutive positions"):
        parity._positions(tantivy_index, searcher, rid, "title", tokens[::-1])


@pytest.mark.parametrize("extra", [True, False])
def test_the_dictionary_is_checked_both_ways(
    built: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch, extra: bool
) -> None:
    real = parity.terms

    def changed(searcher: object, field: str) -> list[tuple[str, int]]:
        found = real(searcher, field)  # type: ignore[arg-type]
        if field != "abstract":
            return found
        if extra:  # a term Tantivy invented (or split off): in the index, not in normalize()'s output
            return [*found, ("zzzinvented", 1)]
        return [(t, df) for t, df in found if t != "trust"]  # a term Tantivy dropped

    monkeypatch.setattr(parity, "terms", changed)
    message = (
        r"term 'zzzinvented' in abstract: 1 documents in the index, 0 by normalize"
        if extra
        else r"term 'trust' in abstract: 0 documents in the index, \d+ by normalize"
    )
    with pytest.raises(ParityError, match=message):
        check_parity(*built, workers=1)


@pytest.mark.parametrize("change", ["missing", "extra-last", "extra-first"])
def test_documents_on_one_side_only_are_named(
    built: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    real = parity._stored

    def changed(searcher: object) -> Iterator[tuple[str, dict[str, str]]]:
        docs = list(real(searcher))  # type: ignore[arg-type]
        if change == "missing":
            docs = docs[1:]
        elif change == "extra-last":
            docs.append(("op:zz:2099:Zzzz", {"title": "", "abstract": ""}))
        else:
            docs.insert(0, ("op:aa:2000:Aaaa", {"title": "", "abstract": ""}))
        return iter(docs)

    monkeypatch.setattr(parity, "_stored", changed)
    message = {
        "missing": r"op:\S+: in the snapshot, not in the index",
        "extra-last": r"op:zz:2099:Zzzz: in the index, not in the snapshot",
        "extra-first": r"op:aa:2000:Aaaa: in the index, not in the snapshot",
    }[change]
    with pytest.raises(ParityError, match=message):
        check_parity(*built, workers=1)


def test_an_index_from_another_snapshot_is_refused(built: tuple[Path, Path], tmp_path: Path) -> None:
    other = tantivy_of(fixture_records()[:5], tmp_path)
    with pytest.raises(ParityError, match="built from another snapshot"):
        check_parity(tmp_path / "indexes" / other.index_version, built[1])


def test_the_dictionary_is_read_whole(built: tuple[Path, Path]) -> None:
    searcher = open_index(built[0]).searcher()
    vocabulary = {t for t, _df in parity.terms(searcher, "title")}
    assert vocabulary == {t for r in records() for t in normalize(r.title)}
    assert {"trust", "α", "leq", "godel", "信頼性"} <= vocabulary  # LaTeX, accent macros and CJK made it in


def test_the_cli_reports_parity(built: tuple[Path, Path], capsys: pytest.CaptureFixture[str]) -> None:
    index, snapshot = built
    args = [
        "--data-dir",
        str(index.parent.parent),
        "index",
        "parity",
        "--index",
        str(index),
        "--snapshot",
        str(snapshot),
    ]
    assert main(args) == 0
    assert '"differences": 0' in capsys.readouterr().out


def test_a_failure_prints_the_token_but_never_logs_it(
    built: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(index_module, "normalize", lambda text: [*normalize(text), "leakedtoken"])
    monkeypatch.setattr(parity, "_cpus", lambda: 1)  # in-process, so the patched normalize is used
    index, snapshot = built
    args = [
        "--data-dir",
        str(index.parent.parent),
        "index",
        "parity",
        "--index",
        str(index),
        "--snapshot",
        str(snapshot),
    ]
    with caplog.at_level(logging.DEBUG):
        assert main(args) == 1
    assert "leakedtoken" in capsys.readouterr().err  # the person checking their own index sees it
    assert all(
        "leakedtoken" not in r.getMessage() and "leakedtoken" not in str(r.__dict__) for r in caplog.records
    )
