"""Corpus coverage (spec 04 `GET /coverage`, spec 07 §C; coverage-reporting skill): what a snapshot holds per
venue × year × track × status, how many of its abstracts are missing, and when it was crawled.

The numbers are the snapshot manifest's. `ingest/snapshot.py::render` counts them once, from the records,
when the snapshot is built (`counts`, `abstract_missing`, `unknown_track`), and the corpus report
(`docs/results/2026-09-27-corpus.md`) was read from the same keys. `breakdown` only reshapes them into a
stable order and checks that they agree with one another and with `record_count`; it never recounts,
estimates or folds. A track or status outside the vocabulary, a venue-year missing from one of the three
maps, or a sum that doesn't add up is a `SnapshotError`, never a best guess.

Order (stable JSON): venue-years by venue name, then year; within one, cells by the vocabulary order of
track, then of status (`vocab.py`: `main` first, `unknown` last). `unknown` is never merged into another
bucket: it is a cell of its own, and every venue-year also carries `unknown_track` and `unknown_status`,
0 included.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from openproceedings.ingest.snapshot import SnapshotError
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
    `crawl_window`, and a source entry that carries its own `crawl_window` (the M4 crawlers) adds its key."""
    dates = {ALL_SOURCES: _window(manifest["crawl_window"])}
    for source, entry in sorted(_map(manifest["sources"], "sources").items()):
        if isinstance(entry, Mapping) and "crawl_window" in entry and source != ALL_SOURCES:
            dates[source] = _window(entry["crawl_window"])
    return dates


def breakdown(manifest: Mapping[str, Any], name: str) -> dict[str, Any]:
    """The coverage of snapshot `name` (its directory) from its manifest: `snapshot` (name, hash, crawl
    date and windows, build time, sources), `totals` and `venue_years` (see the module docstring)."""
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
            "crawl_dates_kind": crawl_dates_kind(windows, sources, ALL_SOURCES),
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
            venue_years.append(
                {
                    "venue": venue,
                    "year": _year(year),
                    "records": records,
                    "abstract_missing": abstract_missing,
                    "unknown_track": unknown_track,
                    "unknown_status": sum(c["count"] for c in cells if c["status"] == "unknown"),
                    "cells": cells,
                }
            )

    listed = {(v, y) for v in counts for y in _map(counts[v], "counts per venue")}
    for other in (missing, unknown):  # a venue-year the other maps name but `counts` doesn't
        if {(v, y) for v in other for y in _map(other[v], "a per-venue map")} != listed:
            raise SnapshotError("the snapshot manifest's maps name different venue-years")
    totals = {
        key: sum(vy[key] for vy in venue_years)
        for key in ("records", "abstract_missing", "unknown_track", "unknown_status")
    }
    if totals["records"] != record_count:
        raise SnapshotError("the snapshot manifest's counts don't add up to its record_count")
    return {"snapshot": snapshot, "totals": totals, "venue_years": venue_years}
