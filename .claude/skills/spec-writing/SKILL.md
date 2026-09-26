---
name: spec-writing
description: The house format and voice of docs/specs/NN-*.md — header line, section order, tables over prose, how guarantees and other specs are cited, how open questions and "verify at implementation time" are written, and how a spec changes (only by PR, reviewed by review-methodologist and docs-reviewer). Use when writing a new spec, amending an existing one, bringing a spec to as-built, or reviewing a spec diff.
---

# Spec writing (the `docs/specs/` house format)

## File and header
- Name: `docs/specs/NN-<kebab-name>.md`, two-digit number, next free after `08`. 00 is the overview and
  lists every spec in §Parts and specs — add the new row there in the same PR.
- First two lines, exactly:
```
# NN — Title

Status: **draft for review** · depends on: 02 (AST), 03 · consumed by: 04, 07
```
Status values: `draft for review` → `accepted` → `as-built` (with the date). Delivery milestone may be
added: `· delivered in M4`.

## Section order
1. `## Purpose` — one paragraph: what this part produces and for whom.
2. Contract sections — the interfaces others depend on (schemas, signatures, endpoints, grammar), in code
   blocks with real names (`ParseResult`, `SearchResponse`, `index_version`).
3. Behaviour sections — rules, each testable.
4. `## Error handling` — every failure mode and what the user sees (a `Diagnostic`, a logged skip, an
   `unknown` value — never a guess).
5. `## Testing` — the suites that prove the rules, with their gate (see spec 07 for the gate vocabulary).
Optional: `## Implementation notes`, `## Open questions`.

## Voice
- Short declarative sentences. "The parser adds `status:accepted`." not "It is expected that…".
- Tables for anything enumerable (fields, sources, endpoints, cases). Prose for rationale only.
- **Bold** the one rule per section a reader must not miss.
- Cite guarantees by number and name: "(guarantee 5, ranking never changes membership)". Cite other specs
  as `[03](03-search-engine.md)` or "03 §Versioning".
- Carry lessons forward with their source ("from venuetriage: records with no year never merge on
  `(title, "")`"), so the reason survives.
- Roles, never people's names. No AI attribution.

## Facts and uncertainty
- Every number (budget, count, threshold) is either a requirement ("p95 under 100 ms") or has a source.
- Unknowns are written as **open questions with a deadline milestone** (00 §Open questions) or as "decided
  at implementation time: …" — never as a confident guess.
- A spec defines *what must be true*, not the code. Name modules and paths only where they are contract.

## Checklist for every spec change
- [ ] Each guarantee (00) the part touches is addressed explicitly, including how it is tested.
- [ ] Anything a methods section would need (query, date, `index_version`, counts, exclusions) is
      reportable — `review-methodologist` checks this.
- [ ] New error cases have codes (`error-diagnostics`).
- [ ] 00's parts table, milestones and the roster in 08 updated if affected.
- [ ] Changed by PR only; routed to `review-methodologist` + `docs-reviewer`.
- [ ] If the change reverses an earlier choice, a decision record exists (`decision-records`).

## Gotchas
- "As-built" updates describe what shipped, including deviations — don't silently rewrite the draft to
  look as if the deviation was planned; say what changed and why.
- Two specs must never both own a rule. Pick the owner; the other links to it.
