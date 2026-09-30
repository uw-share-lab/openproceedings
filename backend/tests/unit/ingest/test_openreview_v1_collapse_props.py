"""Properties of the v1 crawler's rule 5 (TASK-125's identical notes, TASK-132's silent twin): whatever notes of one
venue-year share pdfs, titles, abstracts, venue strings and listings, a collapse never folds two papers into one
record, never loses an acceptance, keeps every surviving record exactly as the crawl built it, counts every
dropped note, and doesn't depend on listing order. Notes are variations of the recorded silent pair
(NeurIPS 2021 `W6e384Lkjbw` and `rDdb26AQ0SO`), crawled through `FakeOpenReviewV1`. No network (conftest)."""

from __future__ import annotations

import copy
import random
import tempfile
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest import mock

from hypothesis import example, given
from hypothesis import strategies as st
from openproceedings import storage
from openproceedings.ingest.record import PaperRecord
from openproceedings.ingest.sources import openreview_v1 as v1
from openproceedings.ingest.sources.openreview_client import Credentials

from tests.unit.ingest.openreview_fakes import PASSWORD, USERNAME, FakeClock, FakeOpenReviewV1, v1_note

MAIN = "NeurIPS.cc/2021/Conference/-/Blind_Submission"
WITHDRAWN = "NeurIPS.cc/2021/Conference/-/Withdrawn_Submission"
ROUND2 = "NeurIPS.cc/2021/Track/Datasets_and_Benchmarks/Round2/-/Submission"
SILENT = v1_note("neurips-2021/notes-main-listing-silent-twin.json")
SPEAKING = v1_note("neurips-2021/notes-main-listing-accepted-silent-twin.json")
ABSENT = None  # the key is left out of the note

PDFS = (SPEAKING["content"]["pdf"], "/pdf/0123456789abcdef0123456789abcdef01234567.pdf")
TITLES = (SPEAKING["content"]["title"], "Another synthetic title.")
ABSTRACTS = (SPEAKING["content"]["abstract"], "Another synthetic abstract.")
VENUES = (ABSENT, "", "NeurIPS 2021 Poster", "NeurIPS 2021 Spotlight", "NeurIPS 2021 Submitted")
VENUEIDS = (ABSENT, "NeurIPS.cc/2021/Conference")


@st.composite
def notes(draw: st.DrawFn) -> dict[str, list[dict[str, Any]]]:
    """1–5 notes on the NeurIPS 2021 main, withdrawn and D&B Round 2 listings, each the recorded silent note with
    its pdf, title, abstract, venue and venueid drawn from small pools (so they collide), a distinct id and
    number."""
    n = draw(st.integers(min_value=1, max_value=5))
    numbers = draw(st.lists(st.integers(min_value=1, max_value=20_000), min_size=n, max_size=n, unique=True))
    listings: dict[str, list[dict[str, Any]]] = {MAIN: [], WITHDRAWN: [], ROUND2: []}
    for i, number in enumerate(numbers):
        note = copy.deepcopy(SILENT)
        note["id"] = note["forum"] = f"Zz{i}Note{number}"
        note["number"] = number
        content = note["content"]
        content["pdf"] = draw(st.sampled_from(PDFS))
        content["title"] = draw(st.sampled_from(TITLES))
        content["abstract"] = draw(st.sampled_from(ABSTRACTS))
        for key, pool in (("venue", VENUES), ("venueid", VENUEIDS)):
            value = draw(st.sampled_from(pool))
            if value is not ABSENT:
                content[key] = value
        listings[draw(st.sampled_from((MAIN, MAIN, MAIN, WITHDRAWN, ROUND2)))].append(note)
    return listings


def crawl(listings: dict[str, list[dict[str, Any]]]) -> v1.Crawl:
    # the cache's F_FULLFSYNC is most of a crawl's time and varies with disk load, which the 500 ms dev deadline
    # measures; a throwaway cache needs no durability
    with tempfile.TemporaryDirectory() as tmp, mock.patch.object(storage, "fsync"):
        client = v1.make_client(Path(tmp), credentials=Credentials(USERNAME, PASSWORD),
                                transport=FakeOpenReviewV1(listings), clock=FakeClock(), jitter=lambda: 0.0)  # fmt: skip
        return v1.crawl(client, "NeurIPS", 2021)


@contextmanager
def no_collapse() -> Iterator[None]:
    with (
        mock.patch.object(v1, "collapse_duplicate_submissions", return_value=[]),
        mock.patch.object(v1, "collapse_silent_twins", return_value=[]),
    ):
        yield


def silent_note(listings: dict[str, list[dict[str, Any]]], record: PaperRecord) -> bool:
    """Whether the record's note was on a submission listing with neither a venue nor a venueid key."""
    return any(
        n["id"] == record.native and "venue" not in n["content"] and "venueid" not in n["content"]
        for n in listings[MAIN] + listings[ROUND2]
    )


def papers(records: tuple[PaperRecord, ...]) -> Counter[tuple[str, str]]:
    """Each paper (content and track, not status) with a status, as many times as records hold it."""
    return Counter((v1._same_paper_but_status(r), r.status) for r in records)


REAL_PAIR = {MAIN: [copy.deepcopy(SILENT), copy.deepcopy(SPEAKING)], WITHDRAWN: [], ROUND2: []}


def main_note(nid: str, number: int, which: int, venue: str | None) -> dict[str, Any]:
    """The silent note as `nid` #`number`, with the `which`-th pdf, title and abstract and the given venue."""
    note = copy.deepcopy(SILENT)
    note["id"] = note["forum"] = nid
    note["number"] = number
    note["content"].update(pdf=PDFS[which], title=TITLES[which], abstract=ABSTRACTS[which])
    if venue is not ABSENT:
        note["content"]["venue"] = venue
    return note


# TASK-147 (Hypothesis found it): rule 5 kept Note2 (silent) for its identical Note3, whose empty `venue` is a key
# and so not silence; the silent-twin pass then folded Note2 into the accepted Note4. A survivor is silent only if
# every note it stands for is, so Note2 stays: had Note3 carried the lower number, it would have been kept instead.
# Note1 and Note5 are a plain rule-5 pair.
CHAINED = {
    MAIN: [
        main_note("Zz0Note3", 3, 1, ""),
        main_note("Zz1Note1", 1, 0, ABSENT),
        main_note("Zz2Note4", 4, 1, "NeurIPS 2021 Poster"),
        main_note("Zz3Note5", 5, 0, ABSENT),
        main_note("Zz4Note2", 2, 1, ABSENT),
    ],
    WITHDRAWN: [],
    ROUND2: [],
}


@given(notes(), st.randoms(use_true_random=False))
@example(REAL_PAIR, random.Random(0))
@example(CHAINED, random.Random(0))
def test_a_collapse_never_folds_two_papers_or_loses_an_acceptance(
    listings: dict[str, list[dict[str, Any]]], rnd: random.Random
) -> None:
    with no_collapse():
        every = {r.id: r for r in crawl(listings).records}
    got = crawl(listings)
    kept = {r.id: r for r in got.records}

    # conservation: every note is a record or a counted duplicate, and a kept record is exactly as built
    assert got.report.imported + got.report.skipped["duplicate_submission"] == len(every)
    assert all(every[rid] == r for rid, r in kept.items())

    for rid in every.keys() - kept.keys():
        gone = every[rid]
        # the same paper by content and track survives: a dropped note never stands for another paper
        twins = [k for k in kept.values() if v1._same_paper_but_status(k) == v1._same_paper_but_status(gone)]
        assert twins, rid
        if v1._same_paper(gone) in {v1._same_paper(k) for k in twins}:
            continue  # rule 5: an identical note, status and all
        # otherwise only a silent note, and only into the one accepted record of its paper
        assert silent_note(listings, gone) and gone.status == "unknown", rid
        assert [k.status for k in twins] == ["accepted"], rid

    # no status is lost: every status a note gave survives on a record of the same paper
    assert {(v1._same_paper_but_status(r), r.status) for r in every.values() if r.status != "unknown"} <= {
        (v1._same_paper_but_status(r), r.status) for r in kept.values()
    }

    # listing order doesn't matter
    shuffled = {inv: rnd.sample(ns, len(ns)) for inv, ns in listings.items()}
    assert crawl(shuffled).records == got.records

    # nor do the note numbers, rule 5's tie-break (TASK-147): permuted, the same papers survive with the same
    # statuses, whichever note of each stands for them
    renumbered = copy.deepcopy(listings)
    ns = [n for inv in (MAIN, WITHDRAWN, ROUND2) for n in renumbered[inv]]
    for n, number in zip(ns, rnd.sample([n["number"] for n in ns], len(ns)), strict=True):
        n["number"] = number
    assert papers(crawl(renumbered).records) == papers(got.records)


def test_the_real_pair_collapses_to_its_accepted_note() -> None:
    [record] = crawl(copy.deepcopy(REAL_PAIR)).records
    assert (record.native, record.status, record.presentation) == ("rDdb26AQ0SO", "accepted", "poster")


def test_a_survivor_that_stands_for_a_speaking_note_is_not_silent() -> None:
    # TASK-147: rule 5 folds Note3 (an empty venue) into Note2 and Note5 into Note1; Note2 now stands for a note
    # with a venue key, so it is no silent twin and stays beside the accepted Note4
    got = crawl(copy.deepcopy(CHAINED))
    assert [(r.native, r.status) for r in got.records] == [
        ("Zz1Note1", "unknown"), ("Zz2Note4", "accepted"), ("Zz4Note2", "unknown")
    ]  # fmt: skip
    assert (got.report.skipped["duplicate_submission"], got.report.unknown_status) == (2, 2)
    # the same notes with Note2's and Note3's numbers swapped: rule 5 keeps Note3 instead, and the same paper
    # survives as two records, so the silent-twin collapse no longer depends on rule 5's tie-break
    swapped = copy.deepcopy(CHAINED)
    for note in swapped[MAIN]:
        note["number"] = {2: 3, 3: 2}.get(note["number"], note["number"])
    got = crawl(swapped)
    assert [(r.native, r.status) for r in got.records] == [
        ("Zz0Note3", "unknown"), ("Zz1Note1", "unknown"), ("Zz2Note4", "accepted")
    ]  # fmt: skip
    assert (got.report.skipped["duplicate_submission"], got.report.unknown_status) == (2, 2)


def test_a_survivor_of_only_silent_notes_still_folds_into_its_accepted_twin() -> None:
    # the other half of TASK-147's rule: two identical silent notes are one silent survivor, whichever is kept
    for first, second in ((1, 2), (2, 1)):
        listings = {
            MAIN: [
                main_note("Zz0NoteA", first, 1, ABSENT),
                main_note("Zz1NoteB", second, 1, ABSENT),
                main_note("Zz2NoteC", 4, 1, "NeurIPS 2021 Poster"),
            ],
            WITHDRAWN: [],
            ROUND2: [],
        }
        got = crawl(listings)
        assert [(r.native, r.status) for r in got.records] == [("Zz2NoteC", "accepted")]
        assert got.report.skipped["duplicate_submission"] == 2
