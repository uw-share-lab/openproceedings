"""`op search` and `op export` (spec 08 §CLI, spec 04 §Exports; task-030): every format streams the full
matched set in id order and round-trips to its ids; BibTeX passes the pinned refaudit parser with one entry
per record whatever the title holds; CSV cells can't run as spreadsheet formulas; the CLI prints diagnostics
to stderr, logs one privacy-safe `search_run` line, never leaves a partial file, and stops quietly on a
closed pipe."""

from __future__ import annotations

import csv
import io
import json
import re
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
    paper("AbCd0006", "Trusta ends here", abstract="=HYPERLINK(1)", authors=("Jo Smith",), venue="ICLR",
          year=2024, keywords=("trust", "calibration")),
    paper("AbCd0007", "Trust Q&A 100% #1 \\", abstract="-lead", authors=("Jo Smith",), venue="ICLR", year=2024),
    paper("AbCd0008", "Trust set \\{x\\} notation", abstract=None, authors=("Jo Smith",), venue="ICLR", year=2024),
    paper("AbCd0009", "Trust } swapped {", abstract=None, authors=("Jo Smith",), venue="ICLR", year=2024),
]  # fmt: skip
PROVENANCE = Provenance("abcdef123456", "0" * 64, "2026-09-26")
ALL = "(trust OR trusta) track:(main OR workshop)"  # every record but AbCd0005 (all accepted)
MATCHED = ["AbCd0001", "AbCd0002", "AbCd0003", "AbCd0004", "AbCd0006", "AbCd0007", "AbCd0008", "AbCd0009"]


@pytest.fixture(scope="module")
def data_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("export-data")
    snap = snapshot_of(CORPUS, root / "snapshots" / "2026-09-26-fixture")
    build_index(snap, root / "indexes")
    return root


def index_of(data_dir: Path) -> Path:
    return next(p for p in (data_dir / "indexes").iterdir() if not p.name.startswith("."))  # not `.lock`


def exported(data_dir: Path, fmt: str, q: str = ALL) -> tuple[str, int]:
    engine = TantivyEngine(index_of(data_dir))
    total, documents = engine.documents(parse(q).effective_ast)  # type: ignore[arg-type]
    out = io.StringIO()
    n = write(fmt, documents, PROVENANCE, out)
    assert n == total
    return out.getvalue(), n


def natives(ids: list[str]) -> list[str]:
    return [i.rsplit(":", 1)[1] for i in ids]


def test_ris_round_trips_every_id_in_id_order(data_dir: Path) -> None:
    text, n = exported(data_dir, "ris")
    records = [r for r in text.split("ER  - \n") if r.strip()]
    assert n == len(records) == 8
    ids = [line[6:] for line in text.splitlines() if line.startswith("ID  - ")]
    assert ids == sorted(ids) and sorted(natives(ids)) == MATCHED
    first = records[[i.endswith("AbCd0001") for i in ids].index(True)]
    assert first.startswith("TY  - CPAPER\n") and "AU  - Jo Smith\nAU  - Ana Pérez" in first
    assert "AB  - We study trust. Across two lines." in first  # RIS is line-based
    assert "T2  - International Conference on Learning Representations (ICLR 2024)" in first
    urls = [line for line in first.splitlines() if line.startswith("UR  - ")]
    assert urls[0].endswith("forum?id=AbCd0001") and urls[1].endswith("pdf?id=AbCd0001")  # forum, then pdf
    assert f"N1  - {PROVENANCE.line()}" in first and "KW  - main" in first
    assert "DO  - 10.1234/abcd" in text and text.endswith("ER  - \n\n")  # the tag's trailing space kept


def test_csv_has_a_bom_the_columns_provenance_and_no_formulas(data_dir: Path) -> None:
    text, n = exported(data_dir, "csv")
    assert text.startswith("\ufeff")
    rows = list(csv.DictReader(io.StringIO(text[1:])))
    assert n == len(rows) == 8 and tuple(rows[0]) == export.CSV_COLUMNS
    assert [r["id"] for r in rows] == sorted(r["id"] for r in rows)
    by = {r["id"].rsplit(":", 1)[1]: r for r in rows}
    assert by["AbCd0001"]["authors"] == "Jo Smith; Ana Pérez"
    assert by["AbCd0001"]["abstract"] == "We study trust.\nAcross two lines."
    assert by["AbCd0002"]["abstract"] == "" and by["AbCd0002"]["doi"] == "10.1234/abcd"
    assert by["AbCd0006"]["keywords"] == "trust; calibration"
    assert (
        by["AbCd0006"]["abstract"] == "'=HYPERLINK(1)" and by["AbCd0007"]["abstract"] == "'-lead"
    )  # never run
    assert {r["index_version"] for r in rows} == {"abcdef123456"}


def test_bibtex_passes_refaudit_one_entry_per_record(data_dir: Path) -> None:
    text, n = exported(data_dir, "bibtex")
    entries = parse_string(text)
    assert n == len(entries) == 8 and all(e.entry_type == "inproceedings" for e in entries)
    assert sorted(natives([e.fields["openproceedings_id"] for e in entries])) == MATCHED
    keys = [e.key for e in entries]
    assert len(set(keys)) == 8  # `smith2024trusta` is both a suffixed key and a real one: never twice
    by = {e.fields["openproceedings_id"].rsplit(":", 1)[1]: e.fields for e in entries}
    assert by["AbCd0001"]["title"] == "Trust in {BERT} models"  # balanced braces keep their meaning
    assert by["AbCd0001"]["url"].endswith("forum?id=AbCd0001") and by["AbCd0001"]["note"] == PROVENANCE.line()
    assert by["AbCd0003"]["title"] == "Trust a unbalanced title"  # an unbalanced brace is dropped
    assert by["AbCd0007"]["title"] == "Trust Q\\&A 100\\% \\#1 \\"  # escaped; its closing brace not swallowed
    assert by["AbCd0002"]["doi"] == "10.1234/abcd"
    # escaped braces that nest either way are kept: every parser reads them alike
    assert by["AbCd0008"]["title"] == "Trust set \\{x\\} notation"
    assert by["AbCd0009"]["title"] == "Trust swapped"  # `}` before `{` never balances


def test_jsonl_is_one_record_per_line(data_dir: Path) -> None:
    text, n = exported(data_dir, "jsonl")
    rows = [json.loads(line) for line in text.splitlines()]
    assert n == len(rows) == 8 and [r["id"] for r in rows] == sorted(r["id"] for r in rows)
    assert all(r["canonical_hash"] == "0" * 64 and r["index_version"] == "abcdef123456" for r in rows)
    assert rows[0]["authors"] == ["Jo Smith", "Ana Pérez"] and rows[0]["urls"]["pdf"].endswith("AbCd0001")


def test_bibtex_keys() -> None:
    assert bibtex_key({"authors": ["Kurt Gödel"], "year": 1931, "title": "Über formal"}) == "godel1931uber"
    assert bibtex_key({"authors": [], "year": 2024, "title": "!!!"}) == "anon2024untitled"
    assert bibtex_key({"authors": [], "year": 2021, "title": "Ørsted and trust"}) == "anon2021orsted"
    assert bibtex_key({"authors": ["A B"], "year": 1, "title": '=HYPERLINK("http://x")'}) == "b1hyperlink"
    assert [export._suffix(n) for n in (0, 1, 25, 26, 27)] == ["a", "b", "z", "aa", "ab"]
    records = [{"authors": ["A Smith"], "year": 2024, "title": t, "venue": "ICLR", "id": f"x{i}"}
               for i, t in enumerate(["Deep one", "Deep two", "Deepa trust"])]  # fmt: skip
    keys = [e.key for e in parse_string("".join(export._bibtex(records, PROVENANCE)))]
    assert keys == ["smith2024deep", "smith2024deepa", "smith2024deepaa"]  # the real `deepa` moves on


def run(data_dir: Path, *args: str) -> int:
    return main(["--data-dir", str(data_dir), *args, "--index", index_of(data_dir).name])


def test_op_export_writes_the_file_whole(
    data_dir: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "out.jsonl"
    assert run(data_dir, "export", "trust", "--format", "jsonl", "--out", str(out)) == 0
    assert len(out.read_text().splitlines()) == 6  # the defaults leave out the workshop paper
    assert sorted(p.name for p in tmp_path.iterdir()) == ["out.jsonl"]  # no temporary file left
    assert "exported 6 records (jsonl)" in capsys.readouterr().err


@pytest.mark.parametrize("failure", ["write", "count"])
def test_op_export_leaves_nothing_when_it_fails(
    data_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    if failure == "write":

        def broken(*_args: object) -> int:
            raise OSError("disk full")

        monkeypatch.setattr(export, "write", broken)
    else:  # a record lost between the count and the stream: the file must not be kept
        real = TantivyEngine.documents

        def short(self: TantivyEngine, ast: object) -> tuple[int, object]:
            total, documents = real(self, ast)  # type: ignore[arg-type]
            return total, list(documents)[1:]

        monkeypatch.setattr(TantivyEngine, "documents", short)
    (tmp_path / "out.ris").write_text("the user's old file")
    assert run(data_dir, "export", "trust", "--format", "ris", "--out", str(tmp_path / "out.ris")) == 1
    assert sorted(p.name for p in tmp_path.iterdir()) == ["out.ris"]  # untouched, and no temporary file
    assert (tmp_path / "out.ris").read_text() == "the user's old file"


def test_op_export_refuses_a_directory(
    data_dir: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(data_dir, "export", "trust", "--format", "ris", "--out", str(tmp_path)) == 1
    assert "is a directory" in capsys.readouterr().err


def test_op_export_to_stdout(data_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert run(data_dir, "export", "trust status:(accepted OR rejected)", "--format", "ris") == 0
    out = capsys.readouterr().out
    assert out.count("ER  - \n") == 6 and "search_run" not in out  # stdout is data only


def test_a_closed_pipe_stops_quietly(
    data_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def closed(*_args: object) -> int:
        raise BrokenPipeError

    monkeypatch.setattr(export, "write", closed)
    monkeypatch.setattr("os.dup2", lambda *_args: None)  # don't redirect the test runner's own stdout
    assert run(data_dir, "export", "trust", "--format", "ris") == 0
    assert "BrokenPipe" not in capsys.readouterr().err


def test_op_search_ranks_and_reports_exclusions(data_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert run(data_dir, "search", "trust", "--limit", "3") == 0
    out = capsys.readouterr().out.splitlines()
    # PRISMA-ready: when and against what (the crawl date from the snapshot); identified, removed, screened
    assert re.fullmatch(
        r"searched \d{4}-\d\d-\d\dT\d\d:\d\dZ · index \w{12} · crawl \d{4}-\d\d-\d\d · tokenizer \d+ · query \d+",
        out[0],
    )
    assert out[1].startswith("note: bootstrap corpus (sources: ris)")  # the fixture snapshot is RIS-only
    assert out[2:5] == [
        "identified 7 (within the query's own limits)",
        "removed by default filters 1: ineligible 1 (track: workshop 1; status: none), "
        "unclassified 0 (track unknown 0, status unknown 0)",
        "screened (total) 6",
    ]
    assert out[5].startswith("canonical: ") and out[6] == "identification: trust"
    ranked = [line for line in out if re.match(r"\s+\d+\. ", line)]
    assert [line.split()[0] for line in ranked] == ["1.", "2.", "3."]
    scores = [float(line.split()[1]) for line in ranked]
    assert scores == sorted(scores, reverse=True) and scores[0] > 0


def test_the_header_splits_ineligible_from_unclassified(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # identified 9 = removed 7 (ineligible 3: workshop 2, rejected 1; unclassified 4: track unknown 2, status
    # unknown 2) + screened 2; the track bucket is assigned first (a workshop paper that's also rejected)
    rows = [("main", "accepted"), ("main", "accepted"), ("workshop", "accepted"), ("workshop", "rejected"),
            ("main", "rejected"), ("unknown", "accepted"), ("unknown", "rejected"), ("main", "unknown"),
            ("position", "unknown")]  # fmt: skip
    corpus = [paper(f"Pq{i:04d}", "trust", abstract=None, venue="ICLR", year=2024, track=t, status=st)
              for i, (t, st) in enumerate(rows)]  # fmt: skip
    build_index(snapshot_of(corpus, tmp_path / "snapshots" / "s"), tmp_path / "indexes")
    assert (
        main(
            [
                "--data-dir",
                str(tmp_path),
                "search",
                "trust",
                "--limit",
                "0",
                "--index",
                index_of(tmp_path).name,
            ]
        )
        == 0
    )
    out = capsys.readouterr().out.splitlines()
    assert out[2:5] == [
        "identified 9 (within the query's own limits)",
        "removed by default filters 7: ineligible 3 (track: workshop 2; status: rejected 1), "
        "unclassified 4 (track unknown 2, status unknown 2)",
        "screened (total) 2",
    ]


def test_a_bootstrap_corpus_says_its_counts_arent_identification_numbers(data_dir: Path) -> None:
    from openproceedings.cli import _report
    from openproceedings.engine.exclusions import excluded

    engine = TantivyEngine(index_of(data_dir))
    result = parse("trust*")
    total = len(engine.match_ids(result.effective_ast))  # type: ignore[arg-type]
    gone = excluded(engine, result, total)
    ris_only = _report(engine, result, total, gone, {"crawl_date": "2026-09-23", "sources": {"ris": []}})
    assert " · crawl 2026-09-23 · " in ris_only[0]
    assert (
        ris_only[1].startswith("note: bootstrap corpus (sources: ris)")
        and "not PRISMA identification" in ris_only[1]
    )
    crawled = _report(
        engine, result, total, gone, {"crawl_date": "2026-09-23", "sources": {"ris": [], "openreview": []}}
    )
    assert not any(line.startswith("note:") for line in crawled)
    unknown = _report(engine, result, total, gone, None)
    assert " · crawl unknown (snapshot not found) · " in unknown[0]
    assert unknown[-1] == "expansion: trust* → 2 terms (trust, trusta)"


def test_an_expansion_line_says_term_or_terms_and_where_the_rest_are(data_dir: Path) -> None:
    from types import SimpleNamespace

    from openproceedings.cli import _report
    from openproceedings.engine.exclusions import Excluded

    engine = SimpleNamespace(
        index_version="x" * 12,
        expansions=lambda _ast: {("a", "*"): tuple(f"a{i:02d}" for i in range(12)), ("b", "$"): ("b",)},
    )
    result = parse("a* b$")
    lines = _report(engine, result, 0, Excluded(0, {"unknown": 0}, {"unknown": 0}), None)  # type: ignore[arg-type]
    assert (
        "expansion: a* → 12 terms (a00, a01, a02, a03, a04, a05, a06, a07, a08, a09, …; every term with --explain)"
        in lines
    )
    assert "expansion: b$ → 1 term (b)" in lines


def test_op_search_shows_every_wildcard_expansion(data_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert run(data_dir, "search", "trust*", "--limit", "1") == 0
    out = capsys.readouterr().out
    assert re.search(r"^expansion: trust\* → 2 terms \(trust, trusta\)$", out, re.M)  # guarantee 6


def test_without_an_index_the_cli_says_to_pass_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["--data-dir", str(tmp_path), "search", "trust", "--ids"]) == 1
    assert "pass --index" in capsys.readouterr().err


def test_cli_choices_match_the_engine_and_the_exporter() -> None:
    from openproceedings import cli
    from openproceedings.engine.index import RANKING_PARAMS
    from openproceedings.engine.tantivy_engine import SORTS

    assert cli.FORMATS == export.FORMATS
    assert set(cli.SORTS) == set(SORTS) == set(RANKING_PARAMS["sorts"])


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


def test_the_oracle_refuses_a_snapshot_the_index_was_not_built_from(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    snap = snapshot_of(CORPUS[:2], tmp_path / "snapshots" / "2026-09-26-fixture")
    build_index(snap, tmp_path / "indexes")
    snap.rename(tmp_path / "snapshots" / "moved")
    snapshot_of(CORPUS[2:4], tmp_path / "snapshots" / "2026-09-26-fixture")  # same name, other records
    assert run(tmp_path, "search", "trust", "--ids", "--engine", "reference") == 1
    assert "isn't the snapshot index" in capsys.readouterr().err


def test_diagnostics_go_to_stderr_and_one_search_run_line_is_logged(
    data_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(data_dir, "search", "trustwo* OR xyzzy AND", "--ids") == 1  # a parse error: stderr, no run
    refused = capsys.readouterr()
    assert refused.out == "" and "PARSE_" in refused.err
    assert '"level": "WARNING"' not in refused.err  # a user's own parse error logs at DEBUG at most
    assert run(data_dir, "search", "trust calibration", "--mode", "scholar", "--ids") == 0
    captured = capsys.readouterr()
    logged = [json.loads(line) for line in (captured.out + captured.err).splitlines() if line.startswith("{")]
    runs = [entry for entry in logged if entry.get("event") == "search_run"]
    assert len(runs) == 1  # at most one INFO line per search
    assert {"index_version", "canonical_hash", "total", "ms", "mode", "command", "engine"} <= runs[0].keys()
    assert "calibration" not in json.dumps(runs[0])  # never the query text
    assert captured.out.strip().splitlines() == ["op:iclr:2024:AbCd0002"]


def test_the_stdout_export_is_counted_and_an_internal_error_logs_at_error(
    data_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    real = TantivyEngine.documents

    def short(self: TantivyEngine, ast: object) -> tuple[int, object]:
        total, documents = real(self, ast)  # type: ignore[arg-type]
        return total, list(documents)[1:]

    monkeypatch.setattr(TantivyEngine, "documents", short)
    assert run(data_dir, "export", "trust", "--format", "jsonl") == 1
    err = capsys.readouterr().err
    logged = [json.loads(line) for line in err.splitlines() if line.startswith("{")]
    refused = [e for e in logged if e.get("event") == "cli_refused"]
    assert "but 6 match" in err and refused and refused[0]["level"] == "ERROR"


def test_op_export_keeps_the_mode_a_redirect_would_give(data_dir: Path, tmp_path: Path) -> None:
    import os
    import stat

    fresh, kept = tmp_path / "fresh.ris", tmp_path / "kept.ris"
    kept.write_text("")
    kept.chmod(0o640)
    old = os.umask(0o022)
    try:
        for out in (fresh, kept):
            assert run(data_dir, "export", "trust", "--format", "ris", "--out", str(out)) == 0
    finally:
        os.umask(old)
    assert stat.S_IMODE(fresh.stat().st_mode) == 0o644 and stat.S_IMODE(kept.stat().st_mode) == 0o640


def test_op_export_names_a_missing_directory(
    data_dir: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(data_dir, "export", "trust", "--format", "ris", "--out", str(tmp_path / "nope" / "x.ris")) == 1
    err = capsys.readouterr().err
    assert "no directory" in err and ".partial" not in err


def test_ris_reads_back_with_an_independent_parser(data_dir: Path) -> None:
    from scholarmend.parse import parse_ris

    text, n = exported(data_dir, "ris")
    parsed = {r.first("ID"): r for r in parse_ris(text, "export.ris")}
    engine = TantivyEngine(index_of(data_dir))
    stored = {d["id"]: d for d in engine.documents(parse(ALL).effective_ast)[1]}  # type: ignore[arg-type]
    assert len(parsed) == n == len(stored)
    for rid, d in stored.items():  # every field, every record: title, abstract, ordered authors, year
        r = parsed[rid]
        assert r.fields["TI"] == [" ".join(d["title"].split())]
        assert r.fields.get("AB", []) == ([" ".join(d["abstract"].split())] if d["abstract"] else [])
        assert r.fields.get("AU", []) == d["authors"] and r.fields["PY"] == [str(d["year"])]


def test_jsonl_escapes_unicode_line_separators_and_carries_the_date() -> None:
    record = {"id": "x", "title": "t", "abstract": "a\u2028b\u2029c\x85d", "year": 2024, "venue": "ICLR"}
    line = "".join(export._jsonl([record], PROVENANCE))
    assert len(line.splitlines()) == 1 and json.loads(line)["abstract"] == record["abstract"]
    assert json.loads(line)["exported_at"] == "2026-09-26"


def test_csv_guards_disguised_formulas_and_strips_control_characters() -> None:
    assert export._cell(" =1+1") == "' =1+1" and export._cell("＝1+1") == "'＝1+1"
    assert export._cell("a\x00b\x1bc") == "abc" and export._cell("plain") == "plain"


def test_bibtex_names_are_never_split_or_read_as_et_al() -> None:
    record = {"id": "x", "title": "t", "year": 2024, "venue": "ICLR",
              "authors": ["Smith and Wesson", "others", "", "Jo Doe"]}  # fmt: skip
    (entry,) = parse_string("".join(export._bibtex([record], PROVENANCE)))
    assert entry.fields["author"] == "{Smith and Wesson} and {others} and Jo Doe"


def logged(err: str) -> list[dict[str, object]]:
    return [json.loads(line) for line in err.splitlines() if line.startswith("{")]


def test_log_levels_follow_the_kind_of_failure(
    data_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # the user's own mistake: no WARNING (DEBUG at most)
    assert run(data_dir, "search", "trust", "--limit", "-1") == 1
    assert not [e for e in logged(capsys.readouterr().err) if e.get("event") == "cli_refused"]
    # an internal failure: ERROR, with its code and the traceback
    real = TantivyEngine.documents
    monkeypatch.setattr(
        TantivyEngine, "documents", lambda self, ast: (lambda t, d: (t, list(d)[1:]))(*real(self, ast))
    )
    assert run(data_dir, "export", "trust", "--format", "jsonl") == 1
    (entry,) = [e for e in logged(capsys.readouterr().err) if e.get("event") == "cli_refused"]
    assert (
        entry["level"] == "ERROR"
        and entry["code"] == "API_INTERNAL"
        and "Traceback" in str(entry.get("exc_info", entry))
    )
    # a bug nothing anticipated: one ERROR line and a clean exit status, not a bare traceback
    monkeypatch.setattr(TantivyEngine, "documents", lambda self, ast: 1 / 0)
    assert run(data_dir, "export", "trust", "--format", "jsonl") == 1
    captured = capsys.readouterr().err
    assert [e["level"] for e in logged(captured) if e.get("event") == "cli_failed"] == ["ERROR"]
    assert "internal error" in captured


def test_a_long_build_and_a_parity_check_say_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import openproceedings.engine.index as index_module

    monkeypatch.setattr(index_module, "PROGRESS_EVERY", 2)
    snap = snapshot_of(CORPUS, tmp_path / "snapshots" / "s")
    assert main(["--data-dir", str(tmp_path), "index", "build", "--snapshot", str(snap)]) == 0
    events = [e["event"] for e in logged(capsys.readouterr().err)]
    assert events[0] == "index_build_started" and events.count("index_build_progress") == len(CORPUS) // 2
    index = index_of(tmp_path)
    assert (
        main(["--data-dir", str(tmp_path), "index", "parity", "--index", str(index), "--snapshot", str(snap)])
        == 0
    )
    assert "index_parity_ok" in [e["event"] for e in logged(capsys.readouterr().err)]


def test_bibtex_keys_take_the_family_name_before_a_comma() -> None:
    assert (
        bibtex_key({"authors": ["Gödel, Kurt"], "year": 1931, "title": "On formally undecidable"})
        == "godel1931on"
    )
    assert bibtex_key({"authors": ["van der Berg, Ada"], "year": 2024, "title": "X"}) == "vanderberg2024x"
    assert bibtex_key({"authors": ["Kurt Gödel"], "year": 1931, "title": "On"}) == "godel1931on"


def test_one_names_stray_brace_never_unbraces_the_others() -> None:
    record = {"id": "x", "title": "t", "year": 2024, "venue": "ICLR", "authors": ["Jo{hn Doe", "X and Y"]}
    (entry,) = parse_string("".join(export._bibtex([record], PROVENANCE)))
    assert entry.fields["author"] == "John Doe and {X and Y}"


def test_a_brace_after_a_backslash_run_is_never_kept() -> None:
    # `\\{b}` nests for BibTeX and for parsers that honour `\{`, but bibtexparser 2 reads the brace as escaped
    assert export._braced("a \\\\{b} c") == "{a \\\\b c}"


def test_ris_urls_and_dois_stay_on_one_line_even_if_they_got_past_ingest() -> None:
    record = {"id": "x", "title": "t", "year": 2024, "venue": "ICLR", "track": "main", "authors": [],
              "urls": {"forum": "https://a/b\nER  - \nTY  - JOUR", "pdf": None, "proceedings": None,
                       "doi": "10.1/x\u2028TY  - JOUR"}}  # fmt: skip
    text = "".join(export._ris([record], PROVENANCE))
    assert text.count("TY  - ") == 1 and text.count("ER  - ") == 1


def test_a_parity_failure_logs_at_error_without_its_tokens(
    data_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from openproceedings.engine import parity

    def broken(*_args: object, **_kw: object) -> object:
        raise parity.ParityError("op:x: title token 1: the index has 'SENTINELTOKEN', normalize() gives 'y'")

    monkeypatch.setattr(parity, "check_parity", broken)
    index = index_of(data_dir)
    assert main(["--data-dir", str(data_dir), "index", "parity", "--index", str(index)]) == 1
    err = capsys.readouterr().err
    (entry,) = [e for e in logged(err) if e.get("event") == "cli_refused"]
    assert (entry["level"], entry["error"]) == ("ERROR", "ParityError")  # a broken guarantee
    assert all("SENTINELTOKEN" not in json.dumps(e) for e in logged(err))  # the tokens stay on the terminal
    assert "SENTINELTOKEN" in err
    monkeypatch.undo()
    other = snapshot_of(CORPUS[:2], tmp_path / "other")  # the wrong snapshot: operator error, a WARNING
    assert (
        main(
            ["--data-dir", str(data_dir), "index", "parity", "--index", str(index), "--snapshot", str(other)]
        )
        == 1
    )
    (entry,) = [e for e in logged(capsys.readouterr().err) if e.get("event") == "cli_refused"]
    assert (entry["level"], entry["error"]) == ("WARNING", "IndexBuildError")
