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


META = Meta(date=date(2026, 9, 29), index_version="abc123def456", sources_sha256="f" * 64,
            command="op eval coverage")  # fmt: skip


def report(crawls: list[Any] | None = None, causes: dict[tuple[str, int, str], str] | None = None) -> str:
    manifest = manifest_of(corpus(), crawls)
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
    assert "| 0 | 31 | −31 | −100.0% |" in line and "✗" in line and "gap" in line


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
    assert [c.strip() for c in line.strip("|").split("|")][-3:] == [
        "1", "0", "accepted, rejected, withdrawn, desk_rejected, unknown"]  # fmt: skip


def test_listings_that_skipped_entries_are_listed_with_their_reasons() -> None:
    text = report(crawls=[listing({"duplicate": 54})])
    assert (
        "| neurips_proceedings | NeurIPS | 2021 | https://example.org/2021 | 174 | 174 | duplicate 54 |"
        in text
    )
    assert "| neurips_proceedings |" not in report(crawls=[listing({})]).split("## Listings")[1]


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


def test_unknown_track_records_are_counted_per_venue_year_and_never_folded_into_main() -> None:
    records = [*corpus(), paper("IC2013unk1", "An unplaced paper", venue="ICLR", year=2013, track="unknown")]
    manifest = manifest_of(records)
    text = render(breakdown(manifest, "x", official=TABLE), manifest, META, official=TABLE)
    main_row = [c.strip() for c in row(text, "ICLR", 2013, "main").strip("|").split("|")]
    assert main_row[2] == "24" and main_row[-2] == "1"  # main stays 24 (✓); the venue-year's unknown is 1
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
