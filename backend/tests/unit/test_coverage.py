"""`coverage.breakdown`: the snapshot manifest's counts, reshaped, never recounted or folded (task-038)."""

from __future__ import annotations

import copy
from collections.abc import Callable
from typing import Any

import pytest
from openproceedings.coverage import breakdown
from openproceedings.ingest.snapshot import SnapshotError

MANIFEST: dict[str, Any] = {
    "snapshot_hash": "ab" * 32,
    "crawl_date": "2026-09-23",
    "crawl_window": {"from": "2026-09-20T10:00:00+00:00", "to": "2026-09-23T09:00:00+00:00"},
    "built_at": "2026-09-24T00:00:00+00:00",
    "sources": {"ris": [], "openreview": []},
    "record_count": 12,
    "counts": {
        "NeurIPS": {"2024": {"unknown": {"accepted": 1}, "main": {"unknown": 2, "accepted": 3}}},
        "ICLR": {
            "2025": {"workshop": {"accepted": 1}},
            "2024": {"datasets_benchmarks": {"rejected": 1}, "main": {"accepted": 4}},
        },
    },
    "abstract_missing": {"NeurIPS": {"2024": 2}, "ICLR": {"2025": 0, "2024": 1}},
    "unknown_track": {"NeurIPS": {"2024": 1}, "ICLR": {"2025": 0, "2024": 0}},
}


def test_the_breakdown_of_a_hand_counted_manifest() -> None:
    assert breakdown(MANIFEST, "2026-09-23-abababababab") == {
        "snapshot": {
            "name": "2026-09-23-abababababab",
            "snapshot_hash": "ab" * 32,
            "crawl_date": "2026-09-23",
            "crawl_from": "2026-09-20T10:00:00+00:00",
            "crawl_to": "2026-09-23T09:00:00+00:00",
            "built_at": "2026-09-24T00:00:00+00:00",
            "sources": ["openreview", "ris"],
        },
        "totals": {"records": 12, "abstract_missing": 3, "unknown_track": 1, "unknown_status": 2},
        "venue_years": [  # by venue name, then year; cells in vocabulary order, unknown last
            {
                "venue": "ICLR",
                "year": 2024,
                "records": 5,
                "abstract_missing": 1,
                "unknown_track": 0,
                "unknown_status": 0,
                "cells": [
                    {"track": "main", "status": "accepted", "count": 4},
                    {"track": "datasets_benchmarks", "status": "rejected", "count": 1},
                ],
            },
            {
                "venue": "ICLR",
                "year": 2025,
                "records": 1,
                "abstract_missing": 0,
                "unknown_track": 0,
                "unknown_status": 0,
                "cells": [{"track": "workshop", "status": "accepted", "count": 1}],
            },
            {
                "venue": "NeurIPS",
                "year": 2024,
                "records": 6,
                "abstract_missing": 2,
                "unknown_track": 1,
                "unknown_status": 2,
                "cells": [
                    {"track": "main", "status": "accepted", "count": 3},
                    {"track": "main", "status": "unknown", "count": 2},
                    {"track": "unknown", "status": "accepted", "count": 1},
                ],
            },
        ],
    }


def _set(path: tuple[str, ...], value: Any) -> Callable[[dict[str, Any]], None]:
    def edit(m: dict[str, Any]) -> None:
        for key in path[:-1]:
            m = m[key]
        m[path[-1]] = value

    return edit


def _drop(path: tuple[str, ...]) -> Callable[[dict[str, Any]], None]:
    def edit(m: dict[str, Any]) -> None:
        for key in path[:-1]:
            m = m[key]
        del m[path[-1]]

    return edit


@pytest.mark.parametrize(
    "edit",
    [
        _set(("record_count",), 13),  # counts don't add up
        _set(("unknown_track", "NeurIPS", "2024"), 0),  # the unknown track folded away
        _set(("counts", "NeurIPS", "2024", "plenary"), {"accepted": 1}),  # track outside the vocabulary
        _set(("counts", "ICLR", "2025", "workshop"), {"maybe": 1}),  # status outside the vocabulary
        _set(("counts", "ICML"), {"2024": {"main": {"accepted": 1}}}),  # a venue-year missing from the maps
        _set(("abstract_missing", "ICML"), {"2024": 0}),  # a venue-year only the maps name
        _set(("abstract_missing", "ICLR", "2025"), 2),  # more missing abstracts than records
        _set(("counts", "ICLR", "2025", "workshop", "accepted"), True),  # a bool is not a count
        _set(("counts", "ICLR", "2025", "workshop", "accepted"), 0),  # an empty cell
        _set(("counts", "ICLR", "2025", "workshop", "accepted"), -1),
        _set(("counts", "ICLR", "2025"), {}),  # a venue-year with no cells
        _set(("counts", "ICLR", "02025"), {}),  # a year that isn't a plain integer
        _set(("counts", "PMLR"), {}),  # a venue outside the vocabulary
        _drop(("crawl_window",)),
        _drop(("counts",)),
        _set(("crawl_date",), None),
        _set(("counts",), []),
    ],
)
def test_an_inconsistent_manifest_is_refused_never_guessed(edit: Callable[[dict[str, Any]], None]) -> None:
    manifest = copy.deepcopy(MANIFEST)
    edit(manifest)
    with pytest.raises(SnapshotError):
        breakdown(manifest, "s")
