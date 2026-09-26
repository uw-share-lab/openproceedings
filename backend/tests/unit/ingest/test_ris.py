"""RIS importer against the synthetic scholarmend fixture (decision-004: no real corpus text here)."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import pytest
from openproceedings.ingest.record import PaperRecord
from openproceedings.ingest.ris import import_ris

FIXTURE = Path(__file__).parents[2] / "fixtures" / "ris"
H1 = "0123456789abcdef0123456789abcdef"


@pytest.fixture(scope="module")
def imported() -> tuple[dict[str, PaperRecord], object]:
    records, report = import_ris(FIXTURE / "mended.ris")
    return {r.id: r for r in records}, report


def test_ids_and_skips(imported: tuple[dict[str, PaperRecord], object]) -> None:
    by_id, report = imported
    assert set(by_id) == {
        "op:icml:2024:pmlr-v235-smith24a",
        "op:icml:2026:AbCdEf1234",
        "op:iclr:2025:iclr-fedcba9876543210fedcba9876543210",
        "op:iclr:2024:Rej_ected-1",
        "op:neurips:2024:nips-00112233445566778899aabbccddeeff",
        f"op:neurips:2025:nips-{H1}",
    }
    assert report.read == 10 and report.imported == 6  # type: ignore[attr-defined]
    # arXiv and a Scholar-only venue are out of scope; a PMC-only ICML paper has no id to build; a record
    # with no Query date has no fetch time for its claims.
    assert dict(report.skipped) == {"out_of_scope": 2, "no_id": 1, "no_query_date": 1}  # type: ignore[attr-defined]


def test_status_and_track_come_from_claims_only(imported: tuple[dict[str, PaperRecord], object]) -> None:
    by_id, report = imported
    got = {i: (r.track, r.status) for i, r in by_id.items()}
    assert got[f"op:neurips:2025:nips-{H1}"] == ("main", "accepted")  # proceedings listing
    assert got["op:neurips:2024:nips-00112233445566778899aabbccddeeff"] == ("datasets_benchmarks", "accepted")
    assert got["op:icml:2026:AbCdEf1234"] == ("workshop", "accepted")  # venueid
    assert got["op:iclr:2024:Rej_ected-1"] == ("main", "rejected")  # venueid status suffix
    assert got["op:icml:2024:pmlr-v235-smith24a"] == ("main", "accepted")  # an ICML main volume
    assert dict(report.status) == {"accepted": 5, "rejected": 1}  # type: ignore[attr-defined]


def test_abstracts_never_come_from_scholar(imported: tuple[dict[str, PaperRecord], object]) -> None:
    by_id, report = imported
    assert by_id[f"op:neurips:2025:nips-{H1}"].abstract == (
        "We introduce a synthetic benchmark for measuring trust calibration in language models."
    )
    assert (
        by_id["op:icml:2026:AbCdEf1234"].abstract
        == "A made-up abstract about human reliance on model outputs."
    )
    for snippet_only in (
        "op:iclr:2025:iclr-fedcba9876543210fedcba9876543210",
        "op:icml:2024:pmlr-v235-smith24a",
    ):
        assert by_id[snippet_only].abstract is None
    assert by_id["op:neurips:2024:nips-00112233445566778899aabbccddeeff"].abstract == (
        "A synthetic datasets-track abstract with extra spaces."
    )
    assert report.abstract_missing == 2  # type: ignore[attr-defined]
    assert all("…" not in (r.abstract or "") for r in by_id.values())


def test_authors_drop_the_truncation_marker(imported: tuple[dict[str, PaperRecord], object]) -> None:
    by_id, _ = imported
    assert by_id[f"op:neurips:2025:nips-{H1}"].authors == ("Doe, J", "Roe, R")
    assert by_id["op:icml:2024:pmlr-v235-smith24a"].authors == ("Smith, A", "Jones, B")


def test_claims_are_ris_with_scholarmend_evidence_and_the_query_date(
    imported: tuple[dict[str, PaperRecord], object],
) -> None:
    by_id, _ = imported
    r = by_id["op:icml:2026:AbCdEf1234"]
    assert {c.source for c in r.provenance} == {"ris"}
    assert {c.fetched_at for c in r.provenance} == {datetime(2026, 9, 18, 10, 3, 5, tzinfo=UTC)}
    [status] = r.claims("status")
    assert (status.value, status.evidence) == (
        "accepted",
        "scholarmend:openreview_api venueid=ICML.cc/2026/Workshop/SyntheticWS",
    )
    assert r.venue_id_raw == "ICML.cc/2026/Workshop/SyntheticWS"
    assert r.urls.forum == "https://openreview.net/forum?id=AbCdEf1234"
    [abstract] = r.claims("abstract")
    assert abstract.evidence == "scholarmend:openreview_api openreview:AbCdEf1234"
    neurips = by_id[f"op:neurips:2025:nips-{H1}"]
    assert neurips.urls.proceedings is not None and neurips.urls.proceedings.endswith(
        "-Abstract-Conference.html"
    )
    assert neurips.urls.pdf is not None and neurips.urls.pdf.endswith("-Paper-Conference.pdf")
    assert neurips.claims("status")[0].evidence == f"scholarmend:proceedings_url {neurips.urls.proceedings}"
    assert neurips.venue_id_raw is None


def _with(tmp_path: Path, edit: object) -> Path:
    """A copy of the fixture with `resolved.json` edited by `edit(entries)`."""
    (tmp_path / "mended.ris").write_bytes((FIXTURE / "mended.ris").read_bytes())
    entries = json.loads((FIXTURE / "resolved.json").read_text(encoding="utf-8"))
    edit(entries)  # type: ignore[operator]
    (tmp_path / "resolved.json").write_text(json.dumps(entries), encoding="utf-8")
    return tmp_path / "mended.ris"


def test_misaligned_resolved_json_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="RIS records but"):
        import_ris(_with(tmp_path, lambda e: e.pop()))
    with pytest.raises(ValueError, match="line up"):
        import_ris(_with(tmp_path, lambda e: e.reverse()))


def test_proceedings_listing_decides_acceptance_over_a_venueid(tmp_path: Path) -> None:
    def listed(entries: list[dict[str, object]]) -> None:
        url = f"https://proceedings.iclr.cc/paper_files/paper/2024/hash/{H1}-Abstract-Conference.html"
        entries[7]["claims"].append(
            {"field": "venue", "value": "ICLR", "source": "proceedings_url", "evidence": url}
        )  # type: ignore[attr-defined]

    records, _ = import_ris(_with(tmp_path, listed))
    r = next(r for r in records if r.id == "op:iclr:2024:Rej_ected-1")
    assert r.status == "accepted" and r.claims("status")[0].evidence.startswith(
        "scholarmend:proceedings_url "
    )  # type: ignore[union-attr]


def test_two_different_ids_for_one_record_are_ambiguous(tmp_path: Path) -> None:
    def second_hash(entries: list[dict[str, object]]) -> None:
        url = (
            "https://proceedings.neurips.cc/paper_files/paper/2025/hash/"
            + "f" * 32
            + "-Abstract-Conference.html"
        )
        entries[0]["claims"].append(
            {"field": "venue", "value": "NeurIPS", "source": "proceedings_url", "evidence": url}
        )  # type: ignore[attr-defined]

    _, report = import_ris(_with(tmp_path, second_hash))
    assert report.skipped["ambiguous"] == 1


def test_non_icml_pmlr_volumes_give_no_pmlr_id(tmp_path: Path) -> None:
    ris = (FIXTURE / "mended.ris").read_text(encoding="utf-8-sig").replace("/v235/", "/v238/")
    (tmp_path / "mended.ris").write_text(ris, encoding="utf-8")
    (tmp_path / "resolved.json").write_bytes((FIXTURE / "resolved.json").read_bytes())
    records, report = import_ris(tmp_path / "mended.ris")
    assert not any(r.venue == "ICML" and r.native.startswith("pmlr-") for r in records)
    assert report.skipped["no_id"] == 2  # scholarmend still says ICML, but v238 is no ICML volume: no id


def test_logs_counts_without_text(imported: object, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="openproceedings.ingest.ris"):
        import_ris(FIXTURE / "mended.ris")
    [summary] = [r for r in caplog.records if r.getMessage() == "ris_import"]
    assert (summary.imported, summary.skipped) == (6, {"out_of_scope": 2, "no_id": 1, "no_query_date": 1})  # type: ignore[attr-defined]
    assert not any("Synthetic" in str(r.__dict__) for r in caplog.records)  # no titles or abstracts
