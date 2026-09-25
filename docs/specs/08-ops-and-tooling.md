# 08 — Ops and repo tooling

Status: **draft for review** · depends on: nothing · delivered in M0 (the roster grows with each milestone)

## Repo layout

```
openproceedings/
├── README.md  CLAUDE.md  AGENTS.md  CONTRIBUTING.md  LICENSE (MIT)
├── .claude/                     # committed: agents, skills, commands, hooks (roster below)
├── backend/                     # Python package `openproceedings` (uv project)
│   ├── src/openproceedings/
│   │   ├── ingest/              # 01: sources/, classify.py, dedup.py, snapshot.py, ris.py
│   │   ├── query/               # 02: normalize.py, lexer.py, parser.py, ast.py, canonical.py, compat.py
│   │   ├── engine/              # 03: reference.py, tantivy_engine.py, compile.py, rank.py, highlight.py
│   │   ├── semantic/            # 06 (phase 2)
│   │   ├── api/                 # 04: FastAPI app, routers, exporters/, records.py
│   │   ├── eval/                # 07 report generators
│   │   └── cli.py               # `op` entry point
│   └── tests/{unit,golden,differential,contract,fixtures}/
├── frontend/                    # 05: Next.js app
├── docs/{specs,plans,results}/         # decisions live in backlog/decisions (Backlog.md CLI)
├── backlog/                     # Backlog.md: tasks, docs, decisions — CLI only
├── deploy/                      # Dockerfiles, compose.yml
└── data/                        # gitignored: cache/, snapshots/, indexes/, records.sqlite
```

## CLI (`op`)

`op ingest …` · `op snapshot build|diff` · `op index build [--snapshot]` · `op search "<q>" [--explain] [--engine tantivy|reference]
[--mode scholar] [--ids]` · `op export "<q>" --format ris` · `op serve` · `op embed build` · `op eval
scholar|coverage|audit`. The CLI and the API call the same functions, and the CLI is enough on its own to
run a whole review.

## CI (GitHub Actions)

| Workflow | Runs |
|---|---|
| `lint` | ruff, ruff-format, mypy --strict (backend); eslint, tsc, prettier (frontend); a markdown link check |
| `test` | pytest (unit, golden, differential@2k, contract); vitest; OpenAPI → TS types freshness check |
| `e2e` | Playwright against `op serve` over the fixture index |
| `bench` | pytest-benchmark, comparing against the main branch |
| `nightly` | Differential@50k, full-index benchmarks, tokenizer parity over the full corpus |
| `claude-tooling` | Roster lint (`.claude/scripts/lint_tooling.py`), learnings index `--check`, every hook case table |
| `pr-gates` | `attribution` (no AI authorship in commits/PR), `learnings` (branch adds an entry unless labelled `no-learning`), `review-attested` (PR body attests APPROVE for the head sha) |

## Git and PR rules (enforced by hooks)

- `feature → PR → dev → PR → main`. No direct commits, pushes or merges on `dev` or `main`
  (`enforce-pr-workflow.sh`, inherited from Kreate with its 105-case table). `main` also needs a second
  person's approval.
- **Review before push:** `/review-gate` routes the diff to the required reviewers (`review-gates` skill),
  every finding is dispositioned, and `record-review.py` writes an APPROVE record for the exact HEAD sha.
  `require-review.sh` blocks `git push`/`gh pr create` without one. `/open-pr` attests it in the PR body
  for CI.
- **Learnings every time:** a PR must add a `.claude/learnings/` entry (`/record-learnings`), and every
  session starts with the index loaded (`load-learnings.sh`).
- **No AI authorship:** commits and PRs must not contain `Co-Authored-By: Claude`, `Generated with Claude
  Code`, or similar trailers. `.claude/` is committed. This is a project decision (2026-09-25).
- Secrets (OpenReview credentials) live only in `.env`, which is gitignored. `data/` is never committed.

## Deploy

`deploy/compose.yml`: `api` (uvicorn, loads `data/indexes/current`) and `web` (Next.js standalone), with
Caddy in front for TLS. The data volume is read-only in `api`, except `records.sqlite`. Refreshing the
index means building a new `index_version` offline, switching the `current` symlink, and sending SIGHUP.
Where it's hosted is still open (00, question 5).

---

## `.claude/` roster

It follows the Kreate model:
- **Skills** hold the standards and domain knowledge: what's true and what's required.
- **Agents** do work and cite the skills: who does it.
- **Commands** are thin entry points that spawn agents.
- **Hooks** enforce the gates.

Kreate splits `.claude/` per project. Our parts are not independent projects (they share one contract),
so we use **one root `.claude/`** and prefix names by area. Every agent's description says *when* to use
it. Every reviewer agent is read-only (`tools: Read, Grep, Glob, Bash`).

Built in M0: **41 agents, 43 skills** (the original 40/42 plus `learning-recorder` and `review-gates`) (inside the 25–150 range). New ones are added when a
milestone brings a new recurring task, never speculatively.

### Agents (41)

**Global roles (8, adapted from Kreate)**
| Agent | Role |
|---|---|
| `senior-engineer` | Designs and implements non-trivial changes, minimal and tested |
| `code-reviewer` | Line-level review of a diff; the pre-push gate |
| `pr-reviewer` | Whole-PR review: scope, gates, reviewability |
| `security-reviewer` | Secrets, injection, SSRF in crawlers, dependency risk |
| `qa-auditor` | Adversarial: tries to falsify "it works" and "it's exact" claims |
| `docs-writer` | Docs as built, in the repo's voice |
| `docs-reviewer` | Docs vs code accuracy, staleness, links |
| `project-manager` | Turns specs into tracked tasks with acceptance criteria |
| `learning-recorder` | Writes or extends the learnings entry that closes every task (required before a PR) |

**Ingestion (6)**
| `openreview-crawler` | Builds and maintains the API v1/v2 crawlers and per-year schema adapters |
| `proceedings-miner` | PMLR and NeurIPS proceedings scrapers, and the volume table |
| `ris-importer` | The RIS bootstrap from scholarmend output |
| `track-classifier-auditor` | Read-only: checks track/status classification against evidence claims |
| `dedup-auditor` | Read-only: reviews `merges.csv` and `conflicts.csv`, hunts over-merges |
| `coverage-auditor` | Compares indexed counts with official accepted counts per venue-year |

**Query language (4)**
| `grammar-engineer` | Parser, lexer, AST and canonical form |
| `query-compat-translator` | Scholar/PoP/WoS syntax → native, with translation notices |
| `parser-fuzzer` | Writes Hypothesis strategies and finds crashes and round-trip failures |
| `query-semantics-reviewer` | Read-only: checks any change against the 02 token contract |

**Search engine (6)**
| `index-engineer` | Tantivy schema, build, AST compilation |
| `exactness-guardian` | Read-only: blocks any change that could add a match the oracle wouldn't (guarantee 1) |
| `reference-oracle-keeper` | Owns `ReferenceEngine`, which must stay obviously correct |
| `differential-tester` | Runs and extends the Tantivy vs oracle suites, and minimizes counterexamples |
| `ranking-engineer` | BM25 field weights, tie-breaking, determinism |
| `performance-profiler` | Latency and build budgets, benchmark regressions |

**Backend (4)**
| `api-engineer` | FastAPI routers, models, streaming exports |
| `api-contract-reviewer` | Read-only: OpenAPI diff review, breaking-change detection |
| `export-format-validator` | RIS/CSV/BibTeX correctness vs Covidence, venuetriage and refaudit parsers |
| `search-records-keeper` | Search records, replay, drift reports |

**Frontend (6)**
| `frontend-engineer` | Next.js pages and components |
| `query-editor-engineer` | CodeMirror/Lezer grammar, diagnostics, autocomplete |
| `query-builder-engineer` | Concept-group builder and the AST round-trip |
| `ux-reviewer` | Read-only: reviewer workflows, clarity of exclusions and expansions |
| `accessibility-auditor` | WCAG 2.2 AA, keyboard-only flows |
| `e2e-tester` | Playwright flows, visual regression |

**Semantic (2)**
| `embedding-engineer` | SPECTER2 pipeline, `semantic_version`, re-sort |
| `near-miss-evaluator` | The recall@25 protocol and the invariant test |

**Evaluation and research (2)**
| `scholar-comparison-analyst` | Runs and classifies the Scholar comparison (07 B) |
| `review-methodologist` | Read-only: PRISMA and reproducibility lens on any feature or report |

**Ops (2)**
| `ci-engineer` | Workflows, caching, the claude-tooling lint |
| `release-manager` | Versioning, changelog, deploy runbook, snapshot/index promotion |

### Skills (43)

| Area | Skills |
|---|---|
| Repo (7) | `repo-conventions`, `pr-workflow`, `review-gates` (routing table, severity, dispositions), `no-ai-attribution`, `spec-writing`, `learnings` (dated journal, as in Kreate), `decision-records` |
| Engineering (5) | `python-standards`, `typescript-standards`, `testing-standards`, `property-testing`, `error-diagnostics` (one shape for errors and diagnostics across layers) |
| Ingestion (8) | `openreview-api` (v1 vs v2, auth, 429s, venueid is authoritative), `openreview-venueids` (all known forms), `pmlr-proceedings`, `neurips-proceedings`, `record-schema`, `track-taxonomy`, `dedup-rules`, `snapshots` |
| Query (5) | `query-grammar`, `token-contract` (the 02 normalization rules), `wildcards-and-expansion`, `scholar-syntax-compat`, `default-filters` |
| Engine (5) | `tantivy-indexing`, `ast-compilation`, `reference-oracle`, `field-weighted-bm25`, `index-versioning` |
| API and exports (5) | `fastapi-conventions`, `api-contract`, `ris-format`, `bibtex-format`, `search-records` |
| Frontend (4) | `nextjs-conventions`, `codemirror-lezer`, `ui-design-system`, `accessibility` |
| Research and eval (3) | `prisma-reporting`, `scholar-comparison-protocol`, `coverage-reporting` |
| Semantic (1) | `specter2-embeddings` (model pinning, the "never changes the set" rule) |

### Commands (18)

Gate and workflow: `/review-gate`, `/open-pr`, `/record-learnings`, `/review-pr`, `/plan`, `/new-spec`.
Reviews: `/security-review`, `/audit`, `/review-docs`, `/exactness-check` (runs `exactness-guardian` +
`differential-tester`), `/review-export`, `/ux-review`. Work: `/write-docs`, `/coverage`, `/scholar-compare`.
(The gate command is `/review-gate` rather than Kreate's `/code-review`, because a built-in `/code-review`
exists and could shadow the project command.)

### Hooks (each with a case table under `.claude/hooks/tests/`, as in Kreate)

| Hook | Event | Blocks / does |
|---|---|---|
| `enforce-pr-workflow.sh` | PreToolUse Bash | `git commit`/`push`/`merge` on `main` or `dev`, and any write to those remote refs (from Kreate) |
| `require-review.sh` | PreToolUse Bash | `git push` / `gh pr create` without an APPROVE record for the exact sha; `gh pr create` without a new learnings entry |
| `block-ai-attribution.sh` | PreToolUse Bash | Any `git commit`/`gh pr create|edit` whose message or body has a Claude co-author trailer or a "Generated with" footer (`.githooks/commit-msg` covers editor commits) |
| `enforce-backlog-cli.sh` | PreToolUse Write/Edit | Hand edits under `backlog/` (from Kreate; decision bodies are Edit-only) |
| `protect-data-dir.sh` | PreToolUse Write/Edit/Bash | Writes to `data/snapshots/` or `data/indexes/` (immutable), `rm` of them, and `git add -f data/` |
| `remind-token-contract.sh` | PostToolUse Edit | Touching `normalize.py` or the tokenizer → reminder to bump `TOKENIZER_VERSION` and run parity and differential tests |
| `load-learnings.sh` | SessionStart | Puts `.claude/learnings/INDEX.md` into every session's context |

### Branch protection (GitHub)

`dev` and `main` require a PR, with these checks green: `lint`, `test`, `claude-tooling`, `attribution`,
`learnings`, `review-attested`. No force-push, no deletion, and admins are included. `main` additionally
requires 1 approving review. Applied 2026-09-25, after the repo was made public (free-plan orgs can't
protect private repos). `dev` is the default branch, and merged feature branches are deleted
automatically.
