"""`op eval coverage` (TASK-054, spec 07 §C, coverage-reporting skill): the dated coverage report and the M4
gate verdict, rendered from exactly what `GET /coverage` serves."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest
from openproceedings.cli import main
from openproceedings.coverage import breakdown
from openproceedings.engine.index import build_index
from openproceedings.eval.coverage_report import Meta, gate, render
from openproceedings.ingest.dedup import DedupResult
from openproceedings.ingest.record import PaperRecord
from openproceedings.ingest.snapshot import render as render_snapshot
from openproceedings.ingest.sources.common import ListingReport
from openproceedings.official_counts import OfficialCount

from tests.unit.ingest.test_dedup import paper

BUILT = datetime(2026, 9, 29, tzinfo=UTC)
ACCESSED = date(2026, 9, 27)


def official(n: int) -> OfficialCount:
    return OfficialCount(n, "papers on the accepted list", "https://example.org/list", ACCESSED)


# ICLR 2013 main: 24 of 24 (✓); ICLR 2014 main: 30 of 35 (✗, −14.3%); ICLR 2015 main: no records (a gap);
# ICLR 2016 workshop: not gated; ICML 2020 main: records but no official count (no source)
TABLE = {("ICLR", 2013, "main"): official(24), ("ICLR", 2014, "main"): official(35),
         ("ICLR", 2015, "main"): official(31)}  # fmt: skip


def corpus() -> list[PaperRecord]:
    def many(venue: str, year: int, n: int, track: str = "main") -> list[PaperRecord]:
        return [paper(f"{venue[:2]}{year}x{i:04d}", f"Paper {venue} {year} {track} {i}", venue=venue, year=year,
                      track=track, abstract=None if i == 0 else "An abstract.") for i in range(n)]  # fmt: skip

    return (
        many("ICLR", 2013, 24)
        + many("ICLR", 2014, 30)
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
    assert "| 0 | 31 | −31 | −100.0% |" in line and "✗ gap" in line and line.endswith("| none (no source) |")


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
    assert "| openreview_v2 | ICLR | 2024 | 651 | 651 | — | skipped groups 1 |" in text


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
    assert "| 59 | 4 | 0 | 0 |" in report()  # records, missing abstracts, unknown track, unknown status


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
    assert "is not" in capsys.readouterr().err and not (tmp_path / "r").exists()


def test_unknown_track_records_are_counted_per_venue_year_and_never_folded_into_main() -> None:
    records = [*corpus(), paper("IC2013unk1", "An unplaced paper", venue="ICLR", year=2013, track="unknown")]
    manifest = manifest_of(records)
    text = render(breakdown(manifest, "x", official=TABLE), manifest, META, official=TABLE)
    main_row = [c.strip() for c in row(text, "ICLR", 2013, "main").strip("|").split("|")]
    assert main_row[2] == "24" and main_row[-3] == "1"  # main stays 24 (✓); the venue-year's unknown is 1
    assert "not gated" in row(text, "ICLR", 2013, "unknown")


def test_causes_load_from_toml_and_an_empty_cause_is_refused(tmp_path: Path) -> None:
    from openproceedings.eval.coverage_report import load_causes

    path = tmp_path / "coverage-causes.toml"
    assert load_causes(path) == {}  # no file: no causes, so every failing cell reads unclassified
    path.write_text('["NeurIPS 2021 datasets_benchmarks"]\ncause = "dedup: ids collided (TASK-118)"\n')
    assert load_causes(path) == {("NeurIPS", 2021, "datasets_benchmarks"): "dedup: ids collided (TASK-118)"}
    path.write_text('["ICLR 2014 main"]\ncause = "  "\n')
    with pytest.raises(ValueError, match="needs a non-empty cause"):
        load_causes(path)
    for heading in ("ICLR 2014", "ICLR twenty main", "Iclr 2014 main", "ICLR 2014 mainn"):
        path.write_text(f'["{heading}"]\ncause = "x"\n')
        with pytest.raises(ValueError, match="is not"):
            load_causes(path)
