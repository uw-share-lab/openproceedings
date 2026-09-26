"""Deduplication (spec 01 §Pipeline 4; dedup-rules skill; decision-005).

One record per paper, and never two papers folded into one: an over-merge silently deletes a paper from
a review, a duplicate only shows in the hit count.

1. Records with the same id merge, from any source: the same OpenReview forum id in the same venue and
   year, or the same proceedings id (one paper reached by both Trust-Evals searches). One forum id in two
   venue-years is a conflict, never a merge.
2. Clusters then merge on `(venue, year, title key)` only **across sources** (their provenance source
   sets are disjoint), never two different forum ids or two different proceedings ids, and never a
   paper whose track the proceedings don't host into a proceedings listing (a record with a proceedings
   id or a proceedings source). A key that would join clusters sharing a source is ambiguous: nothing
   merges, and `conflicts.csv` says so.

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

_TEXT: tuple[Source, ...] = ("openreview_v2", "openreview_v1", "neurips_proceedings", "pmlr", "ris")
_ACCEPTANCE: tuple[Source, ...] = ("neurips_proceedings", "pmlr", "openreview_v2", "openreview_v1", "ris")
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
_PROCEEDINGS_SOURCES = frozenset({"neurips_proceedings", "pmlr"})
_PROCEEDINGS_TRACKS = frozenset({"main", "datasets_benchmarks", "position"})  # proceedings never host others
_URL_FIELDS = ("urls.proceedings", "urls.pdf")


@dataclass(frozen=True, order=True)
class Merge:
    survivor_id: str
    merged_id: str
    rule: str  # forum_id | native_id | title_venue_year
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
    """A step-1 cluster (records sharing one id), judged as the record its claims resolve to."""

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

    @property
    def id(self) -> str:
        return self.members[0].id


def _url_natives(claims: Iterable[Claim]) -> set[str]:
    return {
        n
        for c in claims
        if c.field in _URL_FIELDS and isinstance(c.value, str) and (n := urls.native(c.value))
    }


def _cluster(members: Sequence[PaperRecord]) -> _Cluster:
    summary, _ = resolve(
        members[0].id, [c for r in members for c in r.provenance]
    )  # rows come from the final resolve
    claims = summary.provenance  # kept claims only: the output record carries nothing else
    pids = {
        n
        for c in claims
        if c.field in _URL_FIELDS and isinstance(c.value, str) and (n := urls.native(c.value))
    }
    sources = _sources(members)
    return _Cluster(
        members=tuple(members), summary=summary, sources=sources,
        keys=frozenset(k for c in summary.provenance if c.field == "title" and (k := title_key(_text(c.value)))),
        proceedings_ids=frozenset(pids), listed=bool(pids or sources & _PROCEEDINGS_SOURCES),
    )  # fmt: skip


def _mergeable(group: Sequence[_Cluster]) -> str | None:
    """Why these step-1 clusters must not share a record, or None if they may."""
    srcs = [c.sources for c in group]
    if any(srcs[i] & srcs[j] for i in range(len(srcs)) for j in range(i + 1, len(srcs))):
        return "ambiguous_not_merged"  # two candidates from one source: which one is the paper?
    if len({c.summary.forum_id for c in group} - {None}) > 1:
        return "ambiguous_not_merged"  # two different OpenReview submissions
    if len(frozenset().union(*(c.proceedings_ids for c in group))) > 1:
        return "ambiguous_not_merged"  # two different proceedings papers
    if any(c.listed for c in group) and any(
        c.summary.track not in _PROCEEDINGS_TRACKS and not (c.listed and c.summary.track == "unknown")
        for c in group
    ):  # only a listing's own `unknown` (a PMLR volume holding main and position papers) is let through
        return "track_not_merged"  # the proceedings never host it (an unknown track waits for evidence)
    return None


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
    clusters: list[_Cluster] = []
    for rid in sorted(by_id):
        cluster = _cluster(by_id[rid])
        clusters.append(cluster)
        rule = "forum_id" if cluster.summary.forum_id is not None else "native_id"
        merges += [
            Merge(rid, rid, rule, cluster.summary.native, r.venue, r.year, "+".join(sorted(_sources([r]))))
            for r in by_id[rid][1:]
        ]  # the same id twice: one row per extra copy, survivor_id == merged_id
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
        if _mergeable([clusters[ci] for ci in ordered]) is not None:
            continue  # reported by _refusals, against the output records
        for ci in ordered:
            step2.union(ordered[0], ci)
            joined_by.setdefault(ci, key)

    out: list[PaperRecord] = []
    for group in step2.groups():
        chained = [clusters[ci] for ci in group]
        # keys chained clusters that must not share a record: keep every cluster on its own
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


def _refusals(out: Sequence[PaperRecord]) -> set[Conflict]:
    """The not-merged rows, judged on the output records, so a second run reports exactly the same rows:
    one forum id in two venue-years, and every title key shared by records that stayed apart (a key
    whose records could merge alone was refused as part of a chain)."""
    clusters = sorted((_cluster([r]) for r in out), key=lambda c: c.id)
    rows: set[Conflict] = set()
    by_forum: dict[str, list[_Cluster]] = defaultdict(list)
    for c in clusters:
        if c.summary.forum_id is not None:
            by_forum[c.summary.forum_id].append(c)
    for same in by_forum.values():  # one forum id in two venue-years: a conflict, never a merge
        rows.update(_pair(same[0], c, "venue_year_not_merged", "forum_id") for c in same[1:])
    buckets: dict[tuple[str, int, str], list[_Cluster]] = defaultdict(list)
    for c in clusters:
        for key in c.keys:
            buckets[(c.summary.venue, c.summary.year, key)].append(c)
    for bucket in buckets.values():
        if len(bucket) > 1:
            reason = _mergeable(bucket)
            fld = "title_key" if reason else "title_key_chain"
            rows.update(_pair(bucket[0], c, reason or "ambiguous_not_merged", fld) for c in bucket[1:])
    return rows
