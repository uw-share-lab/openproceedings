---
description: Validate openproceedings exports (RIS, CSV, BibTeX) for one query or the whole fixture set — round-trip, reference parsers, Covidence-safe fields — and add missing fixtures/tests
argument-hint: "(optional) a query string, e.g. \"trust* AND benchmark* year:2020..2026\" — omit to run the fixture set"
allowed-tools: Read, Grep, Glob, Bash, Task, Write
---

Spawn the **export-format-validator** agent (`.claude/agents/export-format-validator.md`) to validate
exports. Target: $ARGUMENTS. If that is empty, use the golden export fixture set under
`backend/tests/fixtures/`.

Give it:
1. The target. For a query, the exact string, to be run through `op export "<q>" --format ris|csv|bibtex`
   and `op search "<q>" --ids` against the fixture index (or the index named by `index_version` if the
   user gave one).
2. The standards: `.claude/skills/ris-format/SKILL.md`, `.claude/skills/bibtex-format/SKILL.md`, and
   `.claude/skills/api-contract/SKILL.md` §Exports.
3. The independent reference parsers from the pinned PyPI packages: `scholarmend.parse.parse_ris` (RIS)
   and `refaudit.bibtex.parse_string` (BibTeX).
4. The instruction to write any missing fixtures and tests under `backend/tests/fixtures/exports/` and
   `backend/tests/contract/`, and to run `uv run pytest backend/tests/contract -q -k export`.

Report to the user:
- the per-format table (count = `X-Total` = `total`, id set, fields, provenance line, parser result);
- findings as Must / Should / Nit with `file:line — problem — fix`, and the verdict;
- the fixture and test files written, with the real test counts;
- which fixture to import into Covidence by hand, and what to check there.

This command does not fix exporters. Route Must findings to `.claude/agents/api-engineer.md`. New test
files are part of the branch, so they go through `/review-gate`, and `/record-learnings` applies.
