"""Deduplication (spec 01 §Pipeline 4; dedup-rules skill; decision-005).

One record per paper, and never two papers folded into one: an over-merge silently deletes a paper from
a review, a duplicate only shows in the hit count.

1. Records with the same id merge, from any source: the same OpenReview forum id in the same venue and
   year, or the same proceedings id (one paper reached by both Trust-Evals searches). One forum id in two
   venue-years is a conflict, never a merge.
   Then the **forum link** (TASK-105): clusters that name the same forum id, as their own id or in a kept
   `urls.forum` claim (PMLR's index links the OpenReview forum from 2023; v235 is recorded), merge in the
   same venue and year whatever their titles say, unless the result would hold two forum ids, two
   proceedings ids, or fail the track rule. A refused link, and a link across venue-years, is a
   `conflicts.csv` row.
2. Clusters then merge on `(venue, year, title key)` only **across sources** (their provenance source
   sets are disjoint), never two different forum ids (own or linked) or two different proceedings ids, and never
   against the **track rule**. A key that would join clusters sharing a source is ambiguous: nothing
   merges, and `conflicts.csv` says so. When such a key holds a listing, the clusters that can't be the
   listed paper (TASK-126: a track the rule keeps from every listing in the group, or a status other than
   accepted/unknown) are set aside as rivals and the rest merge if they may; the set-aside clusters stay
   separate records. A record that is no listing and has a status no listing has (rejected, withdrawn,
   desk-rejected) never merges with imported records alone, imported or crawled itself: `ris` ranks last for
   status, so the merged record would keep that status (`_import_would_take_its_status`). For this rule a
   listing is one by crawled evidence (`_Cluster.crawled`, decision-040): a proceedings source's claim, or a
   crawled note's own proceedings URL; a proceedings id only a RIS row names (TASK-174's shape) is none.
   An imported record stays out of a title group when a crawler gave a record of its venue-year the import's
   own-page abstract and none of its title partners keeps it (`_yields_to_its_abstract`, TASK-189,
   decision-045): Scholar's title `-Guard` has a different paper's key, `Guard`. Step 3 then joins it to the
   abstract's record if it may.

3. An **imported record** that matched nothing (a cluster whose only source is `ris`, after steps 1 and 2) then
   merges on `(venue, year, abstract key)` (TASK-179): its title is Google Scholar's rendering, which drops math
   (`$R^2$-Guard` arrives as `-Guard`) and can be a preprint's earlier title, while its abstract is the
   publisher's own page text (`_own_abstract`: an abstract scholarmend read from another paper's page is no
   evidence). The abstract key is the title key's normalisation of the abstract, and counts only from
   `MIN_ABSTRACT_TOKENS` tokens. Every refusal of step 2 holds here too (forum ids, proceedings ids, the track
   rule, the set-aside rivals), and three of its own (`_abstract_group`, decision-037): a group with no imported
   record is never joined by its abstracts, an abstract never joins two records that aren't imported, and an
   import never merges with a record that is no listing by crawled evidence and is rejected, withdrawn or
   desk-rejected (a note, also one whose forum id's RIS row names a proceedings paper, or another import: a
   forum id's RIS row; decision-040).

`ris` is a route, not a publisher: each RIS row names its paper by a forum id or a proceedings id. So two
candidates that share only `ris` are judged by those ids (at most one of each in a merged record), not refused
as two candidates from one source (TASK-179: a note's cluster holds the RIS row of its forum id, and the same
paper's RIS row under its proceedings id is no rival to it).

The track rule, wherever a listing (a record with a proceedings id or a proceedings source) is involved: every
record is on a `PROCEEDINGS_TRACKS` track (a listing's own `unknown` included, never one an OpenReview claim
gives: TASK-174), or every record is NeurIPS Creative AI (`is_creative_ai`, TASK-137: track `other` that each
claiming source backs with the Creative AI venueid or proceedings URL). The two never mix, and nothing else
(workshop, tiny papers, blogposts, competition, any other `other`, a note's `unknown`) ever merges with a listing.

A merged record's fields are re-resolved from the union of its claims by `PRECEDENCE` (held as data),
never "whichever came first". Track is OpenReview's wherever the record carries an OpenReview track claim (so
OpenReview holds that track), and the proceedings' elsewhere (decision-005 §Track, per track). So every input must already equal what its own claims resolve to; dedup
refuses one that doesn't. When one source claims a field twice (the same paper in both searches), the
newest claim replaces the older one, and a differing value is a `newest:`/`tie:` row. The output depends
only on the set of inputs (sorted ids, set-based decisions).
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from functools import cache
from typing import Any, Literal, Protocol

from openproceedings.ingest import classify, urls
from openproceedings.ingest.record import Claim, ClaimField, PaperRecord, Source, Urls
from openproceedings.query.normalize import normalize

_TEXT: tuple[Source, ...] = (
    "openreview_v2", "openreview_v1", "iclr_archive", "neurips_proceedings", "pmlr", "dblp", "icml_site", "ojs",
    "crossref", "facct_site", "ris",
)  # fmt: skip
_ACCEPTANCE: tuple[Source, ...] = (
    "iclr_archive", "neurips_proceedings", "pmlr", "dblp", "ojs", "crossref", "openreview_v2", "openreview_v1",
    "ris",
)  # fmt: skip
# decision-005: OpenReview first for text and track; the official proceedings decide acceptance; RIS last.
# Track is decided per track (owner, 2026-09-29; TASK-130): an OpenReview track claim is the note's own
# content.venueid, so a record carrying one is on a track OpenReview holds, and that claim wins; a record with
# none takes its listing's track, whether OpenReview doesn't hold the track (ICLR 2016 main) or holds it but the
# paper's note didn't merge (the owner's second answer, 2026-09-29). The OpenReview crawlers claim no proceedings
# URL (`content.pdf` is kept only as an openreview.net `/pdf/` path), so a crawled note alone is never a listing; a
# same-id RIS row naming a proceedings paper can make its cluster one, and `_family` still reads that cluster's
# `unknown` as the note's (TASK-174; a note naming one itself, which no crawler emits, is held to the same rule).
# `_mergeable`'s track rule keeps a note apart from every listing unless both are on `PROCEEDINGS_TRACKS` or both
# are NeurIPS Creative AI (TASK-137): in a merged record OpenReview's track is in `PROCEEDINGS_TRACKS`, or is
# `other` on a Creative AI record whose listing says `other` too.
PRECEDENCE: dict[ClaimField, tuple[Source, ...]] = {
    **dict.fromkeys(
        ("title", "abstract", "authors", "keywords", "presentation", "venue", "year", "track", "venue_id_raw"),
        _TEXT,
    ),
    **dict.fromkeys(("urls.forum", "urls.pdf", "urls.proceedings", "urls.doi"), _TEXT),
    "status": _ACCEPTANCE,
}  # fmt: skip
# Cross-source disagreements written to conflicts.csv. A title counts only when its dedup key differs
# (decision-005); venue and year can't differ inside a merge (they're part of every merge key).
CONFLICT_FIELDS: tuple[ClaimField, ...] = ("title", "track", "status")
# the official proceedings sources, and the taxonomy tracks they host (reconcile.py reads both too). NeurIPS's
# proceedings also host Creative AI, which the taxonomy files under `other`; `other` holds more than Creative AI
# (Education_Program, High_School_Projects_Track, …), so it is not listed here: dedup's track rule admits Creative
# AI by its own evidence (`is_creative_ai`, TASK-137), and reconcile never judges it.
# dblp (ICML 1988-2012, decision-047) is not one: it is a bibliography of the proceedings, and no other source holds
# its venue-years, so reconcile never judges them; its records are still listings by their `dblp-<key>` id.
# ojs (AAAI, AIES, IASEAI; decision-049) is not one either, for the same reason: no other source holds its venue-years.
# crossref (FAccT, AIES 2018-2023; decision-049) is not one either: no other source holds its venue-years.
PROCEEDINGS_SOURCES: frozenset[str] = frozenset({"iclr_archive", "neurips_proceedings", "pmlr"})
OPENREVIEW_SOURCES: frozenset[str] = frozenset({"openreview_v2", "openreview_v1"})
PROCEEDINGS_TRACKS: frozenset[str] = frozenset({"main", "datasets_benchmarks", "position"})
_URL_FIELDS = ("urls.proceedings", "urls.pdf")
ABSENT = "unknown"  # the status a crawled listing gives a paper it doesn't hold (`is_absence`)
ABSENT_EVIDENCE = "not listed:"  # how an absence claim's evidence starts; no miner writes it
# A listing names only accepted papers; `unknown` may still be one (unresolved v1 evidence), so it stays a rival.
_LISTABLE_STATUSES = frozenset({"accepted", "unknown"})
# The import route (TASK-179). A RIS row is scholarmend's reading of a Google Scholar hit: it names its paper by a
# forum id or a proceedings id, so sharing `ris` is no sign of two candidates, and a cluster with no other source
# (an imported record) carries Scholar's title, the one text of it that is not the publisher's.
IMPORTED: frozenset[str] = frozenset({"ris"})
MIN_ABSTRACT_TOKENS = 50  # a shorter abstract (a placeholder, a one-liner) is never merge evidence


@dataclass(frozen=True, order=True)
class Merge:
    survivor_id: str
    merged_id: str
    rule: str  # forum_id | native_id | forum_link | title_venue_year | abstract_venue_year
    # forum_link: the shared forum id; title_venue_year: the title key that joined the merged cluster to the
    # group (in a chain, not always the survivor's); abstract_venue_year: the abstract key (`sha256:<16 hex>`)
    key: str
    venue: str
    year: int
    sources: str  # the merged record's sources, "+"-joined


@dataclass(frozen=True, order=True)
class Conflict:
    id: str
    field: str
    value_a: str
    source_a: str
    value_b: str
    source_b: str
    # precedence:<source> | newest:<source> | tie:<source> | ambiguous_not_merged | track_not_merged
    # | venue_year_not_merged
    resolution: str


@dataclass(frozen=True)
class DedupResult:
    records: tuple[PaperRecord, ...]  # sorted by id
    merges: tuple[Merge, ...]  # sorted
    conflicts: tuple[Conflict, ...]  # sorted


def title_key(title: str) -> str:
    """The token-contract normalisation of the title's NFC form, joined by single spaces: dedup and search agree
    on 'same title' for NFC text (search's `normalize` doesn't NFC first), and every canonically equivalent
    spelling of it (NFC, NFD, marks stored in another order) gets one key (TASK-168, decision-031). `normalize` reads LaTeX before its per-character NFKC, so a backslash before a
    decomposed letter starts a command: NFD `Caf\\e\u0301` lost its `e` (`caf`) where NFC `Caf\\é` keeps it
    (`caf e`), and `Erd\\H{o\u030b}s` was no accent macro (`erd o s`, not `erdos`)."""
    return " ".join(normalize(unicodedata.normalize("NFC", title)))


@cache
def _abstract_digest(abstract: str) -> str:
    """`abstract_key`, remembered for one `dedup` call (which clears it when it returns: the cache would
    otherwise pin every abstract of the corpus for the life of the process)."""
    key = title_key(abstract)
    if key.count(" ") + 1 < MIN_ABSTRACT_TOKENS:
        return ""
    return "sha256:" + hashlib.sha256(key.encode()).hexdigest()


def abstract_key(abstract: str) -> str:
    """The dedup key of an abstract (step 3, TASK-179, decision-037): `sha256:` and the hash of its `title_key`
    (the same token-contract normalisation, so no second normaliser), or `""` when it has fewer than
    `MIN_ABSTRACT_TOKENS` tokens. Matching is on the whole digest; merges.csv shows `shown_key`'s 16 digits."""
    return _abstract_digest(abstract)


def shown_key(key: str) -> str:
    """An abstract key as merges.csv writes it: `sha256:` and the digest's first 16 hex digits."""
    return key[: len("sha256:") + 16]


def _text(v: object) -> str:
    return "; ".join(v) if isinstance(v, tuple) else "" if v is None else str(v)


def _differ(fld: str, a: object, b: object) -> bool:
    return title_key(_text(a)) != title_key(_text(b)) if fld == "title" else _text(a) != _text(b)


def _exact(v: object) -> str:
    """A value's exact form: `("Smith; J",)` and `("Smith", "J")` print alike through `_text` but differ here."""
    return json.dumps(v, sort_keys=True, ensure_ascii=False)


def is_absence(claim: Claim) -> bool:
    """Reconcile's statement that a crawled listing doesn't hold the paper (decision-005, TASK-072): a
    proceedings source's `status=unknown` claim whose evidence starts `not listed:`. It names no paper, so it
    gives the record no proceedings source and never makes it a listing."""
    return (
        claim.field == "status" and claim.source in PROCEEDINGS_SOURCES and claim.value == ABSENT
        and (claim.evidence or "").startswith(ABSENT_EVIDENCE)
    )  # fmt: skip


def _sources(records: Iterable[PaperRecord]) -> frozenset[str]:
    """The sources that hold the records' paper (an absence claim holds none), for merging and merges.csv."""
    return frozenset(c.source for r in records for c in r.provenance if not is_absence(c))


# The site that published an abstract, as the results list names it (TASK-134, decision-018). Distinct from a
# claim's `Source`: a `ris` claim is a route, and its evidence says which of these the abstract came from.
Origin = Literal[
    "openreview",
    "neurips_proceedings",
    "iclr_proceedings",
    "pmlr",
    "iclr_archive",
    "icml_site",
    "ojs",
    "crossref",
    "facct_site",
]
_DIRECT_ORIGIN: dict[str, Origin] = {
    "openreview_v2": "openreview", "openreview_v1": "openreview", "neurips_proceedings": "neurips_proceedings",
    "pmlr": "pmlr", "iclr_archive": "iclr_archive",
    # an official ICML conference page (live, or a pinned Internet Archive capture of one; TASK-206): its claim's
    # url is the page as fetched, so the link reaches the capture
    "icml_site": "icml_site",
    "ojs": "ojs",
    "crossref": "crossref",
    "facct_site": "facct_site",
}  # fmt: skip
_SITE_ORIGIN: dict[str, Origin] = {
    "NeurIPS": "neurips_proceedings",
    "ICLR": "iclr_proceedings",
    "PMLR": "pmlr",
}
# how `ingest/ris.py` writes an abstract claim's evidence: `scholarmend:<its abstract source> <its evidence>`
RIS_VIA_OPENREVIEW = "scholarmend:openreview_api"
RIS_VIA_PROCEEDINGS = "scholarmend:proceedings_page"
# how an `icml_site` claim's evidence says its page is a submission (ICML 1997 and 1998, TASK-207:
# `icml_sites.SUBMISSION_PARSERS`), so its abstract is as the authors submitted it, not as published
# (the snapshot stores this text in the claim's evidence: reword it and snapshots built before stop carrying the
# note; test_icml_submissions.py checks it from crawl to export)
AS_SUBMITTED = (
    "a submission-time abstract, as the authors submitted it (not necessarily the published paper's)"
)
# what the API (`abstract_note`), every export and the UI say of such an abstract (TASK-210): the one wording
SUBMISSION_NOTE = (
    "Submission-time abstract: as the authors submitted it, which may differ from the published paper's."
)


@dataclass(frozen=True, slots=True)
class Attribution:
    """Where a record's abstract came from (decision-018): `source`, the claim precedence took it from;
    `origin`, the site that published it (for a `ris` claim, read from its evidence; None when that names no
    known site); `url`, the paper's page at `origin` (None when there is none); `as_submitted`, whether
    that page holds the abstract as the authors submitted it (its claim's evidence says `AS_SUBMITTED`;
    TASK-210)."""

    source: Source
    origin: Origin | None
    url: str | None
    as_submitted: bool = False

    @property
    def note(self) -> str | None:
        """What the API and every export say of the abstract beside its source: `SUBMISSION_NOTE` for a
        submission-time abstract, else None (TASK-210)."""
        return SUBMISSION_NOTE if self.as_submitted else None


class AbstractClaim(Protocol):
    """What `attribution` reads of a claim: a `Claim`, or the snapshot reader's raw-JSON view of one."""

    @property
    def source(self) -> Any: ...
    @property
    def value(self) -> Any: ...
    @property
    def url(self) -> Any: ...
    @property
    def evidence(self) -> Any: ...


def abstract_claim[C: AbstractClaim](abstract: str | None, claims: Iterable[C]) -> C | None:
    """Of the abstract claims holding exactly the text `abstract`, the one `resolve` ranks first (PRECEDENCE,
    decision-005). None when there is no abstract, or no claim holds its text (a record built without
    provenance, as synthetic fixtures are)."""
    if abstract is None:
        return None
    order = PRECEDENCE["abstract"]
    held = [c for c in claims if c.value == abstract]
    return min(held, key=lambda c: order.index(c.source), default=None)


def attribution(
    abstract: str | None,
    claims: Iterable[AbstractClaim],
    *,
    forum: str | None,
    proceedings: str | None,
    native: str,
) -> Attribution | None:
    """The attribution of a record's abstract, from its abstract claims and its urls. OpenReview's page is the
    forum (its claims carry the API listing they were read from); a proceedings claim's url is the paper's own
    page there. A `ris` claim names its route in its evidence: `openreview_api` → the forum; `proceedings_page`
    → the site its url's host names (NeurIPS, ICLR or PMLR proceedings), linking `proceedings` when that is on
    the same site, else the evidence url when it is this record's (`native`) page, else unlinked. Pure, over
    plain values, so
    the snapshot reader can run it once per record at load."""
    claim = abstract_claim(abstract, claims)
    if claim is None:
        return None
    source: Source = claim.source
    origin: Origin | None = _DIRECT_ORIGIN.get(source)
    if origin == "openreview":
        return Attribution(source, origin, forum)
    if origin == "icml_site":  # a submission page's evidence says so (TASK-207); read here, never re-derived
        return Attribution(source, origin, claim.url, AS_SUBMITTED in (claim.evidence or ""))
    # each claim's url is an API page (an OAI token page, a Crossref work) or a listing of every paper (a FAccT
    # CSV): credit the paper's own page, its urls.proceedings (the article page, the DOI link)
    if origin in ("ojs", "crossref", "facct_site"):
        return Attribution(source, origin, proceedings)
    if origin is not None:
        return Attribution(source, origin, claim.url)
    via, _, rest = (claim.evidence or "").partition(" ")
    if via == RIS_VIA_OPENREVIEW:
        return Attribution(source, "openreview", forum)
    if via == RIS_VIA_PROCEEDINGS:
        # the evidence's url says which site the abstract was read from; the record's proceedings link is the
        # page when it is on that site (or the evidence names none). When the two name different sites the
        # evidence wins, unlinked; the evidence url itself is linked only when it is this paper's page
        # (`urls.names_native`: some evidence urls stop after the hash)
        page = rest.split(" ", 1)[0]
        said = _SITE_ORIGIN.get(urls.proceedings_site(page) or "") if page else None
        held = _SITE_ORIGIN.get(urls.proceedings_site(proceedings) or "") if proceedings else None
        if held is not None and said in (None, held):
            return Attribution(source, held, proceedings)
        if said is not None:
            return Attribution(
                source, said, page if held is None and urls.names_native(page, native) else None
            )
    return Attribution(source, None, None)  # a route that names no site this code knows: named, not linked


def _one_per_field_and_source(record_id: str, claims: Iterable[Claim]) -> tuple[list[Claim], list[Conflict]]:
    """The newest claim for each (field, source). Any other value that source gave is a conflicts.csv row:
    `newest:<source>` when it is older, `tie:<source>` when it was fetched at the same moment (then the
    kept value is only the deterministic pick, so a reviewer must look). For RIS, "newest" compares Publish or
    Perish query dates, which are true UTC only for cache entries `ris_offsets.toml` lists (decision-025): two
    entries on different bases (one listed, one local) can be ordered wrongly when run within the offset of
    each other, which the manifest's `query_dates: local` flags."""
    groups: dict[tuple[str, str], set[Claim]] = defaultdict(set)
    for c in claims:
        groups[(c.field, c.source)].add(c)
    kept, conflicts = [], []
    for (fld, src), group in sorted(groups.items()):
        ordered = sorted(group, key=lambda c: (c.fetched_at, c.sort_key(), _exact(c.value), c.evidence or ""))
        newest = ordered[-1]
        kept.append(newest)
        for other in ordered[:-1]:
            if _exact(other.value) != _exact(newest.value):
                how = "tie" if other.fetched_at == newest.fetched_at else "newest"
                conflicts.append(
                    Conflict(
                        record_id, fld, _text(newest.value), src, _text(other.value), src, f"{how}:{src}"
                    )
                )
    return kept, conflicts


def resolve(record_id: str, claims: Iterable[Claim]) -> tuple[PaperRecord, list[Conflict]]:
    """The record the claims describe, each field from its best-ranked source (PRECEDENCE)."""
    kept, conflicts = _one_per_field_and_source(record_id, claims)
    best: dict[str, Claim] = {}
    for fld, order in PRECEDENCE.items():
        ranked = sorted((c for c in kept if c.field == fld), key=lambda c: order.index(c.source))
        if not ranked:
            continue
        best[fld] = win = ranked[0]
        if fld in CONFLICT_FIELDS:
            conflicts += [
                Conflict(record_id, fld, _text(win.value), win.source, _text(o.value), o.source, f"precedence:{win.source}")
                for o in ranked[1:]
                if _differ(fld, win.value, o.value)
            ]  # fmt: skip
    missing = [f for f in ("title", "venue", "year", "track", "status") if f not in best]
    if missing:
        raise ValueError(
            f"{record_id}: no claim for {', '.join(missing)}; dedup resolves fields from claims only"
        )

    def value(fld: str, default: Any = None) -> Any:
        return best[fld].value if fld in best else default

    # presentation (OpenReview first) is how an accepted paper was presented, so it holds only while the
    # resolved status (proceedings first) is `accepted`: a reconcile-demoted `unknown` shows none. Its claim
    # stays in provenance (spec 01 §Presentation).
    presentation = value("presentation") if value("status") == "accepted" else None

    record = PaperRecord.build(
        id=record_id, title=value("title"), abstract=value("abstract"), authors=value("authors", ()),
        venue=value("venue"), year=value("year"), track=value("track"), status=value("status"),
        presentation=presentation, venue_id_raw=value("venue_id_raw"), keywords=value("keywords", ()),
        urls=Urls(forum=value("urls.forum"), pdf=value("urls.pdf"), proceedings=value("urls.proceedings"),
                  doi=value("urls.doi")),
        provenance=tuple(kept),
    )  # fmt: skip
    return record, conflicts


class _Clusters:
    """Union-find over input positions; the smallest position is the root, so results don't depend on
    the order unions happen in."""

    def __init__(self, n: int) -> None:
        self.parent = list(range(n))

    def find(self, i: int) -> int:
        while self.parent[i] != i:
            self.parent[i] = self.parent[self.parent[i]]
            i = self.parent[i]
        return i

    def union(self, i: int, j: int) -> None:
        a, b = self.find(i), self.find(j)
        if a != b:
            self.parent[max(a, b)] = min(a, b)

    def groups(self) -> list[list[int]]:
        out: dict[int, list[int]] = defaultdict(list)
        for i in range(len(self.parent)):
            out[self.find(i)].append(i)
        return sorted(out.values())


@dataclass(frozen=True)
class _Cluster:
    """A step-1 cluster (records sharing one id, or one forum id by the link), judged as the record its
    claims resolve to under its id."""

    id: str
    members: tuple[PaperRecord, ...]
    summary: PaperRecord
    sources: frozenset[str]
    # every kept title claim's key: a superseded same-source title is only in conflicts.csv, because the
    # output record no longer carries it and matching on it would make a second run merge differently
    keys: frozenset[str]
    # from the kept proceedings URL claims; every proceedings-id record names itself in one (checked on
    # input), so a merged record still carries the ids of the listings it absorbed
    proceedings_ids: frozenset[str]
    listed: bool  # a proceedings listing: proceedings id or proceedings source
    # a listing by crawled evidence: a proceedings source, or a proceedings id a claim other than `ris` names
    # (decision-040); decision-037's status exemption reads this, never `listed`
    crawled: bool
    # its own forum id and every one a kept `urls.forum` claim names (a PMLR listing's link to OpenReview)
    forum_ids: frozenset[str]


def proceedings_ids(claims: Iterable[Claim]) -> set[str]:
    found: set[str] = set()
    for claim in claims:
        if claim.field not in _URL_FIELDS or not isinstance(claim.value, str):
            continue
        native = urls.native(claim.value)
        if native is None and claim.source == "iclr_archive" and claim.field == "urls.proceedings":
            target = urls.iclr_archive_target(claim.value)
            native = target[0] if target is not None else None
        if native is not None:
            found.add(native)
    return found


def forum_ids(record: PaperRecord) -> frozenset[str]:
    """The record's own forum id and every forum id its kept `urls.forum` claims name."""
    linked = {
        f for c in record.provenance
        if c.field == "urls.forum" and isinstance(c.value, str) and (f := urls.forum_id(c.value))
    }  # fmt: skip
    if record.forum_id is not None:
        linked.add(record.forum_id)
    return frozenset(linked)


def _listed(pids: Iterable[str], sources: Iterable[str]) -> bool:
    return bool(set(pids) or PROCEEDINGS_SOURCES & set(sources))


def is_listing(record: PaperRecord) -> bool:
    """A listing, as dedup judges one: a proceedings source's claim (an absence claim is none), or a
    proceedings id in a `urls.proceedings`/`urls.pdf` claim. Reconcile judges by the same rule."""
    return _listed(proceedings_ids(record.provenance), _sources([record]))


def _names_creative_ai(claims: Sequence[Claim], year: int) -> bool:
    """One source's claims show NeurIPS `year`'s Creative AI track: at least one piece of evidence, and all of it
    agrees. Evidence is a `venue_id_raw` claim (the note's `content.venueid`) or a NeurIPS proceedings
    `urls.proceedings`/`urls.pdf` claim (its track token)."""
    said: list[bool] = []
    for c in claims:
        if c.field == "venue_id_raw" and isinstance(c.value, str):
            said.append(classify.is_creative_ai_venueid(c.value, year))
        elif (
            c.field in _URL_FIELDS and isinstance(c.value, str) and (parts := urls.proceedings_parts(c.value))
        ):
            said.append(parts[:2] == ("NeurIPS", year) and parts[3] == classify.CREATIVE_AI)
    return bool(said) and all(said)


def is_creative_ai(record: PaperRecord) -> bool:
    """A NeurIPS Creative AI record (TASK-137): track `other`, and every source with a track claim claims `other`
    and backs it with Creative AI evidence (`_names_creative_ai`). An `other` without that evidence
    (Education_Program, an unseen form) is not Creative AI, and the track rule keeps it from every listing. A
    source with no track claim (a reconcile absence claim's, say) is not checked: it says nothing about the track."""
    if record.venue != "NeurIPS" or record.track != "other":
        return False
    by_source: dict[str, list[Claim]] = defaultdict(list)
    for c in record.provenance:
        by_source[c.source].append(c)
    claimed = [src for src, cs in by_source.items() if any(c.field == "track" for c in cs)]
    return all(
        all(c.value == "other" for c in by_source[src] if c.field == "track")
        and _names_creative_ai(by_source[src], record.year)
        for src in claimed
    )


def _cluster(members: Sequence[PaperRecord], rid: str | None = None) -> _Cluster:
    rid = rid or members[0].id
    summary, _ = resolve(rid, [c for r in members for c in r.provenance])  # rows come from the final resolve
    claims = summary.provenance  # kept claims only: the output record carries nothing else
    pids = proceedings_ids(claims)
    sources = _sources(members)
    return _Cluster(
        id=rid, members=tuple(members), summary=summary, sources=sources,
        keys=frozenset(k for c in summary.provenance if c.field == "title" and (k := title_key(_text(c.value)))),
        proceedings_ids=frozenset(pids), listed=_listed(pids, sources),
        crawled=_listed(proceedings_ids(c for c in claims if c.source not in IMPORTED), sources),
        forum_ids=forum_ids(summary),
    )  # fmt: skip


def _family(c: _Cluster) -> str | None:
    """The cluster's side of the track rule: `creative_ai` (NeurIPS Creative AI, TASK-137), `proceedings` (a
    `PROCEEDINGS_TRACKS` track, or a listing's own `unknown`: a PMLR volume holding main and position papers),
    or None: a track no listing may merge with (an unknown track waits for evidence). A cluster holding an
    OpenReview record has OpenReview's track (every record claims one, and OpenReview ranks first), so its
    `unknown` is the note's, never a listing's own, even where the cluster is a listing because a same-id RIS
    row, or the note itself, names a proceedings paper (TASK-174)."""
    if is_creative_ai(c.summary):
        return "creative_ai"
    if c.summary.track in PROCEEDINGS_TRACKS:
        return "proceedings"
    if c.listed and c.summary.track == "unknown" and c.sources.isdisjoint(OPENREVIEW_SOURCES):
        return "proceedings"
    return None


def _mergeable(group: Sequence[_Cluster], *, linked: bool = False) -> str | None:
    """Why these step-1 clusters must not share a record, or None if they may. `linked`: they share a forum
    id (the forum link), so one source on two sides is no ambiguity: the id says which paper each is."""
    # `ris` on two sides is no ambiguity (TASK-179): each RIS row names its paper by id, and the two id checks
    # below refuse two forum ids or two proceedings ids whatever their sources
    srcs = [c.sources - IMPORTED for c in group]
    if not linked and any(srcs[i] & srcs[j] for i in range(len(srcs)) for j in range(i + 1, len(srcs))):
        return "ambiguous_not_merged"  # two candidates from one source: which one is the paper?
    if len(frozenset[str]().union(*(c.forum_ids for c in group))) > 1:
        return "ambiguous_not_merged"  # two different OpenReview submissions (own or linked forum ids)
    if len(frozenset().union(*(c.proceedings_ids for c in group))) > 1:
        return "ambiguous_not_merged"  # two different proceedings papers
    if not linked and _import_would_take_its_status(group):
        return "ambiguous_not_merged"
    if any(c.listed for c in group):  # the track rule: one family, and never None
        families = {_family(c) for c in group}
        if len(families) > 1 or None in families:
            return "track_not_merged"
    return None


def _import_would_take_its_status(group: Sequence[_Cluster]) -> bool:
    """A record that is no listing by crawled evidence (`crawled`), with a status no listing has (rejected,
    withdrawn, desk-rejected), whose only companions are imported records (decision-037). A crawled listing
    outranks every status claim, so a lone rejected note may merge with one (decision-005). `ris` ranks last:
    merged with only imports, the record would keep that status (or, when it is an import itself, take whichever
    RIS row was fetched last), and an accepted paper would leave every accepted-only result. So they stay apart,
    by title as by abstract. A cluster that is a listing only because a RIS row names a proceedings paper (TASK-174's
    shape: a rejected note and its forum id's RIS row) has no crawled listing's status to outrank its own, so it is
    held to the rule too (decision-040); a note's own proceedings URL is crawled evidence."""
    return len(group) > 1 and any(
        not c.crawled and c.summary.status not in _LISTABLE_STATUSES
        and all(x.sources == IMPORTED for j, x in enumerate(group) if j != i)
        for i, c in enumerate(group)
    )  # fmt: skip


def _not_the_listed_paper(c: _Cluster, group: Sequence[_Cluster]) -> str | None:
    """Why a cluster can never be the paper of a proceedings listing in `group`, as its not-merged resolution, or
    None if it may be one (TASK-126). A listing is always a candidate. A track the track rule keeps from every
    listing in the group is set aside (a workshop note; a Creative AI note beside a main listing, or a main note
    beside a Creative AI one, TASK-137); an `unknown` track only waits for evidence, so like an `unknown` status
    it stays a candidate (and a rival). Proceedings list only accepted papers: a rejected, withdrawn or
    desk-rejected note is not the listed one, though it may merge alone (decision-005: the proceedings then
    decide its status)."""
    if c.listed:
        return None
    family, listed = _family(c), {f for x in group if x.listed and (f := _family(x))}
    if c.summary.track != "unknown" and (family is None or (listed and family not in listed)):
        return "track_not_merged"
    if c.summary.status not in _LISTABLE_STATUSES:
        return "ambiguous_not_merged"  # another candidate for the listing took it
    return None


def _merging(group: Sequence[_Cluster]) -> list[int] | None:
    """Positions in a title-key group that merge, or None. The whole group if it may share a record; else,
    when it holds a listing, the clusters that may be the listed paper, if they may share one (TASK-126): a
    same-title workshop paper or a rejected earlier submission is no rival for the listing."""
    if _mergeable(group) is None:
        return list(range(len(group)))
    if not any(c.listed for c in group):
        return None
    rest = [i for i, c in enumerate(group) if _not_the_listed_paper(c, group) is None]
    if len(rest) < 2 or _mergeable([group[i] for i in rest]) is not None:
        return None  # rest == group is refused here as well: `_mergeable` has just refused the whole group
    return rest


def _pair(a: _Cluster, b: _Cluster, resolution: str, fld: str = "title_key") -> Conflict:
    return Conflict(
        a.id, fld, a.id, "+".join(sorted(a.sources)), b.id, "+".join(sorted(b.sources)), resolution
    )


def _survivor_id(group: Sequence[_Cluster]) -> str:
    """The id with an OpenReview forum id if any cluster has one (record-schema skill), else the smallest."""
    ids = sorted(c.id for c in group)
    return next((i for i in ids if next(c for c in group if c.id == i).summary.forum_id is not None), ids[0])


def dedup(records: Iterable[PaperRecord]) -> DedupResult:
    """Merge duplicates (dedup-rules skill). Every input id is an output id or a `merged_id`, once."""
    try:
        return _dedup(records)
    finally:
        _abstract_digest.cache_clear()  # step 3's memo is for one call


def _dedup(records: Iterable[PaperRecord]) -> DedupResult:
    xs = sorted(records, key=lambda r: (r.id, r.content_hash, r.model_dump_json()))
    conflicts: set[Conflict] = set()
    merges: list[Merge] = []
    for r in xs:
        again, _ = resolve(r.id, r.provenance)
        if again != r:
            raise ValueError(f"{r.id}: fields don't match its own claims; dedup would silently change it")
        if r.forum_id is None and r.native not in proceedings_ids(r.provenance):
            raise ValueError(f"{r.id}: a proceedings record must name itself in a urls.proceedings/pdf claim")

    # Step 1: identical id: the same forum id in the same venue and year, or the same proceedings id.
    by_id: dict[str, list[PaperRecord]] = defaultdict(list)
    for r in xs:
        by_id[r.id].append(r)
    same_id: list[_Cluster] = []
    for rid in sorted(by_id):
        cluster = _cluster(by_id[rid])
        same_id.append(cluster)
        rule = "forum_id" if cluster.summary.forum_id is not None else "native_id"
        merges += [
            Merge(rid, rid, rule, cluster.summary.native, r.venue, r.year, "+".join(sorted(_sources([r]))))
            for r in by_id[rid][1:]
        ]  # the same id twice: one row per extra copy, survivor_id == merged_id
    # The forum link: one forum id (own or in a urls.forum claim) in the same venue and year, any title.
    clusters, linked = _link(same_id)
    merges += linked
    # Step 2: (venue, year, title key) across sources.
    titled: dict[tuple[str, int, str], set[int]] = defaultdict(set)
    for ci, c in enumerate(clusters):
        for key in c.keys:  # a title of only punctuation or math has no key and never matches
            titled[(c.summary.venue, c.summary.year, key)].add(ci)
    clusters, found = _join(clusters, titled, "title_venue_year", _crawled_abstracts(clusters))
    merges += found
    # Step 3: an imported record that matched nothing, on (venue, year, abstract key).
    clusters, found = _join(clusters, _abstract_buckets(clusters), "abstract_venue_year")
    merges += found

    out: list[PaperRecord] = []
    for cluster in clusters:
        merged, rows = resolve(cluster.id, [c for r in cluster.members for c in r.provenance])
        out.append(merged)
        conflicts.update(rows)
    conflicts |= _refusals(out)
    return DedupResult(
        tuple(sorted(out, key=lambda r: r.id)), tuple(sorted(merges)), tuple(sorted(conflicts))
    )


def _imported(c: _Cluster) -> bool:
    """An imported record: a cluster whose only source is the import route (decision-037)."""
    return c.sources == IMPORTED


def _own_abstract(claim: Claim, record: PaperRecord, pids: frozenset[str]) -> bool:
    """Is this abstract claim the text of the record's own page? A crawler's always is. A `ris` claim is
    scholarmend's, and counts only when its evidence ties it to the record: `proceedings_page <url>` where the
    url is the page of the record's own id or of a proceedings paper it names, or `openreview_api
    openreview:<forum>` on a record with that forum id. Anything else (another paper's page, a route this code
    doesn't know) is no evidence of which paper the record is."""
    if claim.source not in IMPORTED:
        return True
    via, _, rest = (claim.evidence or "").partition(" ")
    where = rest.split(" ", 1)[0]
    if via == RIS_VIA_PROCEEDINGS:
        return bool(where) and any(urls.names_native(where, n) for n in {record.native, *pids})
    if via == RIS_VIA_OPENREVIEW:
        return record.forum_id is not None and where == f"openreview:{record.forum_id}"
    return False


def _abstract_keys(c: _Cluster, *, imported: bool = False, crawled: bool = False) -> frozenset[str]:
    """The key of every abstract claim the cluster keeps (as `keys` is of its titles) that is long enough and
    its own page's text (`_own_abstract`). `imported`: only the import route's claims; `crawled`: only the
    others (a crawler's text, which no merge with a RIS row replaces)."""
    return frozenset(
        k for claim in c.summary.provenance
        if claim.field == "abstract" and isinstance(claim.value, str)
        and (claim.source in IMPORTED or not imported) and (claim.source not in IMPORTED or not crawled)
        and _own_abstract(claim, c.summary, c.proceedings_ids) and (k := abstract_key(claim.value))
    )  # fmt: skip


def _abstract_buckets(
    clusters: Sequence[_Cluster], *, merged_too: bool = False
) -> dict[tuple[str, int, str], set[int]]:
    """Step 3's groups: clusters of one venue and year sharing an abstract key, kept only where one of them is an
    imported record holding that key (its sources are `IMPORTED` alone). `merged_too`, for the not-merged rows:
    also where a listing that holds a `ris` claim keeps an abstract with that key, as a record an import merged
    into does (it is always a listing: the import's proceedings id, or the crawled listing a forum-id import
    joined), so a rival set aside by the merge is still reported on the output records. Abstracts are normalised
    only in the venue-years that hold such a cluster."""
    anchors: dict[int, frozenset[str]] = {}
    for ci, c in enumerate(clusters):
        if _imported(c):
            keys = _abstract_keys(c, imported=True)
        elif merged_too and c.listed and c.sources & IMPORTED:
            # every abstract it keeps: one source keeps one claim, so the import's abstract may have given way to
            # a newer RIS row's, while the note's own claim still holds the text the two merged on
            keys = _abstract_keys(c)
        else:
            continue
        if keys:
            anchors[ci] = keys
    scope = {(clusters[ci].summary.venue, clusters[ci].summary.year) for ci in anchors}
    buckets: dict[tuple[str, int, str], set[int]] = defaultdict(set)
    for ci, c in enumerate(clusters):
        if (c.summary.venue, c.summary.year) in scope:
            for key in _abstract_keys(c):
                buckets[(c.summary.venue, c.summary.year, key)].add(ci)
    return {k: cis for k, cis in buckets.items() if any(k[2] in anchors.get(ci, ()) for ci in cis)}


def _crawled_abstracts(clusters: Sequence[_Cluster]) -> dict[tuple[str, int, str], set[int]]:
    """Where `_yields_to_its_abstract` looks for an import's abstract: each crawled cluster under the key of every
    abstract a crawler gave it (`_abstract_keys(crawled=True)`), in the venue-years that hold an imported record.
    A crawler's claim, never a RIS row's: a merge with another RIS row can replace that one (one claim per
    source), and a second run would then judge the title group differently."""
    scope = {(c.summary.venue, c.summary.year) for c in clusters if _imported(c)}
    held: dict[tuple[str, int, str], set[int]] = defaultdict(set)
    for ci, c in enumerate(clusters):
        if not _imported(c) and (c.summary.venue, c.summary.year) in scope:
            for key in _abstract_keys(c, crawled=True):
                held[(c.summary.venue, c.summary.year, key)].add(ci)
    return held


def _yields_to_its_abstract(
    ci: int,
    group: Iterable[int],
    clusters: Sequence[_Cluster],
    abstracts: dict[tuple[str, int, str], set[int]],
) -> bool:
    """Does the imported record at `ci` stay out of this title-key group (TASK-189, decision-045)? Its title is
    Scholar's (`$R^2$-Guard` arrives as `-Guard`, the title key of a different paper, `Guard`), its own-page
    abstract the publisher's. When a crawled cluster of the venue-year holds that abstract (`abstracts`:
    `_crawled_abstracts`) and none of its title partners keeps it (`_abstract_keys`), the title names another
    paper: the import yields, and step 3 joins it to the abstract's record if it may (else it stays apart). A
    partner that keeps the abstract (a main note beside its workshop version sharing it) keeps the title merge,
    and two RIS rows whose abstracts differ (an OpenReview and a camera-ready text) still merge: no crawled
    record holds either."""
    c = clusters[ci]
    if not _imported(c):
        return False
    partners = [clusters[p] for p in group if p != ci]
    return any(
        (c.summary.venue, c.summary.year, key) in abstracts
        and all(key not in _abstract_keys(p) for p in partners)
        for key in _abstract_keys(c)
    )


def _abstract_aside(c: _Cluster, group: Sequence[_Cluster]) -> str | None:
    """Why a cluster in an abstract group can never be the imported record's paper, as its not-merged resolution,
    or None. A listing is always a candidate, unless it is one by RIS evidence alone and has a status no listing
    has (decision-040). Any other record, imported or not: the title step's rule for a rival of a listing
    (`_not_the_listed_paper`), and, listing in the group or not, a status no listing has: `ris` ranks last for
    status, so an accepted import merged into a withdrawn or rejected record (a note, or an import-only row of a
    forum id) would take that status, and an accepted paper would leave every accepted-only result."""
    if c.listed:
        return None if c.crawled or c.summary.status in _LISTABLE_STATUSES else "ambiguous_not_merged"
    if any(x.listed for x in group):
        return _not_the_listed_paper(c, group)
    return None if c.summary.status in _LISTABLE_STATUSES else "ambiguous_not_merged"


def _abstract_group(group: Sequence[_Cluster]) -> str | None:
    """Why these clusters must not share a record on an abstract key, or None: `_mergeable`'s reasons, and step
    3's own. The group holds an imported record, and no record that isn't a listing by crawled evidence has a
    status a listing can't have (decision-040). It also holds at most one cluster that isn't imported, so an
    abstract never joins two crawled records (a listing and a note of another title are an owner decision,
    decision-037, TASK-187).

    Both of those checks are belt-and-braces guards no input reaches today. The status check repeats
    `_abstract_aside`, which `_abstract_merging` runs first and which already sets aside every such cluster. And
    two crawled clusters and an import can only pass `_mergeable` (one forum id, one proceedings id) if the
    import carries the id of one of them, and then step 1 has already merged it into that cluster, which is no
    longer imported."""
    crawled = [c for c in group if not _imported(c)]
    if len(crawled) > 1 or len(crawled) == len(group):
        return "ambiguous_not_merged"
    if any(c.summary.status not in _LISTABLE_STATUSES for c in group if not c.crawled):
        return "ambiguous_not_merged"
    return _mergeable(group)


def _abstract_merging(group: Sequence[_Cluster]) -> list[int] | None:
    """Positions in an abstract-key group that merge, or None: the clusters not set aside (`_abstract_aside`),
    if `_abstract_group` lets them share a record."""
    rest = [i for i, c in enumerate(group) if _abstract_aside(c, group) is None]
    if len(rest) < 2 or _abstract_group([group[i] for i in rest]) is not None:
        return None
    return rest


def _join(
    clusters: Sequence[_Cluster],
    buckets: dict[tuple[str, int, str], set[int]],
    rule: str,
    abstracts: dict[tuple[str, int, str], set[int]] | None = None,
) -> tuple[list[_Cluster], list[Merge]]:
    """Merge the clusters each bucket's key joins, where the step lets them, into new clusters (sorted by id),
    with one `rule` row per merged cluster, from its id to the survivor's. Title keys (step 2) are judged by
    `_merging` and `_mergeable`, abstract keys (step 3) by `_abstract_merging` and `_abstract_group`. `abstracts`
    (step 2: `_crawled_abstracts` of the same clusters) leaves out of a title group every import that yields to
    its abstract (`_yields_to_its_abstract`)."""
    by_abstract = rule == "abstract_venue_year"
    merging_of = _abstract_merging if by_abstract else _merging
    refusal = _abstract_group if by_abstract else _mergeable
    joined = _Clusters(len(clusters))
    joined_by: dict[int, str] = {}  # cluster → the first key it merged on
    for (_, _, key), cis in sorted(buckets.items()):
        if len(cis) < 2:
            continue
        ordered = sorted(cis)
        if abstracts is not None:
            ordered = [ci for ci in ordered if not _yields_to_its_abstract(ci, ordered, clusters, abstracts)]
            if len(ordered) < 2:
                continue
        merging = merging_of([clusters[ci] for ci in ordered])
        if merging is None:
            continue  # reported by _refusals, against the output records
        for ci in (ordered[i] for i in merging):
            joined.union(ordered[merging[0]], ci)
            joined_by.setdefault(ci, shown_key(key) if by_abstract else key)
    out: list[_Cluster] = []
    merges: list[Merge] = []
    for group in joined.groups():
        chained = [clusters[ci] for ci in group]
        # keys chained clusters that must not share a record: keep every cluster on its own. A cluster set
        # aside on one key (TASK-126) never merges through another. A track one never merges: a key's group with a
        # listing sets it aside again, one without refuses it on forum ids. A status one can (`_mergeable` ignores status; a lone rejected note
        # merges with its listing), and this re-check refuses it only because every non-listing record has
        # its own forum id (dedup refuses one naming neither a forum id nor its proceedings URL), unlike the
        # note the listing merged with. The chain splits: the safe direction, never a merge
        refused = len(group) > 1 and refusal(chained) is not None
        for part in [[ci] for ci in group] if refused else [group]:
            members = [clusters[ci] for ci in part]
            if len(members) == 1:
                out.append(members[0])
                continue
            survivor = _survivor_id(members)
            cluster = _cluster([r for m in members for r in m.members], survivor)
            out.append(cluster)
            merges += [
                Merge(survivor, clusters[ci].id, rule, joined_by[ci], cluster.summary.venue, cluster.summary.year,
                      "+".join(sorted(clusters[ci].sources)))
                for ci in part if clusters[ci].id != survivor
            ]  # fmt: skip
    return sorted(out, key=lambda c: c.id), merges


def _link(same_id: Sequence[_Cluster]) -> tuple[list[_Cluster], list[Merge]]:
    """The forum link: step-1 clusters naming one forum id (own or in a kept `urls.forum` claim) in one venue
    and year merge, whatever their titles, unless `_mergeable(linked=True)` refuses. One `forum_link` row per
    merged cluster, from its id to the survivor's. Sorted by id, so the input order never matters."""
    buckets: dict[tuple[str, int, str], set[int]] = defaultdict(set)
    for ci, c in enumerate(same_id):
        for fid in c.forum_ids:
            buckets[(c.summary.venue, c.summary.year, fid)].add(ci)
    joined = _Clusters(len(same_id))
    linked_by: dict[int, str] = {}  # cluster → the forum id it linked on
    for (_, _, fid), cis in sorted(buckets.items()):
        ordered = sorted(cis)
        if len(ordered) < 2 or _mergeable([same_id[ci] for ci in ordered], linked=True) is not None:
            continue  # a refused link is reported by _refusals, against the output records
        for ci in ordered:
            joined.union(ordered[0], ci)
            linked_by.setdefault(ci, fid)
    clusters: list[_Cluster] = []
    merges: list[Merge] = []
    for group in joined.groups():
        # a cluster naming two forum ids never links (_mergeable), so buckets can't chain; checked anyway
        refused = len(group) > 1 and _mergeable([same_id[ci] for ci in group], linked=True) is not None
        for part in [[ci] for ci in group] if refused else [group]:
            members = [same_id[ci] for ci in part]
            if len(members) == 1:
                clusters.append(members[0])
                continue
            survivor = _survivor_id(members)
            cluster = _cluster([r for m in members for r in m.members], survivor)
            clusters.append(cluster)
            merges += [
                Merge(survivor, same_id[ci].id, "forum_link", linked_by[ci], cluster.summary.venue,
                      cluster.summary.year, "+".join(sorted(same_id[ci].sources)))
                for ci in part if same_id[ci].id != survivor
            ]  # fmt: skip
    return sorted(clusters, key=lambda c: c.id), merges


def _refusals(out: Sequence[PaperRecord]) -> set[Conflict]:
    """The not-merged rows, judged on the output records, so a second run reports exactly the same rows:
    one forum id (own or linked) in two venue-years, a forum link refused within one venue-year, and every
    title key shared by records that stayed apart (a key or forum id whose records could merge alone was
    refused as part of a chain)."""
    clusters = sorted((_cluster([r]) for r in out), key=lambda c: c.id)
    rows: set[Conflict] = set()
    by_forum: dict[str, list[_Cluster]] = defaultdict(list)
    for c in clusters:
        for fid in c.forum_ids:
            by_forum[fid].append(c)
    for same in by_forum.values():
        first = same[0]  # one forum id in two venue-years: a conflict, never a merge
        rows.update(
            _pair(first, c, "venue_year_not_merged", "forum_id")
            for c in same[1:]
            if (c.summary.venue, c.summary.year) != (first.summary.venue, first.summary.year)
        )
        by_venue_year: dict[tuple[str, int], list[_Cluster]] = defaultdict(list)
        for c in same:
            by_venue_year[(c.summary.venue, c.summary.year)].append(c)
        for group in by_venue_year.values():  # one forum id in one venue-year, still apart: the link refused
            if len(group) > 1:
                reason = _mergeable(group, linked=True)
                fld = "forum_id" if reason else "forum_id_chain"
                rows.update(_pair(group[0], c, reason or "ambiguous_not_merged", fld) for c in group[1:])
    buckets: dict[tuple[str, int, str], set[int]] = defaultdict(set)
    for ci, c in enumerate(clusters):
        for key in c.keys:
            buckets[(c.summary.venue, c.summary.year, key)].add(ci)
    abstracts = _crawled_abstracts(clusters)
    titled: set[Conflict] = set()
    for cis in buckets.values():
        ordered = sorted(cis)
        # an import that yields to its abstract (decision-045), against the first title partner that doesn't:
        # "first" in cluster order, so with several partners the row names one, and every run names the same one
        yielded = {ci for ci in ordered if _yields_to_its_abstract(ci, ordered, clusters, abstracts)}
        partner = next((ci for ci in ordered if ci not in yielded), None)
        if partner is not None:
            titled.update(_pair(clusters[partner], clusters[ci], "ambiguous_not_merged") for ci in yielded)
        bucket = [clusters[ci] for ci in ordered if ci not in yielded]
        if len(bucket) < 2:
            continue
        # a cluster that can't be a listing's paper (TASK-126) is reported against the first listing, with
        # its own reason; the rest as before (a key whose records could merge alone was refused in a chain)
        aside: dict[str, str] = {}
        if _mergeable(bucket) is not None and any(c.listed for c in bucket):
            aside = {c.id: why for c in bucket if (why := _not_the_listed_paper(c, bucket))}
        if aside:
            listing = next(c for c in bucket if c.listed)
            titled.update(_pair(listing, c, aside[c.id]) for c in bucket if c.id in aside)
        rest = [c for c in bucket if c.id not in aside]
        if len(rest) > 1:
            reason = _mergeable(rest)
            fld = "title_key" if reason else "title_key_chain"
            titled.update(_pair(rest[0], c, reason or "ambiguous_not_merged", fld) for c in rest[1:])
    rows |= titled
    reported = {frozenset((row.value_a, row.value_b)) for row in titled}
    # step 3's groups (TASK-179), on the output records: an imported record that stayed apart, and a record an
    # import merged into (a listing holding a `ris` claim), each with the records sharing that abstract. A pair a
    # title key already reported gets no second row: it says nothing more (on the 2026-10-05 crawl every such
    # abstract pair was a listing and its same-title workshop version).
    found: set[Conflict] = set()
    for cis in _abstract_buckets(clusters, merged_too=True).values():
        bucket = [clusters[ci] for ci in sorted(cis)]
        if len(bucket) < 2:
            continue
        aside = {c.id: why for c in bucket if (why := _abstract_aside(c, bucket))}
        if len(aside) == len(bucket):
            aside = {}  # no candidate to report them against: the group's own refusal below names them
        if aside:  # against the first candidate (a listing, or a record with a status a listing can have)
            anchor = next(c for c in bucket if c.id not in aside)
            found.update(_pair(anchor, c, aside[c.id], "abstract_key") for c in bucket if c.id in aside)
        rest = [c for c in bucket if c.id not in aside]
        if len(rest) > 1:
            reason = _abstract_group(rest)
            fld = "abstract_key" if reason else "abstract_key_chain"
            found.update(_pair(rest[0], c, reason or "ambiguous_not_merged", fld) for c in rest[1:])
    rows.update(row for row in found if frozenset((row.value_a, row.value_b)) not in reported)
    return rows
