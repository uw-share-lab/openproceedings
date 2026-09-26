"""Tokenizer parity (spec 03 §Tokenizer, spec 07 §A; task-029): a built index holds exactly normalize()'s
tokens, read back per document through its analyzer and per term from its dictionary. On the synthetic 5k
corpus here (LaTeX, NFKC forms, marks, CJK, astral characters); on the real corpus locally, never in CI."""

from __future__ import annotations

from pathlib import Path

import pytest
from openproceedings.cli import main
from openproceedings.engine import parity
from openproceedings.engine.parity import ParityError, check_parity
from openproceedings.query.normalize import normalize

from tests.fixtures.corpus.synthetic_5k import records
from tests.unit.engine.test_exclusions import tantivy_of


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    root = tmp_path_factory.mktemp("parity")
    engine = tantivy_of(list(records()), root)
    return root / "indexes" / engine.index_version, root / "snap"


def test_the_index_holds_normalize_tokens_for_every_record(built: tuple[Path, Path]) -> None:
    report = check_parity(*built)
    distinct = {
        (f, t) for r in records() for f in ("title", "abstract") for t in normalize(getattr(r, f) or "")
    }
    assert (report.records, report.terms) == (5_000, len(distinct))


def test_a_token_that_differs_names_the_first_record_field_and_token(
    built: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    real = parity.normalize
    victim = "fx:0003"  # a record id in the raw fixture; its title is changed in normalize's eyes
    title = next(r.title for r in records() if r.id == victim)

    def skewed(text: str) -> list[str]:
        tokens = real(text)
        return [*tokens[:1], "zzz", *tokens[2:]] if text == title else tokens

    monkeypatch.setattr(parity, "normalize", skewed)
    with pytest.raises(
        ParityError, match=r"Fx0003: title token 1: the index has '.+', normalize\(\) gives 'zzz'"
    ):
        check_parity(*built)


def test_a_term_the_dictionary_lacks_is_named(
    built: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    real = parity.terms

    def dropped(searcher: object, field: str) -> list[tuple[str, int]]:
        return [(t, df) for t, df in real(searcher, field) if not (field == "abstract" and t == "trust")]  # type: ignore[arg-type]

    monkeypatch.setattr(parity, "terms", dropped)
    with pytest.raises(
        ParityError, match=r"term 'trust' in abstract: 0 documents in the index, \d+ by normalize"
    ):
        check_parity(*built)


def test_the_dictionary_is_read_whole(built: tuple[Path, Path]) -> None:
    from openproceedings.engine.index import open_index

    searcher = open_index(built[0]).searcher()
    vocabulary = {t for t, _df in parity.terms(searcher, "title")}
    assert vocabulary == {t for r in records() for t in normalize(r.title)}
    assert {"trust", "α", "leq", "godel", "信頼性"} <= vocabulary  # LaTeX, accent macros and CJK made it in


def test_the_cli_reports_parity(built: tuple[Path, Path], capsys: pytest.CaptureFixture[str]) -> None:
    index, snapshot = built
    assert (
        main(
            [
                "--data-dir",
                str(index.parent.parent),
                "index",
                "parity",
                "--index",
                str(index),
                "--snapshot",
                str(snapshot),
            ]
        )
        == 0
    )
    assert '"differences": 0' in capsys.readouterr().out
