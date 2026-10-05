---
description: Run the spec 07 §B Google Scholar comparison on the pinned index and write the dated report plus review.csv
argument-hint: "(optional) query name, e.g. \"Most Updated\"; default: all Trust-Evals strings"
allowed-tools: Read, Write, Edit, Grep, Glob, Bash, Task
---

Spawn the **scholar-comparison-analyst** agent (`.claude/agents/scholar-comparison-analyst.md`) to run the
Scholar comparison, following `.claude/skills/scholar-comparison-protocol/SKILL.md` exactly.
Query: ${ARGUMENTS:-all Trust-Evals strings, Most Updated first}

It must:
1. Pin and record the served `index_version`, `tokenizer_version` and the Scholar export's hash; stop if
   the export is not available: scholarmend's `mended.ris` of the Trust-Evals `clean.ris` (the same records,
   with the years scoping needs; never another export).
2. Run `uv run op eval scholar --ris <export> --index <v> --years <lo>..<hi>` (with `--name "$ARGUMENTS"`
   when given, and `--answers <name>` for the string the set answers). `--years` (and `--venues`) limit both
   sides and change every number, so the range is part of the result: state it.
3. Classify every disagreement in protocol order (`our_bug` → `filtered` → `compat_reading` → `coverage_gap` →
   `stemming` → `full_text`; `scholar_cap` / `scholar_missed`), with oracle checks for `full_text`, and say what
   the matches rest on: crawled records or the set's own import (RIS-only), per venue and year.
4. Write the review rows (`docs/results/<today>-scholar-comparison-review.csv`: unresolved rows + 10% spot
   check, `human_class` blank) and `docs/results/<today>-scholar-comparison.md`.

Then spawn **review-methodologist** (`.claude/agents/review-methodologist.md`) on the new report.

Report: the pinned inputs, the crawled / RIS-only split, per-query sizes and class counts, the `our_bug` count (must be 0; list any
counter-example queries as Must findings), the review.csv row count awaiting a person, the report path,
the methodologist's verdict, and that `/record-learnings` and `/review-gate` are still required before a PR.
