"""Corpus coverage (spec 04 `GET /coverage`, spec 07 §C; coverage-reporting skill): what a snapshot holds per
venue × year × track × status, how many of its abstracts are missing, and when it was crawled.

The numbers are the snapshot manifest's. `ingest/snapshot.py::render` counts them once, from the records,
when the snapshot is built (`counts`, `abstract_missing`, `unknown_track`), and the corpus report
(`docs/results/2026-09-27-corpus.md`) was read from the same keys. `breakdown` only reshapes them into a
stable order and checks that they agree with one another and with `record_count`; it never recounts,
estimates or folds. A track or status outside the vocabulary, a venue-year missing from one of the three
maps, or a sum that doesn't add up is a `SnapshotError`, never a best guess.

Per venue-year also (TASK-082): `statuses_indexed` (the statuses its sources can contain, from the manifest,
`ingest/statuses.py`) and `tracks`, the spec 07 §C cells (venue × year × track): records, indexed accepted,
missing abstracts and claim sources from the manifest's format-2 keys, beside the official accepted count
(`official_counts.py`) with its delta and ±1% gate. A format-1 manifest lacks those keys; the load passes
the records' own per-track facts (`TrackFacts`) instead, and compares them with a format-2 manifest's.

Withheld abstracts (TASK-136, decision-022): a snapshot built with a takedown list counts its withheld records
in `abstract_withheld` (per venue-year) and `abstract_withheld_by_track`; a manifest without them withheld
nothing. Every venue-year, track and the totals carry `abstract_withheld`, 0 included, apart from
`abstract_missing` (a withheld record is not counted missing). The API adds the ids listed after the snapshot
was built (`api/coverage.py::compute`), so `/coverage` counts what it withholds when it serves.

Order (stable JSON): venue-years by venue name, then year; within one, cells by the vocabulary order of
track, then of status (`vocab.py`: `main` first, `unknown` last); tracks in vocabulary order. `unknown` is never merged into another
bucket: it is a cell of its own, and every venue-year also carries `unknown_track` and `unknown_status`,
0 included.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from typing import Any

from openproceedings.ingest.snapshot import SnapshotError, utc_query_sources
from openproceedings.ingest.statuses import statuses_indexed
from openproceedings.official_counts import GATED_TRACKS, OFFICIAL_ACCEPTED, OfficialTable, within_gate
from openproceedings.vocab import STATUSES, TRACKS, VENUES, bootstrap_only, crawl_dates_kind

ALL_SOURCES = "*"  # records.ALL_SOURCES: the corpus-wide window's key (a test pins them equal)

TRACK_ORDER = {t: i for i, t in enumerate(TRACKS)}
STATUS_ORDER = {s: i for i, s in enumerate(STATUSES)}


def _count(value: object) -> int:
    if type(value) is not int or value < 0:  # bool is not a count
        raise SnapshotError("the snapshot manifest holds a count that is not a non-negative integer")
    return value


def _map(value: object, what: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SnapshotError(f"the snapshot manifest's {what} is not a map")
    return value


def _year(key: str) -> int:
    if not key.isascii() or not key.isdigit() or str(int(key)) != key:
        raise SnapshotError("the snapshot manifest holds a year that is not a plain integer")
    return int(key)


def _window(value: object) -> dict[str, str]:
    window = _map(value, "crawl_window")
    if set(window) != {"from", "to"} or not all(isinstance(v, str) and v for v in window.values()):
        raise SnapshotError("a crawl window in the snapshot manifest is not {from, to}")
    return {"from": window["from"], "to": window["to"]}


def crawl_dates(manifest: Mapping[str, Any]) -> dict[str, dict[str, str]]:
    """The manifest's crawl windows in a search record's `crawl_dates` shape: `*` is the corpus-wide
    `crawl_window`, and each source with a window of its own adds its key. A source's window is its claim window,
    format 2's `crawl_windows` (the first and last `fetched_at` of the claims on records, TASK-082; spec 04),
    else its `sources` entry's `crawl_window` (every response its crawls fetched, format 1). The two differ by
    design (an OpenReview crawl fetches /groups before any note), so the claim window wins (TASK-122)."""
    claims = _map(manifest.get("crawl_windows", {}), "crawl_windows")
    if ALL_SOURCES in claims or ALL_SOURCES in _map(manifest["sources"], "sources"):
        raise SnapshotError("the snapshot manifest names a source `*`")
    dates = {ALL_SOURCES: _window(manifest["crawl_window"])}
    for source, entry in sorted(_map(manifest["sources"], "sources").items()):
        if isinstance(entry, Mapping) and "crawl_window" in entry:
            dates[source] = _window(entry["crawl_window"])
    dates.update({source: _window(window) for source, window in sorted(claims.items())})
    return dates


type TrackKey = tuple[str, int, str]  # (venue, year, track)


@dataclass(frozen=True, slots=True)
class TrackFacts:
    """Per (venue, year, track): its missing abstracts (0 included) and the claim sources of its records, as
    the load's one pass over the verified records counted them (`RecordFile`). `breakdown` reads them only
    for a format-1 manifest, which predates the per-track keys; for format 2 the load checks they agree."""

    missing: Mapping[TrackKey, int]
    sources: Mapping[TrackKey, Collection[str]]


PER_TRACK_KEYS = ("abstract_missing_by_track", "sources_by_track", "statuses_indexed")


def _per_track(
    manifest: Mapping[str, Any], facts: TrackFacts | None
) -> tuple[dict[TrackKey, int], dict[TrackKey, list[str]], dict[tuple[str, int], list[str]] | None]:
    """Missing abstracts and claim sources per (venue, year, track), and (format 2) the statuses indexed per
    venue-year: from the manifest's format-2 keys, else (format 1, none of them) from `facts`."""
    if not any(k in manifest for k in PER_TRACK_KEYS):
        if facts is None:
            raise SnapshotError(
                "the snapshot manifest has no per-track counts (format 1) and none were given"
            )
        return dict(facts.missing), {k: sorted(v) for k, v in facts.sources.items()}, None
    missing: dict[TrackKey, int] = {}
    sources: dict[TrackKey, list[str]] = {}
    statuses: dict[tuple[str, int], list[str]] = {}
    try:
        for venue, years in _map(manifest["abstract_missing_by_track"], "abstract_missing_by_track").items():
            for year, tracks in _map(years, "abstract_missing_by_track per venue").items():
                for track, n in _map(tracks, "abstract_missing_by_track per venue-year").items():
                    missing[(venue, _year(year), track)] = _count(n)
        for venue, years in _map(manifest["sources_by_track"], "sources_by_track").items():
            for year, tracks in _map(years, "sources_by_track per venue").items():
                for track, named in _map(tracks, "sources_by_track per venue-year").items():
                    if not isinstance(named, list) or not named or not all(isinstance(x, str) for x in named):
                        raise SnapshotError(
                            "the snapshot manifest names a track's sources other than as a list"
                        )
                    sources[(venue, _year(year), track)] = sorted(named)
        for venue, years in _map(manifest["statuses_indexed"], "statuses_indexed").items():
            for year, held in _map(years, "statuses_indexed per venue").items():
                if not isinstance(held, list) or not held or held != [s for s in STATUSES if s in held]:
                    raise SnapshotError(
                        "the snapshot manifest's statuses_indexed are not vocabulary statuses"
                    )
                statuses[(venue, _year(year))] = held
    except KeyError as e:
        raise SnapshotError(f"the snapshot manifest has no {e.args[0]!r}") from None
    return missing, sources, statuses


def _withheld(manifest: Mapping[str, Any]) -> tuple[dict[tuple[str, int], int], dict[TrackKey, int]]:
    """The manifest's withheld abstracts per venue-year and per track (TASK-136); none when it has no such
    keys. A manifest that has one of the two keys has both."""
    if ("abstract_withheld" in manifest) != ("abstract_withheld_by_track" in manifest):
        raise SnapshotError(
            "the snapshot manifest counts withheld abstracts per venue-year or per track, not both"
        )
    per_year: dict[tuple[str, int], int] = {}
    per_track: dict[TrackKey, int] = {}
    for venue, years in _map(manifest.get("abstract_withheld", {}), "abstract_withheld").items():
        for year, n in _map(years, "abstract_withheld per venue").items():
            per_year[(venue, _year(year))] = _count(n)
    for venue, years in _map(
        manifest.get("abstract_withheld_by_track", {}), "abstract_withheld_by_track"
    ).items():
        for year, tracks in _map(years, "abstract_withheld_by_track per venue").items():
            for track, n in _map(tracks, "abstract_withheld_by_track per venue-year").items():
                per_track[(venue, _year(year), track)] = _count(n)
    return per_year, per_track


def _track_row(
    key: TrackKey,
    cells: list[dict[str, Any]],
    missing: int,
    sources: list[str],
    official: OfficialTable,
    withheld: int = 0,
) -> dict[str, Any]:
    """One spec 07 §C cell (venue × year × track): its indexed counts beside the official accepted count."""
    mine = [c for c in cells if c["track"] == key[2]]
    accepted = sum(c["count"] for c in mine if c["status"] == "accepted")
    row = official.get(key)
    gated = row is not None and key[2] in GATED_TRACKS
    return {
        "track": key[2],
        "records": sum(c["count"] for c in mine),
        "indexed_accepted": accepted,
        "abstract_missing": missing,
        "abstract_withheld": withheld,
        "sources": sources,
        "official_accepted": row.accepted if row else None,
        "official_counts": row.counts if row else None,
        "official_citation": row.citation if row else None,
        "official_accessed": row.accessed.isoformat() if row else None,
        "delta": accepted - row.accepted if row else None,
        "delta_pct": 100 * (accepted - row.accepted) / row.accepted if row else None,
        "gated": gated,
        "within_gate": within_gate(accepted, row.accepted) if row and gated else None,
    }


def breakdown(
    manifest: Mapping[str, Any],
    name: str,
    facts: TrackFacts | None = None,
    official: OfficialTable = OFFICIAL_ACCEPTED,
) -> dict[str, Any]:
    """The coverage of snapshot `name` (its directory) from its manifest: `snapshot` (name, hash, crawl
    date and windows, build time, sources), `totals` and `venue_years` (see the module docstring), each
    venue-year with its statuses indexed and its `tracks` (spec 07 §C cells, beside `official`'s counts).
    `facts` stands in for the per-track keys of a format-1 manifest (and is otherwise unused)."""
    missing_by_track, sources_by_track, statuses = _per_track(manifest, facts)
    withheld_by_year, withheld_by_track = _withheld(manifest)
    try:
        counts = _map(manifest["counts"], "counts")
        missing = _map(manifest["abstract_missing"], "abstract_missing")
        unknown = _map(manifest["unknown_track"], "unknown_track")
        sources = sorted(_map(manifest["sources"], "sources"))
        windows = crawl_dates(manifest)
        snapshot = {
            "name": name,
            "snapshot_hash": manifest["snapshot_hash"],
            "crawl_date": manifest["crawl_date"],
            "crawl_dates": windows,
            "built_at": manifest["built_at"],
            "sources": sources,
            # derived exactly as a search record's (TASK-091; `records.snapshot_facts`)
            "crawl_dates_kind": crawl_dates_kind(windows, sources, ALL_SOURCES, utc_query_sources(manifest)),
            "identification_citable": not bootstrap_only(sources),
        }
        record_count = _count(manifest["record_count"])
    except KeyError as e:
        raise SnapshotError(f"the snapshot manifest has no {e.args[0]!r}") from None
    derived = ("sources", "crawl_dates", "crawl_dates_kind", "identification_citable")
    if not all(isinstance(v, str) and v for k, v in snapshot.items() if k not in derived):
        raise SnapshotError("the snapshot manifest's hash, dates or name are not strings")

    venue_years: list[dict[str, Any]] = []
    for venue in sorted(counts):
        if venue not in VENUES.values():
            raise SnapshotError("the snapshot manifest holds a venue outside the vocabulary")
        years = _map(counts[venue], "counts per venue")
        for year in sorted(years, key=_year):
            cells = []
            for track, by_status in _map(years[year], "counts per venue-year").items():
                for status, n in _map(by_status, "counts per track").items():
                    if track not in TRACK_ORDER or status not in STATUS_ORDER:
                        raise SnapshotError(
                            "the snapshot manifest holds a track or status outside the vocabulary"
                        )
                    if _count(n) == 0:
                        raise SnapshotError("the snapshot manifest holds an empty cell")
                    cells.append({"track": track, "status": status, "count": n})
            cells.sort(key=lambda c: (TRACK_ORDER[c["track"]], STATUS_ORDER[c["status"]]))
            records = sum(c["count"] for c in cells)
            unknown_track = sum(c["count"] for c in cells if c["track"] == "unknown")
            try:
                abstract_missing = _count(_map(missing[venue], "abstract_missing per venue")[year])
                listed_unknown = _count(_map(unknown[venue], "unknown_track per venue")[year])
            except KeyError:
                raise SnapshotError(
                    "a venue-year is in the manifest's counts but not in all its maps"
                ) from None
            if not cells or abstract_missing > records or listed_unknown != unknown_track:
                raise SnapshotError("the snapshot manifest's maps disagree about a venue-year")
            y = _year(year)
            keys = [(venue, y, t) for t in TRACKS if any(c["track"] == t for c in cells)]
            if any(k not in missing_by_track or k not in sources_by_track for k in keys):
                raise SnapshotError("a track is in the manifest's counts but not in its per-track maps")
            rows = [
                _track_row(
                    k, cells, missing_by_track[k], sources_by_track[k], official, withheld_by_track.get(k, 0)
                )
                for k in keys
            ]
            if sum(r["abstract_missing"] for r in rows) != abstract_missing or any(
                r["abstract_missing"] + r["abstract_withheld"] > r["records"] for r in rows
            ):
                raise SnapshotError(
                    "the manifest's missing abstracts per track disagree with its venue-year's"
                )
            abstract_withheld = withheld_by_year.get((venue, y), 0)
            if sum(r["abstract_withheld"] for r in rows) != abstract_withheld:
                raise SnapshotError(
                    "the manifest's withheld abstracts per track disagree with its venue-year's"
                )
            held = (
                statuses_indexed(
                    {s for k in keys for s in sources_by_track[k]}, venue, y, {c["status"] for c in cells}
                )
                if statuses is None
                else statuses.get((venue, y))
            )
            if held is None or not {c["status"] for c in cells} <= set(held):
                raise SnapshotError("a venue-year holds a status its statuses_indexed says it can't")
            venue_years.append(
                {
                    "venue": venue,
                    "year": _year(year),
                    "records": records,
                    "abstract_missing": abstract_missing,
                    "abstract_withheld": abstract_withheld,
                    "unknown_track": unknown_track,
                    "unknown_status": sum(c["count"] for c in cells if c["status"] == "unknown"),
                    "cells": cells,
                    "statuses_indexed": held,
                    "tracks": rows,
                }
            )

    listed = {(v, y) for v in counts for y in _map(counts[v], "counts per venue")}
    for other in (missing, unknown):  # a venue-year the other maps name but `counts` doesn't
        if {(v, y) for v in other for y in _map(other[v], "a per-venue map")} != listed:
            raise SnapshotError("the snapshot manifest's maps name different venue-years")
    in_cells = {(vy["venue"], vy["year"], t["track"]) for vy in venue_years for t in vy["tracks"]}
    if (
        set(missing_by_track) != in_cells
        or set(sources_by_track) != in_cells
        or (statuses is not None and set(statuses) != {(v, y) for v, y, _t in in_cells})
    ):  # a track or venue-year only the per-track maps name
        raise SnapshotError("the snapshot manifest's per-track maps name other tracks than its counts")
    if not set(withheld_by_track) <= in_cells or not {(v, y) for v, y in withheld_by_year} <= {
        (v, y) for v, y, _t in in_cells
    }:
        raise SnapshotError("the snapshot manifest counts withheld abstracts where it holds no records")
    totals = {
        key: sum(vy[key] for vy in venue_years)
        for key in ("records", "abstract_missing", "abstract_withheld", "unknown_track", "unknown_status")
    }
    if totals["records"] != record_count:
        raise SnapshotError("the snapshot manifest's counts don't add up to its record_count")
    return {"snapshot": snapshot, "totals": totals, "venue_years": venue_years}
