---
name: decision-records
description: How openproceedings records architectural and methodological decisions as Backlog.md decisions — create with `backlog decision create`, then Edit the body (the one backlog/ file hand edits are allowed on), the Context / Decision / Consequences shape, statuses, and what warrants a record. Use when a choice is made that a future contributor could reasonably reverse, when an open question from spec 00 is resolved, or when a release or spec change depends on a decision.
---

# Decision records

## When to write one
Write a record when a future contributor could reasonably undo the choice without knowing why it was made:
- An **open question in 00** is resolved (abstract redistribution, rejected ICLR submissions, earliest
  year, planning tool, hosting). Link the record from 00 in the same PR.
- A guarantee is interpreted in a non-obvious way (e.g. which bucket an overlapping workshop+rejected paper
  counts in for `excluded`).
- A dependency, model or data source is pinned or dropped (Tantivy version, SPECTER2 checkpoint, a PMLR
  volume table).
- A process rule is adopted (the no-AI-attribution rule, 2026-09-25; `dev` between feature and `main`).
Don't write one for choices a test already pins, or for reversible style decisions.

## How (the CLI can create but not edit)
```bash
backlog decision create "Index rejected ICLR submissions behind status:accepted default" -s proposed --plain
# → prints the id, e.g. decision-3; the file lands in backlog/decisions/
```
Then open the created file with **Edit** (never Write) and fill the body. `enforce-backlog-cli.sh` allows
Edit/MultiEdit under `backlog/decisions/` only, because the CLI has no way to write the body; Write is
still blocked so the id, date and status come from the CLI. Leave the frontmatter the CLI wrote alone
except `status`.

## Body shape
```markdown
## Context
What forced the choice. Constraints, the options considered (at least two), evidence with sources
(spec sections, learnings entries, measured results in docs/results/). Roles, not names.

## Decision
One or two sentences, in the active voice: "We index rejected and withdrawn ICLR submissions with
status:rejected / status:withdrawn and apply status:accepted by default."

## Consequences
What becomes true, easier or harder. Which specs, skills, agents and tests must change (with paths).
What would make us revisit it. Effects on reproducibility (does index_version change? do old
search records drift?).
```

## Statuses
`proposed` → `accepted` | `rejected`; later `superseded by decision-N`. Status changes are the only
frontmatter edit; to reverse a decision, create a new record that supersedes it rather than rewriting the
old one — the history is the point.

## Gotchas
- A decision that changes matching, filters or `index_version` inputs also needs a spec PR; the record
  explains *why*, the spec states *what*.
- A decision that changes default filters changes canonical strings and therefore `canonical_hash`; say so
  under Consequences and note how existing search records will replay (`drifted`, not silently different).
- Keep the Context honest about options rejected — reviewers use it to avoid re-litigating.
- An empty stub record (title only) is worse than none. Fill the body in the same session.
