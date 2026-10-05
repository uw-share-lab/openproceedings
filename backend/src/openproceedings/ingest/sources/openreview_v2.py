"""The OpenReview API v2 crawler (TASK-050; spec 01 §Sources; openreview-api and openreview-venueids skills).

One venue-year at a time (ICLR 2024+, NeurIPS 2023+, ICML 2023+; earlier years are API v1, `openreview_v1`):

1. **Venue groups.** `GET /groups?parent=<Org>.cc/<Y>` lists the year's groups; `Workshop`,
   `Workshop_<City>` and `Track` are containers whose children are listed too. A group whose path names a
   proposal is skipped. Each remaining group is read by id: it is a v2 venue only when its `domain` is its
   own id and its content names a `submission_venue_id`; anything else is skipped and reported.
2. **Venueids.** Each venue's accepted venueid (its id, or `content.venue_id`) and the four its content
   names (`submission_venue_id`, `rejected_venue_id`, `withdrawn_venue_id`, `desk_rejected_venue_id`;
   decision-012: rejected, withdrawn and desk-rejected submissions are crawled explicitly). A venueid naming
   another venue or year is skipped (never re-yeared).
3. **Notes.** `GET /notes?content.venueid=<vid>&limit=<n>&offset=<k>&sort=number:asc`, until a short page.
   `count` (sent because `offset` is) must equal the rows fetched and the distinct ids; otherwise the listing
   changed under a resumed crawl, and the run is refused (re-run with `--refresh`).
4. **Records.** Only the submission note (`id == forum`) becomes a record, and only its own
   `content.venueid`, through `classify.classify_venueid`, decides track and status: never an invitation,
   never the venueid it was listed under. A note without one is `unknown`/`unknown` (a DEBUG line with its
   forum id; the crawl's one `openreview_crawl_attention` WARNING counts them).
   Every value is a claim with `source="openreview_v2"`, the page URL it came from and the page's
   `fetched_at` from the cache.
5. **Presentation** (TASK-101; spec 01 §Presentation). An accepted, non-workshop note's `content.venue` is
   looked up exactly in its venue-year's table (`classify.classify_v2_presentation`); a string the table lacks
   gives `presentation` null, a DEBUG `openreview_presentation_unmapped` line (forum id only) and a count,
   `presentation_unmapped`, in the report and the crawl's lines.

**Logs** (logging-standards; TASK-116): `openreview_crawl_started`, then `openreview_crawl_progress` at most every
30 s on the client's monotonic clock (`common.Heartbeat`), then `openreview_crawl_finished` (all INFO, with `api`,
`venue`, `year`, the counts so far, `requests` and `cached`), and at most one `openreview_crawl_attention`
WARNING with the anomaly counts (including `cache_incompatible`: pre-projection cache entries purged and
re-fetched, each a DEBUG `openreview_cache_incompatible` line). Per-note anomalies are DEBUG. API v1 (`openreview_v1`) logs the same lines.

The client's public projections of the responses are cached (`openreview_client`); a finished crawl also writes
`<cache>/openreview/v2/crawls/<Venue>-<Year>.json`, which is how `op snapshot build` knows which
venue-years to replay (offline, from the same cached responses).
"""

from __future__ import annotations

import logging
import re
import time
from collections import Counter
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any

from pydantic import ValidationError

from openproceedings.ingest.classify import classify_v2_presentation, classify_venueid
from openproceedings.ingest.record import (
    FORUM_ID,
    Claim,
    ClaimField,
    ClaimValue,
    PaperRecord,
    Source,
    Urls,
    title_evidence,
    title_text,
)
from openproceedings.ingest.sources.common import CrawlError, Crawls, Heartbeat, Report
from openproceedings.ingest.sources.http import CacheMiss
from openproceedings.ingest.sources.openreview_client import OpenReviewClient
from openproceedings.logs import elapsed_ms

log = logging.getLogger(__name__)

SOURCE: Source = "openreview_v2"
FIRST_V2_YEAR = {"ICLR": 2024, "NeurIPS": 2023, "ICML": 2023}  # spec 01 §Sources (verified 2026-09-27)
PAGE_SIZE = 1000  # the API's maximum (`limit=1001` is a 400)
STATUS_VENUEIDS = ("submission_venue_id", "rejected_venue_id", "withdrawn_venue_id", "desk_rejected_venue_id")
PUBLIC_FLAGS = ("public_submissions", "public_withdrawn_submissions", "public_desk_rejected_submissions")
SKIP_REASONS = ("not_submission", "no_title", "out_of_scope", "duplicate", "invalid")
_PDF = re.compile(r"/pdf/[0-9a-f]{40}\.pdf")
_FORUM_URL = "https://openreview.net/forum?id={}"
CRAWL_STARTED = "openreview_crawl_started"
CRAWL_PROGRESS = "openreview_crawl_progress"


def cache_root(cache: Path) -> Path:
    return cache / "openreview" / "v2"


def http_dir(cache: Path) -> Path:
    return cache_root(cache) / "http"


def crawls_dir(cache: Path) -> Path:
    return cache_root(cache) / "crawls"


def check_scope(venue: str, year: int) -> None:
    """Refuse a venue-year this crawler doesn't serve (a v1 year, an unknown venue)."""
    first = FIRST_V2_YEAR.get(venue)
    if first is None:
        raise ValueError(f"unknown venue {venue!r}: one of {', '.join(FIRST_V2_YEAR)}")
    if year < first:
        raise ValueError(f"{venue} {year} is not on OpenReview API v2 (API v1 years: `openreview_v1`)")


@dataclass(frozen=True)
class VenueGroup:
    id: str
    venueids: tuple[str, ...]  # accepted first, then the group's status venueids
    public: Mapping[str, bool]


@dataclass
class CrawlReport(Report):
    """What one venue-year gave; `to_manifest()` goes into the crawl file and the snapshot manifest."""

    source: str = field(default=SOURCE, init=False)
    venue: str
    year: int
    page_size: int = PAGE_SIZE  # part of every page's URL, so a replay must page the same way
    complete: bool = True  # False on a dry run that met an uncached response
    groups: list[str] = field(default_factory=list)
    skipped_groups: dict[str, str] = field(default_factory=dict)  # group id → reason
    public: dict[str, dict[str, bool]] = field(default_factory=dict)  # group id → its public_* flags
    venueids: dict[str, int] = field(default_factory=dict)  # venueid → notes listed
    notes_read: int = 0
    imported: int = 0
    skipped: Counter[str] = field(default_factory=lambda: Counter(dict.fromkeys(SKIP_REASONS, 0)))
    unknown_track: int = 0
    presentation_unmapped: int = 0  # accepted, non-workshop records whose content.venue isn't in the table
    abstract_missing: int = 0
    track_status: dict[str, Counter[str]] = field(default_factory=dict)
    would_fetch: list[str] = field(default_factory=list)  # dry run: the uncached requests met first

    api = "v2"

    def to_manifest(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "api": self.api,
            "venue": self.venue,
            "year": self.year,
            "complete": self.complete,
            "page_size": self.page_size,
            "groups": sorted(self.groups),
            "skipped_groups": dict(sorted(self.skipped_groups.items())),
            "public": {g: dict(sorted(f.items())) for g, f in sorted(self.public.items())},
            "venueids": dict(sorted(self.venueids.items())),
            "notes_read": self.notes_read,
            "imported": self.imported,
            "skipped": dict(sorted(self.skipped.items())),
            "unknown_track": self.unknown_track,
            "presentation_unmapped": self.presentation_unmapped,
            "abstract_missing": self.abstract_missing,
            "track_status": {t: dict(sorted(s.items())) for t, s in sorted(self.track_status.items())},
            "crawl_window": self.crawl_window(),
        }
        if not self.complete:
            out["would_fetch"] = list(self.would_fetch)
        return out


@dataclass(frozen=True)
class Crawl:
    records: tuple[PaperRecord, ...]
    report: CrawlReport

    @property
    def reports(self) -> tuple[CrawlReport]:
        return (self.report,)


# --- notes → records ----------------------------------------------------------------------------------------


def _value(content: Mapping[str, Any], key: str) -> Any:
    """A v2 content field's value (`{"value": …}`); None when absent or not in that shape."""
    item = content.get(key)
    return item.get("value") if isinstance(item, Mapping) else None


def _strings(value: Any) -> tuple[str, ...]:
    return tuple(v for v in value if isinstance(v, str) and v.strip()) if isinstance(value, list) else ()


def _text(value: Any) -> str | None:
    """Whitespace collapsed (as the RIS importer does, so claims from both sources compare); None if empty."""
    if not isinstance(value, str):
        return None
    return " ".join(value.split()) or None


def _title(value: Any, forum: str) -> tuple[str | None, str]:
    """A note's title and its claim's evidence (both API versions). A control character the source left in it
    becomes a space (`record.title_text`, TASK-180, decision-036): the paper is kept, the evidence says how many were replaced,
    and a DEBUG line names the forum. None when no title is left."""
    if not isinstance(value, str):
        return None, "content.title"
    title, replaced = title_text(value)
    if replaced:
        log.debug("openreview_title_control_characters", extra={"forum": forum, "replaced": replaced})
    return title or None, title_evidence("content.title", replaced)


def note_record(
    note: Mapping[str, Any],
    *,
    venue: str,
    year: int,
    page_url: str,
    fetched_at: datetime,
    unmapped: set[str] | None = None,
) -> PaperRecord | str:
    """The record for one listed note, or the reason it is skipped (one of SKIP_REASONS). An accepted,
    non-workshop note whose `content.venue` its venue-year's presentation table lacks gets `presentation`
    null and its forum id added to `unmapped` (the crawl counts them)."""
    forum, nid = note.get("forum"), note.get("id")
    if not isinstance(nid, str) or nid != forum:
        return "not_submission"  # only the submission note speaks for the paper (zkNCWtw2fd)
    if not FORUM_ID.fullmatch(nid):
        return "invalid"
    content: Mapping[str, Any] = note["content"] if isinstance(note.get("content"), Mapping) else {}
    title, title_evidence = _title(_value(content, "title"), nid)
    if title is None:
        return "no_title"
    raw = _value(content, "venueid")
    vid = raw if isinstance(raw, str) and raw else None
    if vid is None:
        track, status, evidence = "unknown", "unknown", "no content.venueid on the submission note"
        log.debug("openreview_unknown_track", extra={"forum": nid, "why": "no_venueid"})
    else:
        cls = classify_venueid(vid)
        if cls.parsed and (cls.venue, cls.year) != (venue, year):
            return "out_of_scope"  # skill rule 3: a conflict, never silently re-yeared
        track, status, evidence = cls.track, cls.status, f"venueid={vid}"
        if not cls.parsed:
            log.debug("openreview_unknown_track", extra={"forum": nid, "why": "venueid_unparsed"})
    presentation, venue_string = None, _value(content, "venue")
    if status == "accepted" and track != "workshop":  # a workshop's sessions aren't the conference's
        found = classify_v2_presentation(venue, year, track, venue_string)
        presentation = found.value
        if not found.mapped:
            log.debug("openreview_presentation_unmapped", extra={"forum": nid})  # the string may be free text
            if unmapped is not None:
                unmapped.add(nid)
    abstract = _text(_value(content, "abstract"))
    if abstract is not None and (abstract.startswith("…") or abstract.endswith("…")):
        abstract = None  # the record refuses a snippet-shaped abstract; the paper is kept on its title
    authors, keywords = _strings(_value(content, "authors")), _strings(_value(content, "keywords"))
    pdf_path = _value(content, "pdf")
    urls = Urls(
        forum=_FORUM_URL.format(nid),
        pdf=f"https://openreview.net{pdf_path}" if isinstance(pdf_path, str) and _PDF.fullmatch(pdf_path) else None,
    )  # fmt: skip

    def claim(fld: ClaimField, value: ClaimValue, ev: str) -> Claim:
        return Claim(field=fld, value=value, source=SOURCE, url=page_url, fetched_at=fetched_at, evidence=ev)

    scope: tuple[tuple[ClaimField, ClaimValue], ...] = (
        ("venue", venue), ("year", year), ("track", track), ("status", status),
    )  # fmt: skip
    provenance = [claim(f, v, evidence) for f, v in scope]
    provenance += [claim("title", title, title_evidence), claim("authors", authors, "content.authors")]
    if abstract is not None:
        provenance.append(claim("abstract", abstract, "content.abstract"))
    if keywords:
        provenance.append(claim("keywords", keywords, "content.keywords"))
    if presentation is not None:
        provenance.append(claim("presentation", presentation, f"content.venue={venue_string}"))
    if vid is not None:
        provenance.append(claim("venue_id_raw", vid, "content.venueid"))
    provenance.append(claim("urls.forum", urls.forum, "note.id"))
    if urls.pdf:
        provenance.append(claim("urls.pdf", urls.pdf, "content.pdf"))
    try:
        return PaperRecord.build(
            id=f"op:{venue.lower()}:{year}:{nid}", title=title, abstract=abstract, authors=authors, venue=venue,
            year=year, track=track, status=status, presentation=presentation, venue_id_raw=vid, urls=urls, keywords=keywords,
            provenance=tuple(provenance),
        )  # fmt: skip
    except ValidationError:
        return "invalid"


# --- the crawl ------------------------------------------------------------------------------------------------


class Progress:
    """One crawl's start line and its heartbeats (INFO, both API versions): `tick()`, called before each note,
    logs `openreview_crawl_progress` when one is due (`common.Heartbeat`, on the client's monotonic clock), with
    the venue-year, the API, `counts()` (what has been processed so far), `requests` and `cached`."""

    def __init__(self, logger: logging.Logger, client: OpenReviewClient, api: str, venue: str, year: int,
                 page_size: int, counts: Callable[[], dict[str, int]]) -> None:  # fmt: skip
        self._log, self._client, self._counts = logger, client, counts
        self._scope: dict[str, str | int] = {"api": api, "venue": venue, "year": year}
        self._beat = Heartbeat(client.clock.monotonic)
        logger.info(CRAWL_STARTED, extra={**self._scope, "offline": client.offline, "page_size": page_size})

    def tick(self) -> None:
        if self._beat.due():
            self._log.info(CRAWL_PROGRESS, extra={**self._scope, **self._counts(),
                                                  "requests": self._client.requests, "cached": self._client.cached})  # fmt: skip


def _pages(client: OpenReviewClient, path: str, params: Mapping[str, str | int], key: str,
           page_size: int) -> Iterator[tuple[dict[str, Any], list[Any]]]:  # fmt: skip
    """Each page's cache entry and its items, `offset` by `page_size`, until a short page. A page holding
    only ids already seen means the API ignored the offset: refused, never looped on. A listing is re-fetched
    as a whole: once one page has expired (TASK-102), every later page is fetched again too, so the pages
    come from one moment and agree."""
    offset = 0
    seen: set[str] = set()
    stale = False
    while True:
        expired = client.stats.expired
        entry = client.get(path, {**params, "limit": page_size, "offset": offset}, refresh=stale)
        stale = stale or client.stats.expired > expired
        items = entry["json"].get(key)
        if not isinstance(items, list):
            raise CrawlError(f"{entry['url']} has no {key} list", reason="unexpected_shape")
        ids = {i for n in items if isinstance(n, Mapping) and isinstance(i := n.get("id"), str)}
        if items and ids <= seen:
            raise CrawlError(f"{entry['url']} repeats the previous pages; the API ignored the offset")
        seen |= ids
        yield entry, items
        if len(items) < page_size:
            return
        offset += page_size


def _is_container(gid: str) -> bool:
    last = gid.rsplit("/", 1)[-1]
    return last in ("Workshop", "Track") or last.startswith("Workshop_")


def _group_ids(client: OpenReviewClient, parent: str, report: CrawlReport, page_size: int) -> list[str]:
    ids: list[str] = []
    # Do not select only `id`: the cache's public projection must see each group's readers ACL before it
    # persists even the id. The projected cache still retains only fields the crawler needs.
    for entry, groups in _pages(client, "/groups", {"parent": parent}, "groups", page_size):
        report.fetched.append(datetime.fromisoformat(entry["fetched_at"]))
        ids += [g["id"] for g in groups if isinstance(g, Mapping) and isinstance(g.get("id"), str)]
    return sorted(set(ids))


def _venue_group(client: OpenReviewClient, gid: str, report: CrawlReport) -> VenueGroup | None:
    entry = client.get("/groups", {"id": gid})
    report.fetched.append(datetime.fromisoformat(entry["fetched_at"]))
    groups = [g for g in entry["json"].get("groups") or [] if isinstance(g, Mapping) and g.get("id") == gid]
    content = groups[0].get("content") if groups else None
    if not groups or groups[0].get("domain") != gid or not isinstance(content, Mapping):
        report.skipped_groups[gid] = "not_a_v2_venue"
        return None
    if not isinstance(_value(content, "submission_venue_id"), str):
        report.skipped_groups[gid] = "no_submission_venue_id"
        return None
    accepted = _value(content, "venue_id")
    venueids = [accepted if isinstance(accepted, str) and accepted else gid]
    venueids += [v for k in STATUS_VENUEIDS if isinstance(v := _value(content, k), str) and v]
    public = {k: v for k in PUBLIC_FLAGS if isinstance(v := _value(content, k), bool)}
    return VenueGroup(gid, tuple(dict.fromkeys(venueids)), MappingProxyType(public))


def _raise(e: CacheMiss) -> None:
    raise e


def venue_groups(client: OpenReviewClient, venue: str, year: int, report: CrawlReport,
                 page_size: int = PAGE_SIZE, on_miss: Callable[[CacheMiss], None] = _raise,
                 ) -> list[VenueGroup]:  # fmt: skip
    """The year's v2 venue groups (module docstring, step 1). `on_miss` decides what an uncached response
    does (a dry run notes it and follows the other branches)."""
    try:
        top = _group_ids(client, f"{venue}.cc/{year}", report, page_size)
    except CacheMiss as e:
        on_miss(e)
        return []
    candidates: list[str] = []
    for gid in top:
        if "proposal" in gid.casefold():
            report.skipped_groups[gid] = "proposal"
        elif not _is_container(gid):
            candidates.append(gid)
        else:
            try:
                candidates += _group_ids(client, gid, report, page_size)
            except CacheMiss as e:
                on_miss(e)
    found = []
    for gid in sorted(set(candidates)):
        if "proposal" in gid.casefold():
            report.skipped_groups[gid] = "proposal"
        elif _is_container(gid):
            report.skipped_groups[gid] = "container"
        else:
            try:
                if (group := _venue_group(client, gid, report)) is not None:
                    found.append(group)
            except CacheMiss as e:
                on_miss(e)
    return found


def crawl(client: OpenReviewClient, venue: str, year: int, *, dry_run: bool = False,
          page_size: int = PAGE_SIZE) -> Crawl:  # fmt: skip
    """Every public submission of one venue-year as records (module docstring). A dry run reads only the
    cache (the client must be offline) and lists the first uncached request of each branch it can't follow."""
    check_scope(venue, year)
    if dry_run and not client.offline:
        raise ValueError("a dry run needs an offline client")
    began, purged = time.monotonic(), client.incompatible
    report = CrawlReport(venue, year, page_size=page_size)
    records: dict[str, PaperRecord] = {}
    unmapped: set[str] = set()  # forum ids whose presentation string isn't in the table
    progress = Progress(log, client, report.api, venue, year, page_size, lambda: {
        "notes_read": report.notes_read, "imported": len(records), "skipped": sum(report.skipped.values())})  # fmt: skip

    def missed(e: CacheMiss) -> None:
        if not dry_run:
            raise e
        report.complete = False
        report.would_fetch.append(e.url)

    for group in venue_groups(client, venue, year, report, page_size, missed):
        report.groups.append(group.id)
        if group.public:
            report.public[group.id] = dict(group.public)
        for vid in group.venueids:
            cls = classify_venueid(vid)
            if (cls.venue, cls.year) != (venue, year):
                report.skipped_groups[f"{group.id} venueid {vid}"] = "out_of_scope"
                continue
            try:
                _listing(client, vid, venue, year, report, records, unmapped, page_size, progress.tick)
            except CacheMiss as e:
                missed(e)
    for r in records.values():
        report.track_status.setdefault(r.track, Counter())[r.status] += 1
    report.imported = len(records)
    report.unknown_track = sum(r.track == "unknown" for r in records.values())
    # only notes that became records: one skipped as invalid, or a re-listed duplicate, isn't counted twice
    report.presentation_unmapped = sum(f"op:{venue.lower()}:{year}:{n}" in records for n in unmapped)
    report.abstract_missing = sum(r.abstract is None for r in records.values())
    incompatible = client.incompatible - purged  # this crawl's share of the client's count
    log.info("openreview_crawl_finished",
             extra={"api": report.api, "venue": venue, "year": year, "complete": report.complete, "groups": len(report.groups),
                    "notes_read": report.notes_read, "imported": report.imported,
                    "skipped": sum(report.skipped.values()), "unknown_track": report.unknown_track,
                    "presentation_unmapped": report.presentation_unmapped,
                    "requests": client.requests, "cached": client.cached, "cache_incompatible": incompatible,
                    "ms": elapsed_ms(began, time.monotonic)})  # fmt: skip
    anomalies = {k: report.skipped[k] for k in ("out_of_scope", "invalid", "duplicate")}
    if report.unknown_track or report.presentation_unmapped or incompatible or any(anomalies.values()):
        log.warning("openreview_crawl_attention",
                    extra={"api": report.api, "venue": venue, "year": year, "unknown_track": report.unknown_track,
                           "presentation_unmapped": report.presentation_unmapped,
                           **anomalies, "cache_incompatible": incompatible})  # fmt: skip
    return Crawl(tuple(sorted(records.values(), key=lambda r: r.id)), report)


def _listing(client: OpenReviewClient, vid: str, venue: str, year: int, report: CrawlReport,
             records: dict[str, PaperRecord], unmapped: set[str], page_size: int,
             tick: Callable[[], None]) -> None:  # fmt: skip
    """Page through one venueid's notes into `records`, checking the listing is consistent; `tick()` before
    each note (the crawl's heartbeat)."""
    params = {"content.venueid": vid, "sort": "number:asc"}
    seen: set[str] = set()
    rows = 0
    counts: set[int] = set()
    for entry, notes in _pages(client, "/notes", params, "notes", page_size):
        report.fetched.append(datetime.fromisoformat(entry["fetched_at"]))
        count = entry["json"].get("count")
        if type(count) is not int or count < 0:
            raise CrawlError(
                f"the listing of {vid} has a missing or invalid count; "
                "re-run with --refresh to fetch it again"
            )
        counts.add(count)
        seen |= {i for n in notes if isinstance(n, Mapping) and isinstance(i := n.get("id"), str)}
        rows += len(notes)
        fetched_at = datetime.fromisoformat(entry["fetched_at"])
        for note in notes:
            tick()
            if not isinstance(note, Mapping):
                report.skipped["invalid"] += 1
                continue
            got = note_record(
                note, venue=venue, year=year, page_url=entry["url"], fetched_at=fetched_at, unmapped=unmapped
            )
            report.notes_read += 1
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
            else:
                records[got.id] = got
    if rows != len(seen) or len(counts) > 1 or (counts and counts.pop() != rows):
        raise CrawlError(
            f"the listing of {vid} changed between its cached pages (rows, distinct ids and count disagree); "
            "re-run with --refresh to fetch it again"
        )
    report.venueids[vid] = rows
    log.debug("openreview_venueid_listed", extra={"venueid": vid, "notes": rows})


# --- the crawl files --------------------------------------------------------------------------------------


def crawl_file(cache: Path, venue: str, year: int) -> Path:
    return crawls_dir(cache) / f"{venue}-{year}.json"


def ingest(client: OpenReviewClient, cache: Path, venue: str, years: Sequence[int], *,
           dry_run: bool = False, page_size: int = PAGE_SIZE) -> list[CrawlReport]:  # fmt: skip
    """Crawl each year into the cache (one crawl at a time per cache: `.lock`) and, for a complete,
    non-dry-run crawl, write its crawl file (atomically) so `op snapshot build` replays it."""
    for year in years:
        check_scope(venue, year)  # refuse the whole request before fetching anything

    def marker(year: int, c: Crawl) -> tuple[str, dict[str, Any]] | None:
        return None if dry_run or not c.report.complete else (f"{venue}-{year}", c.report.to_manifest())

    crawls = CRAWLS.ingest(
        cache, years, lambda year: crawl(client, venue, year, dry_run=dry_run, page_size=page_size), marker
    )
    return [c.report for c in crawls]


def marker_key(marker: Mapping[str, Any]) -> tuple[str, int, int]:
    """A crawl file's venue, year and page size (part of every page's URL, so a replay pages the same way)."""
    return str(marker["venue"]), int(marker["year"]), int(marker["page_size"])


def _replay_one(cache: Path, key: tuple[Any, ...]) -> Crawl:
    venue, year, page_size = key
    return crawl(
        OpenReviewClient(http_dir(cache), credentials=None, offline=True), venue, year, page_size=page_size
    )


CRAWLS: Crawls[Crawl] = Crawls(crawls_dir, marker_key, lambda k: f"{k[0]} {k[1]} (OpenReview API v2)",
                               "op ingest openreview", _replay_one)  # fmt: skip


def replay(cache: Path) -> list[Crawl]:
    """Every finished crawl, rebuilt from the cache alone (no credentials, no network)."""
    return CRAWLS.replay(cache)
