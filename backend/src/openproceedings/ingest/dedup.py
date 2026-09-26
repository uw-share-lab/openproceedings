"""Deduplication (spec 01 §Pipeline 4; dedup-rules skill; decision-005).

One record per paper, and never two papers folded into one: an over-merge silently deletes a paper from
a review, a duplicate only shows in the hit count.

1. Records with the same id merge, from any source: the same OpenReview forum id in the same venue and
   year, or the same proceedings id (one paper reached by both Trust-Evals searches). One forum id in two
   venue-years is a conflict, never a merge.
2. Clusters then merge on `(venue, year, title key)` only **across sources** (their provenance source
   sets are disjoint), never two different forum ids, and never a workshop-or-other paper into a
   proceedings record. A key that joins clusters sharing a source is ambiguous: nothing merges, and
   `conflicts.csv` says so.

A merged record's fields are re-resolved from the union of its claims by `PRECEDENCE` (held as data),
never "whichever came first". So every input must already equal what its own claims resolve to; dedup
refuses one that doesn't. The output depends only on the set of inputs (sorted ids, set-based decisions).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from openproceedings.ingest.record import Claim, ClaimField, PaperRecord, Source, Urls
from openproceedings.query.normalize import normalize

_TEXT: tuple[Source, ...] = ("openreview_v2", "openreview_v1", "neurips_proceedings", "pmlr", "ris")
_ACCEPTANCE: tuple[Source, ...] = ("neurips_proceedings", "pmlr", "openreview_v2", "openreview_v1", "ris")
# decision-005: OpenReview first for text and track; the official proceedings decide acceptance.
PRECEDENCE: dict[ClaimField, tuple[Source, ...]] = {
    **dict.fromkeys(
        (
            "title",
            "abstract",
            "authors",
            "keywords",
            "presentation",
            "venue",
            "year",
            "track",
            "venue_id_raw",
        ),
        _TEXT,
    ),
    **dict.fromkeys(("urls.forum", "urls.pdf", "urls.proceedings", "urls.doi"), _TEXT),
    "status": _ACCEPTANCE,
}
CONFLICT_FIELDS: tuple[ClaimField, ...] = (
    "title",
    "track",
    "status",
)  # year and venue can't differ in a merge
_PROCEEDINGS_SOURCES = frozenset({"neurips_proceedings", "pmlr"})
_PROCEEDINGS_TRACKS = frozenset({"main", "datasets_benchmarks", "position"})  # proceedings never host others


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
    resolution: str  # precedence:<source> | newest:<source> | ambiguous_not_merged | track_not_merged | venue_year_not_merged


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


def _sources(r: PaperRecord) -> frozenset[str]:
    return frozenset(c.source for c in r.provenance)


def _one_per_field_and_source(record_id: str, claims: Iterable[Claim]) -> tuple[list[Claim], list[Conflict]]:
    """The newest claim for each (field, source); a same-source disagreement on a conflict field is kept
    in conflicts.csv (the two searches can both carry a paper)."""
    groups: dict[tuple[str, str], list[Claim]] = defaultdict(list)
    for c in claims:
        groups[(c.field, c.source)].append(c)
    kept, conflicts = [], []
    for (fld, src), group in sorted(groups.items()):
        ordered = sorted(
            set(group), key=lambda c: (c.fetched_at, c.sort_key(), _text(c.value), c.evidence or "")
        )
        newest = ordered[-1]
        kept.append(newest)
        if fld in CONFLICT_FIELDS:
            for old in {_text(c.value) for c in ordered} - {_text(newest.value)}:
                conflicts.append(
                    Conflict(record_id, fld, _text(newest.value), src, old, src, f"newest:{src}")
                )
    return kept, conflicts


def resolve(record_id: str, claims: Iterable[Claim]) -> tuple[PaperRecord, list[Conflict]]:
    """The record the claims describe, each field from its best-ranked source (PRECEDENCE)."""
    kept, conflicts = _one_per_field_and_source(record_id, claims)
    best: dict[str, Claim] = {}
    for fld, order in PRECEDENCE.items():
        ranked = sorted((c for c in kept if c.field == fld), key=lambda c: order.index(c.source))
        if ranked:
            best[fld] = ranked[0]
            if fld in CONFLICT_FIELDS:
                for other in ranked[1:]:
                    if _text(other.value) != _text(ranked[0].value):
                        conflicts.append(
                            Conflict(
                                record_id, fld, _text(ranked[0].value), ranked[0].source,
                                _text(other.value), other.source, f"precedence:{ranked[0].source}",
                            )
                        )  # fmt: skip
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


def _pair(a: PaperRecord, b: PaperRecord, resolution: str, fld: str = "title_key") -> Conflict:
    return Conflict(
        a.id, fld, a.id, "+".join(sorted(_sources(a))), b.id, "+".join(sorted(_sources(b))), resolution
    )


def _mergeable(summaries: Sequence[PaperRecord]) -> str | None:
    """Why these step-1 clusters (each as the record its claims resolve to) must not share a record."""
    srcs = [_sources(r) for r in summaries]
    if any(srcs[i] & srcs[j] for i in range(len(srcs)) for j in range(i + 1, len(srcs))):
        return "ambiguous_not_merged"  # two candidates from one source: which one is the paper?
    if len({r.forum_id for r in summaries} - {None}) > 1:
        return "ambiguous_not_merged"  # two different OpenReview submissions
    if any(s & _PROCEEDINGS_SOURCES for s in srcs) and any(
        r.track not in _PROCEEDINGS_TRACKS for r in summaries
    ):
        return "track_not_merged"
    return None


def _survivor_id(recs: Sequence[PaperRecord]) -> str:
    """The OpenReview forum id's record if any member has one (record-schema skill), else the smallest id."""
    by_id = sorted(recs, key=lambda r: r.id)
    return next((r.id for r in by_id if r.forum_id is not None), by_id[0].id)


def dedup(records: Iterable[PaperRecord]) -> DedupResult:
    """Merge duplicates (dedup-rules skill); every input id survives or appears once as a merged id."""
    xs = sorted(records, key=lambda r: (r.id, r.content_hash, r.model_dump_json()))
    conflicts: set[Conflict] = set()
    for r in xs:
        again, _ = resolve(r.id, r.provenance)
        if again != r:
            raise ValueError(f"{r.id}: fields don't match its own claims; dedup would silently change it")

    # Step 1: identical id: the same forum id in the same venue and year, or the same proceedings id.
    step1 = _Clusters(len(xs))
    by_id: dict[str, list[int]] = defaultdict(list)
    by_forum: dict[str, dict[str, int]] = defaultdict(dict)  # forum id → id → first position
    for i, r in enumerate(xs):
        by_id[r.id].append(i)
        if r.forum_id is not None:
            by_forum[r.forum_id].setdefault(r.id, i)
    for idx in by_id.values():
        for i in idx[1:]:
            step1.union(idx[0], i)
    for ids in by_forum.values():  # one forum id in two venue-years: a conflict, never a merge
        first, *rest = sorted(ids.values())
        conflicts.update(_pair(xs[first], xs[i], "venue_year_not_merged", "forum_id") for i in rest)
    clusters = [[xs[i] for i in group] for group in step1.groups()]

    def resolved(members: Sequence[PaperRecord]) -> tuple[PaperRecord, list[Conflict]]:
        if len(members) == 1:
            return members[0], []
        return resolve(_survivor_id(members), [c for r in members for c in r.provenance])

    # Each cluster is judged by the record its claims resolve to, so a second pass sees the same thing.
    summary = [resolved(m)[0] for m in clusters]

    # Step 2: (venue, year, title key) across sources.
    buckets: dict[tuple[str, int, str], set[int]] = defaultdict(set)
    for ci, r in enumerate(summary):
        for key in {title_key(str(c.value)) for c in r.claims("title")} | {title_key(r.title)}:
            if key:  # a title of only punctuation or math never matches anything
                buckets[(r.venue, r.year, key)].add(ci)
    step2 = _Clusters(len(clusters))
    joined_by: dict[int, str] = {}  # cluster → the title key it merged on
    for (_, _, key), cis in sorted(buckets.items()):
        if len(cis) < 2:
            continue
        ordered = sorted(cis)
        reason = _mergeable([summary[ci] for ci in ordered])
        if reason is not None:
            conflicts.update(_pair(summary[ordered[0]], summary[ci], reason) for ci in ordered[1:])
            continue
        for ci in ordered:
            step2.union(ordered[0], ci)
            joined_by.setdefault(ci, key)

    out: list[PaperRecord] = []
    merges: list[Merge] = []
    for group in step2.groups():
        if len(group) > 1 and _mergeable([summary[ci] for ci in group]) is not None:
            # buckets chained clusters that must not share a record: keep every cluster on its own
            conflicts.update(
                _pair(summary[group[0]], summary[ci], "ambiguous_not_merged") for ci in group[1:]
            )
            parts = [[ci] for ci in group]
        else:
            parts = [group]
        for part in parts:
            members = [r for ci in part for r in clusters[ci]]
            merged, found = resolved(members)
            out.append(merged)
            conflicts.update(found)
            survivor_taken = False
            for ci in part:
                for r in clusters[ci]:
                    if r.id == merged.id and not survivor_taken:
                        survivor_taken = True
                        continue
                    if len(clusters[ci]) > 1 and r.forum_id is not None:
                        rule, key = "forum_id", r.forum_id
                    elif len(clusters[ci]) > 1:
                        rule, key = "native_id", r.native
                    else:
                        rule, key = "title_venue_year", joined_by[ci]
                    merges.append(
                        Merge(merged.id, r.id, rule, key, r.venue, r.year, "+".join(sorted(_sources(r))))
                    )
    return DedupResult(
        tuple(sorted(out, key=lambda r: r.id)), tuple(sorted(merges)), tuple(sorted(conflicts))
    )
