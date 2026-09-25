---
name: learnings
description: How openproceedings records and reuses process lessons — the .claude/learnings/ journal, the mandatory Key-lesson line, de-duplication against INDEX.md, and what belongs here vs docs/results or a Backlog decision. Use at session start to check prior lessons before non-trivial work, and at task close when writing an entry.
---

# Learnings journal

## Why it is enforced, not optional
A lesson nobody reads is a lesson re-learned. So the loop is closed mechanically:
- **Write:** `require-review.sh` blocks `gh pr create` unless the branch adds an entry (escape hatch
  `--label no-learning` only for changes that taught nothing, e.g. a typo). CI `pr-gates` mirrors it.
- **Read:** `load-learnings.sh` (SessionStart) prints `INDEX.md` into every session's context.
- **Index:** `.claude/scripts/learnings_index.py` regenerates `INDEX.md`; CI fails if it is stale.

## At session start
Scan the index lines in your context. For the area you're about to touch, open the matching entries and
treat their "Dead ends" as rules. If you are about to do something an entry warns against, stop and say so.

## At task close
Spawn `learning-recorder` (or run `/record-learnings`). Order matters because approvals are per-commit:
work → commit → **learning entry → commit** → `/review-gate` → push → PR.

## What makes a good entry
| Good | Weak |
|---|---|
| Title is a claim: "OpenReview v1 hides decisions in separate notes" | Title is a topic: "OpenReview" |
| Key lesson is actionable alone | Key lesson needs the body to make sense |
| Evidence: path, command, output, commit | "It seemed like…" |
| Dead end + how to recognise it early | Just the dead end |
| Propagated into a skill/test/hook | Lives only in the journal |

## De-duplication rule
Before writing, grep the index and entries for the key terms. Same lesson → append
`## Addendum — YYYY-MM-DD` to the existing entry. Contradicting lesson → a new entry that links the old one
and says what changed; never edit the old entry's claims (the journal is append-only history).

## Where things go
- Measured numbers → `docs/results/` (with the command that produced them).
- Hard-to-reverse design choices → `backlog decision create`, linked from the entry.
- Follow-ups → Backlog tasks, ids in the entry. Never "noted for later".
- Anything that should change behaviour → also the owning skill/agent/CLAUDE.md ("Propagated to").

## Privacy
No secrets, no names (roles only), no unpublished review content beyond what the repo already holds.
