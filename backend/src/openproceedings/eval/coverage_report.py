"""The coverage report (spec 07 §C, coverage-reporting skill; TASK-054): `op eval coverage` writes
`docs/results/<YYYY-MM-DD>-coverage.md` from exactly what `GET /coverage` serves for the index
(`api.coverage.compute`), so the report and the `/coverage` page never disagree.

What it adds to that data, and nothing else:
- **Gaps.** A gated official cell (main or D&B with an official count) that the snapshot holds no record for is
  a row with 0 indexed and ✗, never a silent zero (spec 07 §C: a venue-year with no source is a reported gap).
- **The M4 gate verdict.** Every gated cell within ±1% (`official_counts.within_gate`), gaps included.
- **Cause notes.** Every failing cell gets its cause from `causes` (a person's classification: source
  definition, classification, dedup or crawl gap), or `**unclassified**`: never adjust an official number to fit.
- **Listings.** Each crawled listing or venue-year whose crawl skipped entries or whose count disagreed with
  its page, from the snapshot manifest's `sources`: a passing `count_ok` can hide a loss at the id step
  (TASK-118).
"""

from __future__ import annotations

import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from openproceedings.official_counts import GATED_TRACKS, OFFICIAL_ACCEPTED, OfficialTable, within_gate
from openproceedings.vocab import TRACKS

type CellKey = tuple[str, int, str]
TRACK_ORDER = {t: i for i, t in enumerate(TRACKS)}
MINUS = "−"  # U+2212, as the other results reports write a negative delta


@dataclass(frozen=True)
class Meta:
    """What the numbers depend on, for the header."""

    date: date
    index_version: str
    sources_sha256: str  # of docs/results/coverage-sources.md, the official counts' cited table
    command: str


@dataclass(frozen=True)
class Verdict:
    gated: int  # gated official cells, gaps included
    passing: int
    failing: list[tuple[CellKey, str]]  # (cell, "gap" | "outside")
    gaps: int

    @property
    def passed(self) -> bool:
        return not self.failing


def _cells(cov: Mapping[str, Any]) -> dict[CellKey, dict[str, Any]]:
    return {(vy["venue"], vy["year"], t["track"]): t for vy in cov["venue_years"] for t in vy["tracks"]}


def gate(cov: Mapping[str, Any], official: OfficialTable = OFFICIAL_ACCEPTED) -> Verdict:
    """The M4 gate over every gated official cell: the snapshot's own verdict per cell, and a gap for a cell it
    holds no record for."""
    cells = _cells(cov)
    failing: list[tuple[CellKey, str]] = []
    gated = passing = gaps = 0
    for key in sorted(k for k in official if k[2] in GATED_TRACKS):
        gated += 1
        cell = cells.get(key)
        if cell is None:
            gaps += 1
            failing.append((key, "gap"))
        elif within_gate(cell["indexed_accepted"], official[key].accepted):
            passing += 1
        else:
            failing.append((key, "outside"))
    return Verdict(gated, passing, failing, gaps)


def load_causes(path: Path) -> dict[CellKey, str]:
    """`docs/results/coverage-causes.toml`: `["<Venue> <year> <track>"]` tables with a `cause` string (the
    classification of a failing cell; coverage-reporting skill). A missing file is no causes."""
    if not path.is_file():
        return {}
    out: dict[CellKey, str] = {}
    for name, body in tomllib.loads(path.read_text(encoding="utf-8")).items():
        venue, year, track = name.split()
        if not isinstance(body, dict) or not isinstance(body.get("cause"), str) or not body["cause"].strip():
            raise ValueError(f"{path}: [{name}] needs a non-empty cause string")
        out[(venue, int(year), track)] = body["cause"].strip()
    return out


def _signed(n: int) -> str:
    return f"{MINUS}{-n}" if n < 0 else str(n)


def _pct(p: float) -> str:
    text = f"{abs(p):.1f}%"
    return f"{MINUS}{text}" if round(p, 1) < 0 else text


def _row(
    key: CellKey, cell: Mapping[str, Any] | None, official: OfficialTable, statuses: str, unknown: str
) -> str:
    year, track = key[1], key[2]
    row = official.get(key)
    if cell is None:  # a gated official cell the snapshot holds nothing for
        assert row is not None
        return (f"| {year} | {track} | 0 | {row.accepted:,} | {_signed(-row.accepted)} | {_pct(-100.0)} "
                f"| ✗ gap | 0 | {unknown} | {statuses} |")  # fmt: skip
    indexed = cell["indexed_accepted"]
    if cell["official_accepted"] is None:
        verdict, off, delta, pct = ("no source" if track in GATED_TRACKS else "not gated"), "—", "—", "—"
    else:
        off, delta, pct = f"{cell['official_accepted']:,}", _signed(cell["delta"]), _pct(cell["delta_pct"])
        verdict = ("✓" if cell["within_gate"] else "✗") if cell["gated"] else "not gated"
    return (f"| {year} | {track} | {indexed:,} | {off} | {delta} | {pct} | {verdict} | "
            f"{cell['abstract_missing']:,} | {unknown} | {statuses} |")  # fmt: skip


def _listing_rows(manifest: Mapping[str, Any]) -> list[str]:
    """Every crawled listing or venue-year that skipped entries, or whose entries disagree with its page."""
    rows = []
    for source, entry in sorted(manifest.get("sources", {}).items()):
        if not isinstance(entry, Mapping):
            continue  # `ris`: a list of import reports, no listings
        for report in [*entry.get("listings", []), *entry.get("crawls", [])]:
            skipped = {k: n for k, n in report.get("skipped", {}).items() if n}
            if not skipped and report.get("count_ok", True):
                continue
            what = report.get("listing") or report.get("venueid") or "—"
            reasons = ", ".join(f"{k} {n:,}" for k, n in sorted(skipped.items())) or "—"
            stated = "—" if report.get("stated") is None else f"{report['stated']:,}"
            listed = report.get("listed", report.get("notes_read"))
            shown = f"{listed:,}" if isinstance(listed, int) else "—"
            rows.append(
                f"| {source} | {report['venue']} | {report['year']} | {what} | {shown} | {stated} | {reasons} |"
            )
    return rows


def render(
    cov: Mapping[str, Any],
    manifest: Mapping[str, Any],
    meta: Meta,
    *,
    official: OfficialTable = OFFICIAL_ACCEPTED,
    causes: Mapping[CellKey, str] | None = None,
) -> str:
    """The report's Markdown. `cov` is the coverage the API serves (`coverage.breakdown`'s shape); `manifest` is
    the same snapshot's manifest (for the listings)."""
    causes = causes or {}
    verdict = gate(cov, official)
    cells = _cells(cov)
    statuses = {(vy["venue"], vy["year"]): ", ".join(vy["statuses_indexed"]) for vy in cov["venue_years"]}
    unknown = {(vy["venue"], vy["year"]): f"{vy['unknown_track']:,}" for vy in cov["venue_years"]}
    snap = cov["snapshot"]
    lines = [
        f"# Coverage report, {meta.date.isoformat()}",
        "",
        f"- Snapshot: `{snap['name']}`, `snapshot_hash` `{snap['snapshot_hash']}` (built {snap['built_at']})",
        f"- Index: `index_version` `{meta.index_version}`",
        f"- Official counts: `docs/results/coverage-sources.md`, sha256 `{meta.sources_sha256}`",
        f"- Command: `{meta.command}`",
        "",
        f"**M4 gate: {'PASS' if verdict.passed else 'FAIL'}** — {verdict.passing} of {verdict.gated} gated cells "
        f"within ±1%; {verdict.gaps} gap{'' if verdict.gaps == 1 else 's'}. The gate (spec 07 §C) covers every "
        "main-track and D&B cell with an official count; other cells are reported, not gated.",
        "",
    ]
    keys = set(cells) | {k for k in official if k[2] in GATED_TRACKS}
    for venue in sorted({k[0] for k in keys}):
        lines += [
            f"## {venue}",
            "",
            "| year | track | indexed accepted | official | Δ | Δ% | gate | missing abstracts "
            "| unknown track (venue-year) | statuses indexed |",
            "|---|---|---|---|---|---|---|---|---|---|",
        ]
        mine = sorted((k for k in keys if k[0] == venue), key=lambda k: (k[1], TRACK_ORDER[k[2]]))
        lines += [
            _row(k, cells.get(k), official, statuses.get((k[0], k[1]), "—"), unknown.get((k[0], k[1]), "—"))
            for k in mine
        ]
        lines.append("")
    lines += ["## Causes of every failing cell", ""]
    if verdict.failing:
        lines += [
            f"- {v} {y} {t}: {causes.get((v, y, t), '**unclassified**')}" for (v, y, t), _ in verdict.failing
        ]
    else:
        lines.append("None: every gated cell is within ±1%.")
    listing_rows = _listing_rows(manifest)
    lines += ["", "## Listings that skipped entries", ""]
    if listing_rows:
        lines += [
            "| source | venue | year | listing | listed | stated | skipped |",
            "|---|---|---|---|---|---|---|",
        ]
        lines += listing_rows
    else:
        lines.append("None: every listing made a record of every entry.")
    t = cov["totals"]
    lines += [
        "",
        "## Totals",
        "",
        "| records | missing abstracts | unknown track | unknown status |",
        "|---|---|---|---|",
        f"| {t['records']:,} | {t['abstract_missing']:,} | {t['unknown_track']:,} | {t['unknown_status']:,} |",
        "",
    ]
    return "\n".join(lines)


def write(text: str, out_dir: Path, day: date) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{day.isoformat()}-coverage.md"
    path.write_text(text, encoding="utf-8")
    return path


def failing_summary(verdict: Verdict) -> Sequence[str]:
    return [f"{v} {y} {t} ({why})" for (v, y, t), why in verdict.failing]
