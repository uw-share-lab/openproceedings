# Learnings journal

The process memory of openproceedings. **One file per completed task/session**, written at task close by the
`learning-recorder` agent (`/record-learnings`). This step is required: `require-review.sh` blocks
`gh pr create` on a branch that neither adds nor extends an entry, and CI's `learnings` job (in
`pr-gates.yml`) checks the same thing. Extending an existing entry with a dated addendum satisfies both.
`--label no-learning` is only for changes that taught nothing; a same-repo `dev → main` promotion is
exempt.

## Why this exists
Specs (`docs/specs/`) say what the system must do. Results (`docs/results/`) record measured numbers. This
folder records **how the work went**: dead ends we must not re-walk, tooling and API quirks (OpenReview
429s, venueid forms, Tantivy slop semantics …), decisions and why, and "next time, do X". Every session
starts with `INDEX.md` loaded into context by `.claude/hooks/load-learnings.sh`, so a lesson written here is
seen by the next session automatically.

## Conventions
- Name: `YYYY-MM-DD-<short-slug>.md`, the date the work completed, placed **directly** in this folder
  (no subfolders). Several a day is fine. Only files with this name count for the gate; `README.md`,
  `_TEMPLATE.md` and `INDEX.md` don't.
- Start from `_TEMPLATE.md`. The `**Key lesson:**` line is mandatory and must stand alone: it is the only
  line that appears in the session-start index.
- **Append-only.** Don't rewrite an old entry; record a correction as a new entry that links the old one.
  If a new lesson duplicates an existing one, *extend* that entry with a dated addendum instead of adding a
  near-copy (the recorder checks the index first).
- After writing, regenerate the index: `python3 .claude/scripts/learnings_index.py`. CI runs
  `--check` and fails if the index is stale, if an entry's date isn't a real date, if an entry still has
  template `<placeholders>` in its title or key lesson, or if an entry sits in a subfolder.

## Where a lesson goes
| Lesson | Where |
|---|---|
| A measured number (coverage, latency, Scholar-comparison counts) | `docs/results/<date>-*.md`, not here |
| A process / decision / gotcha / dead end | here |
| A lesson that should change future work | here **and** folded into the relevant skill, agent or `CLAUDE.md` (record where under "Propagated to") |
| A design decision that is hard to reverse | a Backlog decision (`backlog decision create`), linked from here |
