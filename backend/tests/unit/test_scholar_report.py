"""`op eval scholar` (TASK-056, spec 07 §B): the review rows, the rendered report and the command, on a
hand-built corpus whose every class is known (`test_scholar_compare`)."""

from __future__ import annotations

import csv
import io
import json
from dataclasses import replace
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
    BOM,
    IN_BOTH,
    REVIEW_COLUMNS,
    SPOT,
    UNRESOLVED,
    Call,
    HumanCalls,
    Meta,
    ReviewRow,
    RisFile,
    after_calls,
    human_calls,
    parse_query_file,
    read_calls,
    render,
    render_review,
    review_name,
    review_rows,
    write,
)
from openproceedings.ingest.dedup import DedupResult
from openproceedings.ingest.record import PaperRecord
from openproceedings.ingest.snapshot import render as render_snapshot
from openproceedings.query.ast import Node

from tests.unit.ingest.test_dedup import paper
from tests.unit.test_scholar_compare import NAME, POP, QUERY, SET, compare, corpus, entry, imported, nid

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
    rows = list(
        csv.DictReader(io.StringIO(render_review(review_rows([c]), "abc123def456").removeprefix(BOM)))
    )
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
        "- Review rows: `2026-10-04-scholar-comparison-review.csv` (4 rows; 3 left for a call, 0 called)",
        "**`our_bug`: 0** across 1 query.",
    ):
        assert line in text.splitlines()


def test_the_tables_hold_the_runs_counts_and_percentages() -> None:
    lines = report(compare(QUERY, SET, corpus(), scope=META.scope)).splitlines()
    for line in (
        "| `q` | 8 | 2 | 1 | 7 | 1 | 1 (12.5%) | 0 | 1 (12.5%) | 3 |",  # the summary row
        "| read | 8 |",
        "| **papers in scope** (the denominator of every percentage of the Scholar set) | **8** |",
        "| title venue year | 6 |",
        "| forum id | 1 |",
        "| no match (not found) | 1 |",
        "| Scholar set, in scope | 8 |",
        "| openproceedings `total` (default filters; every venue and year) | 2 |",
        "| in both | 1 (1 crawled records, 0 RIS-only) |",
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
    assert by_class["`filtered`"] == ["3", "42.9%", "37.5%"]
    assert by_class["`stemming`"] == ["1", "14.3%", "12.5%"]
    assert by_class["`full_text`"] == ["1", "14.3%", "12.5%"]
    assert by_class["`coverage_gap`"] == ["1", "14.3%", "12.5%"]
    assert by_class["`scholar_missed`"] == ["1", "100.0%", "50.0%"]
    assert by_class["`our_bug`"] == ["0", "0.0%", "0.0%"]  # always shown: it must be 0
    assert (
        "**Finding.** Of the 8 in-scope papers of the Scholar set, 1 (12.5%) match this string nowhere in title or "
        "abstract, inflected forms included (`full_text`), and 1 (12.5%) match only through an inflected form "
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
    filled = (
        rows.read_bytes()
        .decode("utf-8")
        .replace(",,,,unresolved,", ",full_text,second reviewer,,unresolved,", 1)
    )
    rows.write_bytes(filled.encode("utf-8"))
    assert human_calls(rows) == 1
    with pytest.raises(ValueError, match="holds 1 filled row"):
        write("third\n", review, tmp_path, DAY)
    assert path.read_text(encoding="utf-8") == "again\n" and rows.read_bytes().decode("utf-8") == filled


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
    assert "| `main` | 8 | 2 | 1 | 7 | 1 | 1 (12.5%) | 0 | 1 (12.5%) | 3 |" in text  # the served index agrees
    assert "**`our_bug`: 0** across 2 queries." in text
    assert (
        f"- Command: `op eval scholar --ris set.ris --query-file strings.txt --years 2020..2026 --index "
        f"{index_name(data_dir)} --date 2026-10-04`"
    ) in text
    assert str(tmp_path) not in text  # file names only: a directory can name a person
    rows = list(
        csv.DictReader(
            (out / "2026-10-04-scholar-comparison-review.csv").open(encoding="utf-8-sig", newline="")
        )
    )
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
    assert (line["level"], line["queries"], line["ris_records"], line["ris_papers"]) == ("INFO", 2, 8, 8)
    assert (line["our_bug"], line["index_version"]) == (0, index_name(data_dir))
    [start] = [ln for ln in lines if ln.get("event") == "scholar_report_started"]  # before the long part
    assert (start["queries"], start["ris_records"], start["index_version"]) == (2, 8, index_name(data_dir))
    assert lines.index(start) < lines.index(line)
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


# --- review round 2: provenance, denominators, the stemmer's sensitivity, the set's own string -----------------


def own_import() -> tuple[str, list[PaperRecord]]:
    """A set whose 2026 papers the index holds only because the set was imported into it."""
    records = [
        paper("crwl0001", "LLM trust benchmark", abstract="An abstract."),
        paper("crwl0002", "Graph theory", track="workshop", abstract="No query word."),
        paper("crwl0003", "LLM trustworthiness benchmark", abstract="An abstract."),
        imported("ris00001", "Graph networks", abstract="The import's own text.", year=2026),
        imported("ris00002", "Another LLM trust benchmark", abstract="The import's own text.", year=2026),
        imported("ris00003", "Graph theory", abstract="The import's own text.", year=2026),
    ]
    text = (
        entry("LLM trust benchmark")
        + entry("Graph theory")
        + entry("LLM trustworthiness benchmark")
        + entry("Graph networks", year=2026)
        + entry("Another LLM trust benchmark", year=2026)
        + entry("Graph theory", year=2026)
        + entry("Graph theory", venue="… Information Processing …", year=2026)
    )
    return text, records


def own_report(meta: Meta = META) -> str:
    text, records = own_import()
    index = MatchIndex.build(records)
    side = scope_and_match(read_ris(text, NAME), index, meta.scope)
    c = compare(QUERY, text, records, scope=meta.scope)
    return render(meta, side, index, [c], review_rows([c]))


def test_the_report_says_how_many_matches_are_the_sets_own_import() -> None:
    lines = own_report().splitlines()
    for line in (
        "**What the matches rest on.** Of the 7 in-scope papers of the Scholar set, 6 match an index record: 3 a "
        "record with an independent source (a crawl), 3 a record whose only source is an imported RIS set. A match "
        "of the second kind is the set matching its own import, and says nothing about coverage (see Matching).",
        "Matched to a record with an independent source (a crawl of OpenReview or the proceedings): **3**. Matched "
        "to a record whose only source is an imported RIS set (RIS-only): **3**.",
        "| NeurIPS | 2024 | 3 | 3 | 0 | 3 |",
        "| NeurIPS | 2026 | 3 | 0 | 3 | 0 |",
        "| in both | 2 (1 crawled records, 1 RIS-only) |",
        "| in both, matched to a RIS-only record whose title another index record has | 0 |",
        "| `q` | 7 | 2 | 2 | 5 | 0 | 3 (42.9%) | 1 | 0 (0.0%) | 2 |",
        "- Of the 3 `full_text` papers, 2 rest on a crawled record and 1 on a RIS-only record, whose title and "
        "abstract are the import's own.",
        "- 1 of them also fail the default track or status filters.",
    ):
        assert line in lines, line
    text = "\n".join(lines)
    assert "Abstract source of the matched records: `openreview_v2` 3; `ris` 3." in text
    assert (
        "The index holds **no crawled record** for" in text
        and "NeurIPS 2026." in text.split("no crawled record")[1]
    )
    assert "no record can be only in openproceedings" in text
    # the class table splits each count by what the record rests on
    assert "| `full_text` | 3 | 60.0% | 42.9% | 2 | 1 |" in text


def test_a_shared_title_on_an_import_only_match_and_a_no_venue_record_are_counted_and_listed() -> None:
    text = own_report()
    assert (
        "1 papers matched a RIS-only record whose title key another index record has too (0 in the same venue and "
        "year: one paper under two ids, so the set can count it twice; the others in another venue or year: the "
        "import's venue or year may be wrong). The match is kept, and each such row that is a disagreement is "
        "`unsettled`, for a reviewer."
    ) in text
    assert "`no match (no venue)`: 1 records whose venue string is empty or cut by Scholar (`…`)" in text
    assert "| no match (no venue) | 1 |" in text
    assert (
        "| `set.ris#7` | Graph theory | … Information Processing … | 2026 | `unsettled` | its venue string is no "
        "venue, so no title match is made; same title: op:neurips:2026:ris00003 (NeurIPS 2026) |"
    ) in text
    assert (
        "| `op:neurips:2026:ris00003` | Graph theory | NeurIPS | 2026 | `unsettled` | matched by title venue year"
        in text
    )


def test_the_stemmer_sensitivity_is_stated_and_no_lower_bound_is_claimed() -> None:
    text = own_report()
    assert (
        "With every searched word replaced by its inflection stem read as a prefix (`benchmarks` → `benchmark*`, "
        "`evaluating` → `evaluat*`), 1 of the 3 (33.3%) `full_text` papers would match title or abstract. That is "
        "all this figure measures"
    ) in text
    assert "strips or adds endings" not in text
    assert (
        "an inflection-only stand-in, kept by decision-038 (see Method); it is not Google Scholar's stemmer"
        in text
    )
    assert "Decision-038 keeps this stand-in and adopts no published stemmer" in text
    assert "open decision" not in text
    assert "lower bound" not in text


def test_the_other_strings_are_marked_as_not_the_sets_own() -> None:
    from dataclasses import replace

    c = compare(QUERY, SET, corpus())
    other = QueryComparison(**{**c.__dict__, "name": "pop"})
    index = MatchIndex.build(corpus())
    side = scope_and_match(read_ris(SET, NAME), index, META.scope)
    text = render(replace(META, answers="q"), side, index, [c, other], review_rows([c, other]))
    assert "| `q` | 8 |" in text and "| `pop` † | 8 |" in text
    assert (
        "† The Scholar set is Google Scholar's answer to `q` only. For `pop` the columns are what the string keeps, "
        "drops and adds against that same set, not a comparison with what Scholar returns for it."
    ) in text
    q_section, pop_section = text.split("## Query `q`")[1].split("## Query `pop`")
    assert "The Scholar set is Google Scholar's answer to `q`, not to this string." in pop_section
    assert "not to this string" not in q_section
    assert "†" not in report(c)  # nobody said which string the set answers: no claim either way


def test_review_csv_says_what_each_rows_record_rests_on() -> None:
    text, records = own_import()
    c = compare(QUERY, text, records)
    rows = list(csv.DictReader(io.StringIO(render_review(review_rows([c]), "v").removeprefix(BOM))))
    assert REVIEW_COLUMNS[-2:] == ("record_source", "abstract_source")
    by_id = {r["op_id"] or r["scholar_key"]: (r["record_source"], r["abstract_source"]) for r in rows}
    assert by_id[nid("ris00003", 2026)] == ("ris_only", "ris")
    assert by_id["set.ris#7"] == ("", "")
    assert {v for v in by_id.values()} <= {("ris_only", "ris"), ("crawled", "openreview_v2"), ("", "")}


def test_answers_must_name_a_query_and_is_part_of_the_command(
    data_dir: Path, inputs: tuple[Path, Path], tmp_path: Path
) -> None:
    ris, queries = inputs
    out = tmp_path / "results"
    assert main(args(data_dir, out, ris, "--query-file", str(queries), "--answers", "absent")) == 1
    assert not out.exists()
    notes = tmp_path / "in" / "notes.md"
    notes.write_text("About this set.\n", encoding="utf-8")
    extra = ["--query-file", str(queries), "--answers", "main", "--notes", str(notes)]
    assert main(args(data_dir, out, ris, *extra)) == 0
    text = (out / "2026-10-04-scholar-comparison.md").read_text(encoding="utf-8")
    assert "| `pop` † |" in text and "--answers main --notes notes.md --index" in text
    assert text.endswith("## Notes on these inputs\n\nAbout this set.\n")


def test_notes_are_never_a_default(data_dir: Path, inputs: tuple[Path, Path], tmp_path: Path) -> None:
    ris, queries = inputs
    assert main(args(data_dir, tmp_path / "r", ris, "--query-file", str(queries))) == 0
    text = (tmp_path / "r" / "2026-10-04-scholar-comparison.md").read_text(encoding="utf-8")
    assert (
        "- Notes: none" in text and "## Notes on these inputs" not in text
    )  # another set's notes would be wrong


def test_a_kept_record_matched_to_a_shared_title_import_is_counted_under_in_both() -> None:
    records = [
        paper("crwl0009", "LLM trust benchmark", abstract="An abstract.", year=2025),
        imported("ris00009", "LLM trust benchmark", abstract="The import's own text.", year=2026),
    ]
    text = entry("LLM trust benchmark", year=2026)
    index = MatchIndex.build(records)
    c = compare(QUERY, text, records)
    assert [(r.op_id, r.shared_title, r.auto_class) for r in c.kept] == [(nid("ris00009", 2026), True, "")]
    out = render(META, scope_and_match(read_ris(text, NAME), index, META.scope), index, [c], review_rows([c]))
    assert "| in both, matched to a RIS-only record whose title another index record has | 1 |" in out


# --- a person's calls, read back (TASK-178) --------------------------------------------------------------------


def fill(rows_file: Path, calls: dict[str, tuple[str, str, str]]) -> None:
    """Fill `human_class`, `reviewer_role` and `note` on the rows whose op id or Scholar key is named."""
    with rows_file.open(encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        if (key := r["op_id"] or r["scholar_key"]) in calls and r["query_name"] == "main":
            r["human_class"], r["reviewer_role"], r["note"] = calls[key]
    with rows_file.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, REVIEW_COLUMNS, lineterminator="\r\n")  # a spreadsheet's line ends
        writer.writeheader()
        writer.writerows(rows)


ALL_CALLED = {
    nid("noab0001"): ("full_text", "second reviewer", "read the PDF"),
    "set.ris#8": ("out_of_scope", "second reviewer", ""),
    nid("miss0001"): ("scholar_missed", "second reviewer", ""),
}


@pytest.fixture
def ran(data_dir: Path, inputs: tuple[Path, Path], tmp_path: Path) -> tuple[list[str], Path, Path]:
    """One query run once: the command, the report and the review file."""
    ris, queries = inputs
    out = tmp_path / "results"
    argv = args(data_dir, out, ris, "--query-file", str(queries), "--name", "main", "--check")
    assert main(argv) == 0
    return argv, out / "2026-10-04-scholar-comparison.md", out / "2026-10-04-scholar-comparison-review.csv"


def test_an_unfilled_review_file_leaves_the_disagreements_unclassified(
    ran: tuple[list[str], Path, Path],
) -> None:
    text = ran[1].read_text(encoding="utf-8")
    assert "## Human calls\n\nNone yet: no row of the review file has a `human_class`." in text
    assert (
        "**Every disagreement classified: no.** `our_bug` by the automation: 0; by a call: 0; rows left for a "
        "call that have none yet: 3."
    ) in text


def test_a_filled_review_file_is_read_back_and_left_as_it_is(
    ran: tuple[list[str], Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    argv, report_file, rows_file = ran
    fill(rows_file, ALL_CALLED)
    before = rows_file.read_bytes()
    capsys.readouterr()
    assert main(argv) == 0
    assert rows_file.read_bytes() == before  # never rewritten, whatever its line ends
    text = report_file.read_text(encoding="utf-8")
    assert f"Read from `{rows_file.name}` (sha256 `" in text and "3 of its 4 rows have a call." in text
    assert "| `main` | 3 | 3 | 1 | none called | — |" in text
    for line in (
        "| `main` | `coverage_gap` | `out_of_scope` | 1 |",
        "| `main` | `scholar_missed` | `scholar_missed` | 1 |",
        "| `main` | `unsettled` | `full_text` | 1 |",
    ):
        assert line in text.splitlines(), line
    assert (
        "**Every disagreement classified: yes, on the calls whose roles this line names.** `our_bug` by the automation: 0; "
        "by a call: 0; rows left for a call that have none yet: 0. The 3 calls were made as: `second reviewer` "
        "(3 rows). A call weighs what its role does: unless every role is an independent reviewer's, this verdict "
        "is provisional and spec 07 §B's bar is not closed."
    ) in text.splitlines()
    assert "**Who made them** (the file's `reviewer_role`, as written): `second reviewer` (3 rows)." in text
    assert "(4 rows; 3 left for a call, 3 called)" in text
    err = capsys.readouterr().err
    assert "as it is: 3 of 4 rows have a call" in err
    assert "every disagreement classified: yes (calls made as: second reviewer (3))" in err
    assert "read the PDF" not in text  # the roles are printed, a note never is


def test_a_spot_check_call_is_compared_with_the_automated_class(ran: tuple[list[str], Path, Path]) -> None:
    argv, report_file, rows_file = ran
    with rows_file.open(encoding="utf-8-sig", newline="") as fh:
        [spot] = [r for r in csv.DictReader(fh) if r["row_kind"] == SPOT]
    fill(rows_file, {**ALL_CALLED, spot["op_id"]: (spot["auto_class"], "second reviewer", "")})
    assert main(argv) == 0
    assert "| `main` | 3 | 3 | 1 | 1 | 1 |" in report_file.read_text(encoding="utf-8")


def test_a_persons_our_bug_fails_the_check_and_is_named(ran: tuple[list[str], Path, Path]) -> None:
    argv, report_file, rows_file = ran
    fill(rows_file, {**ALL_CALLED, nid("miss0001"): ("our_bug", "second reviewer", "")})
    assert main(argv) == 1  # --check
    text = report_file.read_text(encoding="utf-8")
    assert "**1 row(s) are called `our_bug`.**" in text and f"`main` `{nid('miss0001')}`" in text
    assert "**Every disagreement classified: no.** `our_bug` by the automation: 0; by a call: 1;" in text


@pytest.mark.parametrize(
    ("call", "message"),
    [
        (("probably fine", "second reviewer", ""), "human_class must be one of our_bug, filtered"),
        (("", "second reviewer", ""), "the row has a role or a note but no class"),
        (("", "", "looked at it"), "the row has a role or a note but no class"),
        (("full_text", "", ""), "a human_class needs a reviewer_role"),
        (("unsettled", "second reviewer", ""), "human_class must be one of"),  # a person settles it
    ],
)
def test_a_malformed_call_is_refused_and_nothing_is_written(
    ran: tuple[list[str], Path, Path],
    call: tuple[str, str, str],
    message: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    argv, report_file, rows_file = ran
    fill(rows_file, {nid("noab0001"): call})
    before = (report_file.read_bytes(), rows_file.read_bytes())
    capsys.readouterr()
    assert main(argv) == 1
    assert message in capsys.readouterr().err
    assert (report_file.read_bytes(), rows_file.read_bytes()) == before


def test_calls_for_another_runs_rows_are_refused_not_carried_over(
    ran: tuple[list[str], Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    argv, report_file, rows_file = ran
    fill(rows_file, ALL_CALLED)
    before = (report_file.read_bytes(), rows_file.read_bytes())
    other = [a if a != "main" else "pop" for a in argv]  # another query: other rows
    capsys.readouterr()
    assert main(other) == 1
    assert "holds calls for other rows than this run writes" in capsys.readouterr().err
    assert (report_file.read_bytes(), rows_file.read_bytes()) == before


def test_an_automated_our_bug_fails_the_check_and_only_the_check(
    ran: tuple[list[str], Path, Path], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from openproceedings.engine import tantivy_engine

    class Dropping(tantivy_engine.TantivyEngine):  # the served engine loses a paper the oracle matches
        def match_ids(self, ast: Node) -> frozenset[str]:
            return super().match_ids(ast) - {nid("both0001")}

    monkeypatch.setattr(tantivy_engine, "TantivyEngine", Dropping)
    argv, report_file, _ = ran
    capsys.readouterr()
    assert main(argv) == 1  # --check
    err = capsys.readouterr().err
    assert "our_bug: 1 (must be 0: investigate before the report is cited)" in err
    [line] = [
        json.loads(ln) for ln in err.splitlines() if ln.startswith("{") and "scholar_report_written" in ln
    ]
    assert (line["level"], line["our_bug"], line["human_our_bug"]) == ("ERROR", 1, 0)
    assert main([a for a in argv if a != "--check"]) == 0  # reported, not refused, without --check
    assert "**`our_bug`: 1**" in report_file.read_text(encoding="utf-8")


# --- the review file's format, and what a spreadsheet does to it (gate fixes, 2026-10-05) ----------------------


def _filled(text: str, calls: dict[int, tuple[str, str, str]]) -> str:
    """`text` (a review file) with the calls written into the rows at those places, as a spreadsheet saves it."""
    rows = list(csv.DictReader(io.StringIO(text.removeprefix(BOM))))
    for n, call in calls.items():
        rows[n]["human_class"], rows[n]["reviewer_role"], rows[n]["note"] = call
    buffer = io.StringIO()
    buffer.write(BOM)
    writer = csv.DictWriter(buffer, REVIEW_COLUMNS, lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def test_review_csv_is_bom_and_crlf_and_a_non_ascii_title_survives_a_save(tmp_path: Path) -> None:
    review = review_rows([compare(QUERY, SET, corpus())])
    review[0] = ReviewRow(
        review[0].query_name, replace(review[0].row, title="Évaluer la confiance, 信頼"), UNRESOLVED
    )
    text = render_review(review, "v")
    assert text.startswith(BOM) and text.endswith("\r\n") and "\n" not in text.replace("\r\n", "")
    assert "Évaluer la confiance, 信頼" in text
    saved = tmp_path / "review.csv"
    saved.write_bytes(_filled(text, {0: ("full_text", "second reviewer", "lu: résumé")}).encode("utf-8"))
    calls = read_calls(saved, text, review)
    assert calls is not None and calls.calls == {0: Call("full_text", "second reviewer", "lu: résumé")}
    assert calls.roles == [("second reviewer", 1)]


def test_a_review_file_saved_in_a_legacy_encoding_is_refused_with_the_fix(tmp_path: Path) -> None:
    review = review_rows([compare(QUERY, SET, corpus())])
    review[0] = ReviewRow(
        review[0].query_name, replace(review[0].row, title="Évaluer la confiance"), UNRESOLVED
    )
    text = render_review(review, "v")
    saved = tmp_path / "review.csv"
    saved.write_bytes(
        _filled(text, {0: ("full_text", "second reviewer", "")}).removeprefix(BOM).encode("cp1252")
    )
    with pytest.raises(ValueError, match=r"review\.csv is not UTF-8: save it as CSV UTF-8"):
        read_calls(saved, text, review)
    assert human_calls(saved) == 1  # counted as filled: never overwritten on a guess
    (tmp_path / review_name(DAY)).write_bytes(saved.read_bytes())
    with pytest.raises(ValueError, match="holds 1 filled row"):
        write("r\n", text, tmp_path, DAY)


def test_a_cell_the_run_wrote_and_a_spreadsheet_rewrote_is_named(
    ran: tuple[list[str], Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    argv, _, rows_file = ran
    text = rows_file.read_bytes().decode("utf-8")
    rows = list(csv.reader(io.StringIO(text.removeprefix(BOM))))
    rows[2][REVIEW_COLUMNS.index("index_version")] = "1.23E+11"  # a spreadsheet reading an all-digit version
    rows[1][REVIEW_COLUMNS.index("human_class")], rows[1][REVIEW_COLUMNS.index("reviewer_role")] = (
        "full_text",
        "r",
    )
    buffer = io.StringIO()
    csv.writer(buffer, lineterminator="\r\n").writerows(rows)
    rows_file.write_bytes((BOM + buffer.getvalue()).encode("utf-8"))
    capsys.readouterr()
    assert main(argv) == 1
    assert "(line 3, column `index_version`)" in capsys.readouterr().err


def test_calls_are_read_back_when_a_cell_carries_the_injection_guard(
    data_dir: Path, inputs: tuple[Path, Path], tmp_path: Path
) -> None:
    ris, _ = inputs
    queries = tmp_path / "in" / "guarded.txt"
    queries.write_text(f"## -ablation\n{QUERY}\n", encoding="utf-8")  # a name a spreadsheet would run
    out = tmp_path / "guarded"
    argv = args(data_dir, out, ris, "--query-file", str(queries), "--check")
    assert main(argv) == 0
    rows_file = out / review_name(DAY)
    text = rows_file.read_bytes().decode("utf-8")
    assert "\r\n'-ablation," in text  # guarded as written
    unresolved = [
        n
        for n, r in enumerate(csv.DictReader(io.StringIO(text.removeprefix(BOM))))
        if r["row_kind"] == UNRESOLVED
    ]
    calls = dict.fromkeys(unresolved, ("full_text", "second reviewer", ""))
    calls[unresolved[1]] = ("out_of_scope", "second reviewer", "")  # set.ris#8, the coverage gap
    calls[unresolved[2]] = ("scholar_missed", "second reviewer", "")  # miss0001
    rows_file.write_bytes(_filled(text, calls).encode("utf-8"))
    assert main(argv) == 0
    report_text = (out / "2026-10-04-scholar-comparison.md").read_text(encoding="utf-8")
    assert "3 of its 4 rows have a call." in report_text
    assert "**Every disagreement classified: yes" in report_text


@pytest.mark.parametrize(
    ("key", "call", "message"),
    [
        (nid("miss0001"), "in_both", "`in_both` is a call about a record of the compared set"),
        (nid("miss0001"), "out_of_scope", "`out_of_scope` is a call about a record of the compared set"),
        ("set.ris#8", "in_both", "`in_both` needs the one index record the row is the same paper as"),
    ],
)
def test_a_verdict_on_a_row_it_cannot_apply_to_is_refused(
    ran: tuple[list[str], Path, Path], key: str, call: str, message: str, capsys: pytest.CaptureFixture[str]
) -> None:
    argv, report_file, rows_file = ran
    fill(rows_file, {key: (call, "second reviewer", "")})
    before = (report_file.read_bytes(), rows_file.read_bytes())
    capsys.readouterr()
    assert main(argv) == 1
    assert message in capsys.readouterr().err
    assert (report_file.read_bytes(), rows_file.read_bytes()) == before


def test_the_counts_after_the_calls_move_each_called_row_once() -> None:
    c = compare(QUERY, SET, corpus())
    review = review_rows([c])
    at = {x.row.op_id or x.row.scholar_key: n for n, x in enumerate(review)}
    gap = at["set.ris#8"]
    # the coverage-gap row names the result's only extra record as the one same-title record: `in_both` pairs them
    review[gap] = ReviewRow(
        review[gap].query_name, replace(review[gap].row, near=(nid("miss0001"),)), UNRESOLVED
    )
    calls = HumanCalls("f.csv", "0" * 64, {
        gap: Call(IN_BOTH, "second reviewer", ""),
        at[nid("noab0001")]: Call("out_of_scope", "second reviewer", ""),
    })  # fmt: skip
    after = after_calls(c, review, calls)
    assert (c.scholar_in_scope, len(c.kept)) == (8, 1)
    assert (after.in_scope, after.both) == (7, 2)  # one record out of the set, one more in both
    assert "coverage_gap" not in after.scholar and "unsettled" not in after.scholar
    assert (
        dict(after.result) == {}
    )  # the paired record left the rows only in the result: the two are one paper
    assert dict(c.counts("openproceedings")) == {"scholar_missed": 1}  # the automation's counts are untouched
    alone = HumanCalls("f.csv", "0" * 64, {at[nid("noab0001")]: Call(IN_BOTH, "second reviewer", "")})
    assert after_calls(c, review, alone).result == {"scholar_missed": 1}  # its own record is no extra row


def test_the_report_prints_the_counts_after_the_calls_beside_the_automations(
    ran: tuple[list[str], Path, Path],
) -> None:
    argv, report_file, rows_file = ran
    fill(
        rows_file, {**ALL_CALLED, nid("noab0001"): (IN_BOTH, "AI assistant, not an independent reviewer", "")}
    )
    assert main(argv) == 0
    text = report_file.read_text(encoding="utf-8")
    for line in (
        "| Scholar set, in scope | 8 | 7 |",
        "| in both | 1 | 2 |",
        "| only in the Scholar set: `unsettled` | 1 | 0 |",
        "| only in the Scholar set: `coverage_gap` | 1 | 0 |",
    ):
        assert line in text.splitlines(), line
    assert "made as: `second reviewer` (2 rows); `AI assistant, not an independent reviewer` (1 row)" in text
    assert "- **After the calls** (section Human calls, made as: " in text
    assert "1 of 7 (14.3%) `full_text`" in text
