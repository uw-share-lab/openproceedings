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
   never the venueid it was listed under. A note without one is `unknown`/`unknown`, logged with its forum id.
   Every value is a claim with `source="openreview_v2"`, the page URL it came from and the page's
   `fetched_at` from the cache.

The raw responses are cached (`openreview_client`); a finished crawl also writes
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

from openproceedings import storage
from openproceedings.ingest.classify import classify_venueid
from openproceedings.ingest.record import FORUM_ID, Claim, ClaimField, ClaimValue, PaperRecord, Source, Urls
from openproceedings.ingest.sources.common import CrawlError, Crawls, Report, write_marker
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


def note_record(
    note: Mapping[str, Any], *, venue: str, year: int, page_url: str, fetched_at: datetime
) -> PaperRecord | str:
    """The record for one listed note, or the reason it is skipped (one of SKIP_REASONS)."""
    forum, nid = note.get("forum"), note.get("id")
    if not isinstance(nid, str) or nid != forum:
        return "not_submission"  # only the submission note speaks for the paper (zkNCWtw2fd)
    if not FORUM_ID.fullmatch(nid):
        return "invalid"
    content: Mapping[str, Any] = note["content"] if isinstance(note.get("content"), Mapping) else {}
    title = _text(_value(content, "title"))
    if title is None:
        return "no_title"
    raw = _value(content, "venueid")
    vid = raw if isinstance(raw, str) and raw else None
    if vid is None:
        track, status, evidence = "unknown", "unknown", "no content.venueid on the submission note"
        log.warning("openreview_unknown_track", extra={"forum": nid, "why": "no_venueid"})
    else:
        cls = classify_venueid(vid)
        if cls.parsed and (cls.venue, cls.year) != (venue, year):
            return "out_of_scope"  # skill rule 3: a conflict, never silently re-yeared
        track, status, evidence = cls.track, cls.status, f"venueid={vid}"
        if not cls.parsed:
            log.warning("openreview_unknown_track", extra={"forum": nid, "why": "venueid_unparsed"})
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
    provenance += [claim("title", title, "content.title"), claim("authors", authors, "content.authors")]
    if abstract is not None:
        provenance.append(claim("abstract", abstract, "content.abstract"))
    if keywords:
        provenance.append(claim("keywords", keywords, "content.keywords"))
    if vid is not None:
        provenance.append(claim("venue_id_raw", vid, "content.venueid"))
    provenance.append(claim("urls.forum", urls.forum, "note.id"))
    if urls.pdf:
        provenance.append(claim("urls.pdf", urls.pdf, "content.pdf"))
    try:
        return PaperRecord.build(
            id=f"op:{venue.lower()}:{year}:{nid}", title=title, abstract=abstract, authors=authors, venue=venue,
            year=year, track=track, status=status, venue_id_raw=vid, urls=urls, keywords=keywords,
            provenance=tuple(provenance),
        )  # fmt: skip
    except ValidationError:
        return "invalid"


# --- the crawl ------------------------------------------------------------------------------------------------


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
    for entry, groups in _pages(client, "/groups", {"parent": parent, "select": "id"}, "groups", page_size):
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
    began = time.monotonic()
    report = CrawlReport(venue, year, page_size=page_size)
    records: dict[str, PaperRecord] = {}

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
                _listing(client, vid, venue, year, report, records, page_size)
            except CacheMiss as e:
                missed(e)
    for r in records.values():
        report.track_status.setdefault(r.track, Counter())[r.status] += 1
    report.imported = len(records)
    report.unknown_track = sum(r.track == "unknown" for r in records.values())
    report.abstract_missing = sum(r.abstract is None for r in records.values())
    log.info("openreview_crawl_finished",
             extra={"venue": venue, "year": year, "complete": report.complete, "groups": len(report.groups),
                    "notes_read": report.notes_read, "imported": report.imported,
                    "skipped": sum(report.skipped.values()), "unknown_track": report.unknown_track,
                    "requests": client.requests, "cached": client.cached, "ms": elapsed_ms(began, time.monotonic)})  # fmt: skip
    if report.unknown_track or report.skipped["out_of_scope"] or report.skipped["invalid"]:
        log.warning("openreview_crawl_attention",
                    extra={"venue": venue, "year": year, "unknown_track": report.unknown_track,
                           "out_of_scope": report.skipped["out_of_scope"], "invalid": report.skipped["invalid"]})  # fmt: skip
    return Crawl(tuple(sorted(records.values(), key=lambda r: r.id)), report)


def _listing(client: OpenReviewClient, vid: str, venue: str, year: int, report: CrawlReport,
             records: dict[str, PaperRecord], page_size: int) -> None:  # fmt: skip
    """Page through one venueid's notes into `records`, checking the listing is consistent."""
    params = {"content.venueid": vid, "sort": "number:asc"}
    seen: set[str] = set()
    rows = 0
    counts: set[int] = set()
    for entry, notes in _pages(client, "/notes", params, "notes", page_size):
        report.fetched.append(datetime.fromisoformat(entry["fetched_at"]))
        if isinstance(count := entry["json"].get("count"), int):
            counts.add(count)
        seen |= {i for n in notes if isinstance(n, Mapping) and isinstance(i := n.get("id"), str)}
        rows += len(notes)
        fetched_at = datetime.fromisoformat(entry["fetched_at"])
        for note in notes:
            if not isinstance(note, Mapping):
                report.skipped["invalid"] += 1
                continue
            got = note_record(note, venue=venue, year=year, page_url=entry["url"], fetched_at=fetched_at)
            report.notes_read += 1
            if isinstance(got, str):
                report.skipped[got] += 1
                log.debug("openreview_note_skipped", extra={"forum": note.get("id"), "reason": got})
            elif got.id in records:
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
    reports = []
    root = cache_root(cache)
    with storage.exclusive(root):
        for year in years:
            result = crawl(client, venue, year, dry_run=dry_run, page_size=page_size)
            reports.append(result.report)
            if not dry_run and result.report.complete:
                write_marker(crawls_dir(cache), f"{venue}-{year}", result.report.to_manifest())
    return reports


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
