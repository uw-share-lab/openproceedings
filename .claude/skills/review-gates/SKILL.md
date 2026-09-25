---
name: review-gates
description: The openproceedings review standard and routing table — which reviewer agents a diff must pass (by path), the Must/Should/Nit severity scale, how every finding gets dispositioned, and how an approval is recorded per-commit so pushes and PRs are gated. Use whenever running /review-gate, acting as any reviewer agent, or deciding whether work is ready to push.
---

# Review gates

Goal: **catch every bug before it leaves the machine.** Four layers, each catching what the one before
misses:

| Layer | When | Enforced by |
|---|---|---|
| 1. Specialist review of the diff | before every push | `require-review.sh` (blocks push/PR without an APPROVE record for the exact sha) |
| 2. Finding disposition | before the record is written | `record-review.py` (refuses undispositioned findings, rejected must-fixes, dirty trees) |
| 3. CI gates | on every PR to `dev`/`main` | `.github/workflows/*` — lint, test, claude-tooling, pr-gates (attribution, learnings, review attestation) |
| 4. Branch protection | merge | GitHub: `dev` and `main` accept only PRs with green required checks; `main` additionally needs an approving review |

## Routing — which reviewers a diff needs

`/review-gate` computes `git diff --name-only origin/dev...HEAD` and spawns **every** matching reviewer
in parallel. `code-reviewer` always runs. When in doubt, include the reviewer — a redundant review costs
minutes; a missed one costs a wrong search result in someone's systematic review.

| Paths changed | Reviewers (in addition to `code-reviewer`) |
|---|---|
| `backend/src/openproceedings/query/**` | `exactness-guardian`, `query-semantics-reviewer` |
| `backend/src/openproceedings/engine/**` | `exactness-guardian` (+ `performance-profiler` if compile/rank/index build changed) |
| `backend/src/openproceedings/ingest/**` | `track-classifier-auditor`, `dedup-auditor`, `security-reviewer` (crawlers make network calls) |
| `backend/src/openproceedings/api/**` | `api-contract-reviewer`, `security-reviewer`; exporters → `export-format-validator` |
| `backend/src/openproceedings/semantic/**` | `near-miss-evaluator` (the membership invariant) |
| `frontend/**` | `ux-reviewer`, `accessibility-auditor` |
| `docs/specs/**` | `review-methodologist`, `docs-reviewer` |
| other `docs/**`, `*.md`, `.claude/**/*.md` | `docs-reviewer` |
| `.claude/hooks/**`, `.github/**`, `deploy/**`, lockfiles, `pyproject.toml`, `package.json` | `security-reviewer` |
| any `src/**` change > 150 changed lines, or any change claiming "exact"/"reproducible"/"fixed" | `qa-auditor` |
| a PR as a whole (after the above) | `pr-reviewer` folds all verdicts together |

## Severity
- **Must** — blocks. Wrong results, a violated guarantee (00 §Guarantees), a security hole, a failing or
  missing test for new behaviour, a broken contract, AI attribution, data committed.
- **Should** — real defect or debt that does not break a guarantee.
- **Nit** — style/clarity.

## Disposition (all findings, including the ones you won't fix)
In the dispositions file, one line per finding:
```
- [must] engine/compile.py:42 phrase compiled across fields → fixed 1a2b3c4
- [should] api/export.py:88 CSV lacks BOM → task-014
- [nit] query/lexer.py:10 name shadows builtin → rejected: matches the stdlib-parallel naming in lexer
```
`[must]` can only be `fixed` (commit must be an ancestor of HEAD). "Noted as non-blocking" is not a
disposition — it produces no artifact and the finding is lost (inherited Kreate lesson).

## Recording
Clean tree → `python3 .claude/scripts/record-review.py APPROVE <file> [--attest]`. The record is per-sha:
any later commit (including the learnings entry) needs a new review round. Reviewers are read-only — the
main session fixes, re-runs the affected reviewers, and records.

## Reviewer output contract (all reviewer agents)
Findings grouped **Must / Should / Nit**, each `file:line — problem — concrete fix`, then a one-line verdict
**APPROVE** / **REQUEST CHANGES**. Don't invent issues; "clean" is a valid review. Verify claims by running
things (tests, the oracle, `op search --explain`) rather than by reading alone.
