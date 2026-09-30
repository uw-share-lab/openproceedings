"""`op search` and `op export` (spec 08 §CLI, spec 04 §Exports; task-030): every format streams the full
matched set in id order and round-trips to its ids; BibTeX passes the pinned refaudit parser with one entry
per record whatever the title holds; CSV cells can't run as spreadsheet formulas; the CLI prints diagnostics
to stderr, logs one privacy-safe `search_run` line, never leaves a partial file, and stops quietly on a
closed pipe."""

from __future__ import annotations

import csv
import io
import json
import os
import re
from pathlib import Path
from typing import get_args

import pytest
from openproceedings import export, vocab
from openproceedings.api.state import snapshot_records
from openproceedings.cli import main
from openproceedings.engine.index import build_index
from openproceedings.engine.protocol import EngineInternalError
from openproceedings.engine.tantivy_engine import TantivyEngine
from openproceedings.export import Provenance, bibtex_key, write
from openproceedings.ingest.dedup import Attribution, Origin
from openproceedings.ingest.record import PaperRecord
from openproceedings.query.parser import parse
from pydantic import ValidationError
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
    sources = snapshot_records(data_dir, index_of(data_dir), engine.index_version).attributions
    n = write(fmt, documents, PROVENANCE, out, sources=sources)
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


def test_three_colliding_keys_the_first_bare_then_a_then_b() -> None:
    """decision-007: the first use of a key stays bare, later ones take a, b, … in the export's id order."""
    records = [{"authors": ["Jo Smith"], "year": 2024, "title": "Deep trust", "venue": "ICLR", "id": f"op:iclr:2024:{n}"}
               for n in ("A1", "B2", "C3")]  # fmt: skip
    entries = parse_string("".join(export._bibtex(records, PROVENANCE)))
    assert [(e.key, e.fields["openproceedings_id"]) for e in entries] == [
        ("smith2024deep", "op:iclr:2024:A1"),
        ("smith2024deepa", "op:iclr:2024:B2"),
        ("smith2024deepb", "op:iclr:2024:C3"),
    ]


def test_a_superset_keeps_keys_unless_an_added_paper_sorts_first() -> None:
    """decision-007's trade-off, pinned: adding colliding papers that sort after the ones already exported
    keeps every earlier key; one that sorts before them takes the bare key and shifts the rest."""

    def keys(natives: list[str]) -> dict[str, str]:
        records = [{"authors": ["Jo Smith"], "year": 2024, "title": "Deep", "venue": "ICLR", "id": f"op:iclr:2024:{n}"}
                   for n in sorted(natives)]  # fmt: skip
        return {
            e.fields["openproceedings_id"][-2:]: e.key
            for e in parse_string("".join(export._bibtex(records, PROVENANCE)))
        }

    small = keys(["B2", "C3"])
    assert small == {"B2": "smith2024deep", "C3": "smith2024deepa"}
    assert {k: v for k, v in keys(["B2", "C3", "D4"]).items() if k in small} == small  # appended: stable
    assert keys(["A1", "B2", "C3"])["B2"] == "smith2024deepa"  # prepended: shifts (keys are per file)


def test_an_added_paper_whose_real_key_is_an_issued_suffix() -> None:
    """decision-007 §Consequences: a paper titled "Deepa …" has the real key `smith2024deepa`. Added after the
    paper that holds that suffix, it moves on itself (`…deepaa`) and nothing earlier shifts; added before it,
    it takes `…deepa` and that paper shifts to `…deepb`."""

    def keys(titles: dict[str, str]) -> dict[str, str]:
        records = [{"authors": ["Jo Smith"], "year": 2024, "title": t, "venue": "ICLR", "id": f"op:iclr:2024:{n}"}
                   for n, t in sorted(titles.items())]  # fmt: skip
        return {
            e.fields["openproceedings_id"][-2:]: e.key
            for e in parse_string("".join(export._bibtex(records, PROVENANCE)))
        }

    before = {"B2": "Deep", "C3": "Deep"}
    assert keys(before) == {"B2": "smith2024deep", "C3": "smith2024deepa"}
    assert keys({**before, "D4": "Deepa trust"}) == {**keys(before), "D4": "smith2024deepaa"}
    assert keys({**before, "B5": "Deepa trust"}) == {
        "B2": "smith2024deep",
        "B5": "smith2024deepa",
        "C3": "smith2024deepb",
    }


# spec 04 §Exports, T2 / booktitle: the full conference name, then the acronym it went by that year. The
# first year of each naming era, the rename and recent years are pinned by hand, apart from `CONFERENCES`.
VENUE_NAMES = {
    ("NeurIPS", 1987): "Conference on Neural Information Processing Systems (NIPS 1987)",
    ("NeurIPS", 2017): "Conference on Neural Information Processing Systems (NIPS 2017)",
    ("NeurIPS", 2018): "Conference on Neural Information Processing Systems (NeurIPS 2018)",
    ("NeurIPS", 2025): "Conference on Neural Information Processing Systems (NeurIPS 2025)",
    ("ICLR", 2013): "International Conference on Learning Representations (ICLR 2013)",
    ("ICLR", 2025): "International Conference on Learning Representations (ICLR 2025)",
    ("ICML", 1988): "International Conference on Machine Learning (ICML 1988)",
    ("ICML", 2023): "International Conference on Machine Learning (ICML 2023)",
    ("ICML", 2026): "International Conference on Machine Learning (ICML 2026)",
}


@pytest.mark.parametrize(("venue", "year"), sorted(VENUE_NAMES))
def test_venue_names_are_pinned(venue: str, year: int) -> None:
    assert export.venue_name(venue, year) == VENUE_NAMES[venue, year]


def test_every_crawlable_year_has_one_venue_name() -> None:
    """2013–2026 for all three venues (the review's 2020–2026 and task-049's 2018 proposal inside it): one
    string per venue and year, whatever the track or status, with the year it names equal to `PY`."""
    for venue in ("NeurIPS", "ICLR", "ICML"):
        for year in range(2013, 2027):
            name = export.venue_name(venue, year)
            acronym = "NIPS" if venue == "NeurIPS" and year < 2018 else venue
            assert name.endswith(f" ({acronym} {year})") and "\n" not in name and "{" not in name


@pytest.mark.parametrize(("venue", "year"), [("NeurIPS", 1986), ("ICLR", 2012), ("ICML", 1987)])
def test_a_year_the_venue_was_not_held_is_refused(venue: str, year: int) -> None:
    with pytest.raises(ValueError, match="no conference name"):
        export.venue_name(venue, year)


def test_an_unknown_venue_has_its_own_message() -> None:
    with pytest.raises(ValueError, match="no conference table for venue 'AAAI'"):
        export.venue_name("AAAI", 2024)


def test_conference_eras_must_be_sorted() -> None:
    """`venue_name` takes the last era that has begun, so the eras must be in year order; the table is checked
    when the module loads, and the check refuses an unsorted table."""
    vocab.check_conferences(vocab.CONFERENCES)
    with pytest.raises(ValueError, match="NeurIPS eras are not in year order"):
        vocab.check_conferences({"NeurIPS": ("N", ((2018, "NeurIPS"), (1987, "NIPS")))})
    with pytest.raises(ValueError, match="ICLR has no eras"):
        vocab.check_conferences({"ICLR": ("I", ())})


def test_a_record_for_a_year_its_venue_was_not_held_is_refused_at_ingest() -> None:
    """Refused when the record is built, so an export never meets it mid-stream (`venue_name` still raises,
    as a backstop)."""
    with pytest.raises(ValidationError, match="no conference name for ICLR 2012"):
        paper("AbCd0001", venue="ICLR", year=2012)
    assert paper("AbCd0001", venue="ICLR", year=2013).year == 2013


STATUSES = ("accepted", "rejected", "withdrawn", "desk_rejected", "unknown")


def status_record(status: str) -> dict[str, object]:
    return {"id": f"op:iclr:2024:{status[:4]}0001", "title": "Deep trust", "authors": ["Jo Smith"], "venue": "ICLR",
            "year": 2024, "track": "main", "status": status}  # fmt: skip


@pytest.mark.parametrize("status", STATUSES)
def test_ris_carries_the_status_as_a_keyword(status: str) -> None:
    ris = "".join(export._ris([status_record(status)], PROVENANCE))
    assert [line for line in ris.splitlines() if line.startswith("KW  - ")] == [
        "KW  - main",
        f"KW  - status:{status}",
    ]
    assert (
        "TY  - CPAPER\n" in ris
        and "T2  - International Conference on Learning Representations (ICLR 2024)\n" in ris
    )


def test_bibtex_cites_only_accepted_papers_as_inproceedings() -> None:
    """spec 04 §Exports: an accepted paper is `@inproceedings` in its conference; any other status is
    `@unpublished`, with no `booktitle`: the venue string moves into `note`, after `Submitted to`."""
    entries = parse_string("".join(export._bibtex([status_record(s) for s in STATUSES], PROVENANCE)))
    by = {e.fields["openproceedings_id"].split(":")[-1][:4]: e for e in entries}
    venue = "International Conference on Learning Representations (ICLR 2024)"
    accepted = by["acce"]
    assert accepted.entry_type == "inproceedings" and accepted.fields["booktitle"] == venue
    assert (
        accepted.fields["note"] == PROVENANCE.line()
        and accepted.fields["keywords"] == "main, status:accepted"
    )
    for status in STATUSES[1:]:
        e = by[status[:4]]
        assert e.entry_type == "unpublished" and "booktitle" not in e.fields, status
        words = status.replace("_", " ")  # `desk_rejected` in a note would break LaTeX
        assert e.fields["note"] == f"Submitted to {venue}, status: {words}. {PROVENANCE.line()}"
        assert e.fields["keywords"] == f"main, status:{status}"


def test_ris_t2_and_bibtex_booktitle_are_the_same_string() -> None:
    record = {"id": "op:neurips:2017:nips-ab", "title": "t", "authors": ["A B"], "venue": "NeurIPS", "year": 2017,
              "track": "main", "status": "accepted"}  # fmt: skip
    ris = "".join(export._ris([record], PROVENANCE))
    (entry,) = parse_string("".join(export._bibtex([record], PROVENANCE)))
    assert f"T2  - {entry.fields['booktitle']}\n" in ris
    assert entry.fields["booktitle"] == "Conference on Neural Information Processing Systems (NIPS 2017)"


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

        def broken(*_args: object, **_kw: object) -> int:
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
    def closed(*_args: object, **_kw: object) -> int:
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
        r"searched \d{4}-\d\d-\d\dT\d\d:\d\dZ · index \w{12} · crawl (\d{4}-\d\d-\d\d) to \d{4}-\d\d-\d\d · tokenizer \d+ "
        r"· query \d+",
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
    window = {"from": "2026-09-19T00:54:21+00:00", "to": "2026-09-23T12:14:34+00:00"}
    ris_only = _report(
        engine,
        result,
        total,
        gone,
        {"crawl_date": "2026-09-23", "crawl_window": window, "sources": {"ris": []}},
    )
    assert " · crawl 2026-09-19 to 2026-09-23 · " in ris_only[0]  # the whole window, not the last fetch
    assert (
        ris_only[1].startswith("note: bootstrap corpus (sources: ris)")
        and "not PRISMA identification" in ris_only[1]
    )
    crawled = _report(
        engine, result, total, gone, {"crawl_date": "2026-09-23", "sources": {"ris": [], "openreview": []}}
    )
    assert not any(line.startswith("note:") for line in crawled)
    assert " · crawl 2026-09-23 · " in crawled[0]  # no window recorded: the last fetch
    for bad in ("x", {"from": 1, "to": None}, {"from": "2026-09-19"}):  # a hand-edited window: no traceback
        odd = _report(engine, result, total, gone, {"crawl_date": "2026-09-23", "crawl_window": bad})
        assert " · crawl 2026-09-23 · " in odd[0]
    unknown = _report(engine, result, total, gone, None)
    assert " · crawl unknown (snapshot not found) · " in unknown[0]
    assert unknown[1].startswith("note: the index's snapshot is not in <data-dir>/snapshots")
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
    ten = {("c", "*"): tuple(f"c{i}" for i in range(10))}
    engine.expansions = lambda _ast: ten
    lines = _report(engine, parse("c*"), 0, Excluded(0, {"unknown": 0}, {"unknown": 0}), None)  # type: ignore[arg-type]
    assert lines[-1] == "expansion: c* → 10 terms (c0, c1, c2, c3, c4, c5, c6, c7, c8, c9)"  # no "…" at 10


@pytest.mark.parametrize("damage", ["other snapshot hash", "no snapshots dir"])
def test_the_header_never_takes_a_crawl_date_from_another_snapshot(
    data_dir: Path, tmp_path: Path, damage: str, capsys: pytest.CaptureFixture[str]
) -> None:
    import json
    import shutil

    root = tmp_path / "data"
    shutil.copytree(data_dir, root, ignore=shutil.ignore_patterns(".lock"))
    snap = next((root / "snapshots").iterdir())
    if damage == "no snapshots dir":
        shutil.rmtree(
            root / "snapshots",
            onexc=lambda f, p, _e: (os.chmod(os.path.dirname(p), 0o700), os.chmod(p, 0o700), f(p)),
        )
    else:  # a same-named snapshot that isn't the one the index was built from
        (snap / "manifest.json").chmod(0o600)
        m = json.loads((snap / "manifest.json").read_text(encoding="utf-8"))
        m["snapshot_hash"] = "0" * 64
        (snap / "manifest.json").write_text(json.dumps(m), encoding="utf-8")
    assert run(root, "search", "trust", "--limit", "0") == 0
    out = capsys.readouterr().out.splitlines()
    assert " · crawl unknown (snapshot not found) · " in out[0]
    assert out[1].startswith("note: the index's snapshot is not in") and not out[1].startswith(
        "note: bootstrap"
    )


def test_op_search_writes_utf8_whatever_the_locale(data_dir: Path) -> None:
    import subprocess
    import sys

    env = {**os.environ, "PYTHONIOENCODING": "ascii", "LC_ALL": "C"}
    got = subprocess.run(
        [sys.executable, "-c", "import sys; from openproceedings.cli import main; sys.exit(main(sys.argv[1:]))",
         "--data-dir", str(data_dir), "search", "trust*", "--limit", "9",
         "--index", index_of(data_dir).name],
        capture_output=True, env=env, check=False,
    )  # fmt: skip
    assert got.returncode == 0, got.stderr[-500:]
    assert "→".encode() in got.stdout  # non-ASCII, written as UTF-8


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


@pytest.mark.parametrize(
    ("authors", "want"),
    [
        (["Jo\\{hn, D", "Roe, K"], "{John, D and Roe, K}"),  # the escaping backslash goes with its brace
        (["X and Y\\", "Roe, K"], "{{X and Y} and Roe, K}"),  # no trailing `\` to escape `_name`'s brace
        (["Doe, J", "{}", "{", "Roe, K"], "{Doe, J and Roe, K}"),  # a name that was only braces is no name
    ],
)
def test_author_names_are_debraced_like_every_other_value(authors: list[str], want: str) -> None:
    record = {"id": "x", "title": "t", "year": 2024, "venue": "ICLR", "authors": authors}
    text = "".join(export._bibtex([record], PROVENANCE))
    assert f"  author = {want}," in text


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


@pytest.mark.parametrize("fmt", ["xml", "RIS", ""])
def test_an_unknown_format_is_refused_by_header_and_entries_alike(fmt: str) -> None:
    with pytest.raises(ValueError, match="unknown export format"):
        export.header(fmt)
    with pytest.raises(ValueError, match="unknown export format"):
        export.entries(fmt, [], PROVENANCE, sources={})


# --- review-gate fixes (M3a) ------------------------------------------------------------------------------
LEAKS = ("@article{leak,", "@jit(nopython,")  # an entry opener and a decorator, both read as entries if bare


def adversarial() -> list[dict[str, object]]:
    """Accepted and not: each with an `@` opener in its title, its abstract and an author."""
    out: list[dict[str, object]] = []
    for n, (status, leak) in enumerate(
        [(s, leak) for s in ("accepted", "rejected", "unknown") for leak in LEAKS], start=1
    ):
        out.append({"id": f"op:iclr:2024:At{n:04d}", "title": f"Speed {leak} title}} here",
                    "abstract": f"We use {leak}\n parallel=True) and \\@{leak}", "authors": [f"Smith, {leak}", "Jo Doe"],
                    "venue": "ICLR", "year": 2024, "track": "main", "status": status})  # fmt: skip
    return out


def test_an_at_sign_in_any_value_never_opens_an_entry() -> None:
    """refaudit (and BibTeX) start an entry at a bare `@` wherever it is; every `@` is written `{@}`."""
    records = adversarial()
    text = "".join(export._bibtex(records, PROVENANCE))
    entries = parse_string(text)
    assert len(entries) == len(records) == 6
    assert [e.fields["openproceedings_id"] for e in entries] == [r["id"] for r in records]
    assert [e.entry_type for e in entries] == ["inproceedings"] * 2 + ["unpublished"] * 4
    assert not re.search(r"(?<!\{)@(?!\})", text.split("\n", 1)[1].replace("@inproceedings{", "")
                         .replace("@unpublished{", ""))  # fmt: skip


def test_a_bibtex_note_has_no_bare_underscore_and_reads_the_status_in_words() -> None:
    pinned = Provenance(
        "abcdef123456", "0" * 64, "2026-09-26", record_id="ab_cd-ef_gh1", searched_at="2026-09-25T10:00:00Z"
    )
    for status in STATUSES:
        (e,) = parse_string("".join(export._bibtex([status_record(status)], pinned)))
        assert not re.search(r"(?<!\\)_", e.fields["note"]), e.fields["note"]
        assert e.fields["keywords"] == f"main, status:{status}"  # keywords keep the machine form
    (desk,) = parse_string("".join(export._bibtex([status_record("desk_rejected")], PROVENANCE)))
    assert "status: desk rejected." in desk.fields["note"]


@pytest.mark.parametrize("status", STATUSES)
def test_ris_says_a_paper_that_was_not_accepted_is_not_in_the_proceedings(status: str) -> None:
    ris = "".join(export._ris([status_record(status)], PROVENANCE))
    notes = [line[6:] for line in ris.splitlines() if line.startswith("N1  - ")]
    venue = "International Conference on Learning Representations (ICLR 2024)"
    words = status.replace("_", " ")
    if status == "accepted":
        assert notes == [PROVENANCE.line()]
    elif status == "unknown":
        assert notes == [f"Submitted to {venue}; status: unknown (not known to be in its proceedings).",
                         PROVENANCE.line()]  # fmt: skip
    else:
        assert notes == [
            f"Submitted to {venue}; status: {words} (not in its proceedings).",
            PROVENANCE.line(),
        ]
    assert "TY  - CPAPER\n" in ris and f"T2  - {venue}\n" in ris  # one reference type, the venue kept


def test_the_provenance_line_says_exported_and_names_a_pinning_record() -> None:
    assert PROVENANCE.line() == f"openproceedings abcdef123456 · query {'0' * 64} · exported 2026-09-26"
    pinned = Provenance("abcdef123456", "0" * 64, "2026-09-26", record_id="Rec0rd_Id-01",
                        searched_at="2026-09-25T23:59:59Z")  # fmt: skip
    line = f"openproceedings abcdef123456 · query {'0' * 64} · exported 2026-09-26 · record Rec0rd_Id-01 · searched 2026-09-25"
    assert pinned.line() == line
    with pytest.raises(ValueError, match="record_id and searched_at"):
        Provenance("a", "b", "c", record_id="Rec0rd_Id-01")
    record = status_record("accepted")
    ris = "".join(export._ris([record], pinned))
    assert f"N1  - {line}\n" in ris
    (e,) = parse_string("".join(export._bibtex([record], pinned)))
    assert e.fields["note"] == line.replace("_", "\\_")
    row = next(csv.DictReader(io.StringIO(export.header("csv") + "".join(export._csv([record], pinned)))))
    row = {k.lstrip("\ufeff"): v for k, v in row.items()}
    assert (row["record_id"], row["searched_at"]) == ("Rec0rd_Id-01", "2026-09-25T23:59:59Z")
    plain = next(
        csv.DictReader(io.StringIO("".join(export._csv([record], PROVENANCE))), fieldnames=export.CSV_COLUMNS)
    )
    assert (plain["record_id"], plain["searched_at"]) == ("", "")
    (obj,) = [json.loads(x) for x in export._jsonl([record], pinned)]
    assert (obj["record_id"], obj["searched_at"]) == ("Rec0rd_Id-01", "2026-09-25T23:59:59Z")
    (bare,) = [json.loads(x) for x in export._jsonl([record], PROVENANCE)]
    assert (bare["record_id"], bare["searched_at"]) == (None, None)


def test_the_conference_table_names_exactly_the_venues() -> None:
    from typing import get_args

    assert tuple(vocab.CONFERENCES) == get_args(vocab.Venue)
    with pytest.raises(ValueError, match="the conference table must name exactly"):
        vocab.check_conferences({k: v for k, v in vocab.CONFERENCES.items() if k != "ICML"})


def _printable_before(text: str) -> str:
    """`export._printable` as it was: a per-character generator (kept here as the reference)."""
    import unicodedata

    return "".join(ch for ch in text if ch.isspace() or unicodedata.category(ch) != "Cc")


def test_printable_equals_the_per_character_definition_on_every_code_point() -> None:
    """The regex drops exactly the control characters (Cc) that aren't whitespace, for every code point but
    the surrogates (which no decoded UTF-8 text holds); ~1.1M code points, well under a second."""
    every = "".join(chr(c) for c in range(0x110000) if not 0xD800 <= c <= 0xDFFF)
    assert export._printable(every) == _printable_before(every)
    assert export._printable("a\x00\t\n\x0b\x0c\r\x1c\x1f\x7f\x85\x9fb") == "a\t\n\x0b\x0c\r\x1c\x1f\x85b"


def test_check_count_is_the_one_count_check_of_both_exports() -> None:
    """`op export` and `GET /export` end with the same check (M3a review): short or long is an internal
    error that names the counts, never the records."""
    from openproceedings.engine.protocol import EngineInternalError

    export.check_count(3, 3)
    for written in (2, 4):
        with pytest.raises(EngineInternalError, match=f"exported {written} records, but 3 match"):
            export.check_count(written, 3)


# --- each abstract names its source (TASK-138, decision-018; spec 04 §Exports) ------------------------------
PMLR_PAGE = "https://proceedings.mlr.press/v202/okafor23a.html"
PMLR = Attribution("pmlr", "pmlr", PMLR_PAGE)
PMLR_RECORD: dict[str, object] = {
    "id": "op:icml:2023:pmlr-v202-okafor23a", "title": "Sample-Efficient Evaluation", "abstract": "We adapt.",
    "authors": ["Okafor, Chidi"], "venue": "ICML", "year": 2023, "track": "main", "status": "accepted",
    "presentation": None, "venue_id_raw": None, "keywords": [],
    "urls": {"forum": None, "pdf": None, "proceedings": PMLR_PAGE, "doi": None},
}  # fmt: skip
# the columns before TASK-138, in their order: its four abstract columns only follow them
CSV_COLUMNS_BEFORE = (
    "id", "title", "abstract", "authors", "venue", "year", "track", "status", "presentation",
    "venue_id_raw", "forum", "pdf", "proceedings", "doi", "keywords", "index_version", "canonical_hash",
    "exported_at", "record_id", "searched_at",
)  # fmt: skip


def attributed_export(fmt: str, record: dict[str, object], source: Attribution | None) -> str:
    return export.header(fmt) + "".join(
        export.entries(fmt, [record], PROVENANCE, sources={str(record["id"]): source})
    )


def test_each_format_names_a_pmlr_abstracts_source_byte_for_byte() -> None:
    """The mapping, pinned whole on one PMLR record: only additions, every earlier line, field and column as
    it was (spec 04 §Exports; api-contract §Versioning rules)."""
    assert attributed_export("ris", PMLR_RECORD, PMLR) == (
        "TY  - CPAPER\nTI  - Sample-Efficient Evaluation\nAB  - We adapt.\nAU  - Okafor, Chidi\nPY  - 2023\n"
        "T2  - International Conference on Machine Learning (ICML 2023)\n"
        f"UR  - {PMLR_PAGE}\nID  - op:icml:2023:pmlr-v202-okafor23a\nKW  - main\nKW  - status:accepted\n"
        f"N1  - Abstract source: PMLR {PMLR_PAGE}\n"
        f"N1  - {PROVENANCE.line()}\nER  - \n\n"
    )
    assert attributed_export("bibtex", PMLR_RECORD, PMLR) == (
        "@inproceedings{okafor2023sample,\n  title = {Sample-Efficient Evaluation},\n"
        "  author = {Okafor, Chidi},\n"
        "  booktitle = {International Conference on Machine Learning (ICML 2023)},\n  year = 2023,\n"
        "  abstract = {We adapt.},\n"
        f"  abstract_source = {{PMLR {PMLR_PAGE}}},\n"
        f"  url = {{{PMLR_PAGE}}},\n  keywords = {{main, status:accepted}},\n"
        f"  note = {{{PROVENANCE.line()}}},\n  openproceedings_id = {{op:icml:2023:pmlr-v202-okafor23a}}\n}}\n\n"
    )
    assert attributed_export("csv", PMLR_RECORD, PMLR) == (
        "﻿" + ",".join(export.CSV_COLUMNS) + "\r\n"
        'op:icml:2023:pmlr-v202-okafor23a,Sample-Efficient Evaluation,We adapt.,"Okafor, Chidi",ICML,2023,'
        f"main,accepted,,,,,{PMLR_PAGE},,,abcdef123456,{'0' * 64},2026-09-26,,,pmlr,pmlr,{PMLR_PAGE},false,\r\n"
    )
    (obj,) = [json.loads(x) for x in attributed_export("jsonl", PMLR_RECORD, PMLR).splitlines()]
    assert obj["abstract_source"] == {"source": "pmlr", "origin": "pmlr", "url": PMLR_PAGE}
    assert obj["abstract_withheld"] is False and obj["abstract_withheld_reason"] is None
    withheld_keys = ("abstract_source", "abstract_withheld", "abstract_withheld_reason")
    assert {k: v for k, v in obj.items() if k not in withheld_keys} == {
        **PMLR_RECORD, "index_version": "abcdef123456", "canonical_hash": "0" * 64, "exported_at": "2026-09-26",
        "record_id": None, "searched_at": None,
    }  # fmt: skip


def test_without_a_source_every_format_is_byte_for_byte_what_it_was() -> None:
    """A record whose abstract no claim holds (or with none) gets no line and no field; CSV its three source
    columns empty (`abstract_withheld` false), JSONL `abstract_source: null`."""
    no_abstract = {**PMLR_RECORD, "abstract": None}
    for record, source in ((PMLR_RECORD, None), (no_abstract, PMLR)):  # an attribution without text: nothing
        ris = attributed_export("ris", record, source)
        assert "Abstract source" not in ris and ris.count("N1  - ") == 1
        assert "abstract_source" not in attributed_export("bibtex", record, source)
        assert attributed_export("csv", record, source).endswith(",2026-09-26,,,,,,false,\r\n")
        (obj,) = [json.loads(x) for x in attributed_export("jsonl", record, source).splitlines()]
        assert obj["abstract_source"] is None


def test_the_csv_columns_before_task_138_keep_their_positions() -> None:
    assert (
        *CSV_COLUMNS_BEFORE, "abstract_source", "abstract_origin", "abstract_url", "abstract_withheld",
        "abstract_withheld_reason",  # TASK-136, appended last (decision-021 rule 1)
    ) == export.CSV_COLUMNS  # fmt: skip


@pytest.mark.parametrize(
    "source, words",
    [
        (Attribution("openreview_v2", "openreview", "https://openreview.net/forum?id=X"), "OpenReview https://openreview.net/forum?id=X"),
        (Attribution("neurips_proceedings", "neurips_proceedings", "https://proceedings.neurips.cc/p"), "NeurIPS Proceedings https://proceedings.neurips.cc/p"),
        (Attribution("ris", "iclr_proceedings", "https://proceedings.iclr.cc/p"), "ICLR Proceedings (via RIS import) https://proceedings.iclr.cc/p"),
        (Attribution("ris", "pmlr", None), "PMLR (via RIS import)"),  # evidence on another site: named, unlinked
        (Attribution("ris", None, None), "an imported RIS file"),  # a route naming no known site
    ],
)  # fmt: skip
def test_the_source_reads_as_the_results_list_names_it(source: Attribution, words: str) -> None:
    assert export.credit(source) == words
    ris = attributed_export("ris", PMLR_RECORD, source)
    assert f"N1  - Abstract source: {words}\n" in ris


def test_the_source_line_sits_between_the_status_sentence_and_the_provenance_line() -> None:
    """A rejected paper's notes: the status sentence first (as before), the provenance line last (as before)."""
    from scholarmend.parse import parse_ris

    rejected = {**PMLR_RECORD, "status": "rejected"}
    (parsed,) = parse_ris(attributed_export("ris", rejected, PMLR), "x.ris")
    assert parsed.fields["N1"] == [
        "Submitted to International Conference on Machine Learning (ICML 2023); status: rejected (not in its proceedings).",
        f"Abstract source: PMLR {PMLR_PAGE}",
        PROVENANCE.line(),
    ]
    (entry,) = parse_string(attributed_export("bibtex", rejected, PMLR))
    assert entry.fields["abstract_source"] == f"PMLR {PMLR_PAGE}"
    assert entry.fields["note"].startswith("Submitted to ") and entry.fields["note"].endswith(
        PROVENANCE.line()
    )


def test_a_bibtex_source_with_special_characters_stays_one_parseable_field() -> None:
    odd = Attribution("pmlr", "pmlr", "https://proceedings.mlr.press/v1/a%20b.html?x=1&y=2#top")
    text = attributed_export("bibtex", PMLR_RECORD, odd) + attributed_export("bibtex", PMLR_RECORD, PMLR)
    first, second = parse_string(text)
    assert (
        first.fields["abstract_source"]
        == "PMLR https://proceedings.mlr.press/v1/a\\%20b.html?x=1\\&y=2\\#top"
    )
    assert second.fields["abstract_source"] == f"PMLR {PMLR_PAGE}"  # nothing swallowed


@pytest.mark.parametrize(
    "url, bibtex, ris",
    [
        ("https://ex.org/p/@user", "https://ex.org/p/{@}user", "https://ex.org/p/@user"),
        # unbalanced braces are dropped in BibTeX, as `url` drops them (bibtex-format §Escaping)
        ("https://ex.org/p/{abc", "https://ex.org/p/abc", "https://ex.org/p/{abc"),
        ("https://ex.org/p/}abc{", "https://ex.org/p/abc", "https://ex.org/p/}abc{"),
        ("https://ex.org/ünï/çödé", "https://ex.org/ünï/çödé", "https://ex.org/ünï/çödé"),
        ("https://ex.org/" + "x" * 5000, "https://ex.org/" + "x" * 5000, "https://ex.org/" + "x" * 5000),
        # a line break can't start a new RIS tag: it becomes one space
        ("https://x/a\nAB  - y", "https://x/a AB - y", "https://x/a AB - y"),
    ],
)
def test_an_odd_source_url_reads_back_in_one_record_with_the_reference_parsers(
    url: str, bibtex: str, ris: str
) -> None:
    """Two records, the first with an odd url: scholarmend and refaudit read both whole (AC#2)."""
    from scholarmend.parse import parse_ris

    odd = Attribution("pmlr", "pmlr", url)
    first, second = parse_string(
        attributed_export("bibtex", PMLR_RECORD, odd) + attributed_export("bibtex", PMLR_RECORD, PMLR)
    )
    assert first.fields["abstract_source"] == f"PMLR {bibtex}"
    assert second.fields["abstract_source"] == f"PMLR {PMLR_PAGE}"
    one, two = parse_ris(
        attributed_export("ris", PMLR_RECORD, odd) + attributed_export("ris", PMLR_RECORD, PMLR), "x.ris"
    )
    assert one.fields["N1"] == [f"Abstract source: PMLR {ris}", PROVENANCE.line()]
    assert one.fields["AB"] == ["We adapt."]
    assert two.fields["N1"] == [f"Abstract source: PMLR {PMLR_PAGE}", PROVENANCE.line()]


@pytest.mark.parametrize("fmt", export.FORMATS)
def test_a_record_the_sources_lack_is_an_internal_error_never_an_unattributed_export(fmt: str) -> None:
    with pytest.raises(EngineInternalError, match="missing from its snapshot"):
        list(export.entries(fmt, [PMLR_RECORD], PROVENANCE, sources={}))


def test_op_export_names_the_abstract_source_from_the_snapshot(data_dir: Path) -> None:
    """The unit corpus's abstracts are `openreview_v2` claims: AbCd0001 links its forum, the others have none."""
    from scholarmend.parse import parse_ris

    ris, _n = exported(data_dir, "ris")
    notes = {r.first("ID").rsplit(":", 1)[1]: r.fields["N1"] for r in parse_ris(ris, "x.ris")}
    assert notes["AbCd0001"] == [
        "Abstract source: OpenReview https://openreview.net/forum?id=AbCd0001",
        PROVENANCE.line(),
    ]
    assert notes["AbCd0004"] == ["Abstract source: OpenReview", PROVENANCE.line()]  # no forum url: unlinked
    assert notes["AbCd0002"] == [PROVENANCE.line()]  # no abstract, no source
    bib, _n = exported(data_dir, "bibtex")
    by = {e.fields["openproceedings_id"].rsplit(":", 1)[1]: e.fields for e in parse_string(bib)}
    assert by["AbCd0001"]["abstract_source"] == "OpenReview https://openreview.net/forum?id=AbCd0001"
    assert "abstract_source" not in by["AbCd0002"]


def test_the_site_names_are_the_results_lists() -> None:
    """`ORIGIN_NAMES` here and in `hit-item.tsx` say the same, so a screener reads one name for one site."""
    tsx = (Path(__file__).resolve().parents[3] / "frontend/src/components/search/hit-item.tsx").read_text(
        "utf-8"
    )
    block = re.search(r"const ORIGIN_NAMES[^{]*\{(.*?)\};", tsx, re.DOTALL)
    assert block is not None
    assert dict(re.findall(r"(\w+): \"([^\"]+)\"", block.group(1))) == export.ORIGIN_NAMES
    assert set(export.ORIGIN_NAMES) == set(get_args(Origin))


def test_without_sources_every_abstract_is_withheld_and_each_record_says_so() -> None:
    """decision-021: a pinned index whose snapshot can't be verified. The same record and metadata, no abstract,
    no source, and the withheld sentence in the file itself (added lines, fields and keys only)."""
    from scholarmend.parse import parse_ris

    def withheld(fmt: str, record: dict[str, object]) -> str:
        return export.header(fmt) + "".join(export.entries(fmt, [record], PROVENANCE, sources=None))

    rejected = {**PMLR_RECORD, "status": "rejected"}
    (parsed,) = parse_ris(withheld("ris", rejected), "x.ris")
    assert "AB" not in parsed.fields and parsed.fields["TI"] == ["Sample-Efficient Evaluation"]
    assert parsed.fields["N1"] == [
        "Submitted to International Conference on Machine Learning (ICML 2023); status: rejected (not in its proceedings).",
        export.WITHHELD,
        PROVENANCE.line(),
    ]
    assert withheld("ris", PMLR_RECORD) == attributed_export("ris", PMLR_RECORD, PMLR).replace(
        "AB  - We adapt.\n", ""
    ).replace(f"N1  - Abstract source: PMLR {PMLR_PAGE}\n", f"N1  - {export.WITHHELD}\n")
    (entry,) = parse_string(withheld("bibtex", PMLR_RECORD))
    assert "abstract" not in entry.fields and "abstract_source" not in entry.fields
    assert entry.fields["abstract_withheld"] == export.WITHHELD and entry.fields["note"] == PROVENANCE.line()
    assert withheld("csv", PMLR_RECORD).endswith(",2026-09-26,,,,,,true,source_unavailable\r\n")
    assert ",We adapt.," not in withheld("csv", PMLR_RECORD)
    (obj,) = [json.loads(x) for x in withheld("jsonl", PMLR_RECORD).splitlines()]
    assert obj["abstract"] is None and obj["abstract_source"] is None and obj["abstract_withheld"] is True
    assert obj["abstract_withheld_reason"] == "source_unavailable"


def test_the_abstract_source_header_states_are_a_closed_enum() -> None:
    from openproceedings.api.export import ABSTRACT_SOURCE_STATES
    from openproceedings.api.openapi import CLOSED_ENUMS

    assert frozenset(ABSTRACT_SOURCE_STATES) == CLOSED_ENUMS["abstract source state"]
