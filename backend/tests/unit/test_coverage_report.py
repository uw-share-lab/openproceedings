"""`op eval coverage` (TASK-054, spec 07 §C, coverage-reporting skill): the dated coverage report and the M4
gate verdict, rendered from exactly what `GET /coverage` serves."""

from __future__ import annotations

import json
import re
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st
from openproceedings.cli import main
from openproceedings.coverage import breakdown
from openproceedings.engine.index import build_index
from openproceedings.eval.coverage_report import (
    AcceptedException,
    Meta,
    Unresolved,
    Verdict,
    gate,
    load_cause_file,
    load_unresolved,
    missing_decisions,
    render,
    stale_exceptions,
)
from openproceedings.ingest.dedup import Conflict, DedupResult
from openproceedings.ingest.record import PaperRecord
from openproceedings.ingest.snapshot import render as render_snapshot
from openproceedings.ingest.sources.common import ListingReport
from openproceedings.official_counts import OfficialCount, within_gate

from tests.unit.ingest.test_dedup import paper

BUILT = datetime(2026, 9, 29, tzinfo=UTC)
ACCESSED = date(2026, 9, 27)


def official(n: int) -> OfficialCount:
    return OfficialCount(n, "papers on the accepted list", "https://example.org/list", ACCESSED)


# ICLR 2013 main: 24 of 24 (✓); ICLR 2014 main: 30 of 35 (✗, −14.3%); ICLR 2015 main: no records (a gap);
# ICLR 2014 workshop and ICLR 2016 workshop: not gated; ICML 2020 main: records but no official count (no source)
TABLE = {("ICLR", 2013, "main"): official(24), ("ICLR", 2014, "main"): official(35),
         ("ICLR", 2015, "main"): official(31)}  # fmt: skip


def corpus() -> list[PaperRecord]:
    def many(venue: str, year: int, n: int, track: str = "main") -> list[PaperRecord]:
        return [paper(f"{venue[:2]}{year}x{i:04d}", f"Paper {venue} {year} {track} {i}", venue=venue, year=year,
                      track=track, abstract=None if i == 0 else "An abstract.") for i in range(n)]  # fmt: skip

    return (
        many("ICLR", 2013, 24)
        + many("ICLR", 2014, 30)
        + [
            paper(f"IC2014w{i:04d}", f"Poster {i}", venue="ICLR", year=2014, track="workshop")
            for i in range(6)
        ]
        + many("ICLR", 2016, 3, "workshop")
        + many("ICML", 2020, 2)
    )


def listing(skipped: dict[str, int], stated: int | None = 174) -> ListingReport:
    r = ListingReport("neurips_proceedings", "NeurIPS", 2021, "https://example.org/2021", "confirm", stated)
    r.listed = 174
    r.skipped.update(skipped)
    return r


def manifest_of(records: list[PaperRecord], crawls: list[Any] | None = None) -> dict[str, Any]:
    data = render_snapshot(DedupResult(tuple(records), (), ()), [], BUILT, crawls or [])
    return json.loads(data["manifest.json"])


META = Meta(date=date(2026, 9, 29), index_version="abc123def456", sources_sha256="f" * 64, causes_sha256=None,
            command="op eval coverage")  # fmt: skip


def report(
    crawls: list[Any] | None = None,
    causes: dict[tuple[str, int, str], str] | None = None,
    sources: dict[str, Any] | None = None,
) -> str:
    manifest = manifest_of(corpus(), crawls)
    manifest["sources"].update(sources or {})  # OpenReview crawl reports, in their manifest shape
    cov = breakdown(manifest, "2026-09-29-test", official=TABLE)
    return render(cov, manifest, META, official=TABLE, causes=causes or {})


def row(text: str, venue: str, year: int, track: str) -> str:
    """The table row for one cell (the report has one table per venue, rows start `| <year> | <track> |`)."""
    section = text.split(f"## {venue}\n", 1)[1].split("\n## ", 1)[0]
    [line] = [ln for ln in section.splitlines() if ln.startswith(f"| {year} | {track} |")]
    return line


def test_a_cell_within_one_percent_passes_and_one_outside_fails() -> None:
    text = report()
    assert "✓" in row(text, "ICLR", 2013, "main") and "| 24 | 24 | 0 | 0.0% |" in row(
        text, "ICLR", 2013, "main"
    )
    assert "✗" in row(text, "ICLR", 2014, "main") and "| 30 | 35 | −5 | −14.3% |" in row(
        text, "ICLR", 2014, "main"
    )


def test_a_gated_official_cell_with_no_records_is_a_reported_gap_never_a_silent_zero() -> None:
    text = report()
    line = row(text, "ICLR", 2015, "main")
    assert "| 0 | 31 | −31 | −100.0% |" in line and "✗ gap" in line and line.endswith("| none (no records) |")


def test_cells_outside_the_gate_are_reported_as_such() -> None:
    text = report()
    assert "not gated" in row(text, "ICLR", 2016, "workshop")
    assert "no source" in row(text, "ICML", 2020, "main")


def test_the_verdict_counts_every_gated_cell_including_gaps() -> None:
    manifest = manifest_of(corpus())
    verdict = gate(breakdown(manifest, "x", official=TABLE), TABLE)
    assert (verdict.gated, verdict.passing, [k for k, _ in verdict.failing]) == (
        3, 1, [("ICLR", 2014, "main"), ("ICLR", 2015, "main")])  # fmt: skip
    assert not verdict.passed
    assert "**M4 gate: FAIL** — 1 of 3 gated cells within ±1%; 1 gap" in report()


def test_every_failing_cell_has_a_cause_note_unclassified_until_one_is_given() -> None:
    text = report()
    assert "- ICLR 2014 main: **unclassified**" in text and "- ICLR 2015 main: **unclassified**" in text
    text = report(causes={("ICLR", 2014, "main"): "crawl gap: 5 papers missing from the listing"})
    assert "- ICLR 2014 main: crawl gap: 5 papers missing from the listing" in text


def test_the_header_names_everything_the_numbers_depend_on() -> None:
    text = report()
    manifest = manifest_of(corpus())
    for fact in ("2026-09-29", manifest["snapshot_hash"], "abc123def456", "f" * 64, "`op eval coverage`"):
        assert fact in text


def test_per_cell_columns_missing_abstracts_and_statuses_indexed() -> None:
    line = row(report(), "ICLR", 2013, "main")
    # one title-only record, no unknown track; ICLR on OpenReview holds every status (decision-012)
    assert [c.strip() for c in line.strip("|").split("|")][-4:] == [
        "1", "0", "0", "accepted, rejected, withdrawn, desk_rejected, unknown"]  # fmt: skip


def test_listings_that_skipped_entries_are_listed_with_their_reasons() -> None:
    text = report(crawls=[listing({"duplicate": 54})])
    assert (
        "| neurips_proceedings | NeurIPS | 2021 | https://example.org/2021 | 174 | 174 | yes | duplicate 54 |"
        in text
    )
    assert "| neurips_proceedings |" not in report(crawls=[listing({})]).split("## Proceedings listings")[1]


def test_a_listing_whose_count_disagrees_is_listed_even_with_no_skips() -> None:
    wrong = listing({}, stated=175)  # 174 listed, the page says 175
    assert "| 174 | 175 | **no** | — |" in report(crawls=[wrong])


def crawl(**kw: Any) -> dict[str, Any]:
    base = {"api": "v1", "venue": "ICLR", "year": 2017, "complete": True, "notes_read": 651, "imported": 651,
            "skipped": {"not_submission": 12}, "unmapped": {}, "coverage_gaps": []}  # fmt: skip
    return {**base, **kw}


def test_openreview_crawls_that_need_attention_are_listed_and_reply_notes_are_not_skips() -> None:
    quiet = report(sources={"openreview_v1": {"crawls": [crawl()]}})
    assert "None: every crawl is complete" in quiet  # only `not_submission` skips: routine
    text = report(sources={
        "openreview_v1": {"crawls": [crawl(complete=False, coverage_gaps=["ICLR.cc/2017/workshop"],
                                           unmapped={"Submitted to X": 3}, skipped={"no_title": 2, "not_submission": 9})]},
        "openreview_v2": {"crawls": [crawl(api="v2", year=2024, skipped_groups={"ICLR.cc/2024/Tiny": "x"})]},
    })  # fmt: skip
    assert (
        "| openreview_v1 | ICLR | 2017 | 651 | 651 | no_title 2 | **incomplete**; coverage gaps 1; unmapped 3 |"
        in text
    )
    assert "| openreview_v2 | ICLR | 2024 | 651 | 651 | — | skipped groups: x 1 |" in text


def test_routine_v2_group_skips_are_not_attention_but_a_venue_without_submissions_is() -> None:
    routine = {"a": "proposal", "b": "container"}
    quiet = report(sources={"openreview_v2": {"crawls": [crawl(api="v2", skipped_groups=routine)]}})
    assert "None: every crawl is complete" in quiet
    odd = report(sources={"openreview_v2": {"crawls": [crawl(api="v2", skipped_groups={**routine,
                                                                                         "c": "not_a_v2_venue", "d": "no_submission_venue_id"})]}})  # fmt: skip
    assert "skipped groups: no_submission_venue_id 1, not_a_v2_venue 1 |" in odd


def test_a_crawl_with_conflicts_needs_attention() -> None:
    assert "| conflicts 2 |" in report(sources={"openreview_v1": {"crawls": [crawl(conflicts=2)]}})


def test_a_gap_in_a_venue_year_with_other_records_shows_its_statuses() -> None:
    table = {**TABLE, ("ICLR", 2016, "main"): official(80)}  # ICLR 2016 has workshop records, no main
    manifest = manifest_of(corpus())
    text = render(breakdown(manifest, "x", official=table), manifest, META, official=table)
    line = row(text, "ICLR", 2016, "main")
    assert "✗ gap" in line and line.endswith(
        "| 0 | 0 | accepted, rejected, withdrawn, desk_rejected, unknown |"
    )


def test_ris_import_reports_are_not_listings() -> None:
    assert "None: every listing made a record" in report(
        sources={"ris": [{"file": "mended.ris", "skipped": {"x": 1}}]}
    )


def test_big_deltas_have_thousands_separators_and_a_tiny_negative_rounds_to_zero() -> None:
    from openproceedings.eval.coverage_report import _pct, _signed

    assert (_signed(-1095), _signed(2334), _pct(-0.04), _pct(-100.0)) == (
        "−1,095",
        "2,334",
        "0.0%",
        "−100.0%",
    )


def test_stale_cause_notes_are_shown_not_dropped() -> None:
    text = report(causes={("ICLR", 2013, "main"): "was a crawl gap", ("ICLR", 2014, "main"): "crawl gap"})
    assert "- ICLR 2013 main: was a crawl gap" in text.split("not failing")[1]  # ICLR 2013 passes now
    assert "- ICLR 2014 main: crawl gap" in text.split("not failing")[0]


def test_the_header_names_the_causes_file_hash() -> None:
    from dataclasses import replace

    manifest = manifest_of(corpus())
    cov = breakdown(manifest, "x", official=TABLE)
    assert "- Cause notes: none" in render(cov, manifest, META, official=TABLE)
    with_causes = render(cov, manifest, replace(META, causes_sha256="c" * 64), official=TABLE)
    assert f"`docs/results/coverage-causes.toml`, sha256 `{'c' * 64}`" in with_causes


def test_totals() -> None:
    assert "| 65 | 10 | 0 | 0 |" in report()  # records, missing abstracts, unknown track, unknown status


# --- the command -----------------------------------------------------------------------------------------


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    root = tmp_path / "data"
    snap = root / "snapshots" / "2026-09-29-test"
    snap.mkdir(parents=True)
    for name, data in render_snapshot(DedupResult(tuple(corpus()), (), ()), [], BUILT).items():
        (snap / name).write_bytes(data)
    build_index(snap, root / "indexes")
    return root


def index_name(data_dir: Path) -> str:
    return next(p.name for p in (data_dir / "indexes").iterdir() if not p.name.startswith("."))


def test_op_eval_coverage_writes_the_dated_report(data_dir: Path, tmp_path: Path) -> None:
    out = tmp_path / "results"
    args = [
        "--data-dir",
        str(data_dir),
        "eval",
        "coverage",
        "--index",
        index_name(data_dir),
        "--out",
        str(out),
    ]
    assert main(args) == 0
    [written] = list(out.iterdir())
    assert written.name.endswith("-coverage.md")
    text = written.read_text(encoding="utf-8")
    assert index_name(data_dir) in text and "M4 gate: FAIL" in text  # the real table: most cells are gaps
    assert main([*args, "--check"]) == 1  # --check: the gate verdict as the exit status


def eval_args(data_dir: Path, out: Path, *extra: str) -> list[str]:
    return ["--data-dir", str(data_dir), "eval", "coverage", "--index", index_name(data_dir), "--out", str(out),
            *extra]  # fmt: skip


def test_date_is_the_report_name_and_a_bad_one_is_a_usage_error(data_dir: Path, tmp_path: Path) -> None:
    assert main(eval_args(data_dir, tmp_path / "r", "--date", "2026-10-01")) == 0
    assert (tmp_path / "r" / "2026-10-01-coverage.md").is_file()
    assert main(eval_args(data_dir, tmp_path / "r", "--date", "Oct 1")) == 1  # refused (a usage error)


def test_a_same_day_report_is_replaced_whole(
    data_dir: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "r"
    main(eval_args(data_dir, out, "--date", "2026-10-01"))
    (out / "2026-10-01-coverage.md").write_text("stale")
    capsys.readouterr()
    assert main(eval_args(data_dir, out, "--date", "2026-10-01")) == 0
    assert (out / "2026-10-01-coverage.md").read_text().startswith("# Coverage report, 2026-10-01")
    logged = [json.loads(ln) for ln in capsys.readouterr().err.splitlines() if ln.startswith("{")]
    [written] = [e for e in logged if e.get("event") == "coverage_report_written"]  # one INFO line per run
    assert (written["replaced"], written["gated"]) == (True, 44)  # the real official table's gated cells
    assert sorted(p.name for p in out.iterdir()) == ["2026-10-01-coverage.md"]  # no temp file left


def test_outside_a_checkout_it_is_a_usage_error(
    data_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from openproceedings import cli

    monkeypatch.setattr(cli, "_repo_root", lambda: None)
    assert main(eval_args(data_dir, tmp_path / "r")) == 1
    assert not (tmp_path / "r").exists()


def test_a_malformed_causes_file_is_refused_before_anything_is_written(
    data_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from openproceedings import cli

    root = tmp_path / "checkout"
    (root / "docs" / "results").mkdir(parents=True)
    (root / "docs" / "results" / "coverage-sources.md").write_text("| venue |\n")
    (root / "docs" / "results" / "coverage-causes.toml").write_text('["ICLR 2014"]\ncause = "x"\n')
    monkeypatch.setattr(cli, "_repo_root", lambda: root)
    assert main(eval_args(data_dir, tmp_path / "r")) == 1
    err = capsys.readouterr().err
    assert "is not" in err and not (tmp_path / "r").exists()
    [refused] = [e for e in map(json.loads, (ln for ln in err.splitlines() if ln.startswith("{")))
                 if e.get("event") == "cli_refused"]  # fmt: skip
    assert (refused["command"], refused["error"]) == ("eval", "ValueError")


def test_a_missing_sources_table_is_refused_before_anything_is_written(
    data_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from openproceedings import cli

    (tmp_path / "checkout" / "docs" / "results").mkdir(parents=True)  # no coverage-sources.md
    monkeypatch.setattr(cli, "_repo_root", lambda: tmp_path / "checkout")
    assert main(eval_args(data_dir, tmp_path / "r")) == 1 and not (tmp_path / "r").exists()


def test_unknown_track_records_are_counted_per_venue_year_and_never_folded_into_main() -> None:
    records = [*corpus(), paper("IC2013unk1", "An unplaced paper", venue="ICLR", year=2013, track="unknown")]
    manifest = manifest_of(records)
    text = render(breakdown(manifest, "x", official=TABLE), manifest, META, official=TABLE)
    main_row = [c.strip() for c in row(text, "ICLR", 2013, "main").strip("|").split("|")]
    assert main_row[2] == "24" and main_row[-3] == "1"  # main stays 24 (✓); the venue-year's unknown is 1
    assert "not gated" in row(text, "ICLR", 2013, "unknown")


def test_causes_load_from_toml_and_an_empty_cause_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "coverage-causes.toml"
    assert load_cause_file(path) == ({}, {})  # no file: no causes, so every failing cell reads unclassified
    path.write_text('["NeurIPS 2021 datasets_benchmarks"]\ncause = "dedup: ids collided (TASK-118)"\n')
    assert load_cause_file(path) == (
        {("NeurIPS", 2021, "datasets_benchmarks"): "dedup: ids collided (TASK-118)"}, {})  # fmt: skip
    path.write_text('["ICLR 2014 main"]\ncause = "  "\n')
    with pytest.raises(ValueError, match="needs a non-empty cause"):
        load_cause_file(path)
    path.write_text('["ICLR 2014 main"]\ncause = "crawl gap\\nmore"\n')  # a TOML \n escape: a real newline
    with pytest.raises(ValueError, match="control characters"):
        load_cause_file(path)
    for heading in ("ICLR 2014", "ICLR twenty main", "Iclr 2014 main", "ICLR 2014 mainn"):
        path.write_text(f'["{heading}"]\ncause = "x"\n')
        with pytest.raises(ValueError, match="is not"):
            load_cause_file(path)


# --- owner-accepted exceptions ------------------------------------------------------------------------------


def ids(n: int, prefix: str = "op:iclr:2014:IC2014w") -> tuple[str, ...]:
    """`n` corpus record ids; by default ICLR 2014 workshop records: the ICLR 2014 main cell's venue-year,
    outside the cell."""
    return tuple(f"{prefix}{i:04d}" for i in range(n))


def accepted(
    indexed: int = 30,
    official: int = 35,
    decision: str = "decision-016",
    papers: tuple[str, ...] | None = None,
    reason: str = "The list and OpenReview disagree.",
) -> AcceptedException:
    return AcceptedException(indexed, official, reason, ids(abs(official - indexed)) if papers is None else papers,
                             "project owner", date(2026, 9, 29), decision)  # fmt: skip


ICLR14 = ("ICLR", 2014, "main")  # 30 indexed of 35 official in the test corpus: outside ±1%


def locate_in(records: list[PaperRecord]) -> Any:
    cells = {r.id: (r.venue, r.year, r.track, r.status) for r in records}
    return cells.get


LOCATE = locate_in(corpus())


def verdict_with(exceptions: dict[tuple[str, int, str], AcceptedException]) -> Verdict:
    return gate(breakdown(manifest_of(corpus()), "x", official=TABLE), TABLE, exceptions, LOCATE)


def report_with(
    exceptions: dict[tuple[str, int, str], AcceptedException],
    causes: dict[tuple[str, int, str], str] | None = None,
) -> str:
    manifest = manifest_of(corpus())
    cov = breakdown(manifest, "x", official=TABLE)
    return render(
        cov, manifest, META, official=TABLE, causes=causes or {}, exceptions=exceptions, locate=LOCATE
    )


def test_an_exception_matching_the_counts_exactly_passes_its_cell() -> None:
    v = verdict_with({ICLR14: accepted()})
    assert v.accepted == (ICLR14,) and ICLR14 not in {k for k, _ in v.failing}
    assert v.passing == 1  # still one cell *within ±1%*: an accepted cell is counted apart
    only = {k: TABLE[k] for k in (("ICLR", 2013, "main"), ICLR14)}  # no gap: the gate passes outright
    assert gate(
        breakdown(manifest_of(corpus()), "x", official=only), only, {ICLR14: accepted()}, LOCATE
    ).passed
    # unverified (no `locate`): never passes
    assert not gate(breakdown(manifest_of(corpus()), "x", official=only), only, {ICLR14: accepted()}).passed


@pytest.mark.parametrize(
    ("papers", "problem"),
    [
        ((*ids(4), "op:iclr:2014:nosuchpaper"), "paper op:iclr:2014:nosuchpaper is not in the snapshot"),
        ((*ids(4), "op:iclr:2013:IC2013x0000"),
         "paper op:iclr:2013:IC2013x0000 is from ICLR 2013, not this cell's venue-year"),
        ((*ids(4), "op:icml:2020:IC2020x0000"),
         "paper op:icml:2020:IC2020x0000 is from ICML 2020, not this cell's venue-year"),
        ((*ids(4), "op:iclr:2014:IC2014x0007"),
         "paper op:iclr:2014:IC2014x0007 is counted in the cell, so it is not one of the missing papers"),
        (ids(4), "it names 4 paper(s) for a gap of 5"),
        (ids(6), "it names 6 paper(s) for a gap of 5"),
    ],
)  # fmt: skip
def test_counts_that_match_with_papers_that_are_not_the_gap_fail_the_cell(
    papers: tuple[str, ...], problem: str
) -> None:
    ex = {ICLR14: accepted(papers=papers)}
    v = verdict_with(ex)
    assert (ICLR14, "drifted") in v.failing and not v.accepted
    text = report_with(ex, causes={ICLR14: "crawl gap"})
    assert (
        f"- ICLR 2014 main: crawl gap **The accepted exception (decision-016) does not hold:** {problem}."
        in text
    )
    assert "✗" in row(text, "ICLR", 2014, "main")


def test_an_over_count_exception_names_papers_inside_the_cell() -> None:
    table = {ICLR14: official(28)}  # 30 indexed: two extra papers
    cov = breakdown(manifest_of(corpus()), "x", official=table)
    inside = ids(2, "op:iclr:2014:IC2014x")
    assert gate(cov, table, {ICLR14: accepted(30, 28, papers=inside)}, LOCATE).accepted == (ICLR14,)
    v = gate(cov, table, {ICLR14: accepted(30, 28)}, LOCATE)  # two ICLR 2014 workshop records: not the extras
    assert v.failing == ((ICLR14, "drifted"),) and "is not counted in the cell" in dict(v.notes)[ICLR14]


@pytest.mark.parametrize(("indexed", "official"), [(29, 35), (31, 35), (30, 36), (30, 34)])
def test_an_exception_whose_counts_drifted_fails_the_cell_again(indexed: int, official: int) -> None:
    v = verdict_with({ICLR14: accepted(indexed, official)})
    assert (ICLR14, "drifted") in v.failing and not v.accepted and not v.passed
    text = report_with({ICLR14: accepted(indexed, official)}, causes={ICLR14: "crawl gap"})
    assert (f"- ICLR 2014 main: crawl gap **The accepted exception (decision-016) no longer matches:** accepted "
            f"{indexed} indexed vs {official} official, now 30 vs 35.") in text  # fmt: skip
    assert "✗" in row(text, "ICLR", 2014, "main") and "accepted exception" not in row(
        text, "ICLR", 2014, "main"
    )


def test_an_exception_never_covers_a_gap() -> None:
    ex = {("ICLR", 2015, "main"): accepted(30, 31)}  # the cell holds no records
    v = verdict_with(ex)
    assert (("ICLR", 2015, "main"), "gap") in v.failing and v.gaps == 1 and not v.accepted
    text = report_with(ex, causes={("ICLR", 2015, "main"): "crawl gap"})
    assert ("- ICLR 2015 main: crawl gap **The accepted exception (decision-016) does not apply:** the cell holds "
            "no records, and a gap is never accepted.") in text  # fmt: skip
    assert "✗ gap" in row(text, "ICLR", 2015, "main")


@given(st.integers(min_value=0, max_value=200))
def test_an_exception_passes_its_cell_exactly_when_the_observed_count_is_the_accepted_one(
    observed: int,
) -> None:
    table = {ICLR14: official(35)}
    records = [paper(f"IC2014x{i:04d}", f"Paper {i}", venue="ICLR", year=2014) for i in range(observed)]
    # the five accepted papers: ICLR 2014 workshop records (so a snapshot is never empty, either)
    records += [
        paper(f"IC2014w{i:04d}", f"Poster {i}", venue="ICLR", year=2014, track="workshop") for i in range(5)
    ]
    ex = accepted(30, 35, papers=ids(5, "op:iclr:2014:IC2014w"))
    v = gate(breakdown(manifest_of(records), "x", official=table), table, {ICLR14: ex}, locate_in(records))
    within = observed > 0 and within_gate(observed, 35)
    assert v.passed == (within or observed == 30)
    assert v.accepted == ((ICLR14,) if observed == 30 else ())
    assert stale_exceptions({ICLR14: ex}, v) == ([ICLR14] if within else [])


def test_the_report_lists_every_accepted_exception_and_marks_its_cell() -> None:
    text = report_with(
        {ICLR14: accepted()}, causes={ICLR14: "source definition: one paper is a workshop poster"}
    )
    assert "✓ accepted exception" in row(text, "ICLR", 2014, "main")
    assert "; 1 gap; 1 owner-accepted exception." in text
    section = text.split("## Owner-accepted exceptions\n", 1)[1].split("\n## ", 1)[0]
    assert ("- ICLR 2014 main: 30 indexed vs 35 official (Δ −5), accepted by the project owner on 2026-09-29 "
            "(decision-016). The list and OpenReview disagree. Papers: op:iclr:2014:IC2014w0000, "
            "op:iclr:2014:IC2014w0001, op:iclr:2014:IC2014w0002, op:iclr:2014:IC2014w0003, "
            "op:iclr:2014:IC2014w0004. Cause: source definition: one paper is a workshop poster") in section  # fmt: skip
    # a reason without a closing period still ends its sentence before "Papers:"
    unended = report_with({ICLR14: accepted(reason="The list and OpenReview disagree")})
    assert "The list and OpenReview disagree. Papers: op:iclr:2014:IC2014w0000" in unended
    assert "- ICLR 2014 main" not in text.split("## Causes of every failing cell")[1].split("## Owner")[0]
    assert "not failing" not in text  # its cause note is in use, not stale
    none = report_with({})
    assert (
        "; 0 owner-accepted exceptions." in none
        and "None: no failing cell passes as an owner-accepted" in none
    )


def test_a_stale_exception_is_reported_not_dropped() -> None:
    exceptions = {("ICLR", 2013, "main"): accepted(23, 24), ("NeurIPS", 2020, "main"): accepted(9, 10)}
    v = verdict_with(exceptions)  # ICLR 2013 main is 24 of 24; NeurIPS 2020 main is not a gated official cell
    assert stale_exceptions(exceptions, v) == [("ICLR", 2013, "main"), ("NeurIPS", 2020, "main")]
    assert not v.accepted
    text = report_with(exceptions)
    stale = text.split("Accepted exceptions for cells that are within ±1% or not gated", 1)[1]
    assert stale.startswith(" (remove them from coverage-causes.toml; `op eval coverage --check` fails until")
    assert (
        "- ICLR 2013 main: 23 indexed vs 24 official" in stale and "- NeurIPS 2020 main: 9 indexed" in stale
    )


EXCEPTION_TOML = """["ICLR 2013 main"]
cause = "source definition: one paper is a workshop poster on OpenReview"

["ICLR 2013 main".accepted]
indexed = 23
official = 24
reason = "On the official list; OpenReview decides it a workshop poster."
papers = ["op:iclr:2013:11y_SldoumvZl"]
accepted_by = "project owner"
accepted_on = 2026-09-29
decision = "decision-016"
"""


def test_an_exception_loads_from_toml(tmp_path: Path) -> None:
    path = tmp_path / "coverage-causes.toml"
    path.write_text(EXCEPTION_TOML)
    causes, exceptions = load_cause_file(path)
    assert causes == {
        ("ICLR", 2013, "main"): "source definition: one paper is a workshop poster on OpenReview"
    }
    assert exceptions == {("ICLR", 2013, "main"): AcceptedException(
        23, 24, "On the official list; OpenReview decides it a workshop poster.", ("op:iclr:2013:11y_SldoumvZl",),
        "project owner", date(2026, 9, 29), "decision-016")}  # fmt: skip


@pytest.mark.parametrize(
    ("old", "new", "error"),
    [
        ('decision = "decision-016"\n', 'decision = "decision-016"\nnote = "x"\n', "unknown keys: note"),
        ('decision = "decision-016"\n', "", "missing: decision"),
        ('papers = ["op:iclr:2013:11y_SldoumvZl"]\n', "", "missing: papers"),
        ("indexed = 23", 'indexed = "23"', "indexed must be an integer"),
        ("indexed = 23", "indexed = true", "indexed must be an integer"),
        ("indexed = 23", "indexed = 0", "at least 1"),
        ("official = 24", "official = 0", "at least 1"),
        ("indexed = 23", "indexed = 24", "within ±1%"),
        ("accepted_on = 2026-09-29", 'accepted_on = "2026-09-29"', "accepted_on must be a date"),
        ("accepted_on = 2026-09-29", "accepted_on = 2026-09-29T10:00:00Z", "accepted_on must be a date"),
        ('papers = ["op:iclr:2013:11y_SldoumvZl"]', "papers = []", "papers must be a non-empty list"),
        ('papers = ["op:iclr:2013:11y_SldoumvZl"]', 'papers = [" "]', "papers must be a non-empty list"),
        ('papers = ["op:iclr:2013:11y_SldoumvZl"]', 'papers = ["11y_SldoumvZl"]', "list of record ids"),
        ('papers = ["op:iclr:2013:11y_SldoumvZl"]', 'papers = ["op:iclr:2013:a", "op:iclr:2013:a"]',
         "lists a record twice"),
        ('accepted_by = "project owner"', 'accepted_by = "Jane Doe"', "accepted_by must be a role: project owner"),
        ('reason = "On the', 'reason = "Two lines\\nOn the', "reason must not contain control characters"),
        ('reason = "On the', 'reason = "A tab\\tOn the', "reason must not contain control characters"),
        ('accepted_by = "project owner"', 'accepted_by = "project owner\\n"', "control characters"),
        ('reason = "On the official list; OpenReview decides it a workshop poster."', 'reason = " "', "reason must not be empty"),
        ('decision = "decision-016"', 'decision = "the owner said so"', "decision record id"),
        ('cause = "source definition: one paper is a workshop poster on OpenReview"\n', "",
         "needs a non-empty cause"),
        ('cause = "source', 'extra = 1\ncause = "source', "unknown keys: extra"),
        ('["ICLR 2013 main".accepted]', '["ICLR 2013 main".exception]', "unknown keys: exception"),
    ],
)  # fmt: skip
def test_a_malformed_exception_is_refused(tmp_path: Path, old: str, new: str, error: str) -> None:
    path = tmp_path / "coverage-causes.toml"
    assert old in EXCEPTION_TOML
    path.write_text(EXCEPTION_TOML.replace(old, new, 1))
    with pytest.raises(ValueError, match=re.escape(error)):
        load_cause_file(path)


def test_the_committed_causes_file_loads_and_each_exception_has_its_decision_record() -> None:
    root = Path(__file__).resolve().parents[3]
    _, exceptions = load_cause_file(root / "docs" / "results" / "coverage-causes.toml")
    assert exceptions[("ICLR", 2013, "main")].matches(23, 24)  # decision-016
    assert missing_decisions(exceptions, root / "backlog" / "decisions") == []
    assert missing_decisions(exceptions, root / "docs") == ["decision-016"]


def checkout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, table: dict[Any, OfficialCount]) -> Path:
    """A checkout with a sources table and decision-016's record, gating on `table` (the real table's other
    gated cells are gaps in this corpus)."""
    from openproceedings import cli

    root = tmp_path / "checkout"
    (root / "docs" / "results").mkdir(parents=True)
    (root / "docs" / "results" / "coverage-sources.md").write_text("| venue |\n")
    (root / "backlog" / "decisions").mkdir(parents=True)
    (root / "backlog" / "decisions" / "decision-016 - An exception.md").write_text(
        "---\nid: decision-016\n---\n"
    )
    monkeypatch.setattr(cli, "_repo_root", lambda: root)
    monkeypatch.setattr(cli, "_official_table", lambda: table)
    return root


def exception_toml(cell: str, indexed: int, official: int, papers: tuple[str, ...]) -> str:
    return (EXCEPTION_TOML.replace("ICLR 2013", cell).replace("= 23", f"= {indexed}")
            .replace("= 24", f"= {official}")
            .replace('["op:iclr:2013:11y_SldoumvZl"]', json.dumps(list(papers))))  # fmt: skip


def test_op_eval_coverage_check_passes_on_a_matched_exception_and_names_it(
    data_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = checkout(tmp_path, monkeypatch, {("ICLR", 2013, "main"): official(24), ICLR14: official(35)})
    causes = root / "docs" / "results" / "coverage-causes.toml"
    causes.write_text(exception_toml("ICLR 2014", 30, 35, ids(5)))
    capsys.readouterr()
    assert main(eval_args(data_dir, tmp_path / "r", "--check")) == 0
    [report_file] = list((tmp_path / "r").iterdir())
    assert "**M4 gate: PASS** — 1 of 2 gated cells within ±1%; 0 gaps; 1 owner-accepted exception." in (
        report_file.read_text(encoding="utf-8"))  # fmt: skip
    err = capsys.readouterr().err
    assert (
        "ICLR 2014 main (accepted exception, decision-016)" in err and "1 owner-accepted exception(s)" in err
    )
    [written] = [json.loads(ln) for ln in err.splitlines() if '"coverage_report_written"' in ln]
    assert (written["accepted_exceptions"], written["stale_exceptions"]) == (1, 0)
    causes.write_text(causes.read_text().replace("indexed = 30", "indexed = 29"))  # the count drifted
    assert main(eval_args(data_dir, tmp_path / "r", "--check")) == 1
    assert "ICLR 2014 main (drifted)" in capsys.readouterr().err
    # the counts match, but one paper is not in the snapshot: checked against the index's own records
    causes.write_text(exception_toml("ICLR 2014", 30, 35, (*ids(4), "op:iclr:2013:nosuchpaper")))
    assert main(eval_args(data_dir, tmp_path / "r", "--check")) == 1
    assert "ICLR 2014 main (drifted)" in capsys.readouterr().err
    assert "paper op:iclr:2013:nosuchpaper is not in the snapshot" in report_file.read_text(encoding="utf-8")


def test_a_stale_exception_fails_check(
    data_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = checkout(tmp_path, monkeypatch, {("ICLR", 2013, "main"): official(24)})  # 24 of 24: passes
    causes = root / "docs" / "results" / "coverage-causes.toml"
    causes.write_text(exception_toml("ICLR 2013", 23, 24, ("op:iclr:2016:IC2016x0000",)))
    capsys.readouterr()
    assert main(eval_args(data_dir, tmp_path / "r")) == 0  # without --check: reported, exit 0
    assert main(eval_args(data_dir, tmp_path / "r", "--check")) == 1
    err = capsys.readouterr().err
    assert "M4 gate: PASS" in err and "--check: 1 stale accepted exception(s)" in err
    assert "coverage-causes.toml: [ICLR 2013 main.accepted] is not failing; remove the exception" in err
    [report_file] = list((tmp_path / "r").iterdir())
    assert "`op eval coverage --check` fails until they are removed" in report_file.read_text(
        encoding="utf-8"
    )


def test_an_exception_without_its_decision_record_is_refused_before_anything_is_written(
    data_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = checkout(tmp_path, monkeypatch, {ICLR14: official(35)})
    (root / "docs" / "results" / "coverage-causes.toml").write_text(
        exception_toml("ICLR 2014", 30, 35, ids(5)).replace("decision-016", "decision-999")
    )
    assert main(eval_args(data_dir, tmp_path / "r", "--check")) == 1
    assert "no decision record for decision-999" in capsys.readouterr().err
    assert not (tmp_path / "r").exists()


# --- unresolved records (spec 07 §C, TASK-113) ----------------------------------------------------------------

V1 = "unresolved:openreview_v1"
STATUS_ROW = Unresolved(
    "op:iclr:2014:IC2014x0001", "status", "withdrawn (invitation=X)", "accepted (content.venue=Y)", V1
)
TRACK_ROW = Unresolved(
    "op:iclr:2014:IC2014x0002", "track", "main (invitation=X)", "workshop (venueid=A|B)", V1
)
GONE_ROW = Unresolved("op:iclr:2014:NotHere2014", "status", "a", "b", V1)


def unresolved_section(text: str) -> list[str]:
    section = text.split("## Unresolved records\n", 1)[1].split("\n## ", 1)[0]
    return [ln for ln in section.splitlines() if ln.startswith("| op:")]


def test_each_unresolved_record_is_listed_with_its_state_now_and_the_cell_it_would_count_in() -> None:
    manifest = manifest_of(corpus())
    cov = breakdown(manifest, "x", official=TABLE)

    def locate(
        rid: str,
    ) -> Any:  # IC2014x0001's status is still unknown; IC2014x0002's track was decided since
        cell = LOCATE(rid)
        return (*cell[:3], "unknown") if rid == STATUS_ROW.id else cell

    text = render(
        cov, manifest, META, official=TABLE, locate=locate, unresolved=[STATUS_ROW, TRACK_ROW, GONE_ROW]
    )
    assert unresolved_section(text) == [
        "| op:iclr:2014:IC2014x0001 | status | main / unknown | ICLR 2014 main (gated) | withdrawn (invitation=X) "
        "| accepted (content.venue=Y) |",
        "| op:iclr:2014:IC2014x0002 | track | main / accepted (**track no longer unknown**) "
        "| ICLR 2014 main (gated) or ICLR 2014 workshop (not gated) | main (invitation=X) | workshop (venueid=A\\|B) |",
        "| op:iclr:2014:NotHere2014 | status | not in the snapshot | — | a | b |",
    ]  # fmt: skip


def test_an_unresolved_status_decided_since_by_another_source_is_flagged() -> None:
    manifest = manifest_of(corpus())
    cov = breakdown(manifest, "x", official=TABLE)
    [line] = unresolved_section(
        render(cov, manifest, META, official=TABLE, locate=LOCATE, unresolved=[STATUS_ROW])
    )
    assert "| main / accepted (**status no longer unknown**) |" in line


def test_no_unresolved_record_says_so() -> None:
    assert "## Unresolved records\n\nNone: no source left a field unresolved." in report()


def test_unresolved_rows_load_from_the_snapshots_conflicts_file_checked_against_its_hash(
    tmp_path: Path,
) -> None:
    rows = (Conflict("op:iclr:2014:IC2014x0001", "status", "withdrawn (x)", "openreview_v1", "accepted (y)",
                     "openreview_v1", V1),
            Conflict("op:iclr:2014:IC2014x0003", "title_key", "a", "ris", "b", "ris", "ambiguous_not_merged"))  # fmt: skip
    for name, data in render_snapshot(DedupResult(tuple(corpus()), (), rows), [], BUILT).items():
        (tmp_path / name).write_bytes(data)
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert load_unresolved(tmp_path, manifest) == (
        Unresolved("op:iclr:2014:IC2014x0001", "status", "withdrawn (x)", "accepted (y)", V1),
    )
    (tmp_path / "conflicts.csv").write_bytes((tmp_path / "conflicts.csv").read_bytes() + b"x")
    with pytest.raises(ValueError, match=r"conflicts\.csv doesn't match"):
        load_unresolved(tmp_path, manifest)


def test_op_eval_coverage_lists_the_snapshots_unresolved_records(tmp_path: Path) -> None:
    root = tmp_path / "data"
    snap = root / "snapshots" / "2026-09-29-test"
    snap.mkdir(parents=True)
    row = Conflict("op:iclr:2014:IC2014x0001", "status", "withdrawn (x)", "openreview_v1", "accepted (y)",
                   "openreview_v1", V1)  # fmt: skip
    for name, data in render_snapshot(DedupResult(tuple(corpus()), (), (row,)), [], BUILT).items():
        (snap / name).write_bytes(data)
    build_index(snap, root / "indexes")
    out = tmp_path / "results"
    assert main(eval_args(root, out)) == 0
    [written] = list(out.iterdir())
    assert (
        unresolved_section(written.read_text(encoding="utf-8"))
        == [
            "| op:iclr:2014:IC2014x0001 | status | main / accepted (**status no longer unknown**) "
            "| ICLR 2014 main (gated) | withdrawn (x) | accepted (y) |"  # the real table; the test record is accepted
        ]
    )
