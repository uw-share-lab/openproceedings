"""A venue-year status its sources can't supply is reported, with the records behind it (TASK-109)."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import pytest
from openproceedings import cli
from openproceedings.ingest import snapshot as snap
from openproceedings.ingest import status_check as sc
from openproceedings.ingest.record import PaperRecord

from tests.unit.ingest.test_dedup import paper

BUILT = datetime(2026, 9, 28, tzinfo=UTC)


def icml_2019() -> list[PaperRecord]:
    """A proceedings-only venue-year (ICML 2019: PMLR v97; OpenReview holds ICML from 2023) where a synthetic
    RIS record says `withdrawn`, which neither PMLR nor RIS can supply there."""
    return [
        paper("pmlr-v97-alpha19a", "Alpha", source="pmlr", venue="ICML", year=2019),
        paper("pmlr-v97-beta19b", "Beta", source="ris", venue="ICML", year=2019),
        paper("SyntheticW1", "Gamma", source="ris", venue="ICML", year=2019, status="withdrawn"),
    ]


def test_an_unexpected_status_is_reported_with_its_records(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger="openproceedings.ingest.status_check"):
        [cell] = sc.unexpected_statuses(icml_2019())
    assert cell == sc.UnexpectedStatus(
        "ICML", 2019, "withdrawn", ("pmlr", "ris"), ("accepted",), ("op:icml:2019:SyntheticW1",)
    )
    assert cell.to_json()["records"] == ["op:icml:2019:SyntheticW1"]
    [line] = [r for r in caplog.records if r.getMessage() == "snapshot_unexpected_status"]
    assert (line.venue, line.year, line.status, line.records, line.ids) == (  # type: ignore[attr-defined]
        "ICML", 2019, "withdrawn", 1, ["op:icml:2019:SyntheticW1"])  # fmt: skip
    assert "Gamma" not in caplog.text  # never record text


@pytest.mark.parametrize(
    ("venue", "year", "source", "status"),
    [
        ("ICLR", 2024, "ris", "rejected"),  # API v2 holds ICLR 2024
        ("ICLR", 2017, "ris", "unknown"),
        ("ICLR", 2013, "ris", "rejected"),  # API v1 holds ICLR 2013–2023 (a v1 venueid gives `unknown`)
        ("NeurIPS", 2022, "openreview_v1", "withdrawn"),
        ("ICLR", 2015, "iclr_archive", "accepted"),
        ("ICML", 2019, "pmlr", "accepted"),
        ("ICML", 2023, "ris", "desk_rejected"),
    ],
)
def test_a_status_its_sources_can_supply_is_not_reported(
    venue: str, year: int, source: str, status: str
) -> None:
    assert (
        sc.unexpected_statuses([paper("SyntheticA1", venue=venue, year=year, source=source, status=status)])
        == []
    )


@pytest.mark.parametrize(
    ("venue", "year", "source", "status"),
    [
        ("NeurIPS", 2019, "neurips_proceedings", "unknown"),  # before OpenReview: proceedings only
        ("NeurIPS", 2024, "neurips_proceedings", "rejected"),  # a listing is accepted wherever it is
        ("ICLR", 2015, "iclr_archive", "rejected"),
        ("ICLR", 2015, "ris", "rejected"),  # ICLR 2015 is not on OpenReview
    ],
)
def test_a_status_no_source_can_supply_is_reported(venue: str, year: int, source: str, status: str) -> None:
    [cell] = sc.unexpected_statuses(
        [paper("SyntheticA1", venue=venue, year=year, source=source, status=status)]
    )
    assert (cell.venue, cell.year, cell.status) == (venue, year, status)


def test_the_venue_years_sources_together_decide() -> None:
    """An OpenReview record in the venue-year lets it hold every status (as the coverage table reads it)."""
    records = [*icml_2019(), paper("SyntheticO1", "Delta", source="openreview_v2", venue="ICML", year=2019)]
    assert sc.unexpected_statuses(records) == []


def test_the_table_is_an_input() -> None:
    """The seam the coverage table (`statuses_indexed`, TASK-082) plugs into when the branches merge."""
    assert sc.unexpected_statuses(icml_2019(), table=lambda sources, venue, year: sc.EVERY_STATUS) == []
    cells = sc.unexpected_statuses(icml_2019(), table=lambda sources, venue, year: ())
    assert [(c.status, len(c.records)) for c in cells] == [("accepted", 2), ("withdrawn", 1)]


def test_cells_come_in_venue_year_status_order() -> None:
    records = [
        paper("SyntheticB1", source="ris", venue="ICML", year=2020, status="unknown"),
        paper("SyntheticB2", source="ris", venue="ICML", year=2020, status="rejected"),
        paper("SyntheticB3", source="ris", venue="ICML", year=2019, status="withdrawn"),
    ]
    got = [(c.year, c.status) for c in sc.unexpected_statuses(records)]
    assert got == [(2019, "withdrawn"), (2020, "rejected"), (2020, "unknown")]


def test_every_claim_source_has_a_row() -> None:
    for source in sc.SOURCE_STATUSES:
        assert sc.expected([source], "ICML", 2019)


# --- the build ----------------------------------------------------------------------------------------------


def test_the_build_reports_it_and_leaves_the_snapshot_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(snap, "load_sources", lambda cache: (icml_2019(), [], []))
    result = snap.build(tmp_path / "cache", tmp_path / "snapshots", BUILT)
    assert [c.records for c in result.unexpected_statuses] == [("op:icml:2019:SyntheticW1",)]
    assert "op:icml:2019:SyntheticW1" in snap.load_records(result.path)  # reported, never dropped
    manifest = json.loads((result.path / "manifest.json").read_text(encoding="utf-8"))
    assert "unexpected_statuses" not in manifest  # a report, not part of the snapshot

    again = snap.build(tmp_path / "cache", tmp_path / "snapshots", BUILT)  # an existing snapshot reports too
    assert (again.created, again.unexpected_statuses) == (False, result.unexpected_statuses)

    data = ["--data-dir", str(tmp_path / "data")]
    assert cli.main([*data, "snapshot", "build"]) == 0
    [cell] = json.loads(capsys.readouterr().out)["unexpected_statuses"]
    assert (cell["venue"], cell["year"], cell["status"], cell["records"]) == (
        "ICML", 2019, "withdrawn", ["op:icml:2019:SyntheticW1"])  # fmt: skip
