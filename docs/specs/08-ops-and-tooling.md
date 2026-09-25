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
├── docs/{specs,plans,results,decisions}/
├── deploy/                      # Dockerfiles, compose.yml
└── data/                        # gitignored: cache/, snapshots/, indexes/, records.sqlite
```

## CLI (`op`)

`op ingest …` · `op snapshot build|diff` · `op index build [--snapshot]` · `op search "<q>" [--explain]
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
| `claude-tooling` | Frontmatter lint for every agent and skill (name, description, tools), plus the hook test scripts |

## Git and PR rules (enforced by hooks)

- `feature → PR → main`. No direct commits or pushes to `main`. Before pushing, run `/code-review` and fix
  the must-fix findings.
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

Target for M0: **40 agents, 42 skills** (inside the 25–150 range). New ones are added when a
milestone brings a new recurring task, never speculatively.

### Agents (40)

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

### Skills (42)

| Area | Skills |
|---|---|
| Repo (6) | `repo-conventions`, `pr-workflow`, `no-ai-attribution`, `spec-writing`, `learnings` (dated journal, as in Kreate), `decision-records` |
| Engineering (5) | `python-standards`, `typescript-standards`, `testing-standards`, `property-testing`, `error-diagnostics` (one shape for errors and diagnostics across layers) |
| Ingestion (8) | `openreview-api` (v1 vs v2, auth, 429s, venueid is authoritative), `openreview-venueids` (all known forms), `pmlr-proceedings`, `neurips-proceedings`, `record-schema`, `track-taxonomy`, `dedup-rules`, `snapshots` |
| Query (5) | `query-grammar`, `token-contract` (the 02 normalization rules), `wildcards-and-expansion`, `scholar-syntax-compat`, `default-filters` |
| Engine (5) | `tantivy-indexing`, `ast-compilation`, `reference-oracle`, `field-weighted-bm25`, `index-versioning` |
| API and exports (5) | `fastapi-conventions`, `api-contract`, `ris-format`, `bibtex-format`, `search-records` |
| Frontend (4) | `nextjs-conventions`, `codemirror-lezer`, `ui-design-system`, `accessibility` |
| Research and eval (3) | `prisma-reporting`, `scholar-comparison-protocol`, `coverage-reporting` |
| Semantic (1) | `specter2-embeddings` (model pinning, the "never changes the set" rule) |

### Commands (≈12)

`/code-review`, `/review-pr`, `/security-review`, `/audit`, `/write-docs`, `/plan`, `/exactness-check`
(runs `exactness-guardian` + `differential-tester`), `/coverage`, `/scholar-compare`, `/review-export`,
`/log-learning`, `/new-spec`.

### Hooks (each with a test script under `.claude/hooks/tests/`, as in Kreate)

| Hook | Event | Blocks / does |
|---|---|---|
| `enforce-pr-workflow.sh` | PreToolUse Bash | `git commit`/`push`/`merge` on `main` |
| `block-ai-attribution.sh` | PreToolUse Bash | Any `git commit`/`gh pr create` whose message or body contains Claude co-author or "Generated with" lines |
| `protect-data-dir.sh` | PreToolUse Write/Edit | Writes into `data/snapshots/` or `data/indexes/` (immutable) and `git add -f data/` |
| `remind-token-contract.sh` | PostToolUse Edit | Touching `normalize.py` or the tokenizer → reminds you to bump `TOKENIZER_VERSION` and run parity tests |
