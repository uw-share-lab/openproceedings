---
description: Scaffold a new spec at docs/specs/NN-<name>.md in the house format (status line, depends-on/consumed-by, Purpose, body sections, Error handling, Testing), link it from 00-overview, then have review-methodologist and docs-reviewer review it
argument-hint: "<kebab-name> [one-line purpose], e.g. 'venue-extension Add ACL/EMNLP to the corpus'"
allowed-tools: Read, Write, Edit, Grep, Glob, Bash, Task
---

Create a new spec for: **$ARGUMENTS** (first word = kebab-case name, the rest = purpose). Follow
`.claude/skills/spec-writing/SKILL.md`.

1. **Number it.** `ls docs/specs/` → NN = next two-digit number. Refuse if a spec with the same name or
   scope exists; propose editing that one instead.
2. **Scaffold `docs/specs/NN-<name>.md`** in the house format used by `01`–`08`:
   ```
   # NN — <Title>

   Status: **draft for review** · depends on: <specs or "nothing"> · consumed by: <specs or people>

   ## Purpose
   <what it produces, and which guarantees in 00 it carries>

   ## <body sections: schema / grammar / contract tables, pipeline, CLI (`op …`)>

   ## Error handling
   ## Testing
   ```
   Fill Purpose and depends-on/consumed-by from the argument and from reading the specs it touches;
   leave the other sections as short, explicit TODO lists, never invented detail. State which of the six
   guarantees the part must uphold and how its tests prove it.
3. **Link it** from `docs/specs/00-overview.md` §Parts and specs (and §Milestones if it adds one), and
   add the reciprocal depends-on/consumed-by in the specs it names.
4. **Review.** In one message spawn `.claude/agents/review-methodologist.md` (PRISMA and reproducibility
   lens: can a review cite what this spec produces?) and `.claude/agents/docs-reviewer.md` (format,
   cross-references, guarantee wording). Fix every Must.
5. Spec changes land only by PR: on a feature branch, `/record-learnings`, `/review-gate`, `/open-pr`.

Report the spec path, what was filled vs left TODO, each reviewer's verdict with findings, and suggest
`/plan docs/specs/NN-<name>.md` once it is accepted.
