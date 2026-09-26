"""`op search` and `op export` (spec 08 §CLI, spec 04 §Exports; task-030): every format streams the full
matched set in id order and round-trips to its ids; BibTeX passes the pinned refaudit parser; the CLI prints
diagnostics to stderr and logs one privacy-safe `search_run` line."""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path

import pytest
from openproceedings import export
from openproceedings.cli import main
from openproceedings.engine.index import build_index
from openproceedings.engine.tantivy_engine import TantivyEngine
from openproceedings.export import Provenance, bibtex_key, write
from openproceedings.ingest.record import PaperRecord
from openproceedings.query.parser import parse
from refaudit.bibtex import parse_string

from tests.unit.engine.test_index import snapshot_of
from tests.unit.ingest.test_dedup import paper

CORPUS: list[PaperRecord] = [
    paper("AbCd0001", "Trust in {BERT} models", abstract="We study trust.\nAcross two lines.",
          authors=("Jo Smith", "Ana Pérez"), urls_forum="https://openreview.net/forum?id=AbCd0001",
          urls_pdf="https://openreview.net/pdf?id=AbCd0001", venue="ICLR", year=2024),
    paper("AbCd0002", "Trust calibration", abstract=None, authors=("Jo Smith",), venue="ICLR", year=2024,
          urls_doi="10.1234/abcd"),
    paper("AbCd0003", "Trust a } unbalanced title", abstract="Trust, with 100% of {braces.",
          authors=("Jo Smith",), venue="ICLR", year=2024, track="workshop"),
    paper("AbCd0004", "Ørsted and trust", abstract="Trust in Gödel.", authors=(), venue="ICML", year=2021),
    paper("AbCd0005", "Nothing relevant", abstract="Other words.", authors=("Li Wei",), venue="NeurIPS"),
]  # fmt: skip
PROVENANCE = Provenance("abcdef123456", "0" * 64, "2026-09-26")


@pytest.fixture(scope="module")
def data_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("export-data")
    snap = snapshot_of(CORPUS, root / "snapshots" / "2026-09-26-fixture")
    build_index(snap, root / "indexes")
    return root


def index_of(data_dir: Path) -> Path:
    return next(p for p in (data_dir / "indexes").iterdir() if not p.name.startswith("."))  # not `.lock`


def engine_of(data_dir: Path) -> TantivyEngine:
    return TantivyEngine(index_of(data_dir))


def exported(data_dir: Path, fmt: str, q: str = "trust track:(main OR workshop)") -> tuple[str, int]:
    engine = engine_of(data_dir)
    out = io.StringIO()
    n = write(fmt, engine.documents(parse(q).effective_ast), PROVENANCE, out)  # type: ignore[arg-type]
    return out.getvalue(), n


MATCHED = ["AbCd0001", "AbCd0002", "AbCd0003", "AbCd0004"]  # `trust`, main or workshop, every status


def ids_in_order(ids: list[str]) -> list[str]:
    return [i.rsplit(":", 1)[1] for i in ids]


def test_ris_round_trips_every_id_in_id_order(data_dir: Path) -> None:
    text, n = exported(data_dir, "ris")
    records = [r for r in text.split("ER  -") if r.strip()]
    assert n == len(records) == 4
    ids = [line[6:] for line in text.splitlines() if line.startswith("ID  - ")]
    assert ids == sorted(ids) and sorted(ids_in_order(ids)) == MATCHED
    first = records[[i.endswith("AbCd0001") for i in ids].index(True)]
    assert "TY  - CPAPER" in first and "AU  - Jo Smith\nAU  - Ana Pérez" in first
    assert "AB  - We study trust. Across two lines." in first  # RIS is line-based
    assert "T2  - International Conference on Learning Representations (ICLR 2024)" in first
    urls = [line for line in first.splitlines() if line.startswith("UR  - ")]
    assert urls[0].endswith("forum?id=AbCd0001") and urls[1].endswith("pdf?id=AbCd0001")  # forum, then pdf
    assert f"N1  - {PROVENANCE.line()}" in first and "KW  - main" in first
    assert "DO  - 10.1234/abcd" in text


def test_csv_has_a_bom_the_schema_columns_and_provenance(data_dir: Path) -> None:
    text, n = exported(data_dir, "csv")
    assert text.startswith("﻿")
    rows = list(csv.DictReader(io.StringIO(text[1:])))
    assert n == len(rows) == 4 and tuple(rows[0]) == export.CSV_COLUMNS
    assert [r["id"] for r in rows] == sorted(r["id"] for r in rows)
    first = next(r for r in rows if r["id"].endswith("AbCd0001"))
    assert (
        first["authors"] == "Jo Smith; Ana Pérez"
        and first["abstract"] == "We study trust.\nAcross two lines."
    )
    assert {r["index_version"] for r in rows} == {"abcdef123456"}
    assert next(r for r in rows if r["id"].endswith("AbCd0002"))["abstract"] == ""


def test_bibtex_passes_refaudit_and_recovers_every_id(data_dir: Path) -> None:
    text, n = exported(data_dir, "bibtex")
    entries = parse_string(text)
    assert n == len(entries) == 4 and all(e.entry_type == "inproceedings" for e in entries)
    assert sorted(ids_in_order([e.fields["openproceedings_id"] for e in entries])) == MATCHED
    keys = [e.key for e in entries]
    assert keys[:3] == ["smith2024trust", "smith2024trusta", "smith2024trustb"]  # a repeat key gets a, b, …
    assert keys[3] == "anon2021rsted"  # no authors; `Ø` has no ASCII form, so the first word is `rsted`
    assert entries[0].fields["title"] == "Trust in {BERT} models"  # balanced braces keep their meaning
    assert entries[0].fields["note"] == PROVENANCE.line()


def test_jsonl_is_one_record_per_line(data_dir: Path) -> None:
    text, n = exported(data_dir, "jsonl")
    rows = [json.loads(line) for line in text.splitlines()]
    assert n == len(rows) == 4 and [r["id"] for r in rows] == sorted(r["id"] for r in rows)
    assert all(r["canonical_hash"] == "0" * 64 and r["index_version"] == "abcdef123456" for r in rows)
    assert rows[0]["authors"] == ["Jo Smith", "Ana Pérez"] and rows[0]["urls"]["pdf"].endswith("AbCd0001")


def test_bibtex_keys() -> None:
    assert bibtex_key({"authors": ["Kurt Gödel"], "year": 1931, "title": "Über formal"}) == "godel1931uber"
    assert bibtex_key({"authors": [], "year": 2024, "title": "!!!"}) == "anon2024untitled"
    assert [export._suffix(n) for n in (0, 1, 25, 26, 27)] == ["a", "b", "z", "aa", "ab"]


def run(data_dir: Path, *args: str) -> int:
    return main(["--data-dir", str(data_dir), *args, "--index", index_of(data_dir).name])


def test_op_export_writes_the_file_whole(
    data_dir: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "out.jsonl"
    assert run(data_dir, "export", "trust", "--format", "jsonl", "--out", str(out)) == 0
    assert (
        len(out.read_text().splitlines()) == 3
    )  # the defaults (main/… and accepted) leave out the workshop paper
    assert not (tmp_path / "out.jsonl.partial").exists()
    assert "exported 3 records (jsonl)" in capsys.readouterr().err


def test_op_export_leaves_no_partial_file_when_it_fails(
    data_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(*_args: object) -> int:
        raise OSError("disk full")

    monkeypatch.setattr(export, "write", broken)
    out = tmp_path / "out.ris"
    assert run(data_dir, "export", "trust", "--format", "ris", "--out", str(out)) == 1
    assert not out.exists() and not (tmp_path / "out.ris.partial").exists()


def test_op_export_to_stdout(data_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert run(data_dir, "export", "trust status:(accepted OR rejected)", "--format", "ris") == 0
    assert capsys.readouterr().out.count("ER  -") == 3


def test_op_search_ranks_and_reports_exclusions(data_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert run(data_dir, "search", "trust") == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith(
        "total 3 · excluded by default filters 1 (track: workshop 1, unknown 0; status: unknown 0)"
    )
    assert [line.split()[0] for line in out[2:]] == ["1.", "2.", "3."]


def test_the_oracle_and_tantivy_agree_through_the_cli(
    data_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(data_dir, "search", "trust NOT calibration", "--ids") == 0
    tantivy_ids = capsys.readouterr().out
    assert run(data_dir, "search", "trust NOT calibration", "--ids", "--engine", "reference") == 0
    assert capsys.readouterr().out == tantivy_ids != ""


def test_the_oracle_is_for_ids_only(data_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert run(data_dir, "search", "trust", "--engine", "reference") == 1
    assert "--engine reference needs --ids" in capsys.readouterr().err


def test_diagnostics_go_to_stderr_and_one_search_run_line_is_logged(
    data_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(data_dir, "search", "trustwo* OR xyzzy AND", "--ids") == 1  # a parse error: stderr, no run
    refused = capsys.readouterr()
    assert refused.out == "" and "PARSE_" in refused.err
    assert run(data_dir, "search", "trust calibration", "--mode", "scholar", "--ids") == 0
    captured = capsys.readouterr()
    logged = [json.loads(line) for line in (captured.out + captured.err).splitlines() if line.startswith("{")]
    runs = [entry for entry in logged if entry.get("event") == "search_run"]
    assert len(runs) == 1  # at most one INFO line per search
    assert {"index_version", "canonical_hash", "total", "ms", "mode", "command", "engine"} <= runs[0].keys()
    assert "calibration" not in json.dumps(runs[0])  # never the query text
    assert captured.out.strip().splitlines() == [f"op:iclr:2024:{i}" for i in ("AbCd0002",)]
