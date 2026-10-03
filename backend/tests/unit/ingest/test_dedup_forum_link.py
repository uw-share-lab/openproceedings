"""The forum link (TASK-105) against the recorded fixtures: PMLR v235's index links each paper's OpenReview
forum, so dedup joins the PMLR and OpenReview records on it before (and whatever) the titles say.

Of the recorded PMLR volumes only v235 (ICML 2024) carries the link; v28 (ICML 2013) has none, and v220 is a
NeurIPS competition volume that is never ingested. The scrubbed fixtures' synthetic titles differ between
the PMLR index (`Synthetic title 1`) and the OpenReview note (`Synthetic title text 1.`), so no title key
matches and only the link can merge them. The OpenReview side is the recorded ICML 2024 note, cloned to
each forum id v235 links (numbered titles; its venueid edited where a case says so); the PMLR side is the v235 miner's output.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from openproceedings.ingest import snapshot as snap
from openproceedings.ingest.dedup import Conflict, Merge, dedup
from openproceedings.ingest.record import PaperRecord
from openproceedings.ingest.sources import openreview_v2 as orv

from tests.unit.ingest.openreview_fakes import clone, recorded_note
from tests.unit.ingest.test_pmlr import V235_KEYS, mine, seed_v28, seed_v235

FETCHED = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)
PAGE_URL = "https://api2.openreview.net/notes?content.venueid=ICML.cc/2024/Conference&limit=1000&offset=0"
# v235's index: key → the forum id its OpenReview link names (the recorded page)
LINKS = {"abad-rocamora24a": "AZWqXfM6z9", "abe24a": "9U29U3cDKq", "abhyankar24a": "wDDGQabYPQ"}


def openreview(
    forum: str, number: int, venueid: str = "ICML.cc/2024/Conference", year: int = 2024
) -> PaperRecord:
    note = clone(recorded_note("icml-2024/notes-accepted.json"), forum, number, venueid)
    note["content"]["title"] = {"value": f"Synthetic title text {number}."}  # one title per clone
    record = orv.note_record(note, venue="ICML", year=year, page_url=PAGE_URL, fetched_at=FETCHED)
    assert isinstance(record, PaperRecord), record
    return record


@pytest.fixture
def v235(tmp_path: Path) -> dict[str, PaperRecord]:
    seed_v235(tmp_path)
    return {r.native.removeprefix("pmlr-v235-"): r for r in mine(tmp_path, 235).records}


def pmlr_id(key: str) -> str:
    return f"op:icml:2024:pmlr-v235-{key}"


def test_the_recorded_v235_index_links_every_paper_and_v28_links_none(
    v235: dict[str, PaperRecord], tmp_path: Path
) -> None:
    assert set(v235) == set(V235_KEYS)
    assert {k: r.urls.forum for k, r in v235.items()} == {
        k: f"https://openreview.net/forum?id={f}" for k, f in LINKS.items()
    }
    seed_v28(tmp_path)
    assert all(r.urls.forum is None for r in mine(tmp_path, 28).records)  # ICML 2013: title match only


def test_pmlr_and_openreview_merge_on_the_link_whatever_the_titles(v235: dict[str, PaperRecord]) -> None:
    ors = [openreview(f, n) for n, f in enumerate(LINKS.values(), 1)]
    result = dedup([*ors, *v235.values()])
    assert [r.id for r in result.records] == sorted(r.id for r in ors)  # the forum id survives
    assert set(result.merges) == {
        Merge(f"op:icml:2024:{f}", pmlr_id(k), "forum_link", f, "ICML", 2024, "pmlr")
        for k, f in LINKS.items()
    }
    by_id = {r.id: r for r in result.records}
    for n, (key, forum) in enumerate(LINKS.items(), 1):
        r = by_id[f"op:icml:2024:{forum}"]
        assert r.title == f"Synthetic title text {n}."  # OpenReview's text wins (decision-005)
        assert (r.track, r.status) == ("main", "accepted")  # v235's own `unknown` track gives way
        assert r.urls.proceedings == f"https://proceedings.mlr.press/v235/{key}.html"
        assert {c.source for c in r.provenance} == {"openreview_v2", "pmlr"}
        # the titles really differ: a precedence row, never a refusal
        assert Conflict(
            r.id, "title", r.title, "openreview_v2", v235[key].title, "pmlr",
            "precedence:openreview_v2",
        ) in result.conflicts  # fmt: skip
    assert not [c for c in result.conflicts if c.resolution.endswith("not_merged")]
    assert dedup(result.records).records == result.records  # a second run merges nothing more


def test_without_the_link_the_same_records_stay_apart(v235: dict[str, PaperRecord]) -> None:
    """The control: the same pair with PMLR's link claim dropped has no shared title key, so nothing merges."""
    record = v235["abe24a"]
    unlinked = record.model_copy(
        update={
            "provenance": tuple(c for c in record.provenance if c.field != "urls.forum"),
            "urls": record.urls.model_copy(update={"forum": None}),
        }
    )
    result = dedup([openreview("9U29U3cDKq", 2), unlinked])
    assert len(result.records) == 2 and result.merges == ()


# case → (the OpenReview note's venueid and year, the conflict it must give instead of a merge)
REFUSED = [
    ("another year", "ICML.cc/2023/Conference", 2023, "forum_id", "venue_year_not_merged"),
    ("a workshop paper", "ICML.cc/2024/Workshop/FM-Wild", 2024, "forum_id", "track_not_merged"),
]


@pytest.mark.parametrize(
    ("why", "venueid", "year", "field", "resolution"), REFUSED, ids=[r[0] for r in REFUSED]
)
def test_a_contradicting_link_is_a_conflict_row_not_a_merge(
    v235: dict[str, PaperRecord], why: str, venueid: str, year: int, field: str, resolution: str
) -> None:
    other = openreview("9U29U3cDKq", 2, venueid, year)
    pmlr = v235["abe24a"]
    result = dedup([other, pmlr])
    assert {r.id for r in result.records} == {other.id, pmlr.id} and result.merges == ()
    assert [(c.field, c.resolution) for c in result.conflicts] == [(field, resolution)]
    [row] = result.conflicts
    assert {row.value_a, row.value_b} == {other.id, pmlr.id}
    assert dedup(result.records).conflicts == result.conflicts  # the refusal is reported again, the same


def test_a_rejected_note_linked_from_the_proceedings_is_accepted_with_a_precedence_row(
    v235: dict[str, PaperRecord],
) -> None:
    rejected = openreview("9U29U3cDKq", 2, "ICML.cc/2024/Conference/Rejected_Submission")
    result = dedup([rejected, v235["abe24a"]])
    [r] = result.records
    assert (r.id, r.status) == (rejected.id, "accepted")  # the proceedings decide acceptance
    assert Conflict(r.id, "status", "accepted", "pmlr", "rejected", "openreview_v2", "precedence:pmlr") in (
        result.conflicts
    )


def test_a_crawl_conflict_on_the_linked_listing_follows_the_link(v235: dict[str, PaperRecord]) -> None:
    result = dedup([openreview("9U29U3cDKq", 2), v235["abe24a"]])
    found = Conflict(pmlr_id("abe24a"), "status", "a", "pmlr", "b", "pmlr", "unresolved:openreview_v1")
    moved = snap.with_crawl_conflicts(result, [SimpleNamespace(conflicts=(found,))])  # type: ignore[list-item]
    assert Conflict(
        "op:icml:2024:9U29U3cDKq", "status", "a", "pmlr", "b", "pmlr", "unresolved:openreview_v1"
    ) in (moved.conflicts)
