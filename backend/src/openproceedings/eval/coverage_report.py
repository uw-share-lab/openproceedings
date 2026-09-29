"""The coverage report (spec 07 §C, coverage-reporting skill; TASK-054): `op eval coverage` writes
`docs/results/<YYYY-MM-DD>-coverage.md` from exactly what `GET /coverage` serves for the index
(`api.coverage.compute`), so the report and the `/coverage` page never disagree.

What it adds to that data, and nothing else:
- **Gaps.** A gated official cell (main or D&B with an official count) that the snapshot holds no record for is
  a row with 0 indexed and ✗, never a silent zero (spec 07 §C: a venue-year with no source is a reported gap).
- **The M4 gate verdict.** Every gated cell within ±1% (`official_counts.within_gate`), gaps included.
- **Cause notes.** Every failing cell gets its cause from `causes` (a person's classification: source
  definition, classification, dedup or crawl gap), or `**unclassified**`: never adjust an official number to fit.
- **Owner-accepted exceptions.** A cell outside ±1% whose gap the project owner accepted (a decision record) passes
  the gate only while its indexed and official counts are exactly the accepted ones; a drifted count fails again.
  Every accepted exception is listed in the report, and one whose cell no longer fails is reported as stale.
- **Listings.** Each proceedings listing that skipped entries or whose count disagreed with its page, and each
  OpenReview venue-year crawl that is incomplete or has coverage gaps, conflicts, unmapped venues, non-routine
  skipped groups or non-routine skipped notes, from the snapshot manifest's `sources`: a passing `count_ok` can
  hide a loss at the id step (TASK-118). Routine: `not_submission` notes and `proposal`/`container` groups.

`cov` and `manifest` are plain mappings in `coverage.breakdown`'s and the manifest's JSON shapes, as the rest of
the coverage code passes them.
"""

from __future__ import annotations

import re
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from openproceedings import storage
from openproceedings.official_counts import GATED_TRACKS, OFFICIAL_ACCEPTED, OfficialTable, within_gate
from openproceedings.vocab import TRACKS, VENUES

type CellKey = tuple[str, int, str]
TRACK_ORDER = {t: i for i, t in enumerate(TRACKS)}
MINUS = "−"  # U+2212, as the other results reports write a negative delta
ROUTINE_SKIPS = frozenset({"not_submission"})  # an OpenReview reply or decision note: never a paper
# v2 groups skipped by their id on every crawl (openreview_v2.venue_groups): a workshop proposal, a container of
# venues. Not routine: `not_a_v2_venue` (a committee, but also an empty or unreadable group response, which can
# hide a venue) and `no_submission_venue_id` (a venue group whose submissions can't be found).
ROUTINE_GROUP_SKIPS = frozenset({"proposal", "container"})


@dataclass(frozen=True)
class Meta:
    """What the numbers depend on, for the header."""

    date: date
    index_version: str
    sources_sha256: str  # of docs/results/coverage-sources.md, the official counts' cited table
    causes_sha256: str | None  # of docs/results/coverage-causes.toml; None when there is no such file
    command: str


@dataclass(frozen=True)
class AcceptedException:
    """A failing cell's gap the project owner accepted (`["<cell>".accepted]` in coverage-causes.toml). It
    covers exactly `indexed` records against an official count of exactly `official`, nothing else."""

    indexed: int
    official: int
    reason: str
    papers: tuple[str, ...]  # the record ids (or titles) the gap is made of
    accepted_by: str  # a role, never a name
    accepted_on: date
    decision: str  # the decision record, `decision-<n>`

    def matches(self, indexed: int, official: int) -> bool:
        return (indexed, official) == (self.indexed, self.official)


@dataclass(frozen=True)
class Verdict:
    gated: int  # gated official cells, gaps included
    passing: int  # within ±1%
    failing: tuple[tuple[CellKey, str], ...]  # (cell, "gap" | "outside" | "drifted"), drifted: an exception's
    # counts no longer match the cell's
    gaps: int
    accepted: tuple[CellKey, ...] = ()  # outside ±1% by exactly an owner-accepted exception's counts

    @property
    def passed(self) -> bool:
        return not self.failing


def _cells(cov: Mapping[str, Any]) -> dict[CellKey, dict[str, Any]]:
    return {(vy["venue"], vy["year"], t["track"]): t for vy in cov["venue_years"] for t in vy["tracks"]}


def gate(
    cov: Mapping[str, Any],
    official: OfficialTable = OFFICIAL_ACCEPTED,
    exceptions: Mapping[CellKey, AcceptedException] | None = None,
) -> Verdict:
    """The M4 gate over every gated official cell: the snapshot's own verdict per cell, and a gap for a cell it
    holds no record for. A cell outside ±1% passes as accepted only when an exception's indexed and official
    counts equal the cell's exactly; with any other counts it fails as `drifted`."""
    exceptions = exceptions or {}
    cells = _cells(cov)
    failing: list[tuple[CellKey, str]] = []
    accepted: list[CellKey] = []
    gated = passing = gaps = 0
    for key in sorted(k for k in official if k[2] in GATED_TRACKS):
        gated += 1
        cell = cells.get(key)
        indexed = 0 if cell is None else cell["indexed_accepted"]
        if cell is not None and within_gate(indexed, official[key].accepted):
            passing += 1
            continue
        gaps += cell is None
        exception = exceptions.get(key)
        if exception is None:
            failing.append((key, "gap" if cell is None else "outside"))
        elif exception.matches(indexed, official[key].accepted):
            accepted.append(key)
        else:
            failing.append((key, "drifted"))
    return Verdict(gated, passing, tuple(failing), gaps, tuple(accepted))


_CELL_KEYS = frozenset({"cause", "accepted"})
_EXCEPTION_KEYS = {"indexed": int, "official": int, "reason": str, "papers": list, "accepted_by": str,
                   "accepted_on": date, "decision": str}  # fmt: skip
_KIND = {int: "an integer", str: "a string", list: "a list", date: "a date (YYYY-MM-DD, unquoted)"}


def _cell_key(path: Path, name: str) -> CellKey:
    parts = name.split()
    if len(parts) != 3 or parts[0] not in VENUES.values() or not parts[1].isdigit() or parts[2] not in TRACKS:
        raise ValueError(f'{path}: [{name}] is not "<Venue> <year> <track>" (e.g. "ICLR 2014 main")')
    return parts[0], int(parts[1]), parts[2]


def _exception(path: Path, name: str, body: object) -> AcceptedException:
    where = f"{path}: [{name}.accepted]"
    if not isinstance(body, dict):
        raise ValueError(f"{where} must be a table")
    if unknown := sorted(set(body) - set(_EXCEPTION_KEYS)):
        raise ValueError(f"{where} has unknown keys: {', '.join(unknown)}")
    if missing := [k for k in _EXCEPTION_KEYS if k not in body]:
        raise ValueError(f"{where} is missing: {', '.join(missing)}")
    # a TOML date-time is a datetime, a subclass of date: refused, the day is what is recorded
    for k, kind in _EXCEPTION_KEYS.items():
        v = body[k]
        if not isinstance(v, kind) or isinstance(v, bool) or (kind is date and isinstance(v, datetime)):
            raise ValueError(f"{where}: {k} must be {_KIND[kind]}")
        if isinstance(v, str) and not v.strip():
            raise ValueError(f"{where}: {k} must not be empty")
    # a cell with no records is a reported gap, never accepted
    if body["indexed"] < 1 or body["official"] < 1:
        raise ValueError(f"{where}: indexed and official must be at least 1")
    if within_gate(body["indexed"], body["official"]):
        raise ValueError(f"{where}: {body['indexed']} of {body['official']} is within ±1%; nothing to accept")
    papers = body["papers"]
    if not papers or not all(isinstance(p, str) and p.strip() for p in papers):
        raise ValueError(f"{where}: papers must be a non-empty list of non-empty strings")
    if not re.fullmatch(r"decision-[0-9]+", body["decision"]):
        raise ValueError(f"{where}: decision must be a decision record id (decision-<n>)")
    return AcceptedException(
        indexed=body["indexed"],
        official=body["official"],
        reason=body["reason"].strip(),
        papers=tuple(p.strip() for p in papers),
        accepted_by=body["accepted_by"].strip(),
        accepted_on=body["accepted_on"],
        decision=body["decision"],
    )


def load_cause_file(path: Path) -> tuple[dict[CellKey, str], dict[CellKey, AcceptedException]]:
    """`docs/results/coverage-causes.toml`: `["<Venue> <year> <track>"]` tables, each with a `cause` string (the
    classification of a failing cell; coverage-reporting skill) and optionally an `accepted` table, the project
    owner's accepted exception for that cell. Unknown keys and missing fields are refused (ValueError). A missing
    file is no causes and no exceptions."""
    if not path.is_file():
        return {}, {}
    causes: dict[CellKey, str] = {}
    exceptions: dict[CellKey, AcceptedException] = {}
    for name, body in tomllib.loads(path.read_text(encoding="utf-8")).items():
        key = _cell_key(path, name)
        if not isinstance(body, dict) or not isinstance(body.get("cause"), str) or not body["cause"].strip():
            raise ValueError(f"{path}: [{name}] needs a non-empty cause string")
        if unknown := sorted(set(body) - _CELL_KEYS):
            raise ValueError(f"{path}: [{name}] has unknown keys: {', '.join(unknown)}")
        causes[key] = body["cause"].strip()
        if "accepted" in body:
            exceptions[key] = _exception(path, name, body["accepted"])
    return causes, exceptions


def load_causes(path: Path) -> dict[CellKey, str]:
    """The cause notes of `load_cause_file`."""
    return load_cause_file(path)[0]


def _signed(n: int) -> str:
    return f"{MINUS}{-n:,}" if n < 0 else f"{n:,}"


def _pct(p: float) -> str:
    text = f"{abs(p):.1f}%"
    return f"{MINUS}{text}" if round(p, 1) < 0 else text


def _row(
    key: CellKey,
    cell: Mapping[str, Any] | None,
    official: OfficialTable,
    statuses: str,
    unknown: str,
    accepted: bool = False,
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
        if accepted:  # outside ±1% by exactly the owner-accepted counts: passes, and says why
            verdict = "✓ accepted exception"
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
    exceptions: Mapping[CellKey, AcceptedException] | None = None,
) -> str:
    """The report's Markdown. `cov` is the coverage the API serves (`coverage.breakdown`'s shape); `manifest` is
    the same snapshot's manifest (for the listings)."""
    causes = causes or {}
    exceptions = exceptions or {}
    verdict = gate(cov, official, exceptions)
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
        f"within ±1%; {verdict.gaps} gap{'' if verdict.gaps == 1 else 's'}; {len(verdict.accepted)} owner-accepted "
        f"exception{'' if len(verdict.accepted) == 1 else 's'}. The gate (spec 07 §C) covers every "
        "main-track and D&B cell with an official count; other cells are reported, not gated. An owner-accepted "
        "exception passes its cell only while the cell's counts are exactly the accepted ones. Δ% is rounded to "
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
                k in verdict.accepted,
            )
            for k in mine
        ]
        lines.append("")
    lines += ["## Causes of every failing cell", ""]
    if verdict.failing:
        lines += [
            f"- {v} {y} {t}: {causes.get((v, y, t), '**unclassified**')}"
            + (_drift((v, y, t), exceptions[(v, y, t)], cells, official) if why == "drifted" else "")
            for (v, y, t), why in verdict.failing
        ]
    else:
        lines.append("None: every gated cell is within ±1% or an owner-accepted exception.")
    stale = stale_causes(causes, verdict)
    if stale:  # a note left behind after its cell was fixed: shown, never silently dropped
        lines += [
            "",
            "Cause notes for cells that are not failing (remove them from coverage-causes.toml):",
            "",
        ]
        lines += [f"- {v} {y} {t}: {causes[(v, y, t)]}" for v, y, t in stale]
    lines += ["", "## Owner-accepted exceptions", ""]
    if verdict.accepted:
        lines += [
            "Each passes its cell only while the indexed and official counts are exactly these.",
            "",
            *(_exception_line(k, exceptions[k], causes.get(k)) for k in verdict.accepted),
        ]
    else:
        lines.append("None: no failing cell passes as an owner-accepted exception.")
    # an exception whose cell is within ±1% again, or not a gated official cell: shown, never dropped
    stale_ex = stale_exceptions(exceptions, verdict)
    if stale_ex:
        lines += [
            "",
            "Accepted exceptions for cells that are within ±1% or not gated (remove them from coverage-causes.toml):",
            "",
        ]
        lines += [_exception_line(k, exceptions[k], None) for k in stale_ex]
    listings, crawls = _listing_rows(manifest)
    lines += ["", "## Proceedings listings that skipped entries", ""]
    if listings:
        lines += ["| source | venue | year | listing | listed | stated | count ok | skipped |",
                  "|---|---|---|---|---|---|---|---|", *listings]  # fmt: skip
    else:
        lines.append("None: every listing made a record of every entry, and every stated count matched.")
    lines += ["", "## OpenReview crawls that need attention", ""]
    if crawls:
        lines += [f"Routine skips are not counted: reply and decision notes (`{', '.join(sorted(ROUTINE_SKIPS))}`) "
                  f"and groups skipped by id (`{', '.join(sorted(ROUTINE_GROUP_SKIPS))}`).", "",
                  "| source | venue | year | notes read | imported | skipped | notes |",
                  "|---|---|---|---|---|---|---|", *crawls]  # fmt: skip
    else:
        lines.append(
            "None: every crawl is complete, with no coverage gaps, conflicts, unmapped venues or non-routine skips."
        )
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


def _exception_line(key: CellKey, ex: AcceptedException, cause: str | None) -> str:
    v, y, t = key
    return (f"- {v} {y} {t}: {ex.indexed:,} indexed vs {ex.official:,} official "
            f"(Δ {_signed(ex.indexed - ex.official)}), accepted by the {ex.accepted_by} on "
            f"{ex.accepted_on.isoformat()} ({ex.decision}). {ex.reason} Papers: {', '.join(ex.papers)}."
            + (f" Cause: {cause}" if cause else ""))  # fmt: skip


def _drift(
    key: CellKey, ex: AcceptedException, cells: Mapping[CellKey, Mapping[str, Any]], official: OfficialTable
) -> str:
    cell = cells.get(key)
    now = 0 if cell is None else cell["indexed_accepted"]
    return (f" **The accepted exception ({ex.decision}) no longer matches:** accepted {ex.indexed:,} indexed vs "
            f"{ex.official:,} official, now {now:,} vs {official[key].accepted:,}.")  # fmt: skip


def stale_causes(causes: Mapping[CellKey, str], verdict: Verdict) -> list[CellKey]:
    kept = {k for k, _ in verdict.failing} | set(verdict.accepted)
    return sorted(k for k in causes if k not in kept)


def stale_exceptions(exceptions: Mapping[CellKey, AcceptedException], verdict: Verdict) -> list[CellKey]:
    """Exceptions whose cell neither passes as accepted nor fails: within ±1%, or not a gated official cell. (A
    drifted exception's cell is failing, and says so in the causes.)"""
    kept = {k for k, _ in verdict.failing} | set(verdict.accepted)
    return sorted(k for k in exceptions if k not in kept)


def failing_summary(verdict: Verdict) -> Sequence[str]:
    """One line per failing cell; `drifted` is an accepted exception whose counts no longer match."""
    return [f"{v} {y} {t} ({why})" for (v, y, t), why in verdict.failing]
