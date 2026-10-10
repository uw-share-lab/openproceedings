"""RIS importer against the synthetic scholarmend fixture (decision-004: no real corpus text here).

Fixture rows (`fixtures/ris/generate.py`): 0 NeurIPS proceedings page + PDF; 1 ICML workshop venueid;
2 ICLR proceedings with only a Scholar snippet; 3 arXiv; 4 no identifier; 5 ICML via PMC only; 6 PMLR
v202; 7 ICLR rejected venueid; 8 NeurIPS D&B PDF on `Papers.NIPS.cc` with a query string; 9 no Query
date; 10 a forum scholarmend couldn't resolve; 11 a neurips.cc media link.

`fixtures/ris/v1/` rows carry scholarmend 0.1.4's `venue_string` claim (hand-written, TASK-098): 0 ICLR 2022
Poster; 1 NeurIPS 2021 Oral; 2 ICLR 2022 Submitted; 3 ICLR 2023 withdrawn (`""`); 4 an unmapped ICLR 2023
string; 5 ICLR 2024 (v2: ignored); 6 an ICLR 2022 venueid whose venue string's evidence names another venueid;
7 the same with a string that agrees with the venueid; 8 two agreeing claims, one with another venueid's evidence;
9–13 ICLR 2017's lower-case `conference` venueid (track `other`; TASK-142) with `ICLR 2017 Poster`, `ICLR 2017 Oral`,
`ICLR 2017 Invite to Workshop`, `Submitted to ICLR 2017` and another year's `ICLR 2022 Poster`; 14 an ICLR 2023
blog post (`Blogposts @ ICLR 2023`).
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
from openproceedings.ingest.ris import (
    QUERY_DATE_OFFSETS,
    SKIP_REASONS,
    ImportReport,
    import_ris,
    load_offsets,
)
from openproceedings.ingest.volumes import ICML_PMLR_VOLUMES

FIXTURE = Path(__file__).parents[2] / "fixtures" / "ris"
V1_FIXTURE = FIXTURE / "v1"
H1 = "0123456789abcdef0123456789abcdef"
NEURIPS = f"op:neurips:2025:nips-{H1}"
ICLR = "op:iclr:2025:iclr-fedcba9876543210fedcba9876543210"
DB = "op:neurips:2024:nips-00112233445566778899aabbccddeeff"
PMLR = "op:icml:2023:pmlr-v202-smith23a"
WORKSHOP = "op:icml:2026:AbCdEf1234"
REJECTED = "op:iclr:2024:Rej_ected-1"
V1 = {
    "poster": "op:iclr:2022:V1Poster01",
    "oral": "op:neurips:2021:V1Oral0001",
    "submitted": "op:iclr:2022:V1Submit01",
    "withdrawn": "op:iclr:2023:V1Withdr01",
    "unmapped": "op:iclr:2023:V1Unmapp01",
    "v2": "op:iclr:2024:V2Ignore01",
    "other_note": "op:iclr:2022:V1Disagr01",
    "agreeing_other_note": "op:iclr:2022:V1Agree001",
    "one_bad_claim": "op:iclr:2022:V1OneBad01",
    "2017_poster": "op:iclr:2017:V1Ic17Pos1",
    "2017_oral": "op:iclr:2017:V1Ic17Ora1",
    "2017_workshop": "op:iclr:2017:V1Ic17Wks1",
    "2017_rejected": "op:iclr:2017:V1Ic17Rej1",
    "2017_another_year": "op:iclr:2017:V1Ic17Yr01",
    "2023_blogpost": "op:iclr:2023:V1Blog2301",
    # scholarmend 0.1.5's `invitation` claim (TASK-157)
    "2017_workshop_copy": "op:iclr:2017:rkB_5hEKe",
    "2017_rejected_invitation": "op:iclr:2017:V1Ic17Inv1",
    "2017_invitation_of_another_note": "op:iclr:2017:V1Ic17Inv2",
    "2017_unlisted_invitation": "op:iclr:2017:V1Ic17Inv3",
    "2017_poster_on_workshop": "op:iclr:2017:V1Ic17Inv4",
    "v2_invitation": "op:iclr:2024:V2Invite01",
    "2017_two_invitations": "op:iclr:2017:V1Ic17Inv5",
    "2017_empty_invitation": "op:iclr:2017:V1Ic17Inv6",
}

Entries = list[dict[str, Any]]
Imported = tuple[dict[str, PaperRecord], ImportReport]


@pytest.fixture(scope="module")
def imported() -> Imported:
    records, report = import_ris(FIXTURE / "mended.ris")
    return {r.id: r for r in records}, report


def run(tmp_path: Path, edit: Callable[[Entries], object], fixture: Path = FIXTURE) -> Imported:
    """Import a copy of the fixture with `resolved.json` edited in place by `edit`."""
    (tmp_path / "mended.ris").write_bytes((fixture / "mended.ris").read_bytes())
    entries = json.loads((fixture / "resolved.json").read_text(encoding="utf-8"))
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


def test_an_abstract_with_a_control_character_is_imported_with_a_space(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """decision-044 (TASK-188): the title rule, for abstracts. The note goes after the route and url, which
    `dedup.attribution` reads from the start of the evidence. A claim that is only control characters is
    empty, so the next source's abstract is taken."""
    text = "A made-up abstract about human reliance on model outputs."

    def controls(e: Entries) -> None:
        for entry in e:
            for c in entry["claims"]:
                if c["field"] == "abstract" and c["value"] == text:
                    c["value"] = "A made-up abstract about human re\x02liance on model outputs.\x00"
                elif c["field"] == "abstract" and c["value"].startswith("A synthetic datasets-track"):
                    entry["claims"].insert(
                        0, claim("abstract", "\x02 \x00", "openreview_api", "openreview:x")
                    )
                    break

    with caplog.at_level(logging.INFO, logger="openproceedings.ingest.ris"):
        by_id, report = run(tmp_path, controls)
    [line] = [r for r in caplog.records if r.getMessage() == "ris_import"]
    assert line.__dict__["abstract_control_characters"] == 1
    assert by_id[WORKSHOP].abstract == "A made-up abstract about human re liance on model outputs."
    # TASK-199: one record's abstract lost a control character (the all-control claim was passed over)
    assert report.abstract_control_characters == 1 == report.to_manifest()["abstract_control_characters"]
    [abstract] = by_id[WORKSHOP].claims("abstract")
    assert abstract.evidence is not None and abstract.evidence.endswith(
        " (2 control characters replaced by a space)"
    )
    assert abstract.evidence.startswith("scholarmend:openreview_api ")
    assert by_id[DB].abstract == "A synthetic datasets-track abstract with extra spaces."


def test_the_abstract_counter_cannot_be_faked_by_evidence_text(
    tmp_path: Path, imported: Imported, caplog: pytest.LogCaptureFixture
) -> None:
    """TASK-199 security note: a RIS abstract claim's evidence is the reviewer's file's text, so it can say
    `(5 control characters replaced by a space)` without any. The count is the importer's own, so it stays 0,
    and a file with none keeps its manifest shape."""
    text = "A made-up abstract about human reliance on model outputs."

    def spoof(e: Entries) -> None:
        for entry in e:
            for c in entry["claims"]:
                if c["field"] == "abstract" and c["value"] == text:
                    c["evidence"] += " (5 control characters replaced by a space)"

    with caplog.at_level(logging.INFO, logger="openproceedings.ingest.ris"):
        by_id, report = run(tmp_path, spoof)
    [line] = [r for r in caplog.records if r.getMessage() == "ris_import"]
    assert line.__dict__["abstract_control_characters"] == 0  # on the line even at 0
    [abstract] = by_id[WORKSHOP].claims("abstract")
    assert abstract.evidence is not None and abstract.evidence.endswith(
        "(5 control characters replaced by a space)"
    )
    assert (
        report.abstract_control_characters == 0 and "abstract_control_characters" not in report.to_manifest()
    )
    assert "abstract_control_characters" not in imported[1].to_manifest()


def test_authors_drop_the_truncation_marker(imported: Imported) -> None:
    by_id, _ = imported
    assert by_id[NEURIPS].authors == ("Doe, J", "Roe, R")
    assert by_id[PMLR].authors == ("Smith, A", "Jones, B")


def test_an_entry_missing_from_the_offset_table_keeps_local_wall_time(imported: Imported) -> None:
    """TASK-077: the fixture's directory isn't in `ris_offsets.toml`, so its query dates stay as written,
    labelled UTC, and its report says the offset is unknown."""
    _, report = imported
    assert report.utc_offset is None and report.to_manifest()["utc_offset"] is None


@pytest.mark.parametrize(
    ("offset", "fetched"),
    [
        ("-04:00", datetime(2026, 9, 18, 14, 3, 5, tzinfo=UTC)),
        ("+05:30", datetime(2026, 9, 18, 4, 33, 5, tzinfo=UTC)),
        ("+00:00", datetime(2026, 9, 18, 10, 3, 5, tzinfo=UTC)),
        ("-09:30", datetime(2026, 9, 18, 19, 33, 5, tzinfo=UTC)),
        ("+14:00", datetime(2026, 9, 17, 20, 3, 5, tzinfo=UTC)),  # the date moves back a day
    ],
)
def test_a_listed_entry_converts_its_query_dates_to_utc(offset: str, fetched: datetime) -> None:
    """The workshop record's `Query date: 2026-09-18 10:03:05` is local time at `offset` (TASK-077)."""
    records, report = import_ris(FIXTURE / "mended.ris", cache_entry="search", offsets={"search": offset})
    [r] = [r for r in records if r.id == WORKSHOP]
    assert {c.fetched_at for c in r.provenance} == {fetched}
    assert report.utc_offset == offset
    unlisted, other = import_ris(FIXTURE / "mended.ris", cache_entry="other", offsets={"search": offset})
    assert other.utc_offset is None and {
        c.fetched_at for r in unlisted if r.id == WORKSHOP for c in r.provenance
    } == {datetime(2026, 9, 18, 10, 3, 5, tzinfo=UTC)}


def test_the_offset_table_holds_both_trust_evals_searches() -> None:
    """decision-025: both Publish or Perish searches ran at UTC−04:00, read from PoP's own query records."""
    assert dict(QUERY_DATE_OFFSETS) == {"out-covidence": "-04:00", "out-covidence-2020-2024": "-04:00"}


@pytest.mark.parametrize(
    ("row", "error"),
    [
        ('utc_offset = "-04:00"\nevidence = "x"', "exactly"),
        ('utc_offset = "-04:00"\nevidence = "x"\nverified = 2026-10-01\nextra = 1', "exactly"),
        ('utc_offset = "-4:00"\nevidence = "x"\nverified = 2026-10-01', r"\+HH:MM"),
        ('utc_offset = "EDT"\nevidence = "x"\nverified = 2026-10-01', r"\+HH:MM"),
        ('utc_offset = -4\nevidence = "x"\nverified = 2026-10-01', r"\+HH:MM"),
        ('utc_offset = "+04:60"\nevidence = "x"\nverified = 2026-10-01', "real offset"),
        ('utc_offset = "+14:01"\nevidence = "x"\nverified = 2026-10-01', "real offset"),
        ('utc_offset = "-04:00"\nevidence = " "\nverified = 2026-10-01', "evidence"),
        ('utc_offset = "-04:00"\nevidence = "x"\nverified = "2026-10-01"', "date"),
        ('utc_offset = "-04:00"\nevidence = "x"\nverified = 2026-10-01T00:00:00', "date"),
    ],
)
def test_a_malformed_offset_row_is_an_error(row: str, error: str) -> None:
    with pytest.raises(ValueError, match=error):
        load_offsets(f"[entry]\n{row}\n")


def test_offsets_at_the_limits_load() -> None:
    rows = "".join(
        f'[e{i}]\nutc_offset = "{o}"\nevidence = "x"\nverified = 2026-10-01\n'
        for i, o in enumerate(("+14:00", "-14:00", "+00:00", "-00:59"))
    )
    assert sorted(load_offsets(rows).values()) == ["+00:00", "+14:00", "-00:59", "-14:00"]


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
        28: (2013, "main"),  # v28-v97 added with the PMLR miner (task-053)
        32: (2014, "main"),
        37: (2015, "main"),
        48: (2016, "main"),
        70: (2017, "main"),
        80: (2018, "main"),
        97: (2019, "main"),
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


def test_a_pmlr_url_in_the_added_icml_volumes_now_imports_as_icml(tmp_path: Path) -> None:
    """task-053 added v28-v97 to the volume table: a RIS record whose only identifier is a PMLR URL in one
    of them used to be skipped (`no_id` with scholarmend's pmlr_index venue claim, else `out_of_scope`) and
    is now an ICML record with the table's year and track. A rebuilt snapshot shows it in its diff."""
    by_id, report = run(tmp_path, pmlr_urls("https://proceedings.mlr.press/v97/smith19a.html"))
    r = by_id["op:icml:2019:pmlr-v97-smith19a"]
    assert (r.venue, r.year, r.track, r.status) == ("ICML", 2019, "main", "accepted")
    assert r.urls.proceedings == "https://proceedings.mlr.press/v97/smith19a.html"
    assert (report.imported, report.skipped["no_id"], report.skipped["out_of_scope"]) == (6, 1, 2)
    by_id, report = run(
        tmp_path,
        lambda e: (pmlr_urls("https://proceedings.mlr.press/v28/smith13.html")(e), drop_pmlr_index(e)),
    )
    assert by_id["op:icml:2013:pmlr-v28-smith13"].track == "main"


@pytest.mark.parametrize(
    "volume", [184, 251, 292, 220, 123, 318]
)  # ICML workshops, NeurIPS competition, v318
def test_competition_workshop_and_unlisted_volumes_never_import_as_icml(tmp_path: Path, volume: int) -> None:
    by_id, report = run(
        tmp_path,
        lambda e: (
            pmlr_urls(f"https://proceedings.mlr.press/v{volume}/smith24a.html")(e),
            drop_pmlr_index(e),
        ),
    )
    assert not any(":pmlr-" in rid for rid in by_id)
    assert report.skipped["out_of_scope"] == 3  # arXiv, a Scholar-only venue, and this one


DB_ABS = "https://datasets-benchmarks-proceedings.neurips.cc/paper_files/paper/2021/hash/0123456789abcdef0123456789abcdef-Abstract"


def dbhost(track: str, url: str = f"{DB_ABS}-round1.html") -> Callable[[Entries], None]:
    """Row 0's proceedings claims moved to the NeurIPS 2021 D&B host (by default `-Abstract-round1.html`)."""
    values = {"venue": "NeurIPS", "year": "2021", "track": track, "version": "proceedings"}

    def edit(e: Entries) -> None:
        e[0]["claims"] = [c for c in e[0]["claims"] if c["source"] != "proceedings_url"]
        e[0]["claims"] += [claim(f, v, "proceedings_url", url) for f, v in values.items()]

    return edit


def test_the_2021_db_host_is_a_neurips_listing_with_the_miners_track_rule(tmp_path: Path) -> None:
    by_id, report = run(tmp_path, dbhost("Datasets_and_Benchmarks"))
    r = by_id[f"op:neurips:2021:nips-{H1}-round1"]  # the D&B host's hashes repeat per round (TASK-118)
    assert (r.track, r.status) == ("datasets_benchmarks", "accepted")
    assert f"op:neurips:2021:nips-{H1}" not in by_id
    by_id, report = run(tmp_path, dbhost("Conference"))  # the claim disagrees with the address it cites
    assert f"op:neurips:2021:nips-{H1}-round1" not in by_id and report.skipped["conflict"] == 1


def test_one_hash_on_the_main_and_db_hosts_is_two_papers_so_ambiguous(tmp_path: Path) -> None:
    """The same 2021 hash on proceedings.neurips.cc and the D&B host names two different papers (TASK-118)."""
    main = f"https://proceedings.neurips.cc/paper_files/paper/2021/hash/{H1}-Abstract.html"

    def edit(e: Entries) -> None:
        dbhost("Datasets_and_Benchmarks")(e)
        e[0]["claims"].append(claim("year", "2021", "proceedings_url", main))

    by_id, report = run(tmp_path, edit)
    assert not any(H1 in rid and ":2021:" in rid for rid in by_id)
    assert report.skipped["ambiguous"] == 1


def test_one_hash_in_both_db_rounds_is_two_papers_so_ambiguous(tmp_path: Path) -> None:
    def edit(e: Entries) -> None:
        dbhost("Datasets_and_Benchmarks")(e)
        e[0]["claims"].append(claim("year", "2021", "proceedings_url", f"{DB_ABS}-round2.html"))

    by_id, report = run(tmp_path, edit)
    assert not any(H1 in rid and ":2021:" in rid for rid in by_id)
    assert report.skipped["ambiguous"] == 1


def test_a_db_url_without_a_round_is_unresolved_not_a_bare_hash_id(tmp_path: Path) -> None:
    """With a D&B track claim the round-less URL is a `conflict` (its address gives no track); with a claim
    that also has no rule, the two agree on `unknown`, and the missing round leaves no id."""
    by_id, report = run(tmp_path, dbhost("Mystery_Track", f"{DB_ABS}.html"))
    _, base = run(tmp_path, lambda e: None)
    assert not any(H1 in rid and ":2021:" in rid for rid in by_id)
    assert report.skipped["unresolved"] == base.skipped["unresolved"] + 1


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


def test_a_facct_v81_pmlr_url_is_still_out_of_scope(tmp_path: Path, monkeypatch) -> None:
    from openproceedings.ingest import volumes

    monkeypatch.setattr(
        volumes, "PMLR_NATIVE_VOLUMES", {**volumes.PMLR_NATIVE_VOLUMES, 81: ("FAccT", 2018, "main")}
    )
    _, report = run(
        tmp_path,
        lambda e: (pmlr_urls("https://proceedings.mlr.press/v81/one18a.html")(e), drop_pmlr_index(e)),
    )
    assert report.skipped["out_of_scope"] == 3


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
    assert manifest["parser_version"] == "0.1.5" and len(manifest["mended_sha256"]) == 64
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
    # Only NeurIPS main-conference links through 2021 used the tokenless URL form.
    def edit(e: Entries) -> None:
        for c in e[2]["claims"]:
            if c["source"] == "proceedings_url":
                c["evidence"] = re.sub(
                    r"-Abstract(?:-[A-Za-z_]+)?\.html$",
                    "-Abstract.html",
                    c["evidence"]
                    .replace("proceedings.iclr.cc", "proceedings.neurips.cc")
                    .replace("/2025/", "/2021/"),
                )
                if c["field"] == "venue":
                    c["value"] = "NeurIPS"
                elif c["field"] == "year":
                    c["value"] = "2021"

    (tmp_path / "base").mkdir()
    (tmp_path / "edited").mkdir()
    base = run(tmp_path / "base", lambda e: None)[1]
    by_id, report = run(tmp_path / "edited", edit)
    assert report.skipped["conflict"] == base.skipped["conflict"]
    rec = next(r for i, r in by_id.items() if i.endswith("fedcba9876543210fedcba9876543210"))
    assert (rec.venue, rec.year, rec.track, rec.status) == ("NeurIPS", 2021, "main", "accepted")


def test_a_post_2021_url_without_a_track_token_is_a_conflict(tmp_path: Path) -> None:
    def edit(e: Entries) -> None:
        for c in e[2]["claims"]:
            if c["source"] == "proceedings_url":
                c["evidence"] = re.sub(r"-Abstract(?:-[A-Za-z_]+)?\.html$", "-Abstract.html", c["evidence"])

    (tmp_path / "base").mkdir()
    (tmp_path / "edited").mkdir()
    base = run(tmp_path / "base", lambda e: None)[1]
    by_id, report = run(tmp_path / "edited", edit)
    assert report.skipped["conflict"] == base.skipped["conflict"] + 1
    assert not any(i.endswith("fedcba9876543210fedcba9876543210") for i in by_id)


def test_a_v1_venueid_is_not_status_evidence(tmp_path: Path) -> None:
    """ICLR 2022 put `ICLR.cc/2022/Conference` on 1,523 rejected papers (TASK-095): venue, year and track
    only; the status stays `unknown`, so the default `status:accepted` filter excludes and counts it."""
    by_id, report = run(tmp_path, lambda e: set_venueid_of(e, 7, "ICLR.cc/2022/Conference"))
    r = by_id["op:iclr:2022:Rej_ected-1"]
    assert (r.venue, r.year, r.track, r.status) == ("ICLR", 2022, "main", "unknown")
    [status] = r.claims("status")
    assert status.evidence == (
        "scholarmend:openreview_api venueid=ICLR.cc/2022/Conference (API v1 venue-year: not status evidence)"
    )
    [track] = r.claims("track")
    assert track.evidence == "scholarmend:openreview_api venueid=ICLR.cc/2022/Conference"
    assert report.track_status["main"]["unknown"] == 1 and report.status_overrides == 0


def test_a_listing_decides_a_v1_venueids_acceptance(tmp_path: Path) -> None:
    def v1_listed(e: Entries) -> None:
        set_venueid_of(e, 7, "ICLR.cc/2022/Conference")
        listed("2022", "Conference")(e)

    by_id, report = run(tmp_path, v1_listed)
    r = by_id["op:iclr:2022:Rej_ected-1"]
    assert (r.track, r.status) == ("main", "accepted") and report.status_overrides == 1
    [status] = r.claims("status")
    assert status.evidence is not None and status.evidence.endswith(" (overrides venueid status unknown)")


@pytest.fixture(scope="module")
def v1_imported() -> Imported:
    records, report = import_ris(V1_FIXTURE / "mended.ris")
    return {r.id: r for r in records}, report


def test_v1_fixture_counts(v1_imported: Imported) -> None:
    by_id, report = v1_imported
    assert set(by_id) == set(V1.values()) and (report.read, report.imported) == (23, 23)
    assert report.track_status == {
        "main": {"accepted": 4, "rejected": 9, "unknown": 5},
        "workshop": {"unknown": 3},
        "other": {"unknown": 1},
        "blogpost": {"accepted": 1},
    }
    assert report.status_overrides == 0


NOT_STATUS = "(API v1 venue-year: not status evidence; venue_string not used: {})"


@pytest.mark.parametrize(
    ("row", "status", "evidence"),
    [
        ("poster", "accepted", "venueid=ICLR.cc/2022/Conference venue_string=ICLR 2022 Poster"),
        ("oral", "accepted", "venueid=NeurIPS.cc/2021/Conference venue_string=NeurIPS 2021 Oral"),
        ("submitted", "rejected", "venueid=ICLR.cc/2022/Conference venue_string=ICLR 2022 Submitted"),
        (
            "withdrawn",
            "unknown",
            "venueid=ICLR.cc/2023/Conference " + NOT_STATUS.format("not one non-empty string"),
        ),
        (
            "unmapped",  # the string itself isn't kept: an unmapped one can be free text
            "unknown",
            "venueid=ICLR.cc/2023/Conference " + NOT_STATUS.format("not in the v1 table"),
        ),
        ("v2", "rejected", "venueid=ICLR.cc/2024/Conference/Rejected_Submission"),
        (
            "other_note",
            "unknown",
            "venueid=ICLR.cc/2022/Conference " + NOT_STATUS.format("its evidence names another venueid"),
        ),
        (
            "agreeing_other_note",  # "ICLR 2022 Poster" would give accepted, but the evidence is another note's
            "unknown",
            "venueid=ICLR.cc/2022/Conference " + NOT_STATUS.format("its evidence names another venueid"),
        ),
        (
            "one_bad_claim",  # one good claim doesn't outweigh a bad one: every claim must name the venueid
            "unknown",
            "venueid=ICLR.cc/2022/Conference " + NOT_STATUS.format("its evidence names another venueid"),
        ),
    ],
)
def test_a_v1_venue_string_gives_status_with_its_provenance(
    v1_imported: Imported, row: str, status: str, evidence: str
) -> None:
    """TASK-098: scholarmend 0.1.4's `venue_string` claim (OpenReview's `content.venue`) is a v1 venue-year's
    status evidence through classify_v1_venue; outside v1 years, or unusable, it gives nothing."""
    by_id, _ = v1_imported
    r = by_id[V1[row]]
    assert (r.track, r.status) == ("main", status)
    [claim_] = r.claims("status")
    assert claim_.evidence == f"scholarmend:openreview_api {evidence}"
    assert claim_.source == "ris" and claim_.fetched_at == datetime(2026, 9, 19, 1, 6, 30, tzinfo=UTC)
    # venue, year and track stay the venueid's
    assert {c.evidence for c in r.provenance if c.field in ("venue", "year", "track")} == {
        f"scholarmend:openreview_api venueid={r.venue_id_raw}"
    }


@pytest.mark.parametrize(
    ("row", "track", "status", "string"),
    [
        ("2017_poster", "main", "accepted", "ICLR 2017 Poster"),
        ("2017_oral", "main", "accepted", "ICLR 2017 Oral"),
        # invited to the workshop track: not a main-track acceptance, and whether it was presented isn't said
        ("2017_workshop", "workshop", "unknown", "ICLR 2017 Invite to Workshop"),
        ("2017_rejected", "main", "rejected", "Submitted to ICLR 2017"),
    ],
)
def test_an_other_track_v1_venueid_takes_track_and_status_from_the_venue_string(
    v1_imported: Imported, row: str, track: str, status: str, string: str
) -> None:
    """TASK-142: ICLR 2017 puts `ICLR.cc/2017/conference` on every conference note, workshop invitations
    included, so the venueid's track is `other` and `content.venue` gives track and status (openreview-venueids
    table), as the v1 crawler reads it. Venue and year still come from the venueid, and must agree."""
    by_id, _ = v1_imported
    r = by_id[V1[row]]
    assert (r.venue, r.year, r.track, r.status) == ("ICLR", 2017, track, status)
    assert r.venue_id_raw == "ICLR.cc/2017/conference"
    used = f"scholarmend:openreview_api venueid=ICLR.cc/2017/conference venue_string={string}"
    assert [c.evidence for c in r.claims("track")] == [used]
    assert [c.evidence for c in r.claims("status")] == [used]
    assert {c.evidence for c in r.provenance if c.field in ("venue", "year")} == {
        "scholarmend:openreview_api venueid=ICLR.cc/2017/conference"
    }


def test_an_other_track_v1_venueid_refuses_another_years_venue_string(v1_imported: Imported) -> None:
    by_id, _ = v1_imported
    r = by_id[V1["2017_another_year"]]
    assert (r.track, r.status) == ("other", "unknown")
    base = "scholarmend:openreview_api venueid=ICLR.cc/2017/conference"
    assert [c.evidence for c in r.claims("track")] == [base]
    assert [c.evidence for c in r.claims("status")] == [
        f"{base} " + NOT_STATUS.format("ICLR 2022 Poster names ICLR 2022 main")
    ]


def test_an_iclr_2023_blog_post_takes_status_from_its_venue_string(v1_imported: Imported) -> None:
    """`ICLR.cc/2023/BlogPosts` already names the `blogpost` track, so the string must name it too."""
    by_id, _ = v1_imported
    r = by_id[V1["2023_blogpost"]]
    assert (r.track, r.status) == ("blogpost", "accepted")
    vid = "venueid=ICLR.cc/2023/BlogPosts"
    assert [c.evidence for c in r.claims("track")] == [f"scholarmend:openreview_api {vid}"]
    assert [c.evidence for c in r.claims("status")] == [
        f"scholarmend:openreview_api {vid} venue_string=Blogposts @ ICLR 2023"
    ]


@pytest.mark.parametrize(
    ("vid", "string", "reason"),
    [
        # ICLR 2013's lower-case `conference` venueid: no 2013 string is in the v1 table
        ("ICLR.cc/2013/conference", "ICLR 2017 Poster", "ICLR 2017 Poster names ICLR 2017 main"),
        # an `other` venueid the table doesn't say takes its track from `content.venue`: never guessed as main
        (
            "NeurIPS.cc/2022/Challenge/CellSeg",
            "NeurIPS 2022 Accept",
            "NeurIPS 2022 Accept names NeurIPS 2022 main",
        ),
        # a status suffix on the 2017 form isn't the form the table names
        (
            "ICLR.cc/2017/conference/Withdrawn_Submission",
            "ICLR 2017 Poster",
            "ICLR 2017 Poster names ICLR 2017 main",
        ),
    ],
)
def test_only_the_tables_other_track_forms_take_track_from_the_venue_string(
    tmp_path: Path, vid: str, string: str, reason: str
) -> None:
    def edit(e: Entries) -> None:
        for c in e[9]["claims"]:  # row 9: the ICLR 2017 poster
            if c["source"] == "openreview_api":
                c["evidence"] = f"venueid={vid}"
                if c["field"] == "venue_id":
                    c["value"] = vid
                if c["field"] == "venue_string":
                    c["value"] = string

    by_id, _ = run(tmp_path, edit, V1_FIXTURE)
    [r] = [r for r in by_id.values() if r.venue_id_raw == vid]
    assert (r.track, r.status) == ("other", "unknown")
    assert r.claims("status")[0].evidence == f"scholarmend:openreview_api venueid={vid} " + NOT_STATUS.format(
        reason
    )


def set_venue_string(row: int, value: object) -> Callable[[Entries], None]:
    def edit(e: Entries) -> None:
        for c in e[row]["claims"]:
            if c["field"] == "venue_string":
                c["value"] = value

    return edit


@pytest.mark.parametrize(
    ("why", "value", "reason"),
    [
        # a table string for the venueid's venue-year but another track: never a main-track acceptance
        ("another track", "Blogposts @ ICLR 2023", "Blogposts @ ICLR 2023 names ICLR 2023 blogpost"),
        ("another year", "ICLR 2022 Poster", "ICLR 2022 Poster names ICLR 2022 main"),
        ("not a string", ["ICLR 2023 poster"], "not one non-empty string"),
    ],
)
def test_a_venue_string_naming_another_venue_year_or_track_is_not_used(
    tmp_path: Path, why: str, value: object, reason: str
) -> None:
    by_id, _ = run(tmp_path, set_venue_string(4, value), V1_FIXTURE)  # row 4: ICLR.cc/2023/Conference
    r = by_id[V1["unmapped"]]
    assert (r.track, r.status) == ("main", "unknown")
    assert r.claims("status")[0].evidence == (
        "scholarmend:openreview_api venueid=ICLR.cc/2023/Conference " + NOT_STATUS.format(reason)
    )


def test_two_different_venue_strings_are_not_used(tmp_path: Path) -> None:
    def two(e: Entries) -> None:
        e[0]["claims"].append(
            claim("venue_string", "ICLR 2022 Submitted", "openreview_api", "venueid=ICLR.cc/2022/Conference")
        )

    by_id, _ = run(tmp_path, two, V1_FIXTURE)
    r = by_id[V1["poster"]]
    assert r.status == "unknown"
    assert r.claims("status")[0].evidence.endswith(NOT_STATUS.format("not one non-empty string"))  # type: ignore[union-attr]


def test_a_venue_string_from_another_source_is_ignored(tmp_path: Path) -> None:
    def other_source(e: Entries) -> None:
        for c in e[0]["claims"]:
            if c["field"] == "venue_string":
                c["source"] = "semanticscholar"

    by_id, _ = run(tmp_path, other_source, V1_FIXTURE)
    r = by_id[V1["poster"]]
    assert r.status == "unknown"
    assert r.claims("status")[0].evidence == (
        "scholarmend:openreview_api venueid=ICLR.cc/2022/Conference (API v1 venue-year: not status evidence)"
    )


def test_a_listing_overrides_a_v1_venue_strings_rejection(tmp_path: Path) -> None:
    """decision-005: the proceedings decide acceptance; the overruled venue-string status stays visible."""

    def listed_rejection(e: Entries) -> None:
        url = f"https://proceedings.iclr.cc/paper_files/paper/2022/hash/{H1}-Abstract-Conference.html"
        e[2]["claims"] += [
            claim(f, v, "proceedings_url", url)
            for f, v in (("venue", "ICLR"), ("year", "2022"), ("track", "Conference"))
        ]

    by_id, report = run(tmp_path, listed_rejection, V1_FIXTURE)
    r = by_id[V1["submitted"]]
    assert (r.track, r.status) == ("main", "accepted") and report.status_overrides == 1
    assert r.claims("status")[0].evidence.endswith(" (overrides venue_string status rejected)")  # type: ignore[union-attr]


@pytest.mark.parametrize(
    ("row", "key", "string", "status", "override"),
    [
        (9, "2017_poster", "ICLR 2017 Poster", "accepted", False),  # the listing agrees: nothing to override
        (
            12,
            "2017_rejected",
            "Submitted to ICLR 2017",
            "accepted",
            True,
        ),  # decision-005: the proceedings decide
        (
            11,
            "2017_workshop",
            "ICLR 2017 Invite to Workshop",
            None,
            False,
        ),  # workshop vs a main listing: conflict
        (13, "2017_another_year", "ICLR 2022 Poster", None, False),  # refused, so `other` vs main: conflict
    ],
)
def test_a_listing_meets_the_track_an_other_venueid_takes_from_its_venue_string(
    tmp_path: Path, row: int, key: str, string: str, status: str | None, override: bool
) -> None:
    """TASK-142: before it, an ICLR 2017 `conference` record with a listing was always a conflict (`other`
    vs main); now the listing is checked against the string's track, which keeps its venue_string evidence."""

    def with_listing(e: Entries) -> None:
        url = f"https://proceedings.iclr.cc/paper_files/paper/2017/hash/{H1}-Abstract-Conference.html"
        e[row]["claims"] += [
            claim(f, v, "proceedings_url", url)
            for f, v in (("venue", "ICLR"), ("year", "2017"), ("track", "Conference"))
        ]

    (tmp_path / "base").mkdir()
    (tmp_path / "edited").mkdir()
    base = run(tmp_path / "base", lambda e: None, V1_FIXTURE)[1]
    by_id, report = run(tmp_path / "edited", with_listing, V1_FIXTURE)
    if status is None:
        assert V1[key] not in by_id and report.skipped["conflict"] == base.skipped["conflict"] + 1
        return
    r = by_id[V1[key]]
    assert (r.track, r.status) == ("main", status) and report.status_overrides == int(override)
    assert [c.evidence for c in r.claims("track")] == [
        f"scholarmend:openreview_api venueid=ICLR.cc/2017/conference venue_string={string}"
    ]
    [ev] = [c.evidence for c in r.claims("status")]
    assert ev is not None and ev.startswith("scholarmend:proceedings_url https://proceedings.iclr.cc/")
    assert ev.endswith(" (overrides venue_string status rejected)") is override


INVITED = "(the main track's outcome, not this workshop submission's)"


@pytest.mark.parametrize(
    ("row", "track", "status", "evidence", "invitation"),
    [
        # the recorded workshop copy: its claims equal a real rejection's but for the invitation (TASK-157)
        ("2017_workshop_copy", "workshop", "unknown",
         "venueid=ICLR.cc/2017/conference venue_string=Submitted to ICLR 2017 "
         f"invitation=ICLR.cc/2017/workshop/-/submission {INVITED}", "ICLR.cc/2017/workshop/-/submission"),
        ("2017_rejected_invitation", "main", "rejected",
         "venueid=ICLR.cc/2017/conference venue_string=Submitted to ICLR 2017",
         "ICLR.cc/2017/conference/-/submission"),
        # a main-track outcome of any kind on the workshop listing is the twin's, as in the crawler's judge
        ("2017_poster_on_workshop", "workshop", "unknown",
         "venueid=ICLR.cc/2017/conference venue_string=ICLR 2017 Poster "
         f"invitation=ICLR.cc/2017/workshop/-/submission {INVITED}", "ICLR.cc/2017/workshop/-/submission"),
        # an invitation no adapter lists says nothing about the listing: kept, not used
        ("2017_unlisted_invitation", "main", "rejected",
         "venueid=ICLR.cc/2017/conference venue_string=Submitted to ICLR 2017", "ICLR.cc/2017/workshop/-/Synthetic"),
        # an invitation claim whose evidence names another venueid is not this note's: ignored, not recorded
        ("2017_invitation_of_another_note", "main", "rejected",
         "venueid=ICLR.cc/2017/conference venue_string=Submitted to ICLR 2017", None),
        # an entry scholarmend cached before 0.1.5 has no invitation claim: today's reading
        ("2017_rejected", "main", "rejected",
         "venueid=ICLR.cc/2017/conference venue_string=Submitted to ICLR 2017", None),
        # two different invitations, or an empty one, say nothing: neither used nor kept
        ("2017_two_invitations", "main", "rejected",
         "venueid=ICLR.cc/2017/conference venue_string=Submitted to ICLR 2017", None),
        ("2017_empty_invitation", "main", "rejected",
         "venueid=ICLR.cc/2017/conference venue_string=Submitted to ICLR 2017", None),
    ],
)  # fmt: skip
def test_a_v1_invitation_tells_a_workshop_copy_from_a_main_track_rejection(
    v1_imported: Imported, row: str, track: str, status: str, evidence: str, invitation: str | None
) -> None:
    r = v1_imported[0][V1[row]]
    assert (r.track, r.status) == (track, status)
    assert [c.evidence for c in r.claims("status")] == [f"scholarmend:openreview_api {evidence}"]
    assert [c.evidence for c in r.claims("track")] == [f"scholarmend:openreview_api {evidence}"]
    assert [(c.value, c.source, c.evidence) for c in r.claims("invitation")] == (
        []
        if invitation is None
        else [(invitation, "ris", "scholarmend:openreview_api venueid=ICLR.cc/2017/conference")]
    )


def test_an_invitation_outside_the_v1_years_is_ignored(v1_imported: Imported) -> None:
    """TASK-157 (review round 1): only an API v1 venue-year reads the claim; a v2 record keeps its venueid's
    reading and no `invitation` claim, as the `venue_string` row beside it does."""
    r = v1_imported[0][V1["v2_invitation"]]
    assert (r.track, r.status) == ("main", "rejected") and r.claims("invitation") == ()


def test_a_scholar_title_with_a_control_character_is_imported_with_a_space(tmp_path: Path) -> None:
    """decision-036 (TASK-180 review): `_record` has no handler, so a control character in a RIS title raised out
    of the import and failed the build. It becomes a space, and the title claim says so."""
    old, new = "Synthetic Trust Benchmark", "Synthetic Trust\x02 Bench\x02mark"
    (tmp_path / "mended.ris").write_bytes(
        (FIXTURE / "mended.ris").read_bytes().replace(old.encode(), new.encode())
    )
    entries = json.loads((FIXTURE / "resolved.json").read_text(encoding="utf-8"))
    for entry in entries:
        entry["title"] = entry["title"].replace(old, new)
    (tmp_path / "resolved.json").write_text(json.dumps(entries), encoding="utf-8")
    records, _ = import_ris(tmp_path / "mended.ris")
    record = {r.id: r for r in records}[NEURIPS]
    assert record.title == "Synthetic Trust Bench mark for Language Models"
    [title] = record.claims("title")
    assert title.evidence == "mended.ris:TI (2 control characters replaced by a space)"
    untouched = {r.id: r for r in import_ris(FIXTURE / "mended.ris")[0]}[NEURIPS]
    assert [c.evidence for c in untouched.claims("title")] == ["mended.ris:TI"]
