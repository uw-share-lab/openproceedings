"""RIS importer against the synthetic scholarmend fixture (decision-004: no real corpus text here).

Fixture rows (`fixtures/ris/generate.py`): 0 NeurIPS proceedings page + PDF; 1 ICML workshop venueid;
2 ICLR proceedings with only a Scholar snippet; 3 arXiv; 4 no identifier; 5 ICML via PMC only; 6 PMLR
v202; 7 ICLR rejected venueid; 8 NeurIPS D&B PDF on `Papers.NIPS.cc` with a query string; 9 no Query
date; 10 a forum scholarmend couldn't resolve; 11 a neurips.cc media link.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from openproceedings.ingest.record import PaperRecord
from openproceedings.ingest.ris import SKIP_REASONS, ImportReport, import_ris
from openproceedings.ingest.volumes import ICML_PMLR_VOLUMES

FIXTURE = Path(__file__).parents[2] / "fixtures" / "ris"
H1 = "0123456789abcdef0123456789abcdef"
NEURIPS = f"op:neurips:2025:nips-{H1}"
ICLR = "op:iclr:2025:iclr-fedcba9876543210fedcba9876543210"
DB = "op:neurips:2024:nips-00112233445566778899aabbccddeeff"
PMLR = "op:icml:2023:pmlr-v202-smith23a"
WORKSHOP = "op:icml:2026:AbCdEf1234"
REJECTED = "op:iclr:2024:Rej_ected-1"

Entries = list[dict[str, Any]]
Imported = tuple[dict[str, PaperRecord], ImportReport]


@pytest.fixture(scope="module")
def imported() -> Imported:
    records, report = import_ris(FIXTURE / "mended.ris")
    return {r.id: r for r in records}, report


def run(tmp_path: Path, edit: Callable[[Entries], object]) -> Imported:
    """Import a copy of the fixture with `resolved.json` edited in place by `edit`."""
    (tmp_path / "mended.ris").write_bytes((FIXTURE / "mended.ris").read_bytes())
    entries = json.loads((FIXTURE / "resolved.json").read_text(encoding="utf-8"))
    edit(entries)
    (tmp_path / "resolved.json").write_text(json.dumps(entries), encoding="utf-8")
    records, report = import_ris(tmp_path / "mended.ris")
    return {r.id: r for r in records}, report


def claim(field: str, value: str, source: str, evidence: str) -> dict[str, Any]:
    return {"field": field, "value": value, "source": source, "evidence": evidence}


def test_ids_and_skip_reasons(imported: Imported) -> None:
    by_id, report = imported
    assert set(by_id) == {NEURIPS, WORKSHOP, ICLR, PMLR, REJECTED, DB}
    assert (report.read, report.imported) == (12, 6)
    assert report.skipped == {
        "out_of_scope": 2,  # arXiv; a Scholar-only venue
        "unresolved": 2,  # a forum without a venueid; a neurips.cc link that names no paper
        "no_id": 1,  # ICML through PMC: no PMLR key
        "ambiguous": 0,
        "conflict": 0,
        "no_query_date": 1,
    }
    assert set(report.skipped) == set(SKIP_REASONS)


def test_status_and_track_come_from_claims_only(imported: Imported) -> None:
    by_id, report = imported
    assert {i: (r.track, r.status) for i, r in by_id.items()} == {
        NEURIPS: ("main", "accepted"),  # proceedings listing
        DB: ("datasets_benchmarks", "accepted"),  # scholarmend's track claim, on an odd host
        ICLR: ("main", "accepted"),
        WORKSHOP: ("workshop", "accepted"),  # venueid
        REJECTED: ("main", "rejected"),  # venueid status suffix
        PMLR: ("main", "accepted"),  # v202 holds only the main conference
    }
    assert report.track_status == {
        "datasets_benchmarks": {"accepted": 1},
        "main": {"accepted": 3, "rejected": 1},
        "workshop": {"accepted": 1},
    }
    assert (report.unknown_track, report.status_overrides) == (0, 0)


def test_abstracts_never_come_from_scholar(imported: Imported) -> None:
    by_id, report = imported
    assert by_id[NEURIPS].abstract == (
        "We introduce a synthetic benchmark for measuring trust calibration in language models."
    )
    assert by_id[WORKSHOP].abstract == "A made-up abstract about human reliance on model outputs."
    assert by_id[ICLR].abstract is None and by_id[PMLR].abstract is None  # only Scholar's snippet
    # an empty OpenReview abstract falls through to the proceedings page, whitespace collapsed
    assert by_id[DB].abstract == "A synthetic datasets-track abstract with extra spaces."
    assert [c.evidence for c in by_id[DB].claims("abstract")] == [
        f"scholarmend:proceedings_page {by_id[DB].urls.pdf}"
    ]
    assert report.abstract_missing == 2


def test_openreview_abstract_beats_the_proceedings_page(tmp_path: Path) -> None:
    def both(e: Entries) -> None:
        e[1]["claims"].insert(0, claim("abstract", "The proceedings text.", "proceedings_page", "https://x"))
        e[2]["claims"].append(claim("abstract", "A Semantic Scholar abstract.", "semanticscholar", "s2:x"))

    by_id, _ = run(tmp_path, both)
    assert by_id[WORKSHOP].abstract == "A made-up abstract about human reliance on model outputs."
    assert by_id[ICLR].abstract is None  # Semantic Scholar never supplies one


def test_authors_drop_the_truncation_marker(imported: Imported) -> None:
    by_id, _ = imported
    assert by_id[NEURIPS].authors == ("Doe, J", "Roe, R")
    assert by_id[PMLR].authors == ("Smith, A", "Jones, B")


def test_claims_record_where_each_value_came_from(imported: Imported) -> None:
    by_id, _ = imported
    r = by_id[WORKSHOP]
    assert {c.source for c in r.provenance} == {"ris"}
    assert {c.fetched_at for c in r.provenance} == {datetime(2026, 9, 18, 10, 3, 5, tzinfo=UTC)}
    venueid = "scholarmend:openreview_api venueid=ICML.cc/2026/Workshop/SyntheticWS"
    assert {c.field: c.evidence for c in r.provenance} == {
        **dict.fromkeys(("venue", "year", "track", "status", "venue_id_raw"), venueid),
        "title": "mended.ris:TI",
        "authors": "mended.ris:AU",
        "abstract": "scholarmend:openreview_api openreview:AbCdEf1234",
        "urls.forum": "scholarmend:openreview_url https://openreview.net/forum?id=AbCdEf1234",
    }
    assert r.urls.forum == "https://openreview.net/forum?id=AbCdEf1234"
    n = by_id[NEURIPS]
    assert n.urls.proceedings is not None and n.urls.proceedings.endswith("-Abstract-Conference.html")
    assert n.urls.pdf is not None and n.urls.pdf.endswith("-Paper-Conference.pdf")
    assert n.claims("status")[0].evidence == f"scholarmend:proceedings_url {n.urls.proceedings}"
    assert n.venue_id_raw is None
    p = by_id[PMLR]
    assert (p.urls.proceedings, p.urls.pdf) == (
        "https://proceedings.mlr.press/v202/smith23a.html",
        "https://proceedings.mlr.press/v202/smith23a/smith23a.pdf",
    )
    assert (
        p.claims("status")[0].evidence
        == "scholarmend:pmlr_url https://proceedings.mlr.press/v202/smith23a.html"
    )
    # URLs are stored as they appear, query string and all
    assert by_id[DB].urls.pdf is not None and by_id[DB].urls.pdf.startswith("https://Papers.NIPS.cc/")


def pmlr_urls(*urls: str) -> Callable[[Entries], None]:
    def edit(e: Entries) -> None:
        e[6]["claims"] = [c for c in e[6]["claims"] if c["source"] != "pmlr_url"]
        e[6]["claims"] += [claim("pmlr_volume", u.split("/v")[1].split("/")[0], "pmlr_url", u) for u in urls]

    return edit


@pytest.mark.parametrize(
    "url",
    [
        "https://proceedings.mlr.press/v202/smith23a/smith23a.pdf",  # PDF only
        "https://proceedings.mlr.press/v202/smith23a",  # bare, no suffix
        "http://PROCEEDINGS.MLR.PRESS/v202/smith23a.html?x=1",
        "https://raw.githubusercontent.com/mlresearch/v202/main/assets/smith23a/smith23a.pdf",
    ],
)
def test_pmlr_url_forms(tmp_path: Path, url: str) -> None:
    by_id, _ = run(tmp_path, pmlr_urls(url))
    assert PMLR in by_id


def test_icml_volumes_with_position_papers_give_unknown_track(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    assert ICML_PMLR_VOLUMES == {
        119: (2020, "main"),
        139: (2021, "main"),
        162: (2022, "main"),
        202: (2023, "main"),
        235: (2024, "unknown"),
        267: (2025, "unknown"),
    }
    with caplog.at_level(logging.WARNING, logger="openproceedings.ingest.ris"):
        by_id, report = run(tmp_path, pmlr_urls("https://proceedings.mlr.press/v235/smith24a.html"))
    assert by_id["op:icml:2024:pmlr-v235-smith24a"].track == "unknown"
    assert report.unknown_track == 1
    [warning] = [r for r in caplog.records if r.getMessage() == "ris_import_attention"]
    assert warning.unknown_track == 1  # type: ignore[attr-defined]


def drop_pmlr_index(e: Entries) -> None:
    e[6]["claims"] = [c for c in e[6]["claims"] if c["source"] != "pmlr_index"]


def set_venueid_of(e: Entries, row: int, value: str) -> None:
    for c in e[row]["claims"]:
        if c["field"] == "venue_id":
            c["value"] = value


def set_venueid(value: str) -> Callable[[Entries], None]:
    return lambda e: set_venueid_of(e, 1, value)


def short_hash(e: Entries) -> None:
    for c in e[0]["claims"]:
        if c["source"] == "proceedings_url":
            c["evidence"] = c["evidence"].replace("0123456789abcdef0123", "")


PROC = "https://proceedings.{}.cc/paper_files/paper/{}/hash/{}-Abstract-Conference.html"


def listing_year(year: str, host: str | None = None) -> Callable[[Entries], None]:
    """Entry 0's proceedings listing (NeurIPS 2025) moved to `year` (URL and claim agree), optionally to
    another proceedings host (`proceedings.iclr.cc`, with the venue claims to match)."""

    def edit(e: Entries) -> None:
        for c in e[0]["claims"]:
            if c["source"] in ("proceedings_url", "proceedings_page"):
                c["evidence"] = c["evidence"].replace("/2025/", f"/{year}/")
                if host is not None:
                    c["evidence"] = c["evidence"].replace("proceedings.neurips.cc", host)
                if c["field"] == "year":
                    c["value"] = year
                if c["field"] == "venue" and host is not None:
                    c["value"] = "ICLR"

    return edit


@pytest.mark.parametrize(
    ("why", "edit", "reason"),
    [
        (
            "two venueids",
            lambda e: e[1]["claims"].append(
                claim("venue_id", "ICML.cc/2026/Conference", "openreview_api", "v")
            ),
            "ambiguous",
        ),
        (
            "two forum ids",
            lambda e: e[1]["claims"].append(claim("forum_id", "ZzZz9999", "openreview_url", "u")),
            "ambiguous",
        ),
        (
            "two proceedings hashes",
            lambda e: e[0]["claims"].append(
                claim("venue", "NeurIPS", "proceedings_url", PROC.format("neurips", 2025, "a" * 32))
            ),
            "ambiguous",
        ),
        (
            "two PMLR keys",
            pmlr_urls(
                "https://proceedings.mlr.press/v202/a23a.html", "https://proceedings.mlr.press/v202/b23b.html"
            ),
            "ambiguous",
        ),
        ("a short proceedings hash", short_hash, "unresolved"),
        # the URL pattern takes any 4-digit year; one before the venue was held is skipped, not fatal
        ("a NeurIPS listing year before 1987", listing_year("1986"), "unresolved"),
        ("an ICLR listing year before 2013", listing_year("2012", "proceedings.iclr.cc"), "unresolved"),
        ("a listing year past 2099", listing_year("9999"), "unresolved"),
        ("an unparseable PMLR URL", pmlr_urls("https://proceedings.mlr.press/v202/"), "unresolved"),
        ("a venueid of another conference", set_venueid("AAAI.org/2025/Workshop/X"), "out_of_scope"),
        ("a malformed in-scope venueid", set_venueid("ICML.cc/2026//X"), "unresolved"),
        ("a venueid without a forum id", lambda e: e[1]["claims"].pop(0), "no_id"),
        (
            "a non-ICML PMLR volume",
            lambda e: (pmlr_urls("https://proceedings.mlr.press/v238/smith24a.html")(e), drop_pmlr_index(e)),
            "out_of_scope",
        ),
    ],
)
def test_records_that_cannot_be_imported(
    tmp_path: Path, why: str, edit: Callable[[Entries], object], reason: str
) -> None:
    _, report = run(tmp_path, edit)
    assert report.skipped[reason] == 1 + {"out_of_scope": 2, "unresolved": 2, "no_id": 1}.get(reason, 0)
    assert report.imported == 5


def listed(year: str, track: str) -> Callable[[Entries], None]:
    url = f"https://proceedings.iclr.cc/paper_files/paper/{year}/hash/{H1}-Abstract-{track}.html"

    def edit(e: Entries) -> None:
        e[7]["claims"] += [
            claim(f, v, "proceedings_url", url)
            for f, v in (("venue", "ICLR"), ("year", year), ("track", track))
        ]

    return edit


def test_a_listing_decides_acceptance_when_it_agrees_with_the_venueid(tmp_path: Path) -> None:
    by_id, report = run(tmp_path, listed("2024", "Conference"))
    r = by_id[REJECTED]
    assert (r.status, r.track, r.native) == ("accepted", "main", "Rej_ected-1")  # the forum id stays the id
    assert r.claims("status")[0].evidence.startswith(
        "scholarmend:proceedings_url https://proceedings.iclr.cc/"
    )  # type: ignore[union-attr]
    assert r.urls.proceedings is not None and r.urls.forum is not None
    assert report.status_overrides == 1
    [status] = r.claims("status")
    assert status.evidence is not None and status.evidence.endswith(" (overrides venueid status rejected)")


def test_an_agreeing_listing_on_an_accepted_venueid_is_no_override(tmp_path: Path) -> None:
    def accepted(e: Entries) -> None:
        set_venueid_of(e, 7, "ICLR.cc/2024/Conference")
        listed("2024", "Conference")(e)

    by_id, report = run(tmp_path, accepted)
    assert by_id[REJECTED].status == "accepted" and report.status_overrides == 0
    assert "overrides" not in (by_id[REJECTED].claims("status")[0].evidence or "")


def test_a_mixed_volume_listing_agrees_with_any_venueid_track(tmp_path: Path) -> None:
    def icml_2024(e: Entries) -> None:
        set_venueid_of(e, 1, "ICML.cc/2024/Conference")
        e[1]["claims"].append(
            claim("pmlr_volume", "235", "pmlr_url", "https://proceedings.mlr.press/v235/poe24a.html")
        )

    by_id, report = run(tmp_path, icml_2024)
    r = by_id["op:icml:2024:AbCdEf1234"]
    assert (r.track, r.status) == ("main", "accepted")
    assert r.urls.proceedings == "https://proceedings.mlr.press/v235/poe24a.html"
    assert report.skipped["conflict"] == 0


def test_a_forum_without_a_venueid_takes_the_listings_id(tmp_path: Path) -> None:
    by_id, _ = run(
        tmp_path, lambda e: e[0]["claims"].append(claim("forum_id", "FoRum0001", "openreview_url", "u"))
    )
    assert NEURIPS in by_id and by_id[NEURIPS].urls.forum is None


def test_an_unusable_listing_never_outweighs_a_venueid(tmp_path: Path) -> None:
    def stray(e: Entries) -> None:
        url = "https://proceedings.iclr.cc/paper_files/paper/2024/hash/abc-Abstract-Conference.html"  # short hash
        e[7]["claims"] += [
            claim("venue", "ICLR", "proceedings_url", url),
            claim("year", "2024", "proceedings_url", url),
        ]

    by_id, _ = run(tmp_path, stray)
    assert by_id[REJECTED].status == "rejected"


def test_an_unparseable_non_icml_pmlr_url_is_out_of_scope(tmp_path: Path) -> None:
    _, report = run(
        tmp_path, lambda e: (pmlr_urls("https://proceedings.mlr.press/v238/")(e), drop_pmlr_index(e))
    )
    assert (report.skipped["out_of_scope"], report.skipped["unresolved"]) == (3, 2)


@pytest.mark.parametrize(
    ("year", "track", "host"),
    [
        ("2025", "Conference", "iclr"),  # another year
        ("2024", "Datasets_and_Benchmarks_Track", "iclr"),  # another track
        ("2024", "Conference", "neurips"),  # another venue
    ],
)
def test_a_listing_that_disagrees_with_the_venueid_is_a_conflict(
    tmp_path: Path, year: str, track: str, host: str
) -> None:
    def edit(e: Entries) -> None:
        listed(year, track)(e)
        for c in e[7]["claims"]:
            if c["source"] == "proceedings_url":
                c["evidence"] = c["evidence"].replace("proceedings.iclr.cc", f"proceedings.{host}.cc")

    by_id, report = run(tmp_path, edit)
    assert REJECTED not in by_id and report.skipped["conflict"] == 1


def test_misaligned_resolved_json_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="RIS records but"):
        run(tmp_path, lambda e: e.pop())
    with pytest.raises(ValueError, match="line up"):
        run(tmp_path, lambda e: e.reverse())


def test_report_is_consistent_and_manifest_ready(imported: Imported) -> None:
    _, report = imported
    manifest = report.to_manifest()
    assert list(manifest) == sorted(manifest) and list(manifest["skipped"]) == sorted(manifest["skipped"])
    assert manifest["parser_version"] == "0.1.3" and len(manifest["mended_sha256"]) == 64
    json.dumps(manifest)  # plain values only
    with pytest.raises(ValueError, match="read"):
        ImportReport(**{**report.__dict__, "imported": report.imported + 1})
    with pytest.raises(ValueError, match="skip reasons"):
        ImportReport(**{**report.__dict__, "skipped": {"out_of_scope": 6}})
    with pytest.raises(TypeError):
        report.skipped["no_id"] = 0  # type: ignore[index]
    with pytest.raises(TypeError):
        report.track_status["main"]["accepted"] = 0  # type: ignore[index]


def test_logs_counts_never_text(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.DEBUG, logger="openproceedings.ingest.ris"):
        import_ris(FIXTURE / "mended.ris")
    [summary] = [r for r in caplog.records if r.getMessage() == "ris_import"]
    assert (summary.imported, summary.read) == (6, 12)  # type: ignore[attr-defined]
    assert sum(r.getMessage() == "ris_skip" for r in caplog.records) == 6
    [attention] = [r for r in caplog.records if r.getMessage() == "ris_import_attention"]
    assert attention.levelno == logging.WARNING and attention.unresolved == 2  # type: ignore[attr-defined]
    text = " ".join(str(r.__dict__) for r in caplog.records)
    assert "Synthetic" not in text and "abstract about" not in text and "Doe, J" not in text


def test_a_listing_url_with_a_newline_is_dropped_not_imported() -> None:
    from openproceedings.ingest.ris import _url_fields

    forged = "https://proceedings.mlr.press/v267/key23a/x\nER  - \n\nTY  - JOUR\nTI  - injected"
    good = "https://proceedings.mlr.press/v267/key23a.html"
    assert [u for _f, u, _s in _url_fields([forged, good], "pmlr_url")] == [good]


@pytest.mark.parametrize(
    ("change", "why"),
    [
        (lambda u: u.replace("/paper/2025/", "/paper/2023/"), "the URL's year isn't the claimed year"),
        (
            lambda u: re.sub(r"-Abstract(?:-[A-Za-z_]+)?\.html$", "-Abstract-Creative_AI_Track.html", u),
            "track",
        ),
        (
            lambda u: re.sub(r"-Abstract(?:-[A-Za-z_]+)?\.html$", "-Abstract-Workshop.html", u),
            "a workshop page",
        ),
    ],
)
def test_a_listing_claim_must_agree_with_the_url_it_cites(
    tmp_path: Path, change: Callable[[str], str], why: str
) -> None:
    # row 2 is listing-only (ICLR 2025, `Conference`): its track and year come from scholarmend's claims,
    # which must match the proceedings address they cite, or a workshop page could import as `main`
    (tmp_path / "base").mkdir()
    (tmp_path / "edited").mkdir()
    base = run(tmp_path / "base", lambda e: None)[1].skipped["conflict"]

    def edit(e: Entries) -> None:
        for c in e[2]["claims"]:
            if c["source"] == "proceedings_url":
                c["evidence"] = change(c["evidence"])

    by_id, report = run(tmp_path / "edited", edit)
    assert report.skipped["conflict"] == base + 1, why
    assert not any(i.endswith("fedcba9876543210fedcba9876543210") for i in by_id)


def test_a_workshop_venueid_with_a_conference_listing_is_a_conflict(tmp_path: Path) -> None:
    def edit(e: Entries) -> None:
        set_venueid_of(e, 7, "ICLR.cc/2024/Workshop/X")
        listed("2024", "Conference")(e)

    by_id, report = run(tmp_path, edit)
    assert REJECTED not in by_id and report.skipped["conflict"] == 1


def test_a_malformed_forum_id_skips_its_entry_not_the_file(tmp_path: Path) -> None:
    def edit(e: Entries) -> None:
        for c in e[7]["claims"]:
            if c["field"] == "forum_id":
                c["value"] = "has space"

    (tmp_path / "base").mkdir()
    _, base = run(tmp_path / "base", lambda _e: None)
    by_id, report = run(tmp_path, edit)
    assert REJECTED not in by_id and report.skipped["unresolved"] == base.skipped["unresolved"] + 1
    assert report.imported == base.imported - 1


def test_a_pre_2022_url_without_a_track_token_imports(tmp_path: Path) -> None:
    # `/paper/<y>/hash/<h>-Abstract.html` carries no track token: only its year is checked against the claim
    def edit(e: Entries) -> None:
        for c in e[2]["claims"]:
            if c["source"] == "proceedings_url":
                c["evidence"] = re.sub(r"-Abstract(?:-[A-Za-z_]+)?\.html$", "-Abstract.html", c["evidence"])

    (tmp_path / "base").mkdir()
    (tmp_path / "edited").mkdir()
    base = run(tmp_path / "base", lambda e: None)[1]
    by_id, report = run(tmp_path / "edited", edit)
    assert report.skipped["conflict"] == base.skipped["conflict"]
    rec = next(r for i, r in by_id.items() if i.endswith("fedcba9876543210fedcba9876543210"))
    assert (rec.track, rec.status) == ("main", "accepted")
