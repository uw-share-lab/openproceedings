"""Dedup: merge order, never-merge rules, precedence and the audit rows (dedup-rules skill)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from openproceedings.ingest import urls
from openproceedings.ingest.dedup import (
    CONFLICT_FIELDS,
    PRECEDENCE,
    Attribution,
    Conflict,
    Merge,
    abstract_claim,
    attribution,
    dedup,
    resolve,
    title_key,
)
from openproceedings.ingest.record import Claim, PaperRecord

T0 = datetime(2026, 9, 1, tzinfo=UTC)
T1 = datetime(2026, 9, 2, tzinfo=UTC)
T2 = datetime(2026, 9, 3, tzinfo=UTC)
H = {n: f"{n:x}" * 32 for n in range(1, 6)}


def nips(n: int) -> str:
    return f"https://proceedings.neurips.cc/paper_files/paper/2024/hash/{H[n]}-Abstract-Conference.html"


def self_url(native: str, year: int) -> str | None:
    """The proceedings URL a proceedings-id record names itself by (dedup requires one)."""
    prefix, _, rest = native.partition("-")
    if prefix == "nips" and rest.endswith(("-round1", "-round2")):  # the 2021 D&B host (TASK-118)
        sha, _, rnd = rest.partition("-")
        host = "https://datasets-benchmarks-proceedings.neurips.cc"
        return f"{host}/paper_files/paper/{year}/hash/{sha}-Abstract-{rnd}.html"
    if prefix in ("nips", "iclr"):
        host = "neurips" if prefix == "nips" else "iclr"
        return f"https://proceedings.{host}.cc/paper_files/paper/{year}/hash/{rest}-Abstract-Conference.html"
    if prefix == "pmlr":
        volume, _, key = rest.partition("-")
        return f"https://proceedings.mlr.press/{volume}/{key}.html"
    return None


def paper(
    native: str,
    title: str = "Trust in AI",
    *,
    source: str = "openreview_v2",
    venue: str = "NeurIPS",
    year: int = 2024,
    track: str = "main",
    status: str = "accepted",
    abstract: str | None = None,
    fetched: datetime = T0,
    **extra: Any,  # further claim fields, e.g. `urls_proceedings=nips(1)`
) -> PaperRecord:
    """A record whose fields are exactly what its claims say (as every importer builds them); a
    proceedings-id record names itself in `urls.proceedings` unless the caller says otherwise."""
    extra.setdefault("urls_proceedings", self_url(native, year))
    values: dict[str, Any] = {"title": title, "venue": venue, "year": year, "track": track, "status": status,
                              "abstract": abstract, **{k.replace("urls_", "urls.", 1): v for k, v in extra.items()}}  # fmt: skip
    claims = [
        Claim(field=f, value=v, source=source, fetched_at=fetched) for f, v in values.items() if v is not None
    ]  # type: ignore[arg-type]
    record, _ = resolve(f"op:{venue.lower()}:{year}:{native}", claims)
    return record


def resolutions(result: Any) -> list[str]:
    return [c.resolution for c in result.conflicts]


def test_title_key_is_the_token_contract() -> None:
    assert (
        title_key("Trust in AI!")
        == title_key("trust  in ai")
        == title_key("Trust in \\textbf{AI}")
        == "trust in ai"
    )
    assert title_key("—") == ""


def test_the_precedence_table_is_decision_005() -> None:
    text = ("openreview_v2", "openreview_v1", "iclr_archive", "neurips_proceedings", "pmlr", "ris")
    assert PRECEDENCE["status"] == (
        "iclr_archive",
        "neurips_proceedings",
        "pmlr",
        "openreview_v2",
        "openreview_v1",
        "ris",
    )
    assert all(PRECEDENCE[f] == text for f in PRECEDENCE if f != "status")
    assert CONFLICT_FIELDS == ("title", "track", "status")


# --- step 1: identical ids ---------------------------------------------------------------------------


def test_same_forum_id_merges_across_the_two_searches_newest_claim_wins() -> None:
    old = paper("AbCd1234", source="ris", status="unknown", abstract="Old.", fetched=T0)
    new = paper("AbCd1234", source="ris", status="accepted", abstract="New.", fetched=T1)
    result = dedup([new, old])
    [r] = result.records
    assert (r.status, r.abstract) == ("accepted", "New.")
    assert result.merges == (Merge(r.id, r.id, "forum_id", "AbCd1234", "NeurIPS", 2024, "ris"),)
    # every field that changed between the searches is visible, not just the conflict fields
    assert set(result.conflicts) == {
        Conflict(r.id, "status", "accepted", "ris", "unknown", "ris", "newest:ris"),
        Conflict(r.id, "abstract", "New.", "ris", "Old.", "ris", "newest:ris"),
    }


def test_same_moment_disagreement_is_a_tie_not_newest() -> None:
    result = dedup(
        [
            paper("AbCd1234", source="ris", status="accepted"),
            paper("AbCd1234", source="ris", status="unknown"),
        ]
    )
    assert resolutions(result) == ["tie:ris"]


def test_newest_is_by_fetch_time_not_by_claim_url() -> None:
    base = paper("AbCd1234", source="ris")
    old = Claim(field="urls.pdf", value="https://x/old.pdf", source="ris", url="https://z", fetched_at=T0)
    new = Claim(field="urls.pdf", value="https://x/new.pdf", source="ris", url="https://a", fetched_at=T1)
    merged, rows = resolve(base.id, [*base.provenance, old, new])
    assert merged.urls.pdf == "https://x/new.pdf"
    assert [r.resolution for r in rows] == ["newest:ris"]


def test_a_tie_between_values_that_print_alike_is_still_a_tie() -> None:
    a = paper("AbCd1234", source="ris", authors=("Smith; J",))
    b = paper("AbCd1234", source="ris", authors=("Smith", "J"))
    result = dedup([a, b])
    assert [(c.field, c.resolution) for c in result.conflicts] == [("authors", "tie:ris")]
    assert dedup([b, a]) == result


def test_newest_is_by_fetch_time_not_by_url() -> None:
    old = paper("AbCd1234", source="ris", fetched=T0, urls_pdf="https://z.example/old.pdf")
    new = paper("AbCd1234", source="ris", fetched=T1, urls_pdf="https://a.example/new.pdf")
    [r] = dedup([old, new]).records
    assert r.urls.pdf == "https://a.example/new.pdf"


def test_same_proceedings_id_merges() -> None:
    result = dedup(
        [paper(f"nips-{H[1]}", source="ris", fetched=T0), paper(f"nips-{H[1]}", source="ris", fetched=T1)]
    )
    assert len(result.records) == 1
    assert [(m.rule, m.key) for m in result.merges] == [("native_id", f"nips-{H[1]}")]


def test_same_forum_id_in_different_years_is_not_merged() -> None:
    result = dedup([paper("AbCd1234", year=2023), paper("AbCd1234", year=2024), paper("AbCd1234", year=2025)])
    assert len(result.records) == 3 and not result.merges
    assert [(c.field, c.value_b, c.resolution) for c in result.conflicts] == [
        ("forum_id", "op:neurips:2024:AbCd1234", "venue_year_not_merged"),
        ("forum_id", "op:neurips:2025:AbCd1234", "venue_year_not_merged"),
    ]


# --- step 2: title, venue, year across sources --------------------------------------------------------


def test_openreview_and_proceedings_merge_on_title_with_precedence() -> None:
    orv = paper("AbCd1234", "Trust in AI", status="rejected", abstract="OpenReview abstract.")
    proc = paper(
        f"nips-{H[1]}", "Trust in \\textbf{AI}", source="neurips_proceedings", abstract="Proc abstract."
    )
    result = dedup([proc, orv])
    [r] = result.records
    assert r.id == orv.id  # the forum id survives
    assert (r.title, r.abstract) == ("Trust in AI", "OpenReview abstract.")  # OpenReview first for text
    assert r.status == "accepted"  # the proceedings decide acceptance
    assert {c.source for c in r.provenance} == {"openreview_v2", "neurips_proceedings"}  # every claim kept
    assert result.merges == (
        Merge(orv.id, proc.id, "title_venue_year", "trust in ai", "NeurIPS", 2024, "neurips_proceedings"),
    )
    # the titles differ only in markup (same key): no title row, per decision-005
    assert [(c.field, c.resolution) for c in result.conflicts] == [
        ("status", "precedence:neurips_proceedings")
    ]


def test_a_real_title_difference_is_a_conflict_row() -> None:
    orv = paper("AbCd1234", "Trust in AI")
    result = dedup([orv, paper("AbCd1234", "Trust in Machines", source="ris")])
    expected = Conflict(
        orv.id,
        "title",
        "Trust in AI",
        "openreview_v2",
        "Trust in Machines",
        "ris",
        "precedence:openreview_v2",
    )
    assert expected in result.conflicts


def test_openreview_track_beats_the_proceedings_track() -> None:
    result = dedup([paper("AbCd1234", track="position"), paper(f"nips-{H[1]}", source="neurips_proceedings")])
    [r] = result.records
    assert r.track == "position"
    assert ("track", "precedence:openreview_v2") in [(c.field, c.resolution) for c in result.conflicts]


def test_datasets_track_merges_into_proceedings() -> None:
    result = dedup([paper("AbCd1234", track="datasets_benchmarks"),
                    paper(f"nips-{H[1]}", source="neurips_proceedings", track="datasets_benchmarks")])  # fmt: skip
    assert len(result.records) == 1


# --- decision-005 §Track: "on OpenReview" is per track (owner, 2026-09-29; TASK-130) --------------------------

ARXIV = "https://arxiv.org/abs/1511.06644"


def archive(year: int = 2016, title: str = "Trust in AI", **kw: Any) -> PaperRecord:
    """An ICLR archive main-track listing, named as the archive names it (an arXiv target's `iclr-` id)."""
    target = urls.iclr_archive_target(ARXIV)
    assert target is not None
    return paper(
        target[0], title, source="iclr_archive", venue="ICLR", year=year, urls_proceedings=ARXIV, **kw
    )


def test_iclr_2016_main_from_the_archive_keeps_main() -> None:
    # OpenReview holds only ICLR 2016's workshop track: its notes carry no decision (status unknown)
    ws = dict(venue="ICLR", year=2016, source="openreview_v1", track="workshop", status="unknown")
    listing, same_title, other = (
        archive(),
        paper("AbCd1234", **ws),
        paper("EfGh5678", "A workshop paper", **ws),
    )
    result = dedup([listing, same_title, other])
    got = {r.id: (r.track, r.status) for r in result.records}
    assert got == {listing.id: ("main", "accepted"), same_title.id: ("workshop", "unknown"),
                   other.id: ("workshop", "unknown")}  # fmt: skip
    assert result.merges == () and "track_not_merged" in resolutions(result)
    assert not [
        c for c in result.conflicts if c.field == "track"
    ]  # no track claim competes with the archive's


@pytest.mark.parametrize(
    ("or_source", "venue", "year", "or_track", "listing", "listing_track"),
    [
        ("openreview_v2", "NeurIPS", 2023, "datasets_benchmarks", "neurips_proceedings", "main"),
        ("openreview_v1", "NeurIPS", 2022, "main", "neurips_proceedings", "datasets_benchmarks"),
        ("openreview_v2", "ICML", 2025, "position", "pmlr", "unknown"),  # a mixed volume says no track
        ("openreview_v1", "ICLR", 2014, "main", "iclr_archive", "main"),  # the archive agrees: no row
    ],
)
def test_where_openreview_holds_the_track_its_claim_beats_the_proceedings(
    or_source: str, venue: str, year: int, or_track: str, listing: str, listing_track: str
) -> None:
    note = paper("AbCd1234", source=or_source, venue=venue, year=year, track=or_track)
    if listing == "iclr_archive":
        proc = archive(year)
    else:
        native = "pmlr-v267-key1" if listing == "pmlr" else f"nips-{H[1]}"
        proc = paper(native, source=listing, venue=venue, year=year, track=listing_track)
    result = dedup([proc, note])
    [r] = result.records
    assert (r.id, r.track, r.status) == (note.id, or_track, "accepted")
    rows = [
        (c.value_a, c.source_a, c.value_b, c.source_b, c.resolution)
        for c in result.conflicts
        if c.field == "track"
    ]
    expected = [(or_track, or_source, listing_track, listing, f"precedence:{or_source}")]
    assert rows == (expected if or_track != listing_track else [])
    assert dedup(result.records) == dedup(result.records[::-1])
    assert dedup(result.records).records == result.records  # idempotent


def test_a_listing_openreview_does_not_hold_keeps_its_own_track_in_a_track_openreview_holds() -> None:
    # NeurIPS 2025: OpenReview holds Creative AI (`other`) and D&B, but not these two papers (one renamed for the
    # camera-ready): the listings answer their own track; the note under the old title stays a record of its own
    db = dict(venue="NeurIPS", year=2025, track="datasets_benchmarks")
    creative = paper(f"nips-{H[1]}", "A Creative AI piece", source="neurips_proceedings", venue="NeurIPS",
                     year=2025, track="other")  # fmt: skip
    renamed = paper(f"nips-{H[2]}", "The camera-ready title", source="neurips_proceedings", **db)
    note = paper("AbCd1234", "The submitted title", **db)
    result = dedup([creative, renamed, note])
    assert {r.id: r.track for r in result.records} == {
        creative.id: "other",
        renamed.id: "datasets_benchmarks",
        note.id: "datasets_benchmarks",
    }
    assert result.merges == () and result.conflicts == ()


def test_an_openreview_note_with_no_track_never_merges_into_a_listing() -> None:
    # `unknown` names no track OpenReview holds; dedup keeps the note apart, so it never overrules the listing
    listing = paper(f"nips-{H[1]}", source="neurips_proceedings")
    note = paper("AbCd1234", track="unknown")
    result = dedup([listing, note])
    assert {r.id: r.track for r in result.records} == {listing.id: "main", note.id: "unknown"}
    assert resolutions(result) == ["track_not_merged"]


@pytest.mark.parametrize(
    ("why", "a", "b"),
    [
        ("different year", paper("AbCd1234"), paper(f"nips-{H[1]}", source="neurips_proceedings", year=2023)),
        (
            "different venue",
            paper("AbCd1234", venue="ICLR"),
            paper(f"nips-{H[1]}", source="neurips_proceedings"),
        ),
        (
            "different title",
            paper("AbCd1234", "Trust"),
            paper(f"nips-{H[1]}", "Reliance", source="neurips_proceedings"),
        ),
        ("empty title key", paper("AbCd1234", "—"), paper(f"nips-{H[1]}", "—", source="neurips_proceedings")),
    ],
)
def test_no_shared_key_never_merges(why: str, a: PaperRecord, b: PaperRecord) -> None:
    result = dedup([a, b])
    assert len(result.records) == 2 and not result.merges and not result.conflicts


@pytest.mark.parametrize(
    ("why", "records", "resolution"),
    [
        (
            "two OpenReview submissions with one title",
            [paper("AbCd1234"), paper("EfGh5678")],
            "ambiguous_not_merged",
        ),
        (
            "different forum ids across sources",
            [paper("AbCd1234"), paper("EfGh5678", source="ris")],
            "ambiguous_not_merged",
        ),
        (
            "two proceedings ids across sources",
            [paper(f"nips-{H[1]}", source="neurips_proceedings"), paper(f"nips-{H[2]}", source="ris")],
            "ambiguous_not_merged",
        ),
        (
            "a proceedings URL on the OpenReview side names another paper",
            [paper("AbCd1234", urls_proceedings=nips(1)), paper(f"nips-{H[2]}", source="ris")],
            "ambiguous_not_merged",
        ),
        (
            "a workshop paper into a proceedings source",
            [paper("AbCd1234", track="workshop"), paper(f"nips-{H[1]}", source="neurips_proceedings")],
            "track_not_merged",
        ),
        (
            "a workshop paper into a RIS proceedings listing",
            [paper("AbCd1234", track="workshop"), paper(f"nips-{H[1]}", source="ris")],
            "track_not_merged",
        ),
        (
            "an unknown track waits for evidence",
            [
                paper("AbCd1234", source="ris", track="unknown"),
                paper(f"nips-{H[1]}", source="neurips_proceedings"),
            ],
            "track_not_merged",
        ),
    ],
)
def test_never_merge(why: str, records: list[PaperRecord], resolution: str) -> None:
    result = dedup(records)
    assert len(result.records) == len(records) and not result.merges
    assert set(resolutions(result)) == {resolution}


def db21(native: str, title: str = "Trust in AI", **kw: Any) -> PaperRecord:
    """A NeurIPS 2021 Datasets and Benchmarks record (TASK-118: its D&B-host ids carry the round)."""
    kw.setdefault("source", "neurips_proceedings")
    return paper(native, title, year=2021, track=kw.pop("track", "datasets_benchmarks"), **kw)


def test_a_round_qualified_db_listing_merges_with_its_openreview_submission() -> None:
    result = dedup([db21("AbCd1234", source="openreview_v1"), db21(f"nips-{H[1]}-round1")])
    [r] = result.records
    assert r.id == "op:neurips:2021:AbCd1234" and len(result.merges) == 1


# equal titles: main↔round1 and main↔round2 each refused; different titles: only the two rounds (whose
# titles still match each other) are refused
@pytest.mark.parametrize(("title_b", "refused"), [("Trust in AI", 2), ("Reliance on AI", 1)])
def test_one_hash_on_the_main_host_and_in_each_db_round_is_three_papers(title_b: str, refused: int) -> None:
    """md5 of a per-site paper number: the same hash names a main-track paper and one paper per D&B round.
    The sources differ, so the title step does run; it refuses each title match (two proceedings ids)."""
    records = [
        db21(f"nips-{H[1]}", track="main", source="ris"),
        db21(f"nips-{H[1]}-round1", title_b),
        db21(f"nips-{H[1]}-round2", title_b),
    ]
    result = dedup(records)
    assert sorted(r.id for r in result.records) == sorted(r.id for r in records) and not result.merges
    assert [(c.field, c.resolution) for c in result.conflicts] == [
        ("title_key", "ambiguous_not_merged")
    ] * refused


def test_an_openreview_record_naming_the_main_host_hash_is_not_merged_into_the_db_paper() -> None:
    main_url = f"https://proceedings.neurips.cc/paper_files/paper/2021/hash/{H[1]}-Abstract.html"
    result = dedup([db21("AbCd1234", source="openreview_v1", urls_proceedings=main_url),
                    db21(f"nips-{H[1]}-round1")])  # fmt: skip
    assert len(result.records) == 2 and not result.merges
    assert set(resolutions(result)) == {"ambiguous_not_merged"}


def test_three_way_with_two_proceedings_ids_is_refused() -> None:
    result = dedup([paper("AbCd1234"), paper(f"nips-{H[1]}", source="neurips_proceedings"),
                    paper(f"nips-{H[2]}", source="ris")])  # fmt: skip
    assert len(result.records) == 3 and not result.merges


def test_two_candidates_from_one_source_are_ambiguous() -> None:
    result = dedup([paper("AbCd1234"), paper(f"nips-{H[1]}", source="neurips_proceedings"),
                    paper(f"nips-{H[2]}", source="neurips_proceedings")])  # fmt: skip
    assert len(result.records) == 3 and not result.merges
    assert set(resolutions(result)) == {"ambiguous_not_merged"}


def test_three_sources_merge_into_one_and_merges_csv_shows_each_rule() -> None:
    result = dedup([paper("AbCd1234"), paper(f"nips-{H[1]}", source="neurips_proceedings"),
                    paper(f"nips-{H[1]}", source="ris")])  # fmt: skip
    [r] = result.records
    assert r.id == "op:neurips:2024:AbCd1234"
    proc = f"op:neurips:2024:nips-{H[1]}"
    assert [(m.survivor_id, m.merged_id, m.rule) for m in result.merges] == [
        (r.id, proc, "title_venue_year"),  # the proceedings cluster joins the OpenReview record
        (proc, proc, "native_id"),  # its two copies (proceedings crawl and RIS) were one id first
    ]


# --- TASK-126: a cluster that cannot be the listed paper is no rival -----------------------------------


def test_a_same_title_workshop_paper_does_not_block_the_main_track_merge() -> None:
    """NeurIPS 2023/2024: a proceedings listing, its main-track note and an accepted workshop note of the
    same title. The workshop note can never be the listed paper (the track rule), so the pair merges."""
    orv, proc = paper("AbCd1234"), paper(f"nips-{H[1]}", source="neurips_proceedings")
    workshop = paper("EfGh5678", track="workshop")
    result = dedup([workshop, proc, orv])
    assert sorted(r.id for r in result.records) == sorted([orv.id, workshop.id])
    assert result.merges == (
        Merge(orv.id, proc.id, "title_venue_year", "trust in ai", "NeurIPS", 2024, "neurips_proceedings"),
    )
    assert [(c.field, c.value_a, c.value_b, c.resolution) for c in result.conflicts] == [
        ("title_key", orv.id, workshop.id, "track_not_merged")
    ]
    again = dedup(result.records)
    assert (again.records, again.conflicts, again.merges) == (result.records, result.conflicts, ())


def test_a_rejected_round_one_note_does_not_block_its_accepted_resubmission() -> None:
    """NeurIPS 2021 D&B: a round-1 rejection resubmitted (another forum, another pdf) and accepted in round
    2. Proceedings list only accepted papers, so the rejected note is no rival for the listing."""
    accepted = db21("AbCd1234", source="openreview_v1")
    rejected = db21("EfGh5678", source="openreview_v1", status="rejected")
    listing = db21(f"nips-{H[1]}-round2")
    result = dedup([rejected, listing, accepted])
    assert sorted(r.id for r in result.records) == sorted([accepted.id, rejected.id])
    assert [(m.survivor_id, m.merged_id) for m in result.merges] == [(accepted.id, listing.id)]
    assert [(c.field, c.value_a, c.value_b, c.resolution) for c in result.conflicts] == [
        ("title_key", accepted.id, rejected.id, "ambiguous_not_merged")
    ]
    assert dedup(result.records).records == result.records


@pytest.mark.parametrize("status", ["rejected", "withdrawn", "desk_rejected"])
def test_every_not_accepted_status_is_no_rival(status: str) -> None:
    result = dedup([paper("AbCd1234"), paper("EfGh5678", status=status),
                    paper(f"nips-{H[1]}", source="neurips_proceedings")])  # fmt: skip
    assert [(m.survivor_id, m.rule) for m in result.merges] == [
        ("op:neurips:2024:AbCd1234", "title_venue_year")
    ]


@pytest.mark.parametrize(
    ("why", "rival"),
    [
        ("two accepted main-track submissions", paper("EfGh5678")),
        (
            "an accepted D&B submission",
            paper("EfGh5678", source="openreview_v1", track="datasets_benchmarks"),
        ),
        ("a status nobody knows yet: it may be the listed paper", paper("EfGh5678", status="unknown")),
        ("a track nobody knows yet: it may be the listed paper", paper("EfGh5678", track="unknown")),
        ("a rejected note that is itself a listing", paper(f"nips-{H[2]}", source="ris", status="rejected")),
    ],
)
def test_a_rival_that_may_be_the_listed_paper_still_refuses(why: str, rival: PaperRecord) -> None:
    records = [paper("AbCd1234"), paper(f"nips-{H[1]}", source="neurips_proceedings"), rival]
    result = dedup(records)
    assert len(result.records) == 3 and not result.merges
    assert result.conflicts and all(c.resolution.endswith("_not_merged") for c in result.conflicts)


def test_a_rejected_note_alone_still_merges_with_its_listing() -> None:
    """Only a rival is set aside: a lone OpenReview note the proceedings list merges, and the proceedings
    decide its status (decision-005)."""
    result = dedup(
        [paper("EfGh5678", status="rejected"), paper(f"nips-{H[1]}", source="neurips_proceedings")]
    )
    [r] = result.records
    assert r.status == "accepted"


def test_without_a_listing_nothing_is_set_aside() -> None:
    main, workshop, rejected = (
        paper("AbCd1234"),
        paper("EfGh5678", track="workshop"),
        paper("IjKl9012", status="rejected", source="ris"),
    )
    result = dedup([main, workshop, rejected])
    assert len(result.records) == 3 and not result.merges
    assert [(c.value_a, c.value_b, c.resolution) for c in result.conflicts] == [
        (main.id, workshop.id, "ambiguous_not_merged"),
        (main.id, rejected.id, "ambiguous_not_merged"),
    ]


def test_a_rejected_note_chained_back_in_by_a_second_key_splits_the_chain() -> None:
    """The rejected note is set aside on "Trust in AI" but shares "Trust in Machines" with the listing,
    where it would merge alone (status is no bar to `_mergeable`). The chain re-check refuses the whole
    chain on forum ids (every non-listing record has its own; here a shared source too), so nothing merges: the safe direction."""
    accepted = paper("AbCd1234", "Trust in AI")
    listing = [paper(f"nips-{H[1]}", "Trust in AI", source="neurips_proceedings"),
               paper(f"nips-{H[1]}", "Trust in Machines", source="ris")]  # fmt: skip
    rejected = [paper("EfGh5678", "Trust in AI", source="openreview_v1", status="rejected"),
                paper("EfGh5678", "Trust in Machines", status="rejected")]  # fmt: skip
    result = dedup([*rejected, *listing, accepted])
    lid, rid = listing[0].id, rejected[0].id
    assert sorted(r.id for r in result.records) == sorted([accepted.id, lid, rid])
    assert sorted(m.rule for m in result.merges) == ["forum_id", "native_id"]  # step 1 only
    rows = {(c.field, c.value_a, c.value_b, c.resolution) for c in result.conflicts}
    assert ("title_key", lid, rid, "ambiguous_not_merged") in rows  # the set-aside note keeps its row
    assert dedup(result.records).records == result.records


def test_a_workshop_note_set_aside_on_one_key_never_chains_in_on_another() -> None:
    """The workshop note is set aside on "Trust in AI" and also shares "Trust in Machines" with the
    listing; that key's group meets the same track rule, so it never chains in and the pair still merges."""
    accepted = paper("AbCd1234", "Trust in AI")
    listing = [paper(f"nips-{H[1]}", "Trust in AI", source="neurips_proceedings"),
               paper(f"nips-{H[1]}", "Trust in Machines", source="ris")]  # fmt: skip
    workshop = [paper("EfGh5678", "Trust in AI", source="openreview_v1", track="workshop"),
                paper("EfGh5678", "Trust in Machines", track="workshop")]  # fmt: skip
    result = dedup([*workshop, *listing, accepted])
    wid = workshop[0].id
    assert sorted(r.id for r in result.records) == sorted([accepted.id, wid])
    assert (accepted.id, listing[0].id, "title_venue_year") in [
        (m.survivor_id, m.merged_id, m.rule) for m in result.merges
    ]
    assert [
        (c.field, c.value_a, c.value_b, c.resolution) for c in result.conflicts if c.field == "title_key"
    ] == [("title_key", accepted.id, wid, "track_not_merged")]  # one row, though the two share both keys
    assert dedup(result.records).records == result.records


def test_keys_that_chain_forbidden_clusters_merge_nothing() -> None:
    # One paper known under two titles (OpenReview and RIS share its forum id); each title matches a
    # different proceedings record. Each pair is fine alone, but together two proceedings records would
    # fold into one paper.
    orv = paper("AbCd1234", "Trust in AI")
    ris = paper("AbCd1234", "Trust in Machines", source="ris")
    p1 = paper(f"nips-{H[1]}", "Trust in AI", source="neurips_proceedings")
    p2 = paper(f"nips-{H[2]}", "Trust in Machines", source="neurips_proceedings")
    result = dedup([orv, ris, p1, p2])
    assert sorted(r.id for r in result.records) == sorted({orv.id, p1.id, p2.id})
    assert [m.rule for m in result.merges] == ["forum_id"]
    assert ("title_key_chain", "ambiguous_not_merged") in [(c.field, c.resolution) for c in result.conflicts]


def test_a_merge_row_names_the_first_shared_key() -> None:
    # both clusters carry both titles, so they share two keys; merges.csv names the first, in key order
    orv = [paper("AbCd1234", "Trust in Machines"), paper("AbCd1234", "Trust in AI", source="openreview_v1")]
    proc = [paper(f"nips-{H[1]}", "Trust in AI", source="neurips_proceedings"),
            paper(f"nips-{H[1]}", "Trust in Machines", source="ris")]  # fmt: skip
    result = dedup([*orv, *proc])
    [title] = [m for m in result.merges if m.rule == "title_venue_year"]
    assert title.key == "trust in ai"


def test_a_superseded_title_is_reported_not_matched() -> None:
    # Matching on the older title would merge here but not on a second run (the merged record no longer
    # carries it), so it stays a duplicate, the safe direction, with the old title in conflicts.csv.
    old = paper(f"nips-{H[1]}", "Old Title", source="ris", fetched=T0)
    new = paper(f"nips-{H[1]}", "New Title", source="ris", fetched=T1)
    result = dedup([old, new, paper("AbCd1234", "Old Title")])
    assert len(result.records) == 2
    assert ("title", "New Title", "Old Title", "newest:ris") in [
        (c.field, c.value_a, c.value_b, c.resolution) for c in result.conflicts
    ]


def test_conflicts_survive_a_rerun() -> None:
    once = dedup([paper("AbCd1234", status="rejected"), paper(f"nips-{H[1]}", source="neurips_proceedings")])
    twice = dedup(once.records)
    precedence = [c for c in once.conflicts if c.resolution.startswith("precedence:")]
    assert precedence and [c for c in twice.conflicts if c.resolution.startswith("precedence:")] == precedence


def test_a_proceedings_record_must_name_itself() -> None:
    with pytest.raises(ValueError, match="name itself"):
        dedup([paper(f"nips-{H[1]}", source="neurips_proceedings", urls_proceedings=None)])
    with pytest.raises(ValueError, match="name itself"):
        dedup([paper(f"nips-{H[1]}", source="neurips_proceedings", urls_proceedings=nips(2))])


def test_a_merged_record_remembers_the_listing_it_absorbed() -> None:
    # nips-1 merges into the forum record; on a second run the merged record must still refuse nips-2
    xs = [
        paper("AbCd1234", "Trust in AI"),
        paper(f"nips-{H[1]}", "Trust in AI", source="neurips_proceedings"),
        paper(f"nips-{H[1]}", "Trust in Machines", source="ris"),
        paper(f"nips-{H[2]}", "Trust in Machines", source="openreview_v1"),
    ]
    once = dedup(xs)
    assert dedup(once.records).records == once.records
    assert len(once.records) == 2


def test_icml_papers_merge_with_a_mixed_pmlr_volume() -> None:
    orv = paper("AbCd1234", venue="ICML", track="main")
    pmlr = paper("pmlr-v235-smith24a", venue="ICML", source="pmlr", track="unknown")
    [r] = dedup([orv, pmlr]).records
    assert (r.id, r.track) == (orv.id, "main")  # OpenReview's track, the volume's unknown overruled
    workshop = paper("AbCd1234", venue="ICML", track="workshop")
    assert len(dedup([workshop, pmlr]).records) == 2  # but a workshop paper still never joins it


def test_an_old_style_proceedings_url_names_its_paper() -> None:
    old = "https://proceedings.neurips.cc/paper/2021/file/" + H[2].upper() + "-Paper.pdf"
    orv = paper("AbCd1234", year=2021, urls_pdf=old)
    proc = paper(f"nips-{H[1]}", source="neurips_proceedings", year=2021)
    assert len(dedup([orv, proc]).records) == 2  # the forum's PDF is another NeurIPS paper
    hexed = "abcdef" * 5 + "ab"
    upper = f"https://proceedings.neurips.cc/paper/2021/file/{hexed.upper()}-Paper.pdf"
    listing = paper(f"nips-{hexed}", source="neurips_proceedings", year=2021)
    same = paper("AbCd1234", year=2021, urls_pdf=upper)
    assert len(dedup([same, listing]).records) == 1  # upper-case hex names the same paper


# --- the forum link (TASK-105): a proceedings listing that names its OpenReview forum ------------------


def forum(fid: str) -> str:
    return f"https://openreview.net/forum?id={fid}"


def linked(key: str = "key1", fid: str = "AbCd1234", title: str = "Trust in AI", **kw: Any) -> PaperRecord:
    """A PMLR v235 listing whose index links the OpenReview forum `fid` (track unknown: v235 mixes tracks)."""
    kw.setdefault("track", "unknown")
    return paper(
        f"pmlr-v235-{key}", title, source="pmlr", venue="ICML", year=2024, urls_forum=forum(fid), **kw
    )


def icml(fid: str = "AbCd1234", title: str = "Trust in AI", **kw: Any) -> PaperRecord:
    kw.setdefault("venue", "ICML")
    return paper(fid, title, urls_forum=forum(fid), **kw)


@pytest.mark.parametrize(
    ("url", "fid"),
    [
        (forum("AbCd1234"), "AbCd1234"),
        ("http://OpenReview.net/forum?id=AbCd1234", "AbCd1234"),  # any host case, http
        ("https://openreview.net/forum?id=AbCd1234&noteId=XyZ9876", "AbCd1234"),  # a reply anchor
        ("https://openreview.net/forum?id=false", "false"),  # the shape is all a URL can check
        ("https://openreview.net/pdf?id=AbCd1234", None),  # the PDF, not the forum
        ("https://openreview.net/forum?id=AbCd1234&id=EfGh5678", None),  # two ids: which one?
        ("https://openreview.net/forum?id=a", None),  # too short for a forum id
        ("https://openreview.net/forum", None),
        ("https://api2.openreview.net/forum?id=AbCd1234", None),
        ("https://example.org/forum?id=AbCd1234", None),
        ("ftp://openreview.net/forum?id=AbCd1234", None),
    ],
)
def test_forum_id_from_a_url(url: str, fid: str | None) -> None:
    assert urls.forum_id(url) == fid


def test_the_link_merges_whatever_the_titles_say() -> None:
    orv, listing = icml(title="Trust in AI", status="rejected"), linked(title="Reliance on machines")
    result = dedup([listing, orv])
    [r] = result.records
    assert r.id == orv.id  # the forum id survives
    assert (r.title, r.track, r.status) == ("Trust in AI", "main", "accepted")  # decision-005 precedence
    assert r.urls.proceedings == "https://proceedings.mlr.press/v235/key1.html"
    assert result.merges == (Merge(orv.id, listing.id, "forum_link", "AbCd1234", "ICML", 2024, "pmlr"),)
    assert set(resolutions(result)) == {"precedence:openreview_v2", "precedence:pmlr"}  # title, status
    again = dedup(result.records)
    assert again.records == result.records and not again.merges


def test_the_link_comes_before_the_title_and_joins_every_copy() -> None:
    """The OpenReview note, its RIS copy and the linked listing: one record, every step in merges.csv."""
    orv = icml()
    result = dedup(
        [orv, paper("AbCd1234", "Trust in AI!", source="ris", venue="ICML"), linked(title="Other")]
    )
    assert [r.id for r in result.records] == [orv.id]
    assert [(m.survivor_id, m.merged_id, m.rule) for m in result.merges] == [
        (orv.id, orv.id, "forum_id"),  # the RIS copy of the same id
        (orv.id, "op:icml:2024:pmlr-v235-key1", "forum_link"),
    ]


@pytest.mark.parametrize(
    ("why", "records", "field", "resolution"),
    [
        (
            "the link names another year",
            [icml(year=2023), linked()],
            "forum_id",
            "venue_year_not_merged",
        ),
        (
            "the link names another venue",
            [icml(venue="ICLR"), linked()],
            "forum_id",
            "venue_year_not_merged",
        ),
        (
            "the linked note is a workshop paper",
            [icml(track="workshop"), linked(title="Reliance")],
            "forum_id",
            "track_not_merged",
        ),
        (
            "two listings link one forum",
            [icml(title="A"), linked("key1", title="B"), linked("key2", title="C")],
            "forum_id",
            "ambiguous_not_merged",
        ),
        (
            "the title matches but the link names another forum",
            [icml("AbCd1234"), linked(fid="EfGh5678")],
            "title_key",
            "ambiguous_not_merged",
        ),
    ],
)
def test_a_contradicted_link_never_merges(
    why: str, records: list[PaperRecord], field: str, resolution: str
) -> None:
    result = dedup(records)
    assert len(result.records) == len(records) and not result.merges
    assert {(c.field, c.resolution) for c in result.conflicts} == {(field, resolution)}
    assert dedup(result.records).conflicts == result.conflicts


def test_a_link_to_a_forum_that_is_absent_changes_nothing() -> None:
    listing = linked()
    assert dedup([listing]).records == (listing,)
    other = paper("EfGh5678", "Unrelated", venue="ICML")
    result = dedup([listing, other])
    assert len(result.records) == 2 and not result.merges and not result.conflicts


def test_records_must_match_their_claims() -> None:
    r = paper("AbCd1234")
    with pytest.raises(ValueError, match="own claims"):
        dedup([r.model_copy(update={"track": "workshop"})])
    with pytest.raises(ValueError, match="no claim for"):
        dedup([PaperRecord.build(id=r.id, title="T", abstract=None, authors=(), venue="NeurIPS", year=2024,
                                 track="main", status="accepted")])  # fmt: skip


@pytest.mark.parametrize(
    ("status", "presentation"),
    [
        ("accepted", "oral"),
        ("unknown", None),
        ("rejected", None),
        ("withdrawn", None),
        ("desk_rejected", None),
    ],
)
def test_presentation_holds_only_while_the_resolved_status_is_accepted(
    status: str, presentation: str | None
) -> None:
    record = paper("AbCd1234", status=status, presentation="oral")
    assert (record.status, record.presentation) == (status, presentation)
    assert any(
        c.field == "presentation" and c.value == "oral" for c in record.provenance
    )  # the claim is kept


def test_a_proceedings_status_that_outranks_openreview_accepted_drops_the_presentation() -> None:
    claims = [
        *paper("AbCd1234", presentation="spotlight").provenance,
        Claim(field="status", value="unknown", source="neurips_proceedings", fetched_at=T1),
    ]
    record, _ = resolve("op:neurips:2024:AbCd1234", claims)
    assert (record.status, record.presentation) == ("unknown", None)
    same = paper("AbCd1234")  # content_hash doesn't cover presentation
    assert record.content_hash == same.model_copy(update={"status": "unknown"}).content_hash


def _abstract(source: Any, value: str, url: str | None = None, evidence: str | None = None) -> Claim:
    return Claim(field="abstract", value=value, source=source, url=url, fetched_at=T0, evidence=evidence)


def test_abstract_claim_is_the_one_precedence_took_the_abstract_from() -> None:
    """TASK-134 (decision-018): the results list attributes an abstract to the claim `resolve` took it from."""
    pmlr = _abstract("pmlr", "Same text.", "https://proceedings.mlr.press/v162/a22a.html")
    ris = _abstract("ris", "Same text.")
    orv = _abstract("openreview_v2", "Same text.", "https://api2.openreview.net/notes?offset=0")
    assert abstract_claim("Same text.", [ris, pmlr]) == pmlr  # pmlr outranks ris
    assert abstract_claim("Same text.", [ris, pmlr, orv]) == orv  # OpenReview first (decision-005)
    scope = {"title": "Trust in AI", "venue": "ICML", "year": 2022, "track": "main", "status": "accepted"}
    base = [Claim(field=f, value=v, source="pmlr", fetched_at=T0) for f, v in scope.items()]  # type: ignore[arg-type]
    record, _ = resolve("op:icml:2022:pmlr-v162-a22a", [*base, pmlr, ris])
    assert abstract_claim(record.abstract, record.claims("abstract")) == pmlr  # the claim `resolve` chose


def test_abstract_claim_holds_the_abstracts_own_text() -> None:
    other = _abstract("openreview_v2", "A different abstract.")
    pmlr = _abstract("pmlr", "Shown text.", "https://proceedings.mlr.press/v162/a22a.html")
    # a better-ranked claim with other text is not the source of the text shown
    assert abstract_claim("Shown text.", [other, pmlr]) == pmlr
    assert abstract_claim("Shown text.", [other]) is None  # no claim holds it: unknown, never guessed
    assert abstract_claim("Shown text.", []) is None  # no provenance (a synthetic record)
    assert abstract_claim(None, [pmlr]) is None  # no abstract, nothing to attribute


FORUM = "https://openreview.net/forum?id=AbCd1234"
NIPS_PAGE = nips(1)
ICLR_PAGE = f"https://proceedings.iclr.cc/paper_files/paper/2024/hash/{H[2]}-Abstract-Conference.html"
PMLR_PAGE = "https://proceedings.mlr.press/v162/a22a.html"


@pytest.mark.parametrize(
    ("claim", "forum", "proceedings", "expected"),
    [
        # a direct claim: OpenReview's page is the forum (its claim url is the API listing)
        (_abstract("openreview_v1", "T", "https://api.openreview.net/notes"), FORUM, None,
         Attribution("openreview_v1", "openreview", FORUM)),
        (_abstract("pmlr", "T", PMLR_PAGE), None, PMLR_PAGE, Attribution("pmlr", "pmlr", PMLR_PAGE)),
        (_abstract("neurips_proceedings", "T", NIPS_PAGE), None, NIPS_PAGE,
         Attribution("neurips_proceedings", "neurips_proceedings", NIPS_PAGE)),
        # an `ris` claim: its evidence names the route, and the record's url the page
        (_abstract("ris", "T", evidence=f"scholarmend:proceedings_page {NIPS_PAGE}"), None, NIPS_PAGE,
         Attribution("ris", "neurips_proceedings", NIPS_PAGE)),
        (_abstract("ris", "T", evidence=f"scholarmend:proceedings_page {ICLR_PAGE}"), None, ICLR_PAGE,
         Attribution("ris", "iclr_proceedings", ICLR_PAGE)),
        (_abstract("ris", "T", evidence=f"scholarmend:proceedings_page {PMLR_PAGE}"), None, PMLR_PAGE,
         Attribution("ris", "pmlr", PMLR_PAGE)),
        (_abstract("ris", "T", evidence="scholarmend:openreview_api openreview:AbCd1234"), FORUM, None,
         Attribution("ris", "openreview", FORUM)),
        # a route that names no known site, or a proceedings route with no proceedings url: named, not linked
        (_abstract("ris", "T", evidence="scholarmend:semantic_scholar s2:1"), FORUM, NIPS_PAGE,
         Attribution("ris", None, None)),
        (_abstract("ris", "T", evidence="scholarmend:proceedings_page"), None, None, Attribution("ris", None, None)),
        # no proceedings link: the evidence's (possibly cut) url still names the site, unlinked
        (_abstract("ris", "T", evidence=f"scholarmend:proceedings_page {NIPS_PAGE.split('-Abstract')[0]}"), None,
         None, Attribution("ris", "neurips_proceedings", None)),
        (_abstract("ris", "T", evidence="scholarmend:proceedings_page https://example.org/p"), None,
         "https://example.org/p", Attribution("ris", None, None)),
        (_abstract("ris", "T"), FORUM, NIPS_PAGE, Attribution("ris", None, None)),
    ],
)  # fmt: skip
def test_attribution_names_the_site_and_its_page(
    claim: Claim, forum: str | None, proceedings: str | None, expected: Attribution
) -> None:
    assert attribution("T", [claim], forum=forum, proceedings=proceedings) == expected
    assert attribution(None, [claim], forum=forum, proceedings=proceedings) is None
