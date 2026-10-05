"""`op eval scholar` (TASK-056, spec 07 §B): the review rows, the rendered report and the command, on a
hand-built corpus whose every class is known (`test_scholar_compare`)."""

from __future__ import annotations

import csv
import io
import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from openproceedings.cli import main
from openproceedings.engine.index import build_index
from openproceedings.eval.scholar_compare import (
    COVERAGE_GAP,
    SCHOLAR_MISSED,
    UNSETTLED,
    MatchIndex,
    QueryComparison,
    Row,
    Scope,
    read_ris,
    scope_and_match,
)
from openproceedings.eval.scholar_report import (
    REVIEW_COLUMNS,
    SPOT,
    UNRESOLVED,
    Meta,
    RisFile,
    human_calls,
    parse_query_file,
    render,
    render_review,
    review_name,
    review_rows,
    write,
)
from openproceedings.ingest.dedup import DedupResult
from openproceedings.ingest.snapshot import render as render_snapshot

from tests.unit.test_scholar_compare import NAME, POP, QUERY, SET, compare, corpus, entry, nid

DAY = date(2026, 10, 4)
BUILT = datetime(2026, 9, 29, tzinfo=UTC)
META = Meta(
    date=DAY,
    index_version="abc123def456",
    tokenizer_version="3",
    snapshot="2026-09-29-test",
    snapshot_hash="f" * 64,
    records=9,
    ris=(RisFile(NAME, "a" * 64, 8),),
    scope=Scope(years=(2020, 2026)),
    command="op eval scholar --ris set.ris --index abc123def456 --date 2026-10-04",
)


def report(c: QueryComparison, meta: Meta = META) -> str:
    index = MatchIndex.build(corpus())
    side = scope_and_match(read_ris(SET, NAME), index, meta.scope)
    return render(meta, side, index, [c], review_rows([c]))


# --- query files ---------------------------------------------------------------------------------------------


def test_parse_query_file_reads_named_queries_and_skips_comments() -> None:
    text = "# a comment\n\n## first\na OR b\n\n# another\n## second\n\n(c d)\n"
    assert parse_query_file(text, "strings") == [("first", "a OR b"), ("second", "(c d)")]


def test_a_file_with_no_name_line_is_one_query_named_after_the_file() -> None:
    assert parse_query_file("a OR b\n", "stemmed") == [("stemmed", "a OR b")]


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("## first\n## second\na\n", "`first` has no query line"),
        ("## first\na\n## last\n", "`last` has no query line"),
        ("## twice\na\n## twice\nb\n", "used twice: twice"),
        ("# only a comment\n", "no query"),
    ],
)
def test_a_malformed_query_file_is_refused(text: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        parse_query_file(text, "strings")


# --- review rows -----------------------------------------------------------------------------------------------


def test_review_rows_are_every_unsettled_row_plus_a_tenth_of_the_settled_ones() -> None:
    c = compare(QUERY, SET, corpus())
    rows = review_rows([c])
    assert [(x.row.auto_class, x.kind) for x in rows if x.kind == UNRESOLVED] == [
        (UNSETTLED, UNRESOLVED),
        (COVERAGE_GAP, UNRESOLVED),
        (SCHOLAR_MISSED, UNRESOLVED),
    ]
    spot = [x for x in rows if x.kind == SPOT]
    assert len(spot) == 1 and spot[0].row.settled  # ceil(10% of the 5 settled disagreements)
    assert review_rows([c]) == rows  # the draw is a hash of the row's ids: the same every run


def test_the_spot_check_is_a_tenth_rounded_up() -> None:
    settled = tuple(Row("scholar", f"set.ris#{i}", f"op:neurips:2024:x{i:07d}", "t", "NeurIPS", 2024, "full_text", "e")
                    for i in range(21))  # fmt: skip
    c = compare(QUERY, SET, corpus())
    many = QueryComparison(**{**c.__dict__, "dropped": settled, "not_in_index": (), "added": ()})
    assert [x.kind for x in review_rows([many])] == [SPOT] * 3


def test_review_csv_has_the_protocol_columns_and_leaves_the_human_ones_empty() -> None:
    c = compare(QUERY, SET, corpus())
    rows = list(csv.DictReader(io.StringIO(render_review(review_rows([c]), "abc123def456"))))
    assert tuple(rows[0]) == REVIEW_COLUMNS
    assert REVIEW_COLUMNS[:12] == (
        "query_name", "side", "scholar_key", "op_id", "title", "venue", "year", "auto_class", "auto_evidence",
        "human_class", "reviewer_role", "note",
    )  # fmt: skip
    assert all(r["human_class"] == r["reviewer_role"] == r["note"] == "" for r in rows)
    assert {r["index_version"] for r in rows} == {"abc123def456"} and {r["query_name"] for r in rows} == {"q"}
    missed = next(r for r in rows if r["auto_class"] == SCHOLAR_MISSED)
    assert (missed["side"], missed["scholar_key"], missed["op_id"]) == (
        "openproceedings",
        "",
        nid("miss0001"),
    )
    assert (missed["title"], missed["venue"], missed["year"]) == ("A benchmark of trust", "NeurIPS", "2024")
    assert missed["row_kind"] == UNRESOLVED


def test_a_title_a_spreadsheet_would_run_is_quoted() -> None:
    records = [*corpus()]
    text = entry("=HYPERLINK(1)") + entry("LLM trust benchmark")
    c = compare(QUERY, text, records)
    out = render_review(review_rows([c]), "v")
    assert "'=HYPERLINK(1)" in out and "\n=HYPERLINK" not in out


# --- the report ------------------------------------------------------------------------------------------------


def test_header_names_every_input_the_numbers_depend_on() -> None:
    text = report(compare(QUERY, SET, corpus(), scope=META.scope))
    assert text.startswith("# Scholar comparison, 2026-10-04\n")
    for line in (
        "- Index: `index_version` `abc123def456`, `tokenizer_version` `3`",
        f"- Snapshot: `2026-09-29-test`, `snapshot_hash` `{'f' * 64}` (9 records)",
        f"- Scholar set: `set.ris`, sha256 `{'a' * 64}` (8 records)",
        "- Scope, both sides: ICLR, ICML, NeurIPS; 2020–2026",
        "- Queries: `q`",
        "- Notes: none",
        "- Command: `op eval scholar --ris set.ris --index abc123def456 --date 2026-10-04`",
        "- Review rows: `2026-10-04-scholar-comparison-review.csv` (4 rows, 3 unresolved)",
        "**`our_bug`: 0** across 1 query.",
    ):
        assert line in text.splitlines()


def test_the_tables_hold_the_runs_counts_and_percentages() -> None:
    lines = report(compare(QUERY, SET, corpus(), scope=META.scope)).splitlines()
    for line in (
        "| `q` | 8 | 2 | 1 | 7 | 1 | 1 (12.5%) | 2 (25.0%) | 3 |",  # the summary row
        "| read | 8 |",
        "| **papers in scope** | **8** |",
        "| title venue year | 6 |",
        "| forum id | 1 |",
        "| no match (not found) | 1 |",
        "| Scholar set, in scope | 8 |",
        "| openproceedings `total` (default filters; every venue and year) | 2 |",
        "| in both | 1 |",
        "| only in the Scholar set | 7 |",
        "| only in openproceedings | 1 |",
        '| 1. `(llm OR "foundation model")` | 4 | 6 |',
    ):
        assert line in lines, line
    by_class = {
        ln.split("|")[1].strip(): [c.strip() for c in ln.split("|")[2:5]]
        for ln in lines
        if ln.startswith("| `")
    }
    assert by_class["`filtered`"] == ["2", "28.6%", "25.0%"]
    assert by_class["`stemming`"] == ["2", "28.6%", "25.0%"]
    assert by_class["`full_text`"] == ["1", "14.3%", "12.5%"]
    assert by_class["`coverage_gap`"] == ["1", "14.3%", "12.5%"]
    assert by_class["`scholar_missed`"] == ["1", "100.0%", "50.0%"]
    assert by_class["`our_bug`"] == ["0", "0.0%", "0.0%"]  # always shown: it must be 0
    assert (
        "**Finding.** Of the 8 in-scope papers of the Scholar set, 1 (12.5%) match this string nowhere in title or "
        "abstract, inflected forms included (`full_text`), and 2 (25.0%) match only through an inflected form "
        "(`stemming`). 1 (12.5%) are in the exact result."
    ) in lines


def test_the_report_holds_ids_and_titles_but_no_abstract_and_no_path() -> None:
    text = report(compare(QUERY, SET, corpus(), scope=META.scope))
    assert f"| `{nid('miss0001')}` | A benchmark of trust | NeurIPS | 2024 | `scholar_missed` |" in text
    assert "| `set.ris#8` | A paper nobody indexed | NeurIPS | 2024 | `coverage_gap` |" in text
    assert "For every LLM." not in text and "We study graphs" not in text  # abstracts never leave the corpus
    assert "/Users/" not in text and "/home/" not in text


def test_a_pop_string_gets_the_decision_002_note_and_scholars_reading() -> None:
    c = compare(POP, entry("Foundation model trust"), corpus())
    text = report(c)
    assert "**Decision-002.** This string has 1 unquoted multi-word `|` items." in text
    assert "is classed `compat_reading`: it is not a record either side missed." in text
    assert "(foundation AND (model OR llm) AND trust AND track:" in text
    assert "**Decision-002.**" not in report(compare(QUERY, SET, corpus()))


def test_an_our_bug_is_announced_at_the_top() -> None:
    from tests.unit.test_scholar_compare import Lying

    records = corpus()
    c = compare(QUERY, SET, records, engine=Lying(records, drop=frozenset({nid("both0001")})))
    text = report(c)
    assert "**`our_bug`: 1** across 1 query. Each one is a Must-fix with a golden case" in text
    assert f"| `{nid('both0001')}` | Scholar cut this title… | NeurIPS | 2024 | `our_bug` |" in text


def test_notes_are_printed_verbatim_under_their_hash() -> None:
    from dataclasses import replace

    meta = replace(
        META, notes="The export is the mended one.\n", notes_name="notes.md", notes_sha256="b" * 64
    )
    text = report(compare(QUERY, SET, corpus()), meta)
    assert f"- Notes: `notes.md`, sha256 `{'b' * 64}`" in text
    assert text.endswith("## Notes on these inputs\n\nThe export is the mended one.\n")


def test_a_pipe_in_a_title_does_not_break_its_table_row() -> None:
    c = compare(QUERY, entry("A | B paper"), corpus())
    assert "| `set.ris#1` | A \\| B paper | NeurIPS | 2024 | `coverage_gap` |" in report(c)


# --- writing ---------------------------------------------------------------------------------------------------


def test_write_places_both_files_and_never_erases_a_persons_calls(tmp_path: Path) -> None:
    c = compare(QUERY, SET, corpus())
    review = render_review(review_rows([c]), "v")
    path, rows, replaced = write("report\n", review, tmp_path, DAY)
    assert (path.name, rows.name, replaced) == ("2026-10-04-scholar-comparison.md", review_name(DAY), False)
    assert human_calls(rows) == 0
    assert write("again\n", review, tmp_path, DAY)[2] is True  # nothing filled in: replaced whole
    filled = rows.read_text(encoding="utf-8").replace(
        ",,,,unresolved,", ",full_text,second reviewer,,unresolved,", 1
    )
    rows.write_text(filled, encoding="utf-8")
    assert human_calls(rows) == 1
    with pytest.raises(ValueError, match="holds 1 row\\(s\\) a person filled in"):
        write("third\n", review, tmp_path, DAY)
    assert path.read_text(encoding="utf-8") == "again\n" and rows.read_text(encoding="utf-8") == filled


# --- the command -----------------------------------------------------------------------------------------------


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    root = tmp_path / "data"
    snap = root / "snapshots" / "2026-09-29-test"
    snap.mkdir(parents=True)
    records = tuple(sorted(corpus(), key=lambda r: r.id))
    for name, data in render_snapshot(DedupResult(records, (), ()), [], BUILT).items():
        (snap / name).write_bytes(data)
    build_index(snap, root / "indexes")
    return root


def index_name(data_dir: Path) -> str:
    return next(p.name for p in (data_dir / "indexes").iterdir() if not p.name.startswith("."))


@pytest.fixture
def inputs(tmp_path: Path) -> tuple[Path, Path]:
    ris = tmp_path / "in" / "set.ris"
    ris.parent.mkdir()
    ris.write_text(SET, encoding="utf-8-sig")  # with the BOM Scholar exports begin with
    queries = tmp_path / "in" / "strings.txt"
    queries.write_text(f"# the test strings\n## main\n{QUERY}\n\n## pop\n{POP}\n", encoding="utf-8")
    return ris, queries


def args(data_dir: Path, out: Path, ris: Path, *extra: str) -> list[str]:
    return ["--data-dir", str(data_dir), "eval", "scholar", "--ris", str(ris), "--index", index_name(data_dir),
            "--out", str(out), "--date", "2026-10-04", *extra]  # fmt: skip


def test_op_eval_scholar_writes_the_report_and_the_review_rows(
    data_dir: Path, inputs: tuple[Path, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ris, queries = inputs
    out = tmp_path / "results"
    assert (
        main(args(data_dir, out, ris, "--query-file", str(queries), "--years", "2020..2026", "--check")) == 0
    )
    assert sorted(p.name for p in out.iterdir()) == [
        "2026-10-04-scholar-comparison-review.csv",
        "2026-10-04-scholar-comparison.md",
    ]
    text = (out / "2026-10-04-scholar-comparison.md").read_text(encoding="utf-8")
    assert f"`index_version` `{index_name(data_dir)}`" in text and "- Queries: `main`, `pop`" in text
    assert "| `main` | 8 | 2 | 1 | 7 | 1 | 1 (12.5%) | 2 (25.0%) | 3 |" in text  # the served index agrees
    assert "**`our_bug`: 0** across 2 queries." in text
    assert (
        f"- Command: `op eval scholar --ris set.ris --query-file strings.txt --years 2020..2026 --index "
        f"{index_name(data_dir)} --date 2026-10-04`"
    ) in text
    assert str(tmp_path) not in text  # file names only: a directory can name a person
    rows = list(csv.DictReader((out / "2026-10-04-scholar-comparison-review.csv").open(encoding="utf-8")))
    assert {r["query_name"] for r in rows} == {"main", "pop"}
    err = capsys.readouterr().err
    assert (
        "main: Scholar 8, openproceedings 2, both 1, only Scholar 7, only openproceedings 1, our_bug 0" in err
    )


def test_name_selects_and_orders_and_query_adds_one(
    data_dir: Path, inputs: tuple[Path, Path], tmp_path: Path
) -> None:
    ris, queries = inputs
    out = tmp_path / "results"
    extra = ["--query-file", str(queries), "--name", "pop", "--query", "LLM$ trust"]
    assert main(args(data_dir, out, ris, *extra)) == 0
    text = (out / "2026-10-04-scholar-comparison.md").read_text(encoding="utf-8")
    assert "- Queries: `pop`, `query`" in text and "## Query `main`" not in text
    assert "--name pop --query '<the string under `query`>'" in text


@pytest.mark.parametrize(
    "extra",
    [
        ["--years", "2026..2020"],
        ["--years", "twenty"],
        ["--venues", "AISTATS"],
        ["--name", "absent"],
        ["--date", "Oct 4"],
        ["--query", "(LLM AND"],  # a parse error: refused by its code
    ],
)
def test_bad_arguments_are_refused_and_nothing_is_written(
    data_dir: Path, inputs: tuple[Path, Path], tmp_path: Path, extra: list[str]
) -> None:
    ris, queries = inputs
    out = tmp_path / "results"
    base = [
        a
        for a in args(data_dir, out, ris, "--query-file", str(queries))
        if extra[0] != "--date" or a != "2026-10-04"
    ]
    if extra[0] == "--date":
        base.remove("--date")
    assert main([*base, *extra]) == 1
    assert not out.exists()


def test_the_command_logs_counts_and_never_the_query(
    data_dir: Path, inputs: tuple[Path, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ris, queries = inputs
    assert main(args(data_dir, tmp_path / "r", ris, "--query-file", str(queries))) == 0
    lines = [json.loads(ln) for ln in capsys.readouterr().err.splitlines() if ln.startswith("{")]
    [line] = [ln for ln in lines if ln.get("event") == "scholar_report_written"]
    assert (line["level"], line["queries"], line["ris_records"], line["in_scope"]) == ("INFO", 2, 8, 8)
    assert (line["our_bug"], line["index_version"]) == (0, index_name(data_dir))
    assert not any("foundation" in json.dumps(ln) or "benchmark" in json.dumps(ln) for ln in lines)


def test_the_default_strings_are_the_trust_evals_fixture(
    data_dir: Path, inputs: tuple[Path, Path], tmp_path: Path
) -> None:
    ris, _ = inputs
    out = tmp_path / "results"
    assert main(args(data_dir, out, ris, "--name", "main-7-most-updated", "--name", "main-2-pop")) == 0
    text = (out / "2026-10-04-scholar-comparison.md").read_text(encoding="utf-8")
    assert "- Queries: `main-7-most-updated`, `main-2-pop`" in text
    assert "- Query file: `trust-evals.txt`, sha256 `" in text
    assert "**Decision-002.** This string has 10 unquoted multi-word `|` items." in text  # main-2-pop (AC 3)
