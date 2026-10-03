"""Reconciling OpenReview acceptance against the crawled proceedings (decision-005; TASK-072): table tests,
then properties over dedup's colliding pools (dedup-rules skill §Reconcile)."""

from __future__ import annotations

from collections import Counter

from hypothesis import event, example, given
from hypothesis import strategies as st
from openproceedings.ingest.dedup import DedupResult, dedup, is_absence, resolve
from openproceedings.ingest.reconcile import Crawl, Key, Listing, crawled, reconcile
from openproceedings.ingest.record import PaperRecord
from openproceedings.ingest.sources.common import ListingReport

from tests.unit.ingest.test_dedup import T0, T1, T2, H, archive, creative_listing, creative_note, nips, paper
from tests.unit.ingest.test_dedup_props import pools, records

LISTING = "https://proceedings.neurips.cc/paper_files/paper/2024"


def crawl(
    source: str = "neurips_proceedings", venue: str = "NeurIPS", year: int = 2024,
    tracks: tuple[str, ...] = ("main", "datasets_benchmarks"), complete: bool = True,
) -> dict[Key, Crawl]:  # fmt: skip
    return {
        (source, venue, year): Crawl(
            source, venue, year, (Listing(LISTING, frozenset(tracks), T1),), complete
        )
    }


def run(xs: list[PaperRecord], crawls: dict[Key, Crawl]) -> DedupResult:
    return reconcile(dedup(xs), crawls).result


def by_id(result: DedupResult) -> dict[str, PaperRecord]:
    return {r.id: r for r in result.records}


NOTE = "op:neurips:2024:AbCd1234"
LISTED = [  # a listed paper and its note (they merge), and a listing of main and D&B
    paper("EfGh5678", "Listed paper"),
    paper(f"nips-{H[1]}", "Listed paper", source="neurips_proceedings"),
    paper(f"nips-{H[2]}", "A D&B paper", source="neurips_proceedings", track="datasets_benchmarks"),
]


def test_an_openreview_accepted_paper_the_crawled_listing_lacks_is_unknown_with_its_evidence() -> None:
    result = run([*LISTED, paper("AbCd1234", "Not in the proceedings")], crawl())
    note = by_id(result)[NOTE]
    assert note.status == "unknown"
    [absent] = [c for c in note.provenance if is_absence(c)]
    assert (absent.source, absent.url, absent.fetched_at) == ("neurips_proceedings", LISTING, T1)
    assert absent.evidence is not None and "not listed" in absent.evidence and LISTING in absent.evidence
    assert any(c.source == "openreview_v2" and c.value == "accepted" for c in note.provenance)  # kept
    rows = [c for c in result.conflicts if c.id == NOTE]
    assert [(c.field, c.value_a, c.source_a, c.value_b, c.source_b, c.resolution) for c in rows] == [
        ("status", "unknown", "neurips_proceedings", "accepted", "openreview_v2", "precedence:neurips_proceedings")
    ]  # fmt: skip
    assert resolve(note.id, note.provenance)[0] == note  # the record is what its claims say
    # nothing else moved
    assert by_id(result)["op:neurips:2024:EfGh5678"].status == "accepted"
    assert dedup([*LISTED]).merges == result.merges


def test_a_reconcile_demoted_note_loses_its_presentation_and_a_listed_one_keeps_it() -> None:
    listed = [paper("EfGh5678", "Listed paper", presentation="oral"), *LISTED[1:]]
    result = run([*listed, paper("AbCd1234", "Not in the proceedings", presentation="oral")], crawl())
    note, kept = by_id(result)[NOTE], by_id(result)["op:neurips:2024:EfGh5678"]
    assert (note.status, note.presentation) == ("unknown", None)
    assert any(c.field == "presentation" and c.value == "oral" for c in note.provenance)  # evidence kept
    assert (kept.status, kept.presentation) == ("accepted", "oral")


def test_a_listed_note_a_workshop_or_not_accepted_note_and_a_listing_are_left_alone() -> None:
    xs = [
        *LISTED,
        paper("AbCd1234", "A workshop paper", track="workshop"),
        paper("IjKl9012", "Rejected", status="rejected"),
        paper("MnOp3456", "Undecided", status="unknown"),
    ]
    assert run(xs, crawl()) == dedup(xs)


def test_nothing_changes_where_the_track_venue_year_or_a_complete_crawl_is_missing() -> None:
    xs = [*LISTED, paper("AbCd1234", "Not listed", track="position")]
    assert run(xs, crawl()) == dedup(xs)  # no crawled listing holds position papers
    xs = [*LISTED, paper("AbCd1234", "Not listed")]
    assert run(xs, crawl(year=2023)) == dedup(xs)  # another venue-year crawled
    assert run(xs, crawl(source="pmlr", venue="ICML")) == dedup(xs)
    assert run(xs, {}) == dedup(xs)
    outcome = reconcile(dedup(xs), crawl(complete=False))  # a listing skipped an entry: it may be this one
    assert outcome.result == dedup(xs) and outcome.incomplete == (("neurips_proceedings", "NeurIPS", 2024),)


def test_creative_ai_is_never_judged_even_where_its_listing_merged_with_its_note() -> None:
    """TASK-137: a Creative AI listing now merges with its note, but `other` is no covered track (it holds more
    than Creative AI), so an unlisted Creative AI note keeps its status."""
    xs = [creative_listing(), creative_note(),
          creative_note("EfGh5678", "Not in the proceedings", status="accepted")]  # fmt: skip
    crawls = crawl(year=2025, tracks=("main", "other"))
    assert run(xs, crawls) == dedup(xs)
    assert len(dedup(xs).records) == 2


def test_a_track_counts_as_crawled_only_when_a_listing_record_holds_it() -> None:
    xs = [paper("EfGh5678", "Listed paper"), paper(f"nips-{H[1]}", "Listed paper", source="neurips_proceedings"),
          paper("AbCd1234", "Not listed", track="datasets_benchmarks")]  # fmt: skip
    assert run(xs, crawl()) == dedup(xs)  # the report names D&B, but no D&B listing record exists
    assert by_id(run(xs, crawl()))["op:neurips:2024:EfGh5678"].status == "accepted"


def test_a_note_sharing_a_title_or_forum_with_a_listing_it_did_not_merge_with_keeps_its_status() -> None:
    xs = [  # two accepted notes and one listing under one title: ambiguous, so none merge
        paper("AbCd1234", "Shared title"),
        paper("EfGh5678", "Shared title"),
        paper(f"nips-{H[1]}", "Shared title", source="neurips_proceedings"),
    ]
    outcome = reconcile(dedup(xs), crawl())
    assert outcome.result == dedup(xs) and outcome.shares_listing == 2
    linked = [  # two listings (D&B and main) link the note's forum: the link is refused (two proceedings ids),
        # so nothing merges, but the note may still be one of the listed papers
        *LISTED,
        paper("AbCd1234", "One title"),
        paper(f"nips-{H[3]}", "Other title", source="neurips_proceedings", track="datasets_benchmarks",
              urls_forum="https://openreview.net/forum?id=AbCd1234"),
        paper(f"nips-{H[4]}", "Third title", source="neurips_proceedings",
              urls_forum="https://openreview.net/forum?id=AbCd1234"),
    ]  # fmt: skip
    assert len(dedup(linked).records) == len(linked) - 1  # only the listed paper and its note merged
    assert any(
        c.field == "forum_id" and c.resolution == "ambiguous_not_merged" for c in dedup(linked).conflicts
    )
    outcome = reconcile(dedup(linked), crawl())
    assert outcome.result.records == dedup(linked).records and outcome.shares_listing == 1


def test_a_note_titled_like_a_listing_of_another_track_keeps_its_status() -> None:
    xs = [  # a main and a D&B note share the D&B listing's title: ambiguous, so none merge
        *LISTED, paper("AbCd1234", "A D&B paper"), paper("IjKl9012", "A D&B paper", track="datasets_benchmarks"),
    ]  # fmt: skip
    assert len(dedup(xs).records) == len(xs) - 1  # only the listed paper and its note merged
    outcome = reconcile(dedup(xs), crawl())  # the main note may still be the D&B listing's paper
    assert outcome.result == dedup(xs) and outcome.shares_listing == 2


def test_a_note_naming_a_proceedings_paper_by_url_counts_as_a_listing() -> None:
    xs = [  # a note whose urls.proceedings names a paper no crawled listing merged with, and a same-title note
        *LISTED,
        paper("AbCd1234", "Linked by URL", urls_proceedings=nips(3)),
        paper("IjKl9012", "Linked by URL"),
    ]
    outcome = reconcile(dedup(xs), crawl())
    assert outcome.result == dedup(xs)  # the first is a listing (not judged); the second shares its title
    assert outcome.shares_listing == 1


def test_a_listing_merged_into_an_unknown_track_record_covers_nothing() -> None:
    xs = [  # a mixed volume's lone listing (its record's track stays unknown) and an unknown-track note
        paper("pmlr-v267-key1", "Main paper", source="pmlr", venue="ICML", year=2025, track="unknown"),
        paper("AbCd1234", "Unlisted", venue="ICML", year=2025, track="unknown"),
    ]
    assert run(xs, crawl("pmlr", "ICML", 2025, tracks=("unknown",))) == dedup(xs)


def test_the_absence_claim_carries_the_holding_listing_and_its_own_fetch_time() -> None:
    dnb = LISTING + "/datasets"
    crawls = {("neurips_proceedings", "NeurIPS", 2024): Crawl(
        "neurips_proceedings", "NeurIPS", 2024,
        (Listing(LISTING, frozenset({"main"}), T0), Listing(dnb, frozenset({"datasets_benchmarks"}), T2)), True,
    )}  # fmt: skip
    note = by_id(run([*LISTED, paper("AbCd1234", "Not listed", track="datasets_benchmarks")], crawls))[NOTE]
    [absent] = [c for c in note.provenance if is_absence(c)]
    assert (absent.url, absent.fetched_at) == (dnb, T2)


def test_a_mixed_pmlr_volume_covers_the_tracks_its_listings_merged_into() -> None:
    icml = crawl("pmlr", "ICML", 2025, tracks=("unknown",))
    listed = [
        paper("EfGh5678", "Main paper", venue="ICML", year=2025),
        paper("pmlr-v267-key1", "Main paper", source="pmlr", venue="ICML", year=2025, track="unknown"),
    ]
    xs = [*listed, paper("AbCd1234", "Unlisted main", venue="ICML", year=2025),
          paper("IjKl9012", "Unlisted position", venue="ICML", year=2025, track="position")]  # fmt: skip
    out = by_id(run(xs, icml))
    assert out["op:icml:2025:AbCd1234"].status == "unknown"
    assert out["op:icml:2025:IjKl9012"].status == "accepted"  # no position paper merged with the volume
    [absent] = [c for c in out["op:icml:2025:AbCd1234"].provenance if is_absence(c)]
    assert absent.source == "pmlr"


def test_ris_acceptance_alone_is_not_judged_but_a_note_with_ris_is() -> None:
    xs = [*LISTED, paper("AbCd1234", "Not listed", source="ris")]
    assert run(xs, crawl()) == dedup(xs)  # not OpenReview's acceptance
    xs = [*LISTED, paper("AbCd1234", "Not listed"), paper("AbCd1234", "Not listed", source="ris", fetched=T2)]
    assert by_id(run(xs, crawl()))[NOTE].status == "unknown"


def test_an_absence_claim_that_no_longer_holds_is_dropped() -> None:
    xs = [*LISTED, paper("AbCd1234", "Not listed")]
    once = run(xs, crawl())
    again = reconcile(dedup(once.records), {})  # a later build without the crawl
    assert again.result.records == dedup(xs).records
    assert not any(c.id == NOTE and c.field == "status" for c in again.result.conflicts)


def test_a_note_whose_openreview_sources_disagree_has_each_value_against_unknown() -> None:
    """TASK-154: v2 says accepted, v1 rejected; v2 wins, so the note is judged. Its status rows are then the ones its
    claims resolve to, as dedup run again would write them: the v2-over-v1 row gives way to unknown over each."""
    xs = [
        *LISTED,
        paper("AbCd1234", "Not listed"),
        paper("AbCd1234", source="openreview_v1", status="rejected"),
    ]

    def rows(result: DedupResult) -> list[tuple[str, str, str, str, str]]:
        return [(c.value_a, c.source_a, c.value_b, c.source_b, c.resolution)
                for c in result.conflicts if c.id == NOTE and c.field == "status"]  # fmt: skip

    assert rows(dedup(xs)) == [
        ("accepted", "openreview_v2", "rejected", "openreview_v1", "precedence:openreview_v2")
    ]
    once = run(xs, crawl())
    assert by_id(once)[NOTE].status == "unknown"
    assert rows(once) == [
        ("unknown", "neurips_proceedings", "accepted", "openreview_v2", "precedence:neurips_proceedings"),
        ("unknown", "neurips_proceedings", "rejected", "openreview_v1", "precedence:neurips_proceedings"),
    ]
    assert rows(dedup(once.records)) == rows(once)
    assert {c for c in once.conflicts if c.id != NOTE} == {c for c in dedup(xs).conflicts if c.id != NOTE}


def test_a_demoted_note_keeps_its_newest_row() -> None:
    """Only `precedence:` status rows give way: a `newest:` row is the one record of a source's older value, since
    the record keeps only the newest claim per source (TASK-154 review)."""
    xs = [
        *LISTED,
        paper("AbCd1234", "Not listed", fetched=T1),
        paper("AbCd1234", "Not listed", status="rejected"),
    ]
    newest = [c for c in dedup(xs).conflicts if c.id == NOTE and c.resolution.startswith("newest:")]
    assert [(c.field, c.value_a, c.value_b) for c in newest] == [("status", "accepted", "rejected")]
    once = run(xs, crawl())
    assert by_id(once)[NOTE].status == "unknown"
    assert set(newest) <= set(once.conflicts)


def test_iclr_2016_main_keeps_its_archive_track_and_status_through_reconcile() -> None:
    # decision-005 §Track, per track (TASK-130): OpenReview holds only ICLR 2016's workshop track
    ws = dict(venue="ICLR", year=2016, source="openreview_v1", track="workshop", status="unknown")
    xs = [archive(2016), paper("AbCd1234", **ws), paper("EfGh5678", "A workshop paper", **ws)]
    crawls = crawl("iclr_archive", "ICLR", 2016, tracks=("main",))
    once = run(xs, crawls)
    assert once == dedup(xs)
    assert by_id(once)[xs[0].id].track == "main" and by_id(once)[xs[0].id].status == "accepted"
    assert reconcile(dedup(once.records), crawls).result == once  # idempotent


def test_crawled_reads_completeness_from_the_listing_reports() -> None:
    def report(**kw: object) -> ListingReport:
        r = ListingReport("neurips_proceedings", "NeurIPS", 2025, kw.pop("listing", LISTING), "confirm", 3,  # type: ignore[arg-type]
                          listed=3, records=3, tracks=Counter({"main": 3}))  # fmt: skip
        r.fetched = [T0, T2]
        for k, v in kw.items():
            setattr(r, k, v)
        return r

    key = ("neurips_proceedings", "NeurIPS", 2025)
    [got] = crawled([report()]).values()
    assert got.complete and got.listings == (Listing(LISTING, frozenset({"main"}), T0),)  # the index page, T0
    assert crawled([report(records=2, skipped=Counter({"duplicate": 1}))])[key].complete  # a repeated entry
    assert not crawled([report(records=2, skipped=Counter({"invalid": 1}))])[key].complete
    assert not crawled([report(stated=4)])[key].complete  # the page states another count
    assert not crawled([report(stated=None)])[key].complete  # no count: nothing says every entry was seen
    assert not crawled([report(see_also=[LISTING + "/vol38"])])[key].complete  # a volume it didn't follow
    assert not crawled([report(), report(listing=LISTING + "/vol38", fetched=[])])[key].complete  # one unread
    assert not crawled([report(), report(listing=LISTING + "/vol38", records=2)])[key].complete  # one of two
    assert crawled([report(fetched=[])]) == {}


# --- properties ------------------------------------------------------------------------------------------

VENUE_SOURCE = {"NeurIPS": "neurips_proceedings", "ICLR": "iclr_archive", "ICML": "pmlr"}


@st.composite
def crawl_sets(draw: st.DrawFn) -> dict[Key, Crawl]:
    out: dict[Key, Crawl] = {}
    for venue, source in VENUE_SOURCE.items():
        for year in (2023, 2024):
            if draw(st.booleans()):
                tracks = frozenset(
                    draw(st.sets(st.sampled_from(["main", "datasets_benchmarks", "position", "unknown"])))
                )
                out[(source, venue, year)] = Crawl(source, venue, year, (Listing(LISTING, tracks, T1),), draw(st.booleans()))  # fmt: skip
    return out


@st.composite
def unlisted(draw: st.DrawFn) -> tuple[list[PaperRecord], dict[Key, Crawl]]:
    """A crawled venue-year: a listing merged with its note, OpenReview notes it may or may not list (any
    track, status and source, sometimes sharing the listing's title), and pool noise; the crawl is sometimes
    incomplete, sometimes another venue-year's, and often covers more than one track."""
    venue = draw(st.sampled_from(sorted(VENUE_SOURCE)))
    year = draw(st.sampled_from([2023, 2024]))
    track = draw(st.sampled_from(["main", "datasets_benchmarks", "position"]))
    native = {"NeurIPS": f"nips-{H[1]}", "ICLR": f"iclr-{H[1]}", "ICML": "pmlr-v202-key1"}[venue]
    xs = [
        paper("AbCd1234", "Listed paper", venue=venue, year=year, track=track),
        paper(native, "Listed paper", source=VENUE_SOURCE[venue], venue=venue, year=year,
              track=draw(st.sampled_from([track, "unknown"]))),
    ]  # fmt: skip
    for fid in draw(st.lists(st.sampled_from(["EfGh5678", "IjKl9012", "MnOp3456"]), max_size=3, unique=True)):
        xs.append(
            paper(fid, draw(st.sampled_from(["Unlisted paper", "Another paper", "Listed paper", "Unlisted paper"])), venue=venue,
                  year=year, track=draw(st.sampled_from([track, track, "main", "workshop", "unknown"])),
                  status=draw(st.sampled_from(["accepted", "accepted", "accepted", "rejected", "unknown"])),
                  source=draw(st.sampled_from(["openreview_v2", "openreview_v1", "ris"])))
        )  # fmt: skip
    tracks = frozenset({track, *draw(st.sets(st.sampled_from(["main", "datasets_benchmarks", "unknown"])))})
    at = (VENUE_SOURCE[venue], venue, draw(st.sampled_from([year, year, year, 2023, 2024])))
    crawls = {
        at: Crawl(
            at[0], venue, at[2], (Listing(LISTING, tracks, T1),), draw(st.sampled_from([True, True, False]))
        )
    }
    return xs + draw(st.lists(records(), max_size=3)), crawls


shapes = st.one_of(st.tuples(pools, crawl_sets()), unlisted(), unlisted())


def stable(result: DedupResult) -> tuple[tuple[PaperRecord, ...], list[object]]:
    return result.records, [c for c in result.conflicts if not c.resolution.startswith(("newest:", "tie:"))]


# TASK-154 (nightly, 2026-09-30): a note whose OpenReview sources disagree (v2 accepted, v1 rejected) is made
# unknown; its v2-over-v1 status row gives way to the rows its claims now resolve to
NIGHTLY_154 = (
    [
        paper("AbCd1234", "Listed paper", venue="ICLR"),
        paper(f"iclr-{H[1]}", "Listed paper", source="iclr_archive", venue="ICLR"),
        paper("IjKl9012", "Unlisted paper", venue="ICLR"),
        paper(f"iclr-{H[1]}", source="iclr_archive", venue="ICLR", year=2023,
              urls_forum="https://openreview.net/forum?id=AbCd1234"),
        paper("IjKl9012", source="openreview_v1", venue="ICLR", status="rejected"),
    ],
    crawl(source="iclr_archive", venue="ICLR", tracks=("main",)),
)  # fmt: skip


@given(shapes)
@example(NIGHTLY_154)
def test_dedup_and_reconcile_again_change_nothing(shape: tuple[list[PaperRecord], dict[Key, Crawl]]) -> None:
    xs, crawls = shape
    once = run(xs, crawls)
    for r in once.records:  # dedup's input check: every record is what its claims resolve to
        assert resolve(r.id, r.provenance)[0] == r
    again = dedup(once.records)
    assert again.records == once.records and not [m for m in again.merges if m.merged_id != m.survivor_id]
    assert stable(again)[1] == stable(once)[1]  # the absence claim merges nothing and moves no row
    assert stable(run(list(once.records), crawls)) == stable(once)  # idempotent


@given(shapes)
@example(NIGHTLY_154)
def test_only_unlisted_openreview_acceptances_change_and_only_to_unknown(
    shape: tuple[list[PaperRecord], dict[Key, Crawl]],
) -> None:
    xs, crawls = shape
    base, once = dedup(xs), run(xs, crawls)
    event(f"records made unknown: {sum(r != b for r, b in zip(once.records, base.records, strict=True))}")
    assert once.merges == base.merges
    before = by_id(base)
    changed: set[str] = set()
    for r in once.records:
        b = before[r.id]
        if r == b:
            continue
        changed.add(r.id)
        added = set(r.provenance) - set(b.provenance)
        assert added and all(is_absence(c) for c in added) and set(b.provenance) <= set(r.provenance)
        assert (b.status, r.status) == ("accepted", "unknown")
        assert r.track in {"main", "datasets_benchmarks", "position"}
        assert {c.source for c in b.provenance} & {"openreview_v2", "openreview_v1"}
        assert not {c.source for c in b.provenance} & {"iclr_archive", "neurips_proceedings", "pmlr"}
        assert any(k[1:] == (r.venue, r.year) and c.complete for k, c in crawls.items())
        assert any(c.id == r.id and c.field == "status" and c.value_a == "unknown" for c in once.conflicts)
    # rows are only added, except a changed record's status rows: they become the rows its claims now resolve to
    # (dedup run on the output writes the same), and every status value they named is still named against `unknown`
    for d in set(base.conflicts) - set(once.conflicts):
        assert d.id in changed and d.field == "status" and d.resolution.startswith("precedence:")
        against = {
            (c.value_b, c.source_b) for c in once.conflicts
            if c.id == d.id and c.field == "status" and c.value_a == "unknown" and c.resolution.startswith("precedence:")
        }  # fmt: skip
        assert {
            (v, src) for v, src in ((d.value_a, d.source_a), (d.value_b, d.source_b)) if v != "unknown"
        } <= against
