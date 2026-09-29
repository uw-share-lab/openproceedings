"""The coverage report (spec 07 §C, coverage-reporting skill; TASK-054): `op eval coverage` writes
`docs/results/<YYYY-MM-DD>-coverage.md` from exactly what `GET /coverage` serves for the index
(`api.coverage.compute`), so the report and the `/coverage` page never disagree.

What it adds to that data, and nothing else:
- **Gaps.** A gated official cell (main or D&B with an official count) that the snapshot holds no record for is
  a row with 0 indexed and ✗, never a silent zero (spec 07 §C: a venue-year with no source is a reported gap).
- **The M4 gate verdict.** Every gated cell within ±1% (`official_counts.within_gate`), gaps included.
- **Cause notes.** Every failing cell gets its cause from `causes` (a person's classification: source
  definition, classification, dedup or crawl gap), or `**unclassified**`: never adjust an official number to fit.
- **Listings.** Each proceedings listing that skipped entries or whose count disagreed with its page, and each
  OpenReview venue-year crawl that is incomplete, has coverage gaps, unmapped venues or skipped groups, or
  skipped anything but reply notes (`not_submission`), from the snapshot manifest's `sources`: a passing
  `count_ok` can hide a loss at the id step (TASK-118).

`cov` and `manifest` are plain mappings in `coverage.breakdown`'s and the manifest's JSON shapes, as the rest of
the coverage code passes them.
"""

from __future__ import annotations

import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from openproceedings import storage
from openproceedings.official_counts import GATED_TRACKS, OFFICIAL_ACCEPTED, OfficialTable, within_gate
from openproceedings.vocab import TRACKS, VENUES

type CellKey = tuple[str, int, str]
TRACK_ORDER = {t: i for i, t in enumerate(TRACKS)}
MINUS = "−"  # U+2212, as the other results reports write a negative delta
ROUTINE_SKIPS = frozenset({"not_submission"})  # an OpenReview reply or decision note: never a paper
# v2 groups skipped by structure on every crawl (openreview_v2.venue_groups): a workshop proposal, a container of
# venues, a child group that is no venue (a committee). `no_submission_venue_id` is not routine: it can hide one.
ROUTINE_GROUP_SKIPS = frozenset({"proposal", "container", "not_a_v2_venue"})


@dataclass(frozen=True)
class Meta:
    """What the numbers depend on, for the header."""

    date: date
    index_version: str
    sources_sha256: str  # of docs/results/coverage-sources.md, the official counts' cited table
    causes_sha256: str | None  # of docs/results/coverage-causes.toml; None when there is no such file
    command: str


@dataclass(frozen=True)
class Verdict:
    gated: int  # gated official cells, gaps included
    passing: int
    failing: tuple[tuple[CellKey, str], ...]  # (cell, "gap" | "outside")
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
    return Verdict(gated, passing, tuple(failing), gaps)


def load_causes(path: Path) -> dict[CellKey, str]:
    """`docs/results/coverage-causes.toml`: `["<Venue> <year> <track>"]` tables with a `cause` string (the
    classification of a failing cell; coverage-reporting skill). A missing file is no causes."""
    if not path.is_file():
        return {}
    out: dict[CellKey, str] = {}
    for name, body in tomllib.loads(path.read_text(encoding="utf-8")).items():
        parts = name.split()
        if (
            len(parts) != 3
            or parts[0] not in VENUES.values()
            or not parts[1].isdigit()
            or parts[2] not in TRACKS
        ):
            raise ValueError(f'{path}: [{name}] is not "<Venue> <year> <track>" (e.g. "ICLR 2014 main")')
        if not isinstance(body, dict) or not isinstance(body.get("cause"), str) or not body["cause"].strip():
            raise ValueError(f"{path}: [{name}] needs a non-empty cause string")
        out[(parts[0], int(parts[1]), parts[2])] = body["cause"].strip()
    return out


def _signed(n: int) -> str:
    return f"{MINUS}{-n:,}" if n < 0 else f"{n:,}"


def _pct(p: float) -> str:
    text = f"{abs(p):.1f}%"
    return f"{MINUS}{text}" if round(p, 1) < 0 else text


def _row(
    key: CellKey, cell: Mapping[str, Any] | None, official: OfficialTable, statuses: str, unknown: str
) -> str:
    """One cell's row; `unknown` is its venue-year's `unknown`-track and `unknown`-status counts, and `statuses`
    its statuses indexed (`none (no records)` when the venue-year holds no record at all)."""
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


def _listing_rows(manifest: Mapping[str, Any]) -> tuple[list[str], list[str]]:
    """(proceedings listings, OpenReview crawls) that need a reader's attention, as table rows."""
    listings: list[str] = []
    crawls: list[str] = []
    for source, entry in sorted(manifest.get("sources", {}).items()):
        if not isinstance(entry, Mapping):
            continue  # `ris`: a list of import reports, no listings
        for r in entry.get("listings", []):
            skipped = {k: n for k, n in r.get("skipped", {}).items() if n}
            if skipped or not r.get("count_ok", True):
                stated = "—" if r.get("stated") is None else f"{r['stated']:,}"
                listings.append(f"| {source} | {r['venue']} | {r['year']} | {r['listing']} | {r['listed']:,} | "
                                f"{stated} | {'yes' if r.get('count_ok', True) else '**no**'} | "
                                f"{_reasons(skipped)} |")  # fmt: skip
        for r in entry.get("crawls", []):
            skipped = {k: n for k, n in r.get("skipped", {}).items() if n and k not in ROUTINE_SKIPS}
            notes = [
                *([] if r.get("complete", True) else ["**incomplete**"]),
                *([f"coverage gaps {len(r['coverage_gaps'])}"] if r.get("coverage_gaps") else []),
                *([f"unmapped {sum(r['unmapped'].values()):,}"] if r.get("unmapped") else []),
                *([f"conflicts {r['conflicts']:,}"] if r.get("conflicts") else []),
                *(
                    [f"skipped groups: {_reasons(groups)}"]
                    if (groups := _group_reasons(r.get("skipped_groups", {})))
                    else []
                ),
            ]
            if skipped or notes:
                crawls.append(f"| {source} | {r['venue']} | {r['year']} | {r.get('notes_read', 0):,} | "
                              f"{r.get('imported', 0):,} | {_reasons(skipped)} | {'; '.join(notes) or '—'} |")  # fmt: skip
    return listings, crawls


def _group_reasons(skipped_groups: Mapping[str, str]) -> dict[str, int]:
    """Skipped v2 groups by reason, the routine ones left out."""
    out: dict[str, int] = {}
    for reason in skipped_groups.values():
        if reason not in ROUTINE_GROUP_SKIPS:
            out[reason] = out.get(reason, 0) + 1
    return out


def _reasons(skipped: Mapping[str, int]) -> str:
    return ", ".join(f"{k} {n:,}" for k, n in sorted(skipped.items())) or "—"


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
    unknown = {
        (vy["venue"], vy["year"]): f"{vy['unknown_track']:,} | {vy['unknown_status']:,}"
        for vy in cov["venue_years"]
    }
    snap = cov["snapshot"]
    lines = [
        f"# Coverage report, {meta.date.isoformat()}",
        "",
        f"- Snapshot: `{snap['name']}`, `snapshot_hash` `{snap['snapshot_hash']}` (built {snap['built_at']})",
        f"- Index: `index_version` `{meta.index_version}`",
        f"- Official counts: `docs/results/coverage-sources.md`, sha256 `{meta.sources_sha256}`",
        "- Cause notes: "
        + (
            f"`docs/results/coverage-causes.toml`, sha256 `{meta.causes_sha256}`"
            if meta.causes_sha256
            else "none"
        ),
        f"- Command: `{meta.command}`",
        "",
        f"**M4 gate: {'PASS' if verdict.passed else 'FAIL'}** — {verdict.passing} of {verdict.gated} gated cells "
        f"within ±1%; {verdict.gaps} gap{'' if verdict.gaps == 1 else 's'}. The gate (spec 07 §C) covers every "
        "main-track and D&B cell with an official count; other cells are reported, not gated. Δ% is rounded to "
        "one decimal; the gate compares exactly (100 × |Δ| ≤ official), so a cell shown at 1.0% can still fail.",
        "",
    ]
    keys = set(cells) | {k for k in official if k[2] in GATED_TRACKS}
    for venue in sorted({k[0] for k in keys}):
        lines += [
            f"## {venue}",
            "",
            "| year | track | indexed accepted | official | Δ | Δ% | gate | missing abstracts "
            "| unknown track (venue-year) | unknown status (venue-year) | statuses indexed |",
            "|---|---|---|---|---|---|---|---|---|---|---|",
        ]
        mine = sorted((k for k in keys if k[0] == venue), key=lambda k: (k[1], TRACK_ORDER[k[2]]))
        lines += [
            _row(
                k,
                cells.get(k),
                official,
                statuses.get((k[0], k[1]), "none (no records)"),
                unknown.get((k[0], k[1]), "— | —"),
            )
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
    stale = stale_causes(causes, verdict)
    if stale:  # a note left behind after its cell was fixed: shown, never silently dropped
        lines += [
            "",
            "Cause notes for cells that are not failing (remove them from coverage-causes.toml):",
            "",
        ]
        lines += [f"- {v} {y} {t}: {causes[(v, y, t)]}" for v, y, t in stale]
    listings, crawls = _listing_rows(manifest)
    lines += ["", "## Proceedings listings that skipped entries", ""]
    if listings:
        lines += ["| source | venue | year | listing | listed | stated | count ok | skipped |",
                  "|---|---|---|---|---|---|---|---|", *listings]  # fmt: skip
    else:
        lines.append("None: every listing made a record of every entry, and every stated count matched.")
    lines += ["", "## OpenReview crawls that need attention", ""]
    if crawls:
        lines += [f"Reply and decision notes (`{', '.join(sorted(ROUTINE_SKIPS))}`) are not counted as skips.", "",
                  "| source | venue | year | notes read | imported | skipped | notes |",
                  "|---|---|---|---|---|---|---|", *crawls]  # fmt: skip
    else:
        lines.append("None: every crawl is complete, with no gaps, unmapped venues or skipped groups.")
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


def write(text: str, out_dir: Path, day: date) -> tuple[Path, bool]:
    """The report at `<out_dir>/<day>-coverage.md`, written atomically; whether it replaced one."""
    path = out_dir / f"{day.isoformat()}-coverage.md"
    replaced = path.exists()
    storage.write_bytes(path, text.encode("utf-8"))
    return path, replaced


def stale_causes(causes: Mapping[CellKey, str], verdict: Verdict) -> list[CellKey]:
    failing = {k for k, _ in verdict.failing}
    return sorted(k for k in causes if k not in failing)


def failing_summary(verdict: Verdict) -> Sequence[str]:
    return [f"{v} {y} {t} ({why})" for (v, y, t), why in verdict.failing]
