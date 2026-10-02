"""The OpenReview API v1 crawler: one adapter per venue-year schema (TASK-051; spec 01 §Sources, §Track taxonomy;
openreview-api skill §API v1; decision-012, decision-013).

API v1 (`api.openreview.net`) holds ICLR 2013, 2014, 2016–2023 and NeurIPS 2021–2022 (main and D&B), each year
with its own schema, so each venue-year has its own `Adapter` in `ADAPTERS`. An adapter names:

- **Listings**: the exact invitations whose notes are that year's submissions (`?invitation=<inv>`, 1,000 a page,
  `count` checked against the rows and distinct ids), each with the track it was submitted to and its role.
  The submission invitation means "submitted", nothing more. Status evidence naming the main track on a note of a
  non-main listing is its conference twin's outcome (ICLR 2017's 18 workshop copies of rejected papers say
  `Submitted to ICLR 2017`), where the venueid names no track, so the note keeps its listing's track and its status
  is `unknown`, counted in the report's `twin_outcome` (TASK-152). The
  withdrawn and desk-rejected invitations are crawled explicitly (decision-012); a note listed there is
  `withdrawn` / `desk_rejected`.
- **Where status comes from** (`status_from`), per the research run (docs/research/2026-09-27-…-facts.md):
  `decision_field` (ICLR 2013: `content.decision` on the submission, track too), `none` (ICLR 2014 and 2016:
  no decisions on OpenReview, so `unknown`), `venue` (`content.venue` through `classify.classify_v1_venue`:
  ICLR 2017, 2022, 2023, NeurIPS 2021–2022), `decision_note` (ICLR 2018–2020: the decision note in the forum,
  fetched with `?forum=<id>`, matched by its exact invitation, `forum` and `replyto`), or `venue_then_decision_note`
  (ICLR 2021: accepted notes carry `content.venue`; the others need the decision note).
- **Coverage gaps**: what OpenReview can't answer for the year (ICLR 2015 has no group; 2014 has no decisions;
  2016 has only its workshop track), reported in the crawl report, never raised as an error.

The authority rules (never broken):
1. Only the submission note (`id == forum`) becomes a record.
2. **A v1 `content.venueid` never gives status** (TASK-095: rejected papers carry the bare venue path too). It
   only confirms venue and year (a note naming another venue-year is skipped as `out_of_scope`, never
   re-yeared) and, where it names a known track, must agree with the track the status evidence gives
   (otherwise the track is `unknown` and the disagreement is a conflict row).
3. Status and track strings are matched exactly against a table; an unlisted string is `unknown`, counted in
   `unmapped` (the crawl's one `openreview_crawl_attention` WARNING) and logged at DEBUG with the forum id (never
   the string, which can be free text).
4. When a note's own evidence disagrees (a withdrawn-invitation note whose `content.venue` says accepted, such
   as ICLR 2021 `xGZG2kS5bFk`; two decision notes that disagree), the status is `unknown` and the disagreement
   is a `conflicts.csv` row (`unresolved:openreview_v1`), never resolved by picking one side (decision-020: no
   signal outranks another; `xGZG2kS5bFk` was withdrawn yet presented, ICLR 2018 `S1p31z-Ab` accepted yet not
   presented). Likewise across two notes of one paper: an accepted record whose pdf a withdrawn record of the
   crawl in the same track shares (`S1p31z-Ab` and its withdrawn twin `SJTCsqMUf`) becomes `unknown` with such a
   row (`withdrawn_twins`); the twin keeps its status. A record with no decision at all (no decision note in its
   forum) and such a twin has one status signal, the twin's withdrawal, so it becomes `withdrawn`, with no row
   (TASK-139), counted in the report's `withdrawn_by_twin` instead of `unmapped`. A rejected record with a
   withdrawn twin, and any record with only a desk-rejected twin, keep their status. A record the rule touched is
   never collapsed by rule 5 (neither collapse).
5. **Two notes of one paper are one record** (TASK-125): OpenReview v1 holds 300 NeurIPS 2021 main-track papers as
   two Blind_Submission notes (different id and number, identical content but for the id in `_bibtex`), which
   dedup would otherwise refuse as two submissions with one title. After the listings, records that are
   identical in everything but their id, forum URL and provenance, with a pdf and a note number, are
   collapsed to the lowest-numbered note; each other note is counted in `skipped["duplicate_submission"]`
   (`collapse_duplicate_submissions`). A record with a crawl conflict, or one the twin rule (rule 4) made
   `withdrawn`, is never collapsed, by this collapse or the silent-twin one.
   **A silent twin** (TASK-132) is a note that says nothing about its status: in a year whose one status carrier is
   `content.venue`, a submission-listing note with neither a non-null `venue` nor `venueid` (NeurIPS 2021
   `W6e384Lkjbw` #5999, whose accepted twin `rDdb26AQ0SO` #11021 has the same pdf, supplementary material, title,
   authors, abstract and keywords). Such a note is dropped when exactly one other record is identical to it in
   everything but status, presentation and venueid, and that record is accepted with no crawl conflict
   (`collapse_silent_twins`, after rule 5; counted the same way). Its absence of evidence can't contradict an
   acceptance; a second record (with evidence or a conflict) or a non-accepted one leaves every note a record. A
   note rule 5 kept is silent only if every note it stands for is (TASK-147): one that absorbed a note with a
   non-null `venue` or `venueid` (even `''`) is not, so which of two identical notes has the lower number never
   decides whether the paper's third, accepted note absorbs them.

6. **A copy and its main-track twin are two linked records** (TASK-159, decision-028). A record from a non-main
   submission listing whose dedup title key is that of exactly one record from the main-track submission listing
   (or of several, one of which its `_bibtex` url names) is a copy of it: ICLR 2017's workshop listing holds 53,
   18 saying `Submitted to ICLR 2017` (their `_bibtex` names the twin), 34 `Invite to Workshop` (all 35 such
   notes' `_bibtex` name one unrelated forum, so a `_bibtex` counts only when its forum has the copy's title) and
   1 with no venue. They link to 51 conference records (two have two copies), 104 records in all.
   They are different submissions with their own outcomes, so they are never merged; each gets a `twin` claim
   naming the other's id (`link_twins`, after rule 5), counted in the report's `twins_linked`. A copy whose title
   several main-track submissions share, none named by its `_bibtex`, stays unlinked, counted in
   `twins_ambiguous` (0 on the 2026-09-29 crawl). No other v1
   venue-year has such a title match on the 2026-09-29 crawl.

`content.authors` is split into names only by decision-019's count-checked rule (`split_authors`): a list with
no `and`-joined entry is taken as listed; otherwise the split must give exactly as many names as the note has
author ids, or the authors stay empty (counted in `authors_unsplit`), the raw value kept in the claim's evidence.

Every value is a claim with `source="openreview_v1"`, the page URL it came from (the listing page, or the
forum page for a decision note) and that page's `fetched_at` from the cache. A finished crawl writes
`<cache>/openreview/v1/crawls/<Venue>-<Year>.json`, which `op snapshot build` replays offline.
"""

from __future__ import annotations

import json
import logging
import re
import time
from collections import Counter, defaultdict
from collections.abc import Callable, Mapping, Sequence, Set
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import ValidationError

from openproceedings.ingest.classify import Classification, classify_v1_venue, classify_venueid
from openproceedings.ingest.dedup import Conflict, title_key
from openproceedings.ingest.record import FORUM_ID, Claim, ClaimField, ClaimValue, PaperRecord, Source, Urls
from openproceedings.ingest.sources.common import CrawlError, Crawls, Report
from openproceedings.ingest.sources.http import CacheMiss
from openproceedings.ingest.sources.openreview_client import API_V1, API_V2, OpenReviewClient
from openproceedings.ingest.sources.openreview_v2 import (
    FIRST_V2_YEAR,
    SKIP_REASONS,
    Progress,
    _pages,
    _strings,
    _text,
    marker_key,
)
from openproceedings.logs import elapsed_ms

log = logging.getLogger(__name__)

SOURCE: Source = "openreview_v1"
PAGE_SIZE = 1000  # the API's maximum (`limit=1001` is a 400 on v1 too)
CONFLICT = "unresolved:openreview_v1"  # conflicts.csv resolution: the record's value is `unknown`
NO_DECISION_NOTE = (
    "no decision note in the forum"  # a status claim's evidence: the forum has no decision at all
)
_FORUM_URL = "https://openreview.net/forum?id={}"
DUPLICATE_SUBMISSION = "duplicate_submission"  # a second note of one paper (rule 5), counted, never a record
V1_SKIP_REASONS = (*SKIP_REASONS, DUPLICATE_SUBMISSION)

Role = Literal["submission", "withdrawn", "desk_rejected"]
StatusFrom = Literal["decision_field", "none", "venue", "decision_note", "venue_then_decision_note"]
# (track, status, presentation) a status string maps to; track None: the string doesn't name one (`Reject`,
# `Accept (Poster)`), so the track stays the one the note was submitted to (its listing's)
Outcome = tuple[str | None, str, str | None]


@dataclass(frozen=True)
class Listing:
    invitation: (
        str  # exact; v1 invitation filters are prefix regexes, and these contain no regex metacharacter
    )
    track: str  # the track the note was submitted to, until its status evidence says otherwise
    role: Role = "submission"


@dataclass(frozen=True)
class DecisionNotes:
    """How a year's decision note is found in a forum and read. `invitation` may hold `{number}`, the
    submission's number (`ICLR.cc/2020/Conference/Paper<N>/-/Decision`), so a note from another paper's
    forum can never be taken for this one's."""

    invitation: str
    field: str  # `decision`, or ICLR 2019's meta-review `recommendation`
    values: Mapping[str, Outcome]


@dataclass(frozen=True)
class Adapter:
    venue: str
    year: int
    listings: tuple[Listing, ...]
    status_from: StatusFrom
    decisions: Mapping[str, Outcome] = field(
        default_factory=dict
    )  # `decision_field`: content.decision → outcome
    decision_notes: DecisionNotes | None = None
    no_decision: frozenset[str] = frozenset()  # `none`: the content.decision values that mean "never decided"
    gaps: tuple[str, ...] = ()  # coverage gaps, reported with every crawl of the year


def _conf(org: str, year: int, *, desk_rejected: bool = True, withdrawn: bool = True) -> tuple[Listing, ...]:
    """A year's `<Org>.cc/<Y>/Conference/-/Blind_Submission` listing and its withdrawn / desk-rejected ones."""
    base = f"{org}.cc/{year}/Conference/-/"
    out = [Listing(base + "Blind_Submission", "main")]
    if withdrawn:
        out.append(Listing(base + "Withdrawn_Submission", "main", "withdrawn"))
    if desk_rejected:
        out.append(Listing(base + "Desk_Rejected_Submission", "main", "desk_rejected"))
    return tuple(out)


_ICLR_2014_GAP = (
    "ICLR 2014: no decisions on OpenReview (`submitted, no decision`), so every status is unknown (TASK-096)"
)
# Every string below was seen live in TASK-002 (2026-09-27) or TASK-107 (2026-09-29); the scrubbed evidence
# is under `backend/tests/fixtures/http/openreview/v1/`.
# Add one only after seeing it on a live note, with a fixture or a checked forum id.
ADAPTERS: dict[tuple[str, int], Adapter] = {
    ("ICLR", 2013): Adapter(
        "ICLR", 2013, (Listing("ICLR.cc/2013/conference/-/submission", "main"),), "decision_field",
        decisions={
            "conferenceOral-iclr2013-conference": ("main", "accepted", "oral"),
            "conferencePoster-iclr2013-conference": ("main", "accepted", "poster"),
            "conferenceOral-iclr2013-workshop": ("workshop", "accepted", "oral"),
            "conferencePoster-iclr2013-workshop": ("workshop", "accepted", "poster"),
            "reject": (None, "rejected", None),
        },
    ),
    ("ICLR", 2014): Adapter(
        "ICLR", 2014,
        (Listing("ICLR.cc/2014/conference/-/submission", "main"), Listing("ICLR.cc/2014/workshop/-/submission", "workshop")),
        "none", no_decision=frozenset({"submitted, no decision"}), gaps=(_ICLR_2014_GAP,),
    ),
    ("ICLR", 2015): Adapter(
        "ICLR", 2015, (), "none",
        gaps=("ICLR 2015 has no OpenReview group (`/groups?parent=ICLR.cc` skips 2015): nothing to crawl (TASK-096)",),
    ),
    ("ICLR", 2016): Adapter(
        "ICLR", 2016, (Listing("ICLR.cc/2016/workshop/-/submission", "workshop"),), "none",
        gaps=("ICLR 2016: the conference track is not on OpenReview (`ICLR.cc/2016/conference/-/submission` has 0 "
              "notes; TASK-096)", "ICLR 2016: workshop notes carry no decision, so every status is unknown"),
    ),
    ("ICLR", 2017): Adapter(
        "ICLR", 2017,
        (Listing("ICLR.cc/2017/conference/-/submission", "main"), Listing("ICLR.cc/2017/workshop/-/submission", "workshop")),
        "venue",
    ),
    ("ICLR", 2018): Adapter(
        "ICLR", 2018, _conf("ICLR", 2018, desk_rejected=False), "decision_note",
        decision_notes=DecisionNotes("ICLR.cc/2018/Conference/-/Acceptance_Decision", "decision", {
            "Accept (Oral)": (None, "accepted", "oral"),
            "Accept (Poster)": (None, "accepted", "poster"),
            # invited to the workshop track: not a main-track acceptance (as classify.py reads 2017's string)
            "Invite to Workshop Track": ("workshop", "unknown", None),
            "Reject": (None, "rejected", None),
        }),
    ),
    ("ICLR", 2019): Adapter(
        "ICLR", 2019, _conf("ICLR", 2019, desk_rejected=False), "decision_note",
        decision_notes=DecisionNotes("ICLR.cc/2019/Conference/-/Paper{number}/Meta_Review", "recommendation", {
            "Accept (Oral)": (None, "accepted", "oral"),
            "Accept (Poster)": (None, "accepted", "poster"),
            "Reject": (None, "rejected", None),
        }),
    ),
    ("ICLR", 2020): Adapter(
        "ICLR", 2020, _conf("ICLR", 2020), "decision_note",
        decision_notes=DecisionNotes("ICLR.cc/2020/Conference/Paper{number}/-/Decision", "decision", {
            "Accept (Poster)": (None, "accepted", "poster"),
            # 108 spotlights and 48 talks on the live forums (2026-09-29, TASK-123); a talk is an oral
            "Accept (Spotlight)": (None, "accepted", "spotlight"),
            "Accept (Talk)": (None, "accepted", "oral"),
            "Reject": (None, "rejected", None),
        }),
    ),
    ("ICLR", 2021): Adapter(
        "ICLR", 2021, _conf("ICLR", 2021), "venue_then_decision_note",
        decision_notes=DecisionNotes("ICLR.cc/2021/Conference/Paper{number}/-/Decision", "decision", {
            "Accept (Poster)": (None, "accepted", "poster"),
            "Reject": (None, "rejected", None),
        }),
    ),
    ("ICLR", 2022): Adapter("ICLR", 2022, _conf("ICLR", 2022), "venue"),
    ("ICLR", 2023): Adapter(
        "ICLR", 2023,
        (*_conf("ICLR", 2023), Listing("ICLR.cc/2023/TinyPapers/-/Blind_Submission", "tiny_papers"),
         Listing("ICLR.cc/2023/BlogPosts/-/Blind_Submission", "blogpost")),
        "venue",
        gaps=("ICLR 2023 Tiny Papers: every note says `Submitted to Tiny Papers @ ICLR 2023`, so status is unknown",),
    ),
    ("NeurIPS", 2021): Adapter(
        "NeurIPS", 2021,
        (Listing("NeurIPS.cc/2021/Conference/-/Blind_Submission", "main"),
         Listing("NeurIPS.cc/2021/Conference/-/Withdrawn_Submission", "main", "withdrawn"),
         Listing("NeurIPS.cc/2021/Conference/-/Desk_Rejected_Submission", "main", "desk_rejected"),
         Listing("NeurIPS.cc/2021/Track/Datasets_and_Benchmarks/Round1/-/Submission", "datasets_benchmarks"),
         Listing("NeurIPS.cc/2021/Track/Datasets_and_Benchmarks/Round2/-/Submission", "datasets_benchmarks")),
        "venue",
        gaps=("NeurIPS 2021: rejected papers are public only when the authors opted in",),
    ),
    ("NeurIPS", 2022): Adapter(
        "NeurIPS", 2022,
        (Listing("NeurIPS.cc/2022/Conference/-/Blind_Submission", "main"),
         Listing("NeurIPS.cc/2022/Conference/-/Withdrawn_Submission", "main", "withdrawn"),
         Listing("NeurIPS.cc/2022/Conference/-/Desk_Rejected_Submission", "main", "desk_rejected"),
         Listing("NeurIPS.cc/2022/Track/Datasets_and_Benchmarks/-/Submission", "datasets_benchmarks")),
        "venue",
        gaps=("NeurIPS 2022: rejected papers are public only when the authors opted in (D&B: only accepted papers "
              "are public)",),
    ),
}  # fmt: skip

# `content.venue` → presentation, for the venue strings that state one (the status table is classify.py's)
_PRESENTATION: dict[str, str] = {
    **{f"ICLR {y} {w}": w.lower() for y in (2017, 2021, 2022) for w in ("Oral", "Spotlight", "Poster")},
    **{f"NeurIPS 2021 {w}": w.lower() for w in ("Oral", "Spotlight", "Poster")},
    "ICLR 2023 poster": "poster",
}
_NOT_A_TRACK = frozenset({"other", "unknown"})  # a venueid track that can't disagree with anything


def is_twin_outcome(listing_track: str, outcome_track: str | None, by_id: Classification | None) -> bool:
    """Is a main-track outcome on a note of a `listing_track` submission listing its conference twin's (TASK-152)?
    Yes when the listing isn't main and the venueid names no track (ICLR 2017's `conference`): one that names a
    track keeps the agreement check in `judge`, its disagreement a conflict row. The RIS importer asks the same
    question of scholarmend's `invitation` claim (TASK-157)."""
    return (
        outcome_track == "main"
        and listing_track != "main"
        and (by_id is None or not by_id.parsed or by_id.track in _NOT_A_TRACK)
    )


def submission_listing(venue: str, year: int, invitation: str) -> Listing | None:
    """The v1 submission listing of `venue` `year` whose invitation is exactly `invitation`, or None (another
    venue-year, a withdrawn or desk-rejected invitation, an invitation no adapter lists)."""
    ad = ADAPTERS.get((venue, year))
    found = (
        [lst for lst in ad.listings if lst.invitation == invitation and lst.role == "submission"]
        if ad
        else []
    )
    return found[0] if found else None


def api_for(venue: str, year: int) -> Literal["v1", "v2"]:
    """Which OpenReview API serves a venue-year; refuses a year OpenReview doesn't hold (its source is the
    proceedings) and an unknown venue."""
    first = FIRST_V2_YEAR.get(venue)
    if first is None:
        raise ValueError(f"unknown venue {venue!r}: one of {', '.join(FIRST_V2_YEAR)}")
    if year >= first:
        return "v2"
    if (venue, year) in ADAPTERS:
        return "v1"
    raise ValueError(
        f"{venue} {year} is not on OpenReview: its source is the proceedings (`op ingest proceedings`, TASK-052/053)"
    )


def adapter(venue: str, year: int) -> Adapter:
    if api_for(venue, year) != "v1":
        raise ValueError(f"{venue} {year} is on OpenReview API v2, not v1 (`openreview_v2`)")
    return ADAPTERS[(venue, year)]


def cache_root(cache: Path) -> Path:
    return cache / "openreview" / "v1"


def http_dir(cache: Path) -> Path:
    return cache_root(cache) / "http"


def crawls_dir(cache: Path) -> Path:
    return cache_root(cache) / "crawls"


def make_client(cache: Path, **kw: Any) -> OpenReviewClient:
    """A client for api1 (logging in on api2, whose token api1 accepts), caching under `…/v1/http/`."""
    return OpenReviewClient(http_dir(cache), base=API_V1, login_base=API_V2, **kw)


# --- the report ---------------------------------------------------------------------------------------------


@dataclass
class CrawlReport(Report):
    """What one v1 venue-year gave; `to_manifest()` goes into the crawl file and the snapshot manifest."""

    source: str = field(default=SOURCE, init=False)
    venue: str
    year: int
    page_size: int = PAGE_SIZE
    complete: bool = True  # False on a dry run that met an uncached response
    listings: dict[str, int] = field(default_factory=dict)  # invitation → notes listed
    forums: int = 0  # forum listings read for a decision note
    notes_read: int = 0
    imported: int = 0
    skipped: Counter[str] = field(default_factory=lambda: Counter(dict.fromkeys(V1_SKIP_REASONS, 0)))
    unmapped: Counter[str] = field(
        default_factory=Counter
    )  # evidence kind → notes whose string isn't in a table
    unknown_track: int = 0
    unknown_status: int = 0
    abstract_missing: int = 0
    authors_split: int = 0  # `content.authors` split by the count-checked rule (decision-019)
    authors_unsplit_ids: list[str] = field(default_factory=list)  # the refused notes' forum ids
    authors_unsplit: int = (
        0  # a split the rule refused: authors kept out (empty), the raw value in the evidence
    )
    withdrawn_by_twin: int = (
        0  # undecided notes the twin rule made `withdrawn`, no longer in `unmapped` (TASK-139)
    )
    twin_outcome: int = 0  # notes whose main-track outcome was their conference twin's: `unknown` (TASK-152)
    twins_linked: int = 0  # copies on a non-main listing linked to their main-track twin (TASK-159)
    twins_ambiguous: int = 0  # copies whose title several main-track submissions share, none named: unlinked
    track_status: dict[str, Counter[str]] = field(default_factory=dict)
    gaps: tuple[str, ...] = ()
    conflicts: list[Conflict] = field(default_factory=list)
    would_fetch: list[str] = field(default_factory=list)
    forums_uncached: int = 0  # dry run: forum listings a real run would fetch

    api = "v1"

    def to_manifest(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "api": self.api,
            "venue": self.venue,
            "year": self.year,
            "complete": self.complete,
            "page_size": self.page_size,
            "listings": dict(sorted(self.listings.items())),
            "forums": self.forums,
            "notes_read": self.notes_read,
            "imported": self.imported,
            "skipped": dict(sorted(self.skipped.items())),
            "unmapped": dict(sorted(self.unmapped.items())),
            "unknown_track": self.unknown_track,
            "unknown_status": self.unknown_status,
            "abstract_missing": self.abstract_missing,
            "authors_split": self.authors_split,
            "authors_unsplit": self.authors_unsplit,
            # listed only when there are any, so a crawl with none keeps its manifest shape
            **(
                {"authors_unsplit_ids": sorted(set(self.authors_unsplit_ids))}
                if self.authors_unsplit_ids
                else {}
            ),
            **({"withdrawn_by_twin": self.withdrawn_by_twin} if self.withdrawn_by_twin else {}),
            **({"twin_outcome": self.twin_outcome} if self.twin_outcome else {}),
            **({"twins_linked": self.twins_linked} if self.twins_linked else {}),
            **({"twins_ambiguous": self.twins_ambiguous} if self.twins_ambiguous else {}),
            "conflicts": len(self.conflicts),
            "track_status": {t: dict(sorted(s.items())) for t, s in sorted(self.track_status.items())},
            "coverage_gaps": list(self.gaps),
            "crawl_window": self.crawl_window(),
        }
        if not self.complete:
            out["would_fetch"] = list(self.would_fetch)
            out["forums_uncached"] = self.forums_uncached
        return out


@dataclass(frozen=True)
class Crawl:
    records: tuple[PaperRecord, ...]
    report: CrawlReport

    @property
    def reports(self) -> tuple[CrawlReport]:
        return (self.report,)


# --- status evidence ------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Page:
    """Where a claim came from: a cached response's URL and fetch time."""

    url: str
    fetched_at: datetime


@dataclass(frozen=True)
class Verdict:
    track: str
    status: str
    presentation: str | None
    track_evidence: str
    status_evidence: str
    track_page: Page
    status_page: Page  # the listing page, or the forum page holding the decision note
    conflicts: tuple[
        tuple[str, str, str], ...
    ] = ()  # (field, value_a with its evidence, value_b with its evidence)
    unmapped: str | None = None  # the evidence kind whose string isn't in a table
    twin_outcome: bool = False  # a main-track outcome read as the note's conference twin's (TASK-152)


ForumReader = Callable[[str], tuple[Page, list[Mapping[str, Any]]] | None]


def _content_str(content: Mapping[str, Any], key: str) -> str | None:
    value = content.get(key)
    return value if isinstance(value, str) and value else None


@dataclass(frozen=True)
class _Found:
    """What one kind of status evidence said: an outcome, or why there is none."""

    outcome: Outcome | None
    evidence: str
    page: Page | None = None  # the forum page, when a decision note was read
    unmapped: str | None = None  # the evidence kind whose string isn't in a table
    conflicts: tuple[tuple[str, str, str], ...] = ()


def _decision_note(ad: Adapter, note: Mapping[str, Any], read_forum: ForumReader) -> _Found:
    """The forum's decision note: the reply whose invitation is this year's (with the submission's number),
    in this forum, replying to the submission itself."""
    spec = ad.decision_notes
    assert spec is not None
    nid, number = note["id"], note.get("number")
    if "{number}" in spec.invitation and not isinstance(number, int):
        return _Found(None, "no submission number to find its decision note by", unmapped="decision_note")
    invitation = spec.invitation.format(number=number)
    got = read_forum(nid)
    if got is None:
        return _Found(None, "decision note not fetched (dry run)")
    page, notes = got
    decisions = sorted(
        (n["id"], value)
        for n in notes
        if n.get("invitation") == invitation and n.get("forum") == nid and n.get("replyto") == nid
        and isinstance(n.get("id"), str) and n["id"] != nid and isinstance(n.get("content"), Mapping)
        and isinstance(value := n["content"].get(spec.field), str)
    )  # fmt: skip
    if not decisions:
        return _Found(None, NO_DECISION_NOTE, page, "decision_note")
    if any(value not in spec.values for _, value in decisions):
        return _Found(None, "decision note string not in the table", page, "decision_note")
    if len({spec.values[value] for _, value in decisions}) > 1:
        (a, va), (b, vb) = decisions[0], decisions[-1]
        conflict = (
            "status",
            f"{spec.values[va][1]} (decision note {a})",
            f"{spec.values[vb][1]} (decision note {b})",
        )
        return _Found(None, "decision notes disagree", page, conflicts=(conflict,))
    did, value = decisions[0]
    return _Found(spec.values[value], f"decision note {did} ({spec.field}={value})", page)


def _submission_evidence(ad: Adapter, content: Mapping[str, Any], by_venue: Classification | None,
                         note: Mapping[str, Any], read_forum: ForumReader) -> _Found:  # fmt: skip
    """A submission-listing note's status evidence, by the year's `status_from`."""
    venue_string = _content_str(content, "venue")
    if ad.status_from == "decision_field":
        decision = _content_str(content, "decision")
        if decision is None or decision not in ad.decisions:
            return _Found(None, "content.decision not in the table", unmapped="content.decision")
        return _Found(ad.decisions[decision], f"content.decision={decision}")
    if ad.status_from == "none":
        decision = _content_str(content, "decision")
        unmapped = "content.decision" if decision is not None and decision not in ad.no_decision else None
        return _Found(None, "no decision on OpenReview for this venue-year", unmapped=unmapped)
    if by_venue is not None and by_venue.parsed and venue_string is not None:
        presentation = _PRESENTATION.get(venue_string)
        return _Found((by_venue.track, by_venue.status, presentation), f"content.venue={venue_string}")
    if ad.status_from == "venue":
        return _Found(None, "content.venue absent or not in the v1 table", unmapped="content.venue")
    return _decision_note(ad, note, read_forum)  # decision_note, or venue_then_decision_note without a venue


def judge(ad: Adapter, listing: Listing, note: Mapping[str, Any], listing_page: Page,
          read_forum: ForumReader) -> Verdict | str:  # fmt: skip
    """A listed note's track, status and presentation from this year's evidence (module docstring), or the
    reason it is skipped (`out_of_scope`)."""
    content: Mapping[str, Any] = note["content"] if isinstance(note.get("content"), Mapping) else {}
    venue_string = _content_str(content, "venue")
    by_venue = classify_v1_venue(venue_string) if venue_string else None
    if by_venue is not None and by_venue.parsed and (by_venue.venue, by_venue.year) != (ad.venue, ad.year):
        return "out_of_scope"
    raw = _content_str(content, "venueid")
    by_id = classify_venueid(raw) if raw else None
    if by_id is not None and by_id.parsed and (by_id.venue, by_id.year) != (ad.venue, ad.year):
        return "out_of_scope"  # never re-yeared (openreview-venueids rule 3)

    listed = f"invitation={listing.invitation}"
    conflicts: list[tuple[str, str, str]] = []
    twin_outcome = False
    if listing.role != "submission":  # the withdrawn / desk-rejected invitation (decision-012)
        found = _Found((None, listing.role, None), listed)
        if by_venue is not None and by_venue.parsed and by_venue.status == "accepted":
            # e.g. ICLR 2021 xGZG2kS5bFk: never resolved by picking a side
            conflicts.append(
                ("status", f"{listing.role} ({listed})", f"accepted (content.venue={venue_string})")
            )
            found = _Found((None, "unknown", None), f"conflict: {listed} vs content.venue={venue_string}")
    else:
        found = _submission_evidence(ad, content, by_venue, note, read_forum)
        conflicts += found.conflicts
        twin_outcome = found.outcome is not None and is_twin_outcome(listing.track, found.outcome[0], by_id)
        if twin_outcome:
            # a main-track outcome on a note submitted to another track is its conference twin's, not its own
            # (ICLR 2017's workshop copies of rejected papers say `Submitted to ICLR 2017`; TASK-152)
            found = replace(found, outcome=(None, "unknown", None),
                            evidence=f"{found.evidence} (the main track's outcome, not this {listing.track} "
                            "submission's)")  # fmt: skip
    status_page = found.page or listing_page
    named_track, status, presentation = found.outcome or (None, "unknown", None)
    if named_track is None:
        track, track_ev, track_page = listing.track, listed, listing_page
    else:
        track, track_ev, track_page = named_track, found.evidence, status_page
    if (by_id is not None and by_id.parsed and by_id.track not in _NOT_A_TRACK and track not in _NOT_A_TRACK
            and by_id.track != track):  # fmt: skip
        conflicts.append(("track", f"{track} ({track_ev})", f"{by_id.track} (venueid={raw})"))
        track, track_ev, track_page, presentation = (
            "unknown",
            f"conflict: {track_ev} vs venueid={raw}",
            listing_page,
            None,
        )
    return Verdict(track, status, presentation, track_ev, found.evidence, track_page, status_page,
                   tuple(conflicts), found.unmapped, twin_outcome)  # fmt: skip


# --- notes → records ---------------------------------------------------------------------------------------------


def _pdf(nid: str, value: Any) -> str | None:
    """An OpenReview PDF path (`/pdf/<sha1>.pdf`, or ICLR 2016's `/pdf/<forum id>.pdf`) as a URL; anything else
    (ICLR 2013–2014 link arXiv abstract pages) is not a PDF of this note and is dropped."""
    if isinstance(value, str) and (
        re.fullmatch(r"/pdf/[0-9a-f]{40}\.pdf", value) or value == f"/pdf/{nid}.pdf"
    ):
        return f"https://openreview.net{value}"
    return None


# --- authors (decision-019) ------------------------------------------------------------------------------------

_LEADING_AND = re.compile(
    r"^and(\s+|$)"
)  # lowercase only, as every `and` seen live; `And`/`AND` are left as is
_TRAILING_AND = re.compile(r"\s+and$")  # a dangling `A and`
_AUTHOR_SEPARATOR = re.compile(
    r",\s*and\s+|,|\s+and\s+"
)  # `, and ` first, so an Oxford comma is one separator
# an entry starting with `and ` (or a bare `and`), `A and B` in one entry, or a dangling `A and`
_NEEDS_SPLIT = re.compile(r"^\s*and(\s|$)|\sand(\s|$)")

AuthorsHow = Literal["listed", "split", "refused"]


def author_count(content: Mapping[str, Any]) -> int | None:
    """How many authors the note names by id: `content.authorids`, or `content.author_emails` (a list, or one
    comma-separated string, as early ICLR 2017 writes it) when there are no ids; None when neither says."""
    ids = content.get("authorids")
    if isinstance(ids, list):
        return len(ids)
    emails = content.get("author_emails")
    if isinstance(emails, list):
        return len(emails)
    if isinstance(emails, str) and emails.strip():
        return sum(1 for e in emails.split(",") if e.strip())
    return None


def _split_entry(entry: str) -> list[str]:
    body = _TRAILING_AND.sub("", _LEADING_AND.sub("", entry.strip(), count=1))
    return [p.strip() for p in _AUTHOR_SEPARATOR.split(body) if p.strip()]


def split_authors(raw: Any, count: int | None) -> tuple[tuple[str, ...], AuthorsHow]:
    """`content.authors` as names (decision-019). A list with no entry starting with `and ` and none joining two
    names with ` and ` is taken as listed, untouched. Anything else (one string, or a list with such an entry) is
    split: each entry loses a leading `and ` (a bare `and` entry becomes nothing) and a trailing ` and`, and is split
    at `, and `, `,` and ` and `. Only lowercase `and` is a separator. The split is accepted only
    when it gives exactly `count` names (the note's author ids, `author_count`) and no name still needs a split;
    otherwise it is refused and the authors are empty. So an accepted split always has the id count, and a
    split's output, taken again, is listed as it is."""
    if isinstance(raw, list):
        entries = [v for v in raw if isinstance(v, str) and v.strip()]
        if not any(_NEEDS_SPLIT.search(v) for v in entries):
            return tuple(entries), "listed"
    elif isinstance(raw, str) and raw.strip():
        entries = [raw]
    else:
        return (), "listed"
    names = [name for entry in entries for name in _split_entry(entry)]
    # the last check is the implementer's guard (decision-019): a name that still needs a split is refused
    if count is None or len(names) != count or any(_NEEDS_SPLIT.search(n) for n in names):
        return (), "refused"
    return tuple(names), "split"


def _authors_evidence(raw: Any, count: int | None, how: AuthorsHow, names: Sequence[str]) -> str:
    """The authors claim's evidence: `content.authors` when listed; else the rule's outcome and the raw value."""
    if how == "listed":
        return "content.authors"
    counted = "no content.authorids or author_emails to count" if count is None else f"{count} author ids"
    shown = json.dumps(raw, ensure_ascii=False)
    if how == "split":
        return f"content.authors split at `and` and commas into {len(names)} names, as many as its {counted} (raw: {shown})"
    return f"content.authors not split: its pieces don't match its {counted} (raw: {shown})"


def note_record(
    ad: Adapter, listing: Listing, note: Mapping[str, Any], listing_page: Page, read_forum: ForumReader,
    report: CrawlReport | None = None,
) -> PaperRecord | str:  # fmt: skip
    """The record for one listed note, or the reason it is skipped (one of V1_SKIP_REASONS)."""
    nid = note.get("id")
    if not isinstance(nid, str) or nid != note.get("forum"):
        return "not_submission"
    if not FORUM_ID.fullmatch(nid):
        return "invalid"
    content: Mapping[str, Any] = note["content"] if isinstance(note.get("content"), Mapping) else {}
    title = _text(content.get("title"))
    if title is None:
        return "no_title"
    verdict = judge(ad, listing, note, listing_page, read_forum)
    if isinstance(verdict, str):
        return verdict
    venue, year = ad.venue, ad.year
    rid = f"op:{venue.lower()}:{year}:{nid}"
    abstract = _text(content.get("abstract"))
    if abstract is not None and (abstract.startswith("…") or abstract.endswith("…")):
        abstract = None
    raw_authors = content.get("authors")
    count = author_count(content)
    authors, authors_how = split_authors(raw_authors, count)
    keywords = _strings(content.get("keywords"))
    vid = _content_str(content, "venueid")
    urls = Urls(forum=_FORUM_URL.format(nid), pdf=_pdf(nid, content.get("pdf")))

    def claim(fld: ClaimField, value: ClaimValue, ev: str, page: Page = listing_page) -> Claim:
        return Claim(
            field=fld, value=value, source=SOURCE, url=page.url, fetched_at=page.fetched_at, evidence=ev
        )

    provenance = [
        claim("venue", venue, f"invitation={listing.invitation}"),
        claim("year", year, f"invitation={listing.invitation}"),
        claim("track", verdict.track, verdict.track_evidence, verdict.track_page),
        claim("status", verdict.status, verdict.status_evidence, verdict.status_page),
        claim("title", title, "content.title"),
        claim("authors", authors, _authors_evidence(raw_authors, count, authors_how, authors)),
        claim("urls.forum", urls.forum, "note.id"),
    ]  # fmt: skip
    if verdict.presentation is not None:
        provenance.append(
            claim("presentation", verdict.presentation, verdict.status_evidence, verdict.status_page)
        )
    if abstract is not None:
        provenance.append(claim("abstract", abstract, "content.abstract"))
    if keywords:
        provenance.append(claim("keywords", keywords, "content.keywords"))
    if vid is not None:
        provenance.append(claim("venue_id_raw", vid, "content.venueid"))
    if urls.pdf:
        provenance.append(claim("urls.pdf", urls.pdf, "content.pdf"))
    try:
        record = PaperRecord.build(
            id=rid, title=title, abstract=abstract, authors=authors, venue=venue, year=year, track=verdict.track,
            status=verdict.status, presentation=verdict.presentation, venue_id_raw=vid, urls=urls,
            keywords=keywords, provenance=tuple(provenance),
        )  # fmt: skip
    except ValidationError:
        return "invalid"
    if report is not None:
        report.authors_split += authors_how == "split"
        report.authors_unsplit += authors_how == "refused"
        if authors_how == "refused":
            report.authors_unsplit_ids.append(nid)
            log.debug("openreview_v1_authors_unsplit", extra={"forum": nid})
        if verdict.twin_outcome:
            report.twin_outcome += 1
            log.debug("openreview_v1_twin_outcome", extra={"forum": nid})
        if verdict.unmapped is not None:
            report.unmapped[verdict.unmapped] += 1
            log.debug("openreview_v1_unmapped", extra={"forum": nid, "evidence": verdict.unmapped})
        for fld, a, b in verdict.conflicts:
            report.conflicts.append(Conflict(rid, fld, a, SOURCE, b, SOURCE, CONFLICT))
            log.debug("openreview_v1_conflict", extra={"forum": nid, "field": fld})
    return record


# --- the crawl ----------------------------------------------------------------------------------------------------


def crawl(client: OpenReviewClient, venue: str, year: int, *, dry_run: bool = False,
          page_size: int = PAGE_SIZE) -> Crawl:  # fmt: skip
    """Every public submission of one v1 venue-year as records (module docstring). A dry run reads only the
    cache (the client must be offline): an uncached listing is noted in `would_fetch`, an uncached forum
    counted (its note's status stays `unknown` in the dry run's counts)."""
    ad = adapter(venue, year)
    if dry_run and not client.offline:
        raise ValueError("a dry run needs an offline client")
    began, purged = time.monotonic(), client.incompatible
    report = CrawlReport(venue, year, page_size=page_size, gaps=ad.gaps)
    records: dict[str, PaperRecord] = {}
    numbers: dict[str, object] = {}  # record id → its note's `number`, for rule 5
    silent: set[str] = set()  # records whose note carries no status evidence (rule 5's silent twin)
    listed: dict[str, Listed] = {}  # record id → its listing and `_bibtex` forum, for the twin links (rule 6)
    # heartbeats count `imported` before rule 5's collapse, which runs after the listings: NeurIPS 2021's last
    # heartbeat can show up to 3,020 imported where the finished line says 2,720
    progress = Progress(log, client, report.api, venue, year, page_size, lambda: {
        "notes_read": report.notes_read, "forums": report.forums, "imported": len(records),
        "skipped": sum(report.skipped.values())})  # fmt: skip

    def read_forum(fid: str) -> tuple[Page, list[Mapping[str, Any]]] | None:
        notes: list[Mapping[str, Any]] = []
        first: Page | None = None
        try:
            for entry, items in _pages(client, "/notes", {"forum": fid}, "notes", page_size):
                report.fetched.append(datetime.fromisoformat(entry["fetched_at"]))
                first = first or Page(entry["url"], datetime.fromisoformat(entry["fetched_at"]))
                notes += [n for n in items if isinstance(n, Mapping)]
        except CacheMiss as e:
            if not dry_run:
                raise
            report.forums_uncached += 1
            if report.forums_uncached == 1:
                report.would_fetch.append(e.url)
            report.complete = False
            return None
        report.forums += 1
        assert first is not None
        return first, notes

    for listing in ad.listings:
        try:
            _listing(
                client,
                ad,
                listing,
                report,
                records,
                numbers,
                silent,
                read_forum,
                page_size,
                progress.tick,
                listed,
            )
        except CacheMiss as e:
            if not dry_run:
                raise
            report.complete = False
            report.would_fetch.append(e.url)
    twins = withdrawn_twins(records)  # rule 4 across two notes: after every listing, before rule 5
    for c in twins.conflicts:
        report.conflicts.append(c)
        log.debug("openreview_v1_conflict", extra={"forum": c.id.split(":", 3)[3], "field": c.field})
    for rid in twins.withdrawn:
        # its missing decision note was counted in `unmapped`; the twin now answers it, so it moves out of the
        # attention count into its own
        report.unmapped["decision_note"] -= 1
        report.withdrawn_by_twin += 1
        log.debug("openreview_v1_withdrawn_twin", extra={"forum": records[rid].native})
    if report.unmapped["decision_note"] < 0:  # each such note was counted once; never hide a miscount
        raise RuntimeError(f"{venue} {year}: the twin rule resolved more undecided notes than were counted")
    report.unmapped = +report.unmapped  # drop a kind the twin rule emptied
    # a record the twin rule touched is never collapsed: the rule changes a status, never which records exist
    exempt = {c.id for c in report.conflicts} | set(twins.withdrawn)
    rid_of = {r.native: rid for rid, r in records.items()}
    for kept, dropped in collapse_duplicate_submissions(records, numbers, exempt):
        report.skipped[DUPLICATE_SUBMISSION] += 1
        log.debug("openreview_duplicate_submission", extra={"forum": dropped, "kept": kept})
        # a survivor is silent only if every note it stands for is (TASK-147): otherwise the lower number alone
        # would decide whether the silent-twin collapse sees a silent note
        if rid_of[dropped] not in silent:
            silent.discard(rid_of[kept])
    # rule 5's silent twin (TASK-132), after the identical notes; it skips the same records
    for kept, dropped in collapse_silent_twins(records, silent, exempt):
        report.skipped[DUPLICATE_SUBMISSION] += 1
        log.debug("openreview_duplicate_submission", extra={"forum": dropped, "kept": kept})
    # rule 6 (TASK-159): link each copy on a non-main listing to its main-track twin, after both collapses
    linked, ambiguous = link_twins(records, listed)
    for copy, twin in linked:
        report.twins_linked += 1
        log.debug("openreview_v1_twin_linked", extra={"forum": copy, "twin": twin})
    report.twins_ambiguous = len(ambiguous)
    for r in records.values():
        report.track_status.setdefault(r.track, Counter())[r.status] += 1
    report.imported = len(records)
    report.unknown_track = sum(r.track == "unknown" for r in records.values())
    report.unknown_status = sum(r.status == "unknown" for r in records.values())
    report.abstract_missing = sum(r.abstract is None for r in records.values())
    report.conflicts.sort()
    incompatible = client.incompatible - purged  # this crawl's share of the client's count
    log.info("openreview_crawl_finished",
             extra={"api": "v1", "venue": venue, "year": year, "complete": report.complete,
                    "listings": len(report.listings), "forums": report.forums, "notes_read": report.notes_read,
                    "imported": report.imported, "skipped": sum(report.skipped.values()),
                    "unknown_track": report.unknown_track, "unknown_status": report.unknown_status,
                    "conflicts": len(report.conflicts), "twins_linked": report.twins_linked,
                    "requests": client.requests, "cached": client.cached,
                    "cache_incompatible": incompatible,
                    "ms": elapsed_ms(began, time.monotonic)})  # fmt: skip
    if ad.gaps:
        log.info("openreview_coverage_gap", extra={"venue": venue, "year": year, "gaps": len(ad.gaps)})
    if (
        report.unknown_track
        or report.conflicts
        or sum(report.unmapped.values())
        or report.skipped["out_of_scope"]
        or report.skipped["duplicate"]
        or report.skipped[DUPLICATE_SUBMISSION]
        or report.skipped["invalid"]
        or incompatible
    ):
        log.warning("openreview_crawl_attention",
                    extra={"api": "v1", "venue": venue, "year": year, "unknown_track": report.unknown_track,
                           "unmapped": sum(report.unmapped.values()), "conflicts": len(report.conflicts),
                           "out_of_scope": report.skipped["out_of_scope"],
                           "duplicate": report.skipped["duplicate"],
                           "duplicate_submission": report.skipped[DUPLICATE_SUBMISSION],
                           "invalid": report.skipped["invalid"],
                           "cache_incompatible": incompatible})  # fmt: skip
    return Crawl(tuple(sorted(records.values(), key=lambda r: r.id)), report)


def _listing(client: OpenReviewClient, ad: Adapter, listing: Listing, report: CrawlReport,
             records: dict[str, PaperRecord], numbers: dict[str, object], silent: set[str],
             read_forum: ForumReader, page_size: int, tick: Callable[[], None],
             listed: dict[str, Listed]) -> None:  # fmt: skip
    """Page through one invitation's notes into `records` (and the silent ones' ids into `silent`), checking the
    listing is consistent (v1 sends `count` on every page); `tick()` before each note (the crawl's heartbeat)."""
    seen: set[str] = set()
    rows = 0
    counts: set[int] = set()
    for entry, notes in _pages(client, "/notes", {"invitation": listing.invitation}, "notes", page_size):
        report.fetched.append(datetime.fromisoformat(entry["fetched_at"]))
        count = entry["json"].get("count")
        if type(count) is not int or count < 0:
            raise CrawlError(
                f"the listing of {listing.invitation} has a missing or invalid count; "
                "re-run with --refresh to fetch it again"
            )
        counts.add(count)
        seen |= {i for n in notes if isinstance(n, Mapping) and isinstance(i := n.get("id"), str)}
        rows += len(notes)
        page = Page(entry["url"], datetime.fromisoformat(entry["fetched_at"]))
        for note in notes:
            tick()
            report.notes_read += 1
            if not isinstance(note, Mapping):
                report.skipped["invalid"] += 1
                continue
            got = note_record(ad, listing, note, page, read_forum, report)
            if isinstance(got, str):
                report.skipped[got] += 1
                log.debug("openreview_note_skipped", extra={"forum": note.get("id"), "reason": got})
            elif got.id in records:
                prior = records[got.id]
                if got.model_dump(exclude={"provenance"}) != prior.model_dump(exclude={"provenance"}):
                    raise CrawlError(
                        f"note {note.get('id')} appears with conflicting data in two status listings; "
                        "re-run with --refresh to fetch all listings together"
                    )
                report.skipped["duplicate"] += 1
                log.debug(
                    "openreview_v1_duplicate",
                    extra={"forum": note.get("id"), "invitation": listing.invitation},
                )
            else:
                records[got.id] = got
                numbers[got.id] = note.get("number")
                listed[got.id] = Listed(listing, _bibtex_forum(note))
                if _says_nothing_of_status(ad, note, got):
                    silent.add(got.id)
    if rows != len(seen) or len(counts) > 1 or (counts and counts.pop() != rows):
        raise CrawlError(
            f"the listing of {listing.invitation} changed between its cached pages (rows, distinct ids and count "
            "disagree); re-run with --refresh to fetch it again"
        )
    report.listings[listing.invitation] = rows


# --- a copy and its main-track twin (rule 6, TASK-159, decision-028) -------------------------------------------


@dataclass(frozen=True)
class Listed:
    """Where a record's note was listed, and the forum its `_bibtex` url names (None: no url)."""

    listing: Listing
    bibtex_forum: str | None


_BIBTEX_FORUM = re.compile(r"url=\{https://openreview\.net/forum\?id=([A-Za-z0-9_-]+)\}")


def _bibtex_forum(note: Mapping[str, Any]) -> str | None:
    content = note.get("content")
    bib = content.get("_bibtex") if isinstance(content, Mapping) else None
    found = _BIBTEX_FORUM.search(bib) if isinstance(bib, str) else None
    return found.group(1) if found else None


def link_twins(
    records: dict[str, PaperRecord], listed: Mapping[str, Listed]
) -> tuple[list[tuple[str, str]], list[str]]:
    """Link, in place, each copy (a record from a non-main submission listing) to its twin: the main-track
    submission listing's record with the same dedup title key. The copy's `_bibtex` decides between several such
    records when it names one of them; otherwise there must be exactly one. A title whose key is empty
    (punctuation or symbols only) is never matched, as dedup never matches it. A `_bibtex` naming a record with
    another title is ignored (ICLR 2017's 35 `Invite to Workshop` notes all name one unrelated forum). Both stay
    records (two forum ids are two submissions, dedup-rules §Never merge); each gets one `twin` claim, its value
    the other records' ids, sorted, its url and fetched_at its own title claim's (the listing page it came from).
    Run after rule 5's collapses, so a dropped note is never named. On the 2026-09-29 crawl only ICLR 2017 has
    such copies: 53 of its 161 workshop notes (docs/results/2026-10-02-iclr-2017-twins.md). Return the (copy,
    twin) native ids, sorted, and the copies left unlinked because several main-track submissions share their title
    and their `_bibtex` names none (native ids, sorted)."""
    mains: defaultdict[str, list[str]] = defaultdict(list)
    for rid, at in listed.items():
        main = rid in records and at.listing.role == "submission" and at.listing.track == "main"
        if main and (key := title_key(records[rid].title)):
            mains[key].append(rid)
    links: defaultdict[str, list[tuple[str, str]]] = defaultdict(list)  # record id → (other id, evidence)
    pairs: list[tuple[str, str]] = []
    ambiguous: list[str] = []
    for rid in sorted(listed):  # in id order, so each record's links are too
        at = listed[rid]
        if rid not in records or at.listing.role != "submission" or at.listing.track == "main":
            continue
        copy = records[rid]
        same = sorted(mains.get(title_key(copy.title) or "\0", ()))  # "\0": no main record has that key
        named = [m for m in same if records[m].native == at.bibtex_forum]
        if named:
            [twin] = named
            why = "its _bibtex names that forum, the main-track submission with this title"
            theirs = "its _bibtex names this forum, the main-track submission with its title"
        elif len(same) == 1:
            [twin] = same
            why = "the only main-track submission with this title"
            theirs = "the only main-track submission with its title"
        else:
            if same:  # several main-track submissions share the title and its _bibtex names none: no link
                ambiguous.append(copy.native)
                log.debug(
                    "openreview_v1_twin_ambiguous", extra={"forum": copy.native, "candidates": len(same)}
                )
            continue
        track = at.listing.track
        links[rid].append((twin, f"{track} copy of {records[twin].native}: {why}"))
        links[twin].append((rid, f"{track} copy {copy.native}: {theirs}"))
        pairs.append((copy.native, records[twin].native))
    for rid, named_by in links.items():
        record = records[rid]
        title = next((c for c in record.claims("title") if c.source == SOURCE), None)
        if title is None:  # every v1 record is built with one (`note_record`); never guess a page
            raise CrawlError(f"{record.native} has no {SOURCE} title claim to date its twin claim by")
        claim = Claim(field="twin", value=tuple(o for o, _ in named_by), source=SOURCE, url=title.url,
                      fetched_at=title.fetched_at, evidence="; ".join(e for _, e in named_by))  # fmt: skip
        records[rid] = record.model_copy(update={"provenance": (*record.provenance, claim)})
    return sorted(pairs), ambiguous


# --- two notes of one paper (rule 5) -------------------------------------------------------------------------


def _same_paper(record: PaperRecord) -> str:
    """What must be equal for two notes to be one paper: everything the record carries except its id, its forum
    URL (both from the note id) and its provenance (the page each claim came from). So title (whitespace
    collapsed, case kept), authors in order, abstract, keywords, pdf, track, status, presentation and venueid
    all match exactly; `_bibtex`, which embeds the note id, never reaches a record. Status and track are
    compared too: ICLR 2018's 24 pdfs listed as both a blind and a withdrawn note are two claims to reconcile,
    not one note repeated."""
    return json.dumps(
        record.model_dump(mode="json", exclude={"id": True, "provenance": True, "urls": {"forum"}}),
        sort_keys=True,
    )


def collapse_duplicate_submissions(
    records: dict[str, PaperRecord], numbers: Mapping[str, object], exempt: Set[str] = frozenset()
) -> list[tuple[str, str]]:
    """Remove from `records` every second note of one paper (module docstring rule 5) and return the (kept,
    removed) native ids, sorted. Only records with a pdf and an integer note `number`, and not in `exempt` (those
    with a crawl conflict or made `withdrawn` by the twin rule), are candidates. The lowest number (then the lowest id) is kept: a deterministic
    tie-break, so the choice doesn't depend on which listing or page order the API returned and the same cache
    always keeps the same id. It is not "the original": the NeurIPS 2021 proceedings link the kept forum for
    177 of the 297 accepted pairs and the dropped one for 120 (e.g. `0hJ-U3aqUDf` #401 kept, `rvKD3iqtBdk`
    #3462 linked; research facts note, TASK-125)."""
    groups: defaultdict[str, list[str]] = defaultdict(list)
    for rid, record in records.items():
        if record.urls.pdf is None or type(numbers.get(rid)) is not int or rid in exempt:
            continue
        groups[_same_paper(record)].append(rid)
    out = []
    for rids in groups.values():
        kept, *rest = sorted(rids, key=lambda rid: (numbers[rid], rid))
        for rid in rest:
            out.append((records[kept].native, records.pop(rid).native))
    return sorted(out)


def _says_nothing_of_status(ad: Adapter, note: Mapping[str, Any], record: PaperRecord) -> bool:
    """Whether a note carries no status evidence at all (rule 5's silent twin): its year reads status from
    `content.venue` alone, its status is `unknown` (a withdrawn or desk-rejected listing gives its own, and a note
    with a crawl conflict is exempt from rule 5), and it has neither a non-null `venue` nor a non-null `venueid`.
    A venue string the table doesn't know is evidence nobody could read, not silence, and other years' carriers (a
    decision field or note) can't be judged absent from the note alone."""
    content: Mapping[str, Any] = note["content"] if isinstance(note.get("content"), Mapping) else {}
    return (
        ad.status_from == "venue"
        and record.status == "unknown"
        and content.get("venue") is None
        and content.get("venueid") is None
    )


def _same_paper_but_status(record: PaperRecord) -> str:
    """`_same_paper` without the fields a silent note can't supply: status (and the hash over it), presentation
    and venueid. Title, authors, abstract, keywords, pdf and track still match exactly."""
    return json.dumps(
        record.model_dump(
            mode="json",
            exclude={
                "id": True, "provenance": True, "urls": {"forum"}, "status": True, "presentation": True,
                "venue_id_raw": True, "content_hash": True,
            },
        ),
        sort_keys=True,
    )  # fmt: skip


def collapse_silent_twins(
    records: dict[str, PaperRecord], silent: Set[str], exempt: Set[str] = frozenset()
) -> list[tuple[str, str]]:
    """Remove from `records` every silent note (module docstring rule 5) whose group, the records with a pdf that
    are equal by `_same_paper_but_status`, holds exactly two records: the silent note, still `unknown`, and one
    accepted record, neither in `exempt` (a crawl conflict, or made `withdrawn` by the twin rule). Return the (kept, removed) native ids,
    sorted. The accepted record is kept whatever the numbers: it is the one with evidence. Run after
    `collapse_duplicate_submissions`, so notes identical to the accepted one are gone; by then `silent` must hold
    only survivors whose absorbed notes were all silent too (the crawl drops the others, TASK-147). Any third
    record (with evidence, with a conflict, or a second silent note) makes the group a choice: then nothing is
    removed."""
    groups: defaultdict[str, list[str]] = defaultdict(list)
    for rid, record in records.items():
        if record.urls.pdf is not None:
            groups[_same_paper_but_status(record)].append(rid)
    out = []
    for rids in groups.values():
        if len(rids) != 2 or any(rid in exempt for rid in rids):
            continue
        quiet = [rid for rid in rids if rid in silent and records[rid].status == "unknown"]
        if len(quiet) != 1:
            continue
        [other] = [rid for rid in rids if rid not in quiet]
        if other in silent or records[other].status != "accepted":
            continue
        out.append((records[other].native, records.pop(quiet[0]).native))
    return sorted(out)


# --- a note with a withdrawn twin (rule 4, decision-020) ----------------------------------------------------


@dataclass(frozen=True)
class Twins:
    """What `withdrawn_twins` changed: the conflict rows of the accepted records it set to `unknown`, and the ids
    of the undecided records it set to `withdrawn`, both sorted."""

    conflicts: list[Conflict]
    withdrawn: list[str]


def _status_claim(r: PaperRecord) -> Claim:
    [c] = [c for c in r.claims("status") if c.source == SOURCE]
    return c


def withdrawn_twins(records: dict[str, PaperRecord]) -> Twins:
    """Apply the withdrawn-twin rule (module docstring rule 4, decision-020) to `records` in place. A record's
    twins are the other records of the crawl in the same track, listed as withdrawn, that share its pdf; they
    keep their own status.

    - An **accepted** record with a twin is set to `unknown` and loses its presentation (it came from the decision
      it no longer has), with one `unresolved:openreview_v1` row naming every twin: two notes of one paper whose
      status signals disagree. E.g. ICLR 2018 `S1p31z-Ab`: its decision note says `Accept (Poster)`, and
      `SJTCsqMUf`, listed as withdrawn, is the same pdf; the paper was not presented at ICLR 2018. No signal
      outranks another: ICLR 2021 `xGZG2kS5bFk` was withdrawn and presented.
    - A record with **no decision at all** (its forum has no decision note: status `unknown`, evidence
      `NO_DECISION_NOTE`) and a twin is set to `withdrawn`, with no row: the twin's withdrawal is its only status
      signal, so nothing disagrees. The status claim cites the first twin's listing page and names every twin
      (the owner's answer, 2026-09-29, TASK-139: clears ICLR 2018 main's 12 undecided unknowns).
    - Any other record keeps its status: a rejected one (10 in ICLR 2018), one `unknown` for another reason
      (decision notes that disagree, a decision string not in the table, no submission number to find the
      decision note by, a forum a dry run didn't fetch, `Invite to Workshop Track`), a withdrawn or desk-rejected
      one. The crawl moves each record made `withdrawn` out of the report's `unmapped` (where its missing decision
      note was counted) into `withdrawn_by_twin`.

    Only a withdrawn twin counts (decision-020): a desk rejection (e.g. for a duplicate submission) can leave the
    same pdf beside the presented copy. A record with no pdf (or an arXiv link, which `_pdf` drops) has no twin.
    The twins are the records withdrawn before the rule runs, so the result doesn't depend on record order, and
    running it again changes nothing."""
    gone: defaultdict[str, list[PaperRecord]] = defaultdict(list)
    for r in records.values():
        if r.urls.pdf is not None and r.status == "withdrawn":
            gone[r.urls.pdf].append(r)
    conflicts: list[Conflict] = []
    withdrawn: list[str] = []
    for rid in sorted(records):
        r = records[rid]
        if r.urls.pdf is None or r.status not in ("accepted", "unknown"):
            continue
        was = _status_claim(r)
        if r.status == "unknown" and was.evidence != NO_DECISION_NOTE:
            continue
        twins = sorted(
            (t for t in gone.get(r.urls.pdf, ()) if t.id != rid and t.track == r.track), key=lambda t: t.id
        )
        if not twins:
            continue
        said = [(t, _status_claim(t)) for t in twins]
        if r.status == "unknown":
            named = "; ".join(f"withdrawn twin {t.native} shares the pdf ({c.evidence})" for t, c in said)
            first = said[0][1]
            status = Claim(
                field="status", value="withdrawn", source=SOURCE, url=first.url, fetched_at=first.fetched_at,
                evidence=f"{NO_DECISION_NOTE}; {named}",
            )  # fmt: skip
            update: dict[str, Any] = {"status": "withdrawn"}
            withdrawn.append(rid)
        else:
            named = "; ".join(f"twin {t.native}, same pdf: {c.evidence}" for t, c in said)
            side_b = f"withdrawn ({named})"
            status = Claim.model_validate(
                {**was.model_dump(), "value": "unknown", "evidence": f"conflict: {was.evidence} vs {side_b}"}
            )
            update = {"status": "unknown", "presentation": None}
            conflicts.append(
                Conflict(rid, "status", f"accepted ({was.evidence})", SOURCE, side_b, SOURCE, CONFLICT)
            )
        provenance = (*(c for c in r.provenance if c.field not in ("status", "presentation")), status)
        records[rid] = r.model_copy(update={**update, "provenance": provenance})
    return Twins(conflicts, withdrawn)


# --- the crawl files ------------------------------------------------------------------------------------------


def crawl_file(cache: Path, venue: str, year: int) -> Path:
    return crawls_dir(cache) / f"{venue}-{year}.json"


def ingest(client: OpenReviewClient, cache: Path, venue: str, years: Sequence[int], *,
           dry_run: bool = False, page_size: int = PAGE_SIZE) -> list[CrawlReport]:  # fmt: skip
    """Crawl each v1 year into the cache (one crawl at a time per cache: `.lock`) and, for a complete,
    non-dry-run crawl, write its crawl file so `op snapshot build` replays it."""
    for year in years:
        adapter(venue, year)  # refuse the whole request before fetching anything

    def marker(year: int, c: Crawl) -> tuple[str, dict[str, Any]] | None:
        return None if dry_run or not c.report.complete else (f"{venue}-{year}", c.report.to_manifest())

    crawls = CRAWLS.ingest(
        cache, years, lambda year: crawl(client, venue, year, dry_run=dry_run, page_size=page_size), marker
    )
    return [c.report for c in crawls]


def _replay_one(cache: Path, key: tuple[Any, ...]) -> Crawl:
    venue, year, page_size = key
    return crawl(make_client(cache, credentials=None, offline=True), venue, year, page_size=page_size)


CRAWLS: Crawls[Crawl] = Crawls(crawls_dir, marker_key, lambda k: f"{k[0]} {k[1]} (OpenReview API v1)",
                               "op ingest openreview", _replay_one)  # fmt: skip


def replay(cache: Path) -> list[Crawl]:
    """Every finished v1 crawl, rebuilt from the cache alone (no credentials, no network)."""
    return CRAWLS.replay(cache)
