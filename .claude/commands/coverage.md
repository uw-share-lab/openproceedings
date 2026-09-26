---
description: Coverage check — compare a snapshot's accepted counts per venue × year × track against cited official counts, apply the M4 ±1% gate, and report unknown-track and missing-abstract counts
argument-hint: "(optional) venue and/or year, e.g. ICLR 2024 — and optionally a snapshot dir name"
allowed-tools: Read, Grep, Glob, Bash, Task
---

Spawn the **coverage-auditor** agent (`.claude/agents/coverage-auditor.md`) to audit corpus coverage.
Scope: $ARGUMENTS. If that's empty, cover every venue-year in the newest snapshot under `data/snapshots/`.

It must:
1. Name the snapshot it audited: directory, `snapshot_hash`, and `crawl_date` from `manifest.json`.
2. Take official accepted counts only from `docs/results/coverage-sources.md`, each with its citation.
   Cells without one are reported as "no reference", never estimated.
3. Produce the table `venue | year | track | indexed | official | Δ | Δ% | unknown | abstract_missing |
   source`, and flag every main-track cell outside ±1% (the M4 gate, spec 07 §C).
4. Diagnose each flagged cell (pagination, an unverified venueid form, the D&B alias, a missing PMLR
   volume, a workshop leak, a dedup miss). Use `.claude/skills/coverage-reporting/SKILL.md` for the report
   shape.
5. Stay read-only. Never edit `data/` (snapshots are immutable; `protect-data-dir.sh` enforces this).

Report to the user: the table, the list of failing cells with their probable causes, the auditor's
verdict (APPROVE / REQUEST CHANGES for the M4 gate), and suggested next steps. Crawl fixes go to
`.claude/agents/openreview-crawler.md` or `.claude/agents/proceedings-miner.md`. If the result will be
cited, it goes in `docs/results/<date>-coverage.md`, written by the main session.
