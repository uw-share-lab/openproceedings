"""Deduplication (spec 01 §Pipeline 4; dedup-rules skill; decision-005).

One record per paper, and never two papers folded into one: an over-merge silently deletes a paper from
a review, a duplicate only shows in the hit count.

1. Records with the same id merge, from any source: the same OpenReview forum id in the same venue and
   year, or the same proceedings id (one paper reached by both Trust-Evals searches). One forum id in two
   venue-years is a conflict, never a merge.
   Then the **forum link** (TASK-105): clusters that name the same forum id, as their own id or in a kept
   `urls.forum` claim (PMLR's index links the OpenReview forum from 2023; v235 is recorded), merge in the
   same venue and year whatever their titles say, unless the result would hold two forum ids, two
   proceedings ids, or a track the proceedings don't host. A refused link, and a link across venue-years,
   is a `conflicts.csv` row.
2. Clusters then merge on `(venue, year, title key)` only **across sources** (their provenance source
   sets are disjoint), never two different forum ids (own or linked) or two different proceedings ids, and never a
   paper whose track the proceedings don't host into a proceedings listing (a record with a proceedings
   id or a proceedings source). A key that would join clusters sharing a source is ambiguous: nothing
   merges, and `conflicts.csv` says so. When such a key holds a listing, the clusters that can't be the
   listed paper (TASK-126: a track the proceedings don't host, or a status other than accepted/unknown)
   are set aside as rivals and the rest merge if they may; the set-aside clusters stay separate records.

A merged record's fields are re-resolved from the union of its claims by `PRECEDENCE` (held as data),
never "whichever came first". So every input must already equal what its own claims resolve to; dedup
refuses one that doesn't. When one source claims a field twice (the same paper in both searches), the
newest claim replaces the older one, and a differing value is a `newest:`/`tie:` row. The output depends
only on the set of inputs (sorted ids, set-based decisions).
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from openproceedings.ingest import urls
from openproceedings.ingest.record import Claim, ClaimField, PaperRecord, Source, Urls
from openproceedings.query.normalize import normalize

_TEXT: tuple[Source, ...] = (
    "openreview_v2", "openreview_v1", "iclr_archive", "neurips_proceedings", "pmlr", "ris",
)  # fmt: skip
_ACCEPTANCE: tuple[Source, ...] = (
    "iclr_archive", "neurips_proceedings", "pmlr", "openreview_v2", "openreview_v1", "ris",
)  # fmt: skip
# decision-005: OpenReview first for text and track; the official proceedings decide acceptance; RIS last.
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
_PROCEEDINGS_SOURCES = frozenset({"iclr_archive", "neurips_proceedings", "pmlr"})
_PROCEEDINGS_TRACKS = frozenset({"main", "datasets_benchmarks", "position"})  # proceedings never host others
_URL_FIELDS = ("urls.proceedings", "urls.pdf")
# A listing names only accepted papers; `unknown` may still be one (unresolved v1 evidence), so it stays a rival.
_LISTABLE_STATUSES = frozenset({"accepted", "unknown"})


@dataclass(frozen=True, order=True)
class Merge:
    survivor_id: str
    merged_id: str
    rule: str  # forum_id | native_id | forum_link | title_venue_year
    # forum_link: the shared forum id; title_venue_year: the title key that joined the merged cluster to the
    # group (in a chain, not always the survivor's)
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
    """The token-contract normalisation joined by single spaces: dedup and search agree on 'same title'."""
    return " ".join(normalize(title))


def _text(v: object) -> str:
    return "; ".join(v) if isinstance(v, tuple) else "" if v is None else str(v)


def _differ(fld: str, a: object, b: object) -> bool:
    return title_key(_text(a)) != title_key(_text(b)) if fld == "title" else _text(a) != _text(b)


def _exact(v: object) -> str:
    """A value's exact form: `("Smith; J",)` and `("Smith", "J")` print alike through `_text` but differ here."""
    return json.dumps(v, sort_keys=True, ensure_ascii=False)


def _sources(records: Iterable[PaperRecord]) -> frozenset[str]:
    return frozenset(c.source for r in records for c in r.provenance)


def _one_per_field_and_source(record_id: str, claims: Iterable[Claim]) -> tuple[list[Claim], list[Conflict]]:
    """The newest claim for each (field, source). Any other value that source gave is a conflicts.csv row:
    `newest:<source>` when it is older, `tie:<source>` when it was fetched at the same moment (then the
    kept value is only the deterministic pick, so a reviewer must look)."""
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

    record = PaperRecord.build(
        id=record_id, title=value("title"), abstract=value("abstract"), authors=value("authors", ()),
        venue=value("venue"), year=value("year"), track=value("track"), status=value("status"),
        presentation=value("presentation"), venue_id_raw=value("venue_id_raw"), keywords=value("keywords", ()),
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
    # its own forum id and every one a kept `urls.forum` claim names (a PMLR listing's link to OpenReview)
    forum_ids: frozenset[str]


def _url_natives(claims: Iterable[Claim]) -> set[str]:
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


def _forum_ids(record: PaperRecord) -> frozenset[str]:
    """The record's own forum id and every forum id its kept `urls.forum` claims name."""
    linked = {
        f for c in record.provenance
        if c.field == "urls.forum" and isinstance(c.value, str) and (f := urls.forum_id(c.value))
    }  # fmt: skip
    if record.forum_id is not None:
        linked.add(record.forum_id)
    return frozenset(linked)


def _cluster(members: Sequence[PaperRecord], rid: str | None = None) -> _Cluster:
    rid = rid or members[0].id
    summary, _ = resolve(rid, [c for r in members for c in r.provenance])  # rows come from the final resolve
    claims = summary.provenance  # kept claims only: the output record carries nothing else
    pids = _url_natives(claims)
    sources = _sources(members)
    return _Cluster(
        id=rid, members=tuple(members), summary=summary, sources=sources,
        keys=frozenset(k for c in summary.provenance if c.field == "title" and (k := title_key(_text(c.value)))),
        proceedings_ids=frozenset(pids), listed=bool(pids or sources & _PROCEEDINGS_SOURCES),
        forum_ids=_forum_ids(summary),
    )  # fmt: skip


def _mergeable(group: Sequence[_Cluster], *, linked: bool = False) -> str | None:
    """Why these step-1 clusters must not share a record, or None if they may. `linked`: they share a forum
    id (the forum link), so one source on two sides is no ambiguity: the id says which paper each is."""
    srcs = [c.sources for c in group]
    if not linked and any(srcs[i] & srcs[j] for i in range(len(srcs)) for j in range(i + 1, len(srcs))):
        return "ambiguous_not_merged"  # two candidates from one source: which one is the paper?
    if len(frozenset[str]().union(*(c.forum_ids for c in group))) > 1:
        return "ambiguous_not_merged"  # two different OpenReview submissions (own or linked forum ids)
    if len(frozenset().union(*(c.proceedings_ids for c in group))) > 1:
        return "ambiguous_not_merged"  # two different proceedings papers
    if any(c.listed for c in group) and any(
        c.summary.track not in _PROCEEDINGS_TRACKS and not (c.listed and c.summary.track == "unknown")
        for c in group
    ):  # only a listing's own `unknown` (a PMLR volume holding main and position papers) is let through
        return "track_not_merged"  # the proceedings never host it (an unknown track waits for evidence)
    return None


def _not_the_listed_paper(c: _Cluster) -> str | None:
    """Why a cluster can never be a proceedings listing's paper, as its not-merged resolution, or None if it
    may be one (TASK-126). A listing is always a candidate. A track the proceedings don't host is the track
    rule of `_mergeable`; an `unknown` track only waits for evidence, so like an `unknown` status it stays a
    candidate (and a rival). Proceedings list only accepted papers: a rejected, withdrawn or desk-rejected note
    is not the listed one, though it may merge alone (decision-005: the proceedings then decide its status)."""
    if c.listed:
        return None
    if c.summary.track not in _PROCEEDINGS_TRACKS and c.summary.track != "unknown":
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
    rest = [i for i, c in enumerate(group) if _not_the_listed_paper(c) is None]
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
    xs = sorted(records, key=lambda r: (r.id, r.content_hash, r.model_dump_json()))
    conflicts: set[Conflict] = set()
    merges: list[Merge] = []
    for r in xs:
        again, _ = resolve(r.id, r.provenance)
        if again != r:
            raise ValueError(f"{r.id}: fields don't match its own claims; dedup would silently change it")
        if r.forum_id is None and r.native not in _url_natives(r.provenance):
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
    buckets: dict[tuple[str, int, str], set[int]] = defaultdict(set)
    for ci, c in enumerate(clusters):
        for key in c.keys:  # a title of only punctuation or math has no key and never matches
            buckets[(c.summary.venue, c.summary.year, key)].add(ci)
    step2 = _Clusters(len(clusters))
    joined_by: dict[int, str] = {}  # cluster → the first title key it merged on
    for (_, _, key), cis in sorted(buckets.items()):
        if len(cis) < 2:
            continue
        ordered = sorted(cis)
        merging = _merging([clusters[ci] for ci in ordered])
        if merging is None:
            continue  # reported by _refusals, against the output records
        for ci in (ordered[i] for i in merging):
            step2.union(ordered[merging[0]], ci)
            joined_by.setdefault(ci, key)

    out: list[PaperRecord] = []
    for group in step2.groups():
        chained = [clusters[ci] for ci in group]
        # keys chained clusters that must not share a record: keep every cluster on its own. A cluster set
        # aside on one key (TASK-126) never merges through another. A track one never chains in: every key
        # applies the same track rule. A status one can (`_mergeable` ignores status; a lone rejected note
        # merges with its listing), and this re-check refuses it only because every non-listing record has
        # its own forum id (dedup refuses one naming neither a forum id nor its proceedings URL), unlike the
        # note the listing merged with. The chain splits: the safe direction, never a merge
        refused = len(group) > 1 and _mergeable(chained) is not None
        parts = [[ci] for ci in group] if refused else [group]
        for part in parts:
            members = [clusters[ci] for ci in part]
            survivor = _survivor_id(members)
            merged, found = resolve(survivor, [c for m in members for r in m.members for c in r.provenance])
            out.append(merged)
            conflicts.update(found)
            merges += [
                Merge(survivor, clusters[ci].id, "title_venue_year", joined_by[ci], merged.venue, merged.year,
                      "+".join(sorted(clusters[ci].sources)))
                for ci in part if clusters[ci].id != survivor
            ]  # fmt: skip
    conflicts |= _refusals(out)
    return DedupResult(
        tuple(sorted(out, key=lambda r: r.id)), tuple(sorted(merges)), tuple(sorted(conflicts))
    )


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
    buckets: dict[tuple[str, int, str], list[_Cluster]] = defaultdict(list)
    for c in clusters:
        for key in c.keys:
            buckets[(c.summary.venue, c.summary.year, key)].append(c)
    for bucket in buckets.values():
        if len(bucket) < 2:
            continue
        # a cluster that can't be a listing's paper (TASK-126) is reported against the first listing, with
        # its own reason; the rest as before (a key whose records could merge alone was refused in a chain)
        aside: dict[str, str] = {}
        if _mergeable(bucket) is not None and any(c.listed for c in bucket):
            aside = {c.id: why for c in bucket if (why := _not_the_listed_paper(c))}
        if aside:
            listing = next(c for c in bucket if c.listed)
            rows.update(_pair(listing, c, aside[c.id]) for c in bucket if c.id in aside)
        rest = [c for c in bucket if c.id not in aside]
        if len(rest) > 1:
            reason = _mergeable(rest)
            fld = "title_key" if reason else "title_key_chain"
            rows.update(_pair(rest[0], c, reason or "ambiguous_not_merged", fld) for c in rest[1:])
    return rows
