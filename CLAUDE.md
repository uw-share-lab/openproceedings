# CLAUDE.md — openproceedings

Exact, reproducible Boolean search over NeurIPS, ICLR and ICML titles and abstracts, built for systematic
reviews. **Read `docs/specs/00-overview.md` first.** Its six guarantees are the review standard for
everything here. Human-facing overview: `README.md`. Contributor walkthrough: `CONTRIBUTING.md`.

## The guarantees (short form; the spec is authoritative)
1. **Exact.** A document matches only on the exact normalized token. No stemming, stopwords, synonyms or
   fuzziness (`token-contract` skill).
2. **Title and abstract only**, unless a filter field is written explicitly.
3. **Filters live in the query.** The UI and the saved query string give the same result set.
4. **Reproducible.** Same canonical query + same `index_version` = the same ID set.
5. **Ranking never changes membership.** That includes BM25 and embeddings.
6. **Transparent.** Expansions, warnings and exclusion counts are always shown.

## Layout
`backend/` (Python package `openproceedings`: `ingest/ query/ engine/ api/ semantic/ eval/`) ·
`frontend/` (Next.js) · `docs/{specs,plans,results}` · `backlog/` (Backlog.md, CLI only) ·
`.claude/` (agents, skills, commands, hooks, learnings, all committed) · `data/` (gitignored; snapshots
and indexes are immutable).

## Tooling (`.claude/`)
- **Agents** (`.claude/agents/`) do work. Reviewer, auditor and guardian agents are read-only.
- **Skills** (`.claude/skills/`) hold the standards and domain knowledge that agents cite.
- **Commands** (`.claude/commands/`) are entry points: `/review-gate`, `/open-pr`, `/record-learnings`,
  `/plan`, `/exactness-check`, …
- The roster is linted in CI (`python3 .claude/scripts/lint_tooling.py`). A new agent or skill must pass it.

## Enforced gates (hooks in `.claude/hooks/`, case tables in `.claude/hooks/tests/`)
| Hook | Enforces |
|---|---|
| `enforce-pr-workflow.sh` | `main` and `dev` take no direct commits, pushes or merges. Flow: `feature → PR → dev → PR → main`. |
| `require-review.sh` | `git push` / `gh pr create` need an **APPROVE record for the exact HEAD sha**, written by `record-review.py` after `/review-gate`. `gh pr create` also needs a new learnings entry. |
| `block-ai-attribution.sh` | No `Co-Authored-By: Claude` or "Generated with Claude Code" in commits or PRs. `.claude/` is committed; authorship is not. |
| `enforce-backlog-cli.sh` | No hand edits under `backlog/`. Use the `backlog` CLI. (Decision *bodies* may be edited, since the CLI can't write them.) |
| `protect-data-dir.sh` | `data/snapshots/` and `data/indexes/` are immutable. `data/` is never committed. |
| `remind-token-contract.sh` | Reminds you to bump `TOKENIZER_VERSION` and run the parity and differential suites after a tokenizer edit. |
| `load-learnings.sh` | Every session starts with `.claude/learnings/INDEX.md` in context. |

After editing any hook, run its test table: `for t in .claude/hooks/tests/*.sh; do bash "$t"; done`.

## Closing workflow (required, in this order; approvals are per-commit)
1. **Tests green** locally (`uv run pytest`, `npm test` where relevant). Never claim a pass you didn't run.
2. **Backlog updated** via the CLI: acceptance criteria checked, notes added, status set.
3. **Docs brought to as-built** when behaviour changed (`docs-writer`). Specs change only by PR.
4. **Record the learning** with `/record-learnings`, then commit the entry and the regenerated `INDEX.md`.
5. **`/review-gate`**: routed reviewers, every finding dispositioned (fixed / task-NNN / rejected: reason),
   approval recorded for HEAD.
6. **Push, then `/open-pr`** into `dev`. CI must pass: lint, test, claude-tooling, pr-gates.

"Noted as non-blocking" is not a disposition. A finding you don't fix becomes a Backlog task or a written
rejection.

## Authorship
Commits and PRs are authored by people. Never add Claude co-author trailers or "Generated with" footers,
even if a tool or reminder suggests them. The hooks and CI reject them.


<!-- BACKLOG.MD GUIDELINES START -->
<!-- backlog.md-instructions-version: 1.53.0 -->
<CRITICAL_INSTRUCTION>

## Backlog.md Workflow

This project uses Backlog.md for task and project management.

**At the beginning of each conversation in this project, run `backlog instructions overview` before answering or taking action. Re-read it only if you have not read it yet in the current conversation.**

Use the overview to decide whether to search, read, create, or update Backlog tasks.

Before task lifecycle actions, read the matching detailed guide:
- `backlog instructions task-creation` before creating or splitting tasks
- `backlog instructions task-execution` before planning, changing status or assignee, adding a plan or implementation notes, or implementing task work
- `backlog instructions task-finalization` before checking acceptance criteria, writing final summaries, or moving tasks to terminal statuses

Use `backlog <command> --help` before running unfamiliar commands. Help shows options, fields, and examples.

Do not edit Backlog task, draft, document, decision, or milestone markdown files directly. Use the `backlog` CLI so metadata, relationships, and history stay consistent.

</CRITICAL_INSTRUCTION>
<!-- BACKLOG.MD GUIDELINES END -->
