"""`coverage.breakdown`: the snapshot manifest's counts, reshaped, never recounted or folded (task-038), with
the per-track cells, statuses indexed and official counts of TASK-082."""

from __future__ import annotations

import copy
from collections import Counter
from collections.abc import Callable
from datetime import date
from fractions import Fraction
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st
from openproceedings.coverage import TrackFacts, breakdown
from openproceedings.ingest.snapshot import SnapshotError
from openproceedings.official_counts import UNGATED_NOTES, OfficialCount, UngatedNote

EVERY = ["accepted", "rejected", "withdrawn", "desk_rejected", "unknown"]
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
    # format 2 (TASK-082)
    "abstract_missing_by_track": {
        "NeurIPS": {"2024": {"main": 2, "unknown": 0}},
        "ICLR": {"2025": {"workshop": 0}, "2024": {"main": 1, "datasets_benchmarks": 0}},
    },
    "sources_by_track": {
        "NeurIPS": {"2024": {"main": ["ris", "openreview_v2"], "unknown": ["ris"]}},
        "ICLR": {
            "2025": {"workshop": ["openreview_v2"]},
            "2024": {"main": ["ris"], "datasets_benchmarks": ["ris"]},
        },
    },
    "statuses_indexed": {"NeurIPS": {"2024": EVERY}, "ICLR": {"2025": EVERY, "2024": EVERY}},
    "crawl_windows": {"ris": {"from": "2026-09-20T10:00:00+00:00", "to": "2026-09-21T09:00:00+00:00"}},
}


def _track(track: str, records: int, accepted: int, missing: int, sources: list[str]) -> dict[str, Any]:
    """A track row with no official count: nothing to compare against, so not gated."""
    return {
        "track": track,
        "records": records,
        "indexed_accepted": accepted,
        "abstract_missing": missing,
        "abstract_withheld": 0,  # TASK-136: a manifest without takedown keys withheld nothing
        "abstract_official": records - missing,  # decision-049: no OpenAlex keys, so none is OpenAlex's
        "abstract_openalex": 0,
        "sources": sources,
        "official_accepted": None,
        "official_counts": None,
        "official_citation": None,
        "official_accessed": None,
        "delta": None,
        "delta_pct": None,
        "gated": False,
        "within_gate": None,
        "gate_note": None,  # TASK-222: no note says why it is not gated
        "gate_note_citation": None,
        "gate_note_accessed": None,
    }


def test_the_breakdown_of_a_hand_counted_manifest() -> None:
    assert breakdown(MANIFEST, "2026-09-23-abababababab", official={}) == {
        "snapshot": {
            "name": "2026-09-23-abababababab",
            "snapshot_hash": "ab" * 32,
            "crawl_date": "2026-09-23",
            # the manifest's text; the API model renders it in the one `…Z` form. `ris` is format 2's per-source
            # window (TASK-082)
            "crawl_dates": {
                "*": {"from": "2026-09-20T10:00:00+00:00", "to": "2026-09-23T09:00:00+00:00"},
                "ris": {"from": "2026-09-20T10:00:00+00:00", "to": "2026-09-21T09:00:00+00:00"},
            },
            "built_at": "2026-09-24T00:00:00+00:00",
            "sources": ["openreview", "ris"],
            # a crawl and a bootstrap source (TASK-091)
            "crawl_dates_kind": {"*": "mixed", "ris": "scholar_query_dates"},
            "identification_citable": True,
        },
        "totals": {
            "records": 12,
            "abstract_missing": 3,
            "abstract_withheld": 0,
            "abstract_official": 9,
            "abstract_openalex": 0,
            "unknown_track": 1,
            "unknown_status": 2,
        },
        "venue_years": [  # by venue name, then year; cells in vocabulary order, unknown last
            {
                "venue": "ICLR",
                "year": 2024,
                "records": 5,
                "abstract_missing": 1,
                "abstract_withheld": 0,
                "abstract_official": 4,
                "abstract_openalex": 0,
                "unknown_track": 0,
                "unknown_status": 0,
                "cells": [
                    {"track": "main", "status": "accepted", "count": 4},
                    {"track": "datasets_benchmarks", "status": "rejected", "count": 1},
                ],
                "statuses_indexed": EVERY,
                "tracks": [  # vocabulary order; accepted counted per track
                    _track("main", 4, 4, 1, ["ris"]),
                    _track("datasets_benchmarks", 1, 0, 0, ["ris"]),
                ],
            },
            {
                "venue": "ICLR",
                "year": 2025,
                "records": 1,
                "abstract_missing": 0,
                "abstract_withheld": 0,
                "abstract_official": 1,
                "abstract_openalex": 0,
                "unknown_track": 0,
                "unknown_status": 0,
                "cells": [{"track": "workshop", "status": "accepted", "count": 1}],
                "statuses_indexed": EVERY,
                "tracks": [_track("workshop", 1, 1, 0, ["openreview_v2"])],
            },
            {
                "venue": "NeurIPS",
                "year": 2024,
                "records": 6,
                "abstract_missing": 2,
                "abstract_withheld": 0,
                "abstract_official": 4,
                "abstract_openalex": 0,
                "unknown_track": 1,
                "unknown_status": 2,
                "cells": [
                    {"track": "main", "status": "accepted", "count": 3},
                    {"track": "main", "status": "unknown", "count": 2},
                    {"track": "unknown", "status": "accepted", "count": 1},
                ],
                "statuses_indexed": EVERY,
                "tracks": [
                    _track("main", 5, 3, 2, ["openreview_v2", "ris"]),  # sources sorted
                    _track("unknown", 1, 1, 0, ["ris"]),
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


WINDOW = {"from": "2026-09-20T10:00:00+00:00", "to": "2026-09-21T09:00:00+00:00"}


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
        # TASK-082: the per-track maps
        _set(("abstract_missing_by_track", "ICLR", "2024", "main"), 0),  # tracks don't sum to the venue-year
        _set(("abstract_missing_by_track", "ICLR", "2025", "workshop"), 2),  # more than the track's records
        _set(("abstract_missing_by_track", "ICLR", "2024", "main"), True),
        _drop(("abstract_missing_by_track", "NeurIPS", "2024", "unknown")),  # a track the map doesn't name
        _set(("abstract_missing_by_track", "ICLR", "2025", "main"), 0),  # a track only the map names
        _set(("sources_by_track", "ICLR", "2024", "main"), []),
        _set(("sources_by_track", "ICLR", "2024", "main"), "ris"),
        _set(("sources_by_track", "ICLR", "2024", "main"), [1]),
        _drop(("sources_by_track", "ICLR", "2025", "workshop")),
        _set(("sources_by_track", "ICML"), {"2024": {"main": ["pmlr"]}}),
        _set(("statuses_indexed", "ICLR", "2024"), ["accepted"]),  # holds a rejected cell it says it can't
        _set(("statuses_indexed", "ICLR", "2024"), ["rejected", "accepted"]),  # not vocabulary order
        _set(("statuses_indexed", "ICLR", "2024"), ["accepted", "rejected", "maybe"]),
        _set(("statuses_indexed", "ICLR", "2024"), []),
        _drop(("statuses_indexed", "ICLR", "2025")),
        _set(("statuses_indexed", "ICML"), {"2024": ["accepted"]}),
        _drop(("sources_by_track",)),  # a format-2 manifest holds all three
        _set(("crawl_windows", "*"), WINDOW),  # no source is named `*`
        _set(("sources", "*"), {"crawl_window": WINDOW}),  # in either map (TASK-122)
        _set(("crawl_windows", "ris"), {"from": "x"}),
        _set(("query_dates",), {"ris": "UTC"}),  # TASK-077: `utc` or `local` only
        _set(("query_dates",), {"openreview_v2": "utc"}),  # a crawl's dates are always UTC: not a key
        _set(("query_dates",), ["ris"]),
    ],
)
def test_an_inconsistent_manifest_is_refused_never_guessed(edit: Callable[[dict[str, Any]], None]) -> None:
    manifest = copy.deepcopy(MANIFEST)
    edit(manifest)
    with pytest.raises(SnapshotError):
        breakdown(manifest, "s")


def test_crawl_dates_take_a_search_records_shape_with_per_source_windows() -> None:
    """`/coverage`'s `snapshot.crawl_dates` is a record's `crawl_dates` (M3a review): `*` the corpus-wide
    window, plus a key per source with a window of its own (format 2's `crawl_windows`, or a source entry
    that carries one)."""
    from openproceedings import records
    from openproceedings.coverage import ALL_SOURCES, crawl_dates

    assert ALL_SOURCES == records.ALL_SOURCES
    window = {"from": "2026-09-21T00:00:00+00:00", "to": "2026-09-22T00:00:00+00:00"}
    manifest = {**MANIFEST, "sources": {"ris": [], "openreview": {"crawl_window": window}}}
    assert crawl_dates(manifest) == {"*": MANIFEST["crawl_window"], "openreview": window, "ris": WINDOW}
    with pytest.raises(SnapshotError):
        crawl_dates({**manifest, "crawl_window": {"from": "x"}})


def test_a_claim_window_narrower_than_the_fetch_window_is_served_and_wins() -> None:
    """TASK-122: `sources[].crawl_window` spans every response a crawl fetched (OpenReview's /groups calls come
    first); format 2's `crawl_windows` spans the claims on records. The live 2026-09-29 crawl's openreview_v2
    had 06:09:01Z against 06:10:05Z. They differ by design; the claim window is `crawl_dates`' (spec 04), and
    a source with no claim window keeps its fetch window."""
    from openproceedings.coverage import crawl_dates

    fetched = {"from": "2026-09-20T09:00:00+00:00", "to": "2026-09-21T12:00:00+00:00"}  # wider than WINDOW
    only_fetched = {"from": "2026-09-22T00:00:00+00:00", "to": "2026-09-22T01:00:00+00:00"}
    manifest = {
        **MANIFEST,
        "sources": {"ris": {"crawl_window": fetched}, "pmlr": {"crawl_window": only_fetched}},
    }
    assert crawl_dates(manifest) == {"*": MANIFEST["crawl_window"], "ris": WINDOW, "pmlr": only_fetched}
    breakdown(manifest, "s")  # the API's load: no refusal


def _tracks(
    official: dict[tuple[str, int, str], OfficialCount],
) -> dict[tuple[str, int, str], dict[str, Any]]:
    data = breakdown(MANIFEST, "s", official=official)
    return {(vy["venue"], vy["year"], t["track"]): t for vy in data["venue_years"] for t in vy["tracks"]}


def _official(accepted: int, citation: str = "https://example.org/stats") -> OfficialCount:
    return OfficialCount(accepted, "accepted papers", citation, date(2026, 9, 1))


def test_a_cell_with_an_official_count_is_compared_and_gated_if_main_or_db() -> None:
    """Spec 07 §C: delta and delta_pct against the official count, with its citation, and the ±1% verdict on
    main-track and D&B cells only; a cell with no official count is reported, not gated."""
    rows = _tracks(
        {
            ("ICLR", 2024, "main"): _official(4, "https://example.org/a"),
            ("NeurIPS", 2024, "main"): _official(2),
            ("ICLR", 2025, "workshop"): _official(2),
        }
    )
    main = rows[("ICLR", 2024, "main")]
    assert (main["official_accepted"], main["delta"], main["delta_pct"]) == (4, 0, 0.0)
    assert (main["gated"], main["within_gate"], main["official_citation"]) == (
        True,
        True,
        "https://example.org/a",
    )
    assert (main["official_counts"], main["official_accessed"]) == ("accepted papers", "2026-09-01")
    missed = rows[
        ("NeurIPS", 2024, "main")
    ]  # 3 indexed accepted against 2 (the unknown-status 2 don't count)
    assert (missed["delta"], missed["delta_pct"], missed["gated"], missed["within_gate"]) == (
        1,
        50.0,
        True,
        False,
    )
    workshop = rows[("ICLR", 2025, "workshop")]  # compared, never gated
    assert (workshop["delta"], workshop["delta_pct"], workshop["gated"], workshop["within_gate"]) == (
        -1,
        -50.0,
        False,
        None,
    )
    assert rows[("ICLR", 2024, "datasets_benchmarks")]["gated"] is False  # no official count: not gated


@pytest.mark.parametrize(
    ("official", "within"),
    [(400, True), (397, True), (396, False), (404, True), (405, False)],
)
def test_the_gate_is_one_percent_of_the_official_count(official: int, within: bool) -> None:
    """400 indexed: against 396 the delta 4 is over 3.96 (1%), against 397 the delta 3 is under 3.97; against
    404 the delta 4 is under 4.04, against 405 the delta 5 is over 4.05. Exact at both edges."""
    from openproceedings.official_counts import within_gate

    assert within_gate(400, official) is within


@given(st.integers(min_value=0, max_value=10**6), st.integers(min_value=1, max_value=10**6))
def test_the_gate_is_the_spec_definition_in_exact_arithmetic(indexed: int, official: int) -> None:
    """Spec 07 §C: |delta_pct| ≤ 1%, i.e. |indexed − official| / official ≤ 1/100, never rounded."""
    from openproceedings.official_counts import within_gate

    assert within_gate(indexed, official) is (Fraction(abs(indexed - official), official) <= Fraction(1, 100))


def test_a_format_1_manifest_takes_its_per_track_facts_from_the_records() -> None:
    """A snapshot built before TASK-082 has none of the per-track keys: the load passes the facts its one
    pass over the verified records counted, and the statuses indexed come from the source table."""
    dropped = ("abstract_missing_by_track", "sources_by_track", "statuses_indexed", "crawl_windows")
    old = {k: v for k, v in MANIFEST.items() if k not in dropped}
    with pytest.raises(SnapshotError):
        breakdown(old, "s")
    facts = TrackFacts(
        missing={
            ("NeurIPS", 2024, "main"): 2,
            ("NeurIPS", 2024, "unknown"): 0,
            ("ICLR", 2025, "workshop"): 0,
            ("ICLR", 2024, "main"): 1,
            ("ICLR", 2024, "datasets_benchmarks"): 0,
        },
        sources={
            ("NeurIPS", 2024, "main"): {"ris"},
            ("NeurIPS", 2024, "unknown"): {"ris"},
            ("ICLR", 2025, "workshop"): {"neurips_proceedings"},
            ("ICLR", 2024, "main"): {"ris"},
            ("ICLR", 2024, "datasets_benchmarks"): {"ris"},
        },
    )
    data = breakdown(old, "s", facts)
    assert data["snapshot"]["crawl_dates"] == {
        "*": MANIFEST["crawl_window"]
    }  # no per-source window in format 1
    held = {(vy["venue"], vy["year"]): vy["statuses_indexed"] for vy in data["venue_years"]}
    assert held == {("ICLR", 2024): EVERY, ("ICLR", 2025): ["accepted"], ("NeurIPS", 2024): EVERY}
    new = breakdown(MANIFEST, "s", facts)  # format 2: the manifest's own, never the facts
    assert new["venue_years"] == breakdown(MANIFEST, "s")["venue_years"]


def _with_openalex() -> dict[str, Any]:
    """The hand-counted manifest where ICLR 2024 main (4 records, 1 missing) has one abstract from OpenAlex."""
    m = copy.deepcopy(MANIFEST)
    m["abstract_openalex"] = {"ICLR": {"2024": 1}}
    m["abstract_openalex_by_track"] = {"ICLR": {"2024": {"main": 1}}}
    return m


def test_official_openalex_missing_and_withheld_add_up_to_the_records_everywhere() -> None:
    data = breakdown(_with_openalex(), "s", official={})
    [iclr24] = [vy for vy in data["venue_years"] if (vy["venue"], vy["year"]) == ("ICLR", 2024)]
    [main] = [t for t in iclr24["tracks"] if t["track"] == "main"]
    for row in (main, iclr24, data["totals"]):
        assert row["abstract_openalex"] == 1
        assert (
            row["abstract_official"]
            + row["abstract_openalex"]
            + row["abstract_missing"]
            + row["abstract_withheld"]
            == row["records"]
        )
    assert (main["abstract_official"], iclr24["abstract_official"], data["totals"]["abstract_official"]) == (
        2,
        3,
        8,
    )


@pytest.mark.parametrize(
    "edit",
    [
        _drop(("abstract_openalex_by_track",)),  # one key without the other
        _set(("abstract_openalex", "ICLR", "2024"), 2),  # the venue-year disagrees with its tracks
        _set(
            ("abstract_openalex_by_track", "ICLR", "2024", "main"), 4
        ),  # more than the records minus missing
        _set(("abstract_openalex", "ICML"), {"2024": 1}),  # where it holds no records
        _set(("abstract_openalex", "ICLR", "2024"), True),
    ],
)
def test_an_inconsistent_openalex_count_is_refused(edit: Callable[[dict[str, Any]], None]) -> None:
    manifest = _with_openalex()
    edit(manifest)
    with pytest.raises(SnapshotError):
        breakdown(manifest, "s")


class _Records:
    """The `RecordFile` facts `api.coverage.compute` reads, derived from a manifest that agrees with its records."""

    def __init__(self, manifest: dict[str, Any], held: dict[str, Any] | None = None) -> None:
        from collections import Counter
        from pathlib import Path

        data = breakdown(manifest, "s", official={})
        self.manifest = manifest
        self.path = Path("/x/s/records.jsonl")
        self.withheld: frozenset[str] = frozenset()
        self._held = held or {}
        vys = data["venue_years"]
        self.cells = Counter(
            {(v["venue"], v["year"], c["track"], c["status"]): c["count"] for v in vys for c in v["cells"]}
        )
        self.abstract_missing = Counter(
            {(v["venue"], v["year"]): v["abstract_missing"] for v in vys if v["abstract_missing"]}
        )
        tracks = {(v["venue"], v["year"], t["track"]): t for v in vys for t in v["tracks"]}
        self.track_missing = Counter({k: t["abstract_missing"] for k, t in tracks.items()})
        self.track_sources = {k: set(t["sources"]) for k, t in tracks.items()}
        self.abstract_withheld: Counter[tuple[str, int]] = Counter()
        self.track_withheld: Counter[tuple[str, int, str]] = Counter()
        self.abstract_openalex = Counter(
            {(v["venue"], v["year"]): v["abstract_openalex"] for v in vys if v["abstract_openalex"]}
        )
        self.track_openalex = Counter(
            {k: t["abstract_openalex"] for k, t in tracks.items() if t["abstract_openalex"]}
        )
        self._n = sum(self.cells.values())

    def __len__(self) -> int:
        return self._n

    def get(self, rid: str) -> Any:
        return self._held.get(rid)


class _Engine:
    index_version = "abc123def456"
    tokenizer_version = "2"

    def __init__(self, n: int) -> None:
        self.ids = range(n)


def test_a_per_track_openalex_count_that_disagrees_with_the_records_fails_the_load() -> None:
    from openproceedings.api.coverage import compute

    records = _Records(_with_openalex())
    compute(_Engine(len(records)), records)  # type: ignore[arg-type]  # agrees: no error
    records.track_openalex = Counter()  # the venue-year's count still agrees; only the track's does not
    with pytest.raises(SnapshotError) as e:
        compute(_Engine(len(records)), records)  # type: ignore[arg-type]
    assert e.value.reason == "abstract_openalex_mismatch"


def test_listing_one_openalex_and_one_official_id_moves_each_from_its_own_count() -> None:
    from types import SimpleNamespace

    from openproceedings.api.coverage import compute

    held = {
        "op:iclr:2024:a": SimpleNamespace(
            venue="ICLR", year=2024, track="main", abstract="x", abstract_kind="openalex"
        ),
        "op:iclr:2024:b": SimpleNamespace(
            venue="ICLR", year=2024, track="main", abstract="y", abstract_kind="official"
        ),
    }
    manifest = _with_openalex()
    manifest["abstract_openalex"] = {"ICLR": {"2024": 2}}
    manifest["abstract_openalex_by_track"] = {"ICLR": {"2024": {"main": 2}}}
    records = _Records(manifest, held)
    out = compute(_Engine(len(records)), records, frozenset(held))  # type: ignore[arg-type]
    [vy] = [v for v in out.venue_years if (v.venue, v.year) == ("ICLR", 2024)]
    [main] = [t for t in vy.tracks if t.track == "main"]
    for row in (main, vy, out.totals):
        assert (row.abstract_withheld, row.abstract_openalex) == (2, 1)
        assert (
            row.abstract_official + row.abstract_openalex + row.abstract_missing + row.abstract_withheld
            == row.records
        )
    assert (main.abstract_official, main.abstract_missing) == (0, 1)


def test_an_ungated_cell_carries_its_note_and_a_cell_without_one_nulls() -> None:
    """TASK-222: an ungated cell with a note (`official_counts.UNGATED_NOTES`) is served with the note and its
    citation; every other cell with nulls. A note never rides on a gated cell."""
    note = UngatedNote("the list counts a different set", "https://example.org/list", date(2026, 10, 10))
    data = breakdown(
        MANIFEST,
        "s",
        official={("NeurIPS", 2024, "main"): _official(3)},
        notes={("ICLR", 2024, "main"): note, ("NeurIPS", 2024, "main"): note},
    )
    rows = {(vy["venue"], vy["year"], t["track"]): t for vy in data["venue_years"] for t in vy["tracks"]}
    noted = rows[("ICLR", 2024, "main")]
    assert (noted["gated"], noted["gate_note"], noted["gate_note_citation"]) == (
        False,
        "the list counts a different set",
        "https://example.org/list",
    )
    assert noted["gate_note_accessed"] == "2026-10-10"  # shown beside the citation, as an official row's is
    assert rows[("NeurIPS", 2024, "main")]["gated"] is True
    assert rows[("NeurIPS", 2024, "main")]["gate_note"] is None
    assert all(
        (t["gate_note"], t["gate_note_citation"], t["gate_note_accessed"]) == (None, None, None)
        for k, t in rows.items()
        if k != ("ICLR", 2024, "main")
    )


def test_the_iaseai_2026_main_cell_carries_its_note_by_default() -> None:
    """The served notes are `UNGATED_NOTES`: IASEAI 2026 main, 57 archival of 92 accepted, says why it is not gated."""
    manifest = copy.deepcopy(MANIFEST)  # NeurIPS 2024 renamed IASEAI 2026 in every per-venue map
    for value in manifest.values():
        if isinstance(value, dict) and "NeurIPS" in value:
            value["IASEAI"] = {"2026": value.pop("NeurIPS")["2024"]}
    rows = {
        (vy["venue"], vy["year"], t["track"]): t
        for vy in breakdown(manifest, "s", official={})["venue_years"]
        for t in vy["tracks"]
    }
    expected = UNGATED_NOTES[("IASEAI", 2026, "main")]
    assert rows[("IASEAI", 2026, "main")]["gate_note"] == expected.note
    assert rows[("IASEAI", 2026, "main")]["gate_note_citation"] == expected.citation
    assert "57" in expected.note and "92" in expected.note
