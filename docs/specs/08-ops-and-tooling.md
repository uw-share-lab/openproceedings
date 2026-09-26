# 08 — Ops and repo tooling

Status: **draft for review** · depends on: nothing · delivered in M0 (the roster grows with each milestone)

## Monorepo layout

```
openproceedings/
├── README.md  CLAUDE.md  AGENTS.md  CONTRIBUTING.md  LICENSE (MIT)
├── pyproject.toml  uv.lock      # uv WORKSPACE root: depends on the backend member; ruff, mypy-strict and pytest config; dev tools (ruff, mypy, pytest, hypothesis)
├── Makefile                     # sync · fmt · lint · tooling · test · hooks · mutate · mutate-changed
├── .claude/                     # committed: agents, skills, commands, hooks, learnings (roster: .claude/README.md)
├── .githooks/                   # commit-msg (attribution), pre-push (make lint + make tooling)
├── .github/                     # workflows (below), dependabot.yml
├── backend/                     # uv workspace member: Python package `openproceedings` (Python 3.12, .python-version)
│   ├── pyproject.toml
│   ├── src/openproceedings/
│   │   ├── ingest/              # 01: sources/, classify.py, dedup.py, snapshot.py, ris.py
│   │   ├── query/               # 02: normalize.py, lexer.py, parser.py, ast.py, canonical.py, defaults.py, compat.py
│   │   ├── engine/              # 03: protocol.py, reference.py (built); tantivy_engine.py, compile.py, rank.py, highlight.py
│   │   ├── semantic/            # 06 (phase 2)
│   │   ├── api/                 # 04: FastAPI app, routers, exporters/, records.py
│   │   ├── eval/                # 07 report generators
│   │   ├── diagnostics.py       # error-code registry (one Diagnostic shape; error-diagnostics skill)
│   │   ├── vocab.py             # venue/track/status vocabularies (spec 01), shared by ingest and query
│   │   ├── logs.py              # the only place logging is configured (logging-standards skill)
│   │   └── cli.py               # `op` entry point
│   └── tests/{unit,golden,differential,contract,fixtures}/
├── frontend/                    # (M3) Next.js app, npm workspace
├── docs/{specs,plans,results,design,usability,research}/   # created as needed
├── backlog/                     # Backlog.md: tasks, completed, docs, decisions — CLI only
├── deploy/                      # (M6, planned) Dockerfiles, compose.yml
└── data/                        # gitignored: cache/, snapshots/, indexes/, embeddings/, research/, records.sqlite
```

**Environment:** uv for all Python. `uv sync` at the root installs every workspace member and the dev tools
into one `.venv` from one `uv.lock`. New Python packages join by adding their directory to
`[tool.uv.workspace] members`. npm for the frontend. `scripts/setup-dev.sh` once per clone.

## CLI (`op`)

| Command | Does |
|---|---|
| `op ingest openreview\|proceedings\|ris … [--offline]` | fetch sources (`--offline`: cache only, no network) |
| `op snapshot build` · `op snapshot diff <a> <b>` | build an immutable snapshot, or compare two |
| `op index build [--snapshot <id>]` · `op index retire <index_version>` | build an immutable index; retire an old one (refuses if any search record pins it) |
| `op search "<q>" [--mode scholar] [--explain] [--engine tantivy\|reference] [--ids]` | search; `--engine reference` runs the oracle |
| `op export "<q>" --format ris\|csv\|bibtex\|jsonl [--index-version <v>]` | export the full matched set |
| `op record save "<q>" [--mode scholar]` · `op record replay <id>` | freeze a search as a search record (the same function as `POST /records`); replay one and print its status, `reproduced` / `drifted` / `mismatch` (the same function as `GET /records/{id}`) |
| `op serve` | run the API |
| `op embed build` | build embeddings for the current index (06) |
| `op eval scholar [--query <name>]` · `op eval coverage` · `op eval audit` · `op eval near-miss` | the 07 reports; `near-miss` is 06's recall@25 |
| `op openapi` | print the OpenAPI schema (feeds the frontend type codegen) |

The CLI and the API call the same functions, so the CLI alone is enough to run a whole review.

## Error handling

- `op` exits non-zero on any error and prints the same `{code, message}` (with diagnostics and spans for a
  parse error) that the API would return (04 §Error handling). It never prints a stack trace for bad input.
- `op record replay` exits non-zero on `mismatch` (`API_REPLAY_MISMATCH` is logged at ERROR) and zero on
  `reproduced` or `drifted`, so a script can tell a bug from drift.
- A gate hook blocks with exit 2 and says why on stderr. The formatting and reminder hooks (`autofix.sh`,
  `remind-token-contract.sh`) never block; they report back to the agent instead.
- `make lint`, `make tooling` and every CI job fail on the first error; nothing is retried silently.

## Testing

- Every hook has a case table under `.claude/hooks/tests/`, run by `make tooling` and CI `claude-tooling`.
- `make tooling` also runs the roster lint and the `.claude/README.md`, learnings-index and backlog checks.
- CLI commands are covered by the suites of the spec they call (07); the CLI adds only argument-parsing
  and exit-code tests.

## Code quality: autolint (skill: `autolint`)

Modelled on the lab's naturalschema repo:
1. `.claude/hooks/autofix.sh` (PostToolUse) formats and fixes each file as it's edited: ruff for Python,
   prettier and eslint for the frontend, and shellcheck (report only) for shell. It reports anything it can't
   fix back to the agent and never blocks.
2. `make fmt` fixes the whole repo. `make lint` is check-only and is exactly what CI runs.
3. `.githooks/pre-push` runs `make lint` and `make tooling`, so a push never surprises CI.

## Logging (skill: `logging-standards`)

stdlib `logging` with one JSON formatter, configured only in `logs.py`. Each line is an event constant with
structured fields. INFO is one line per unit of work, with one access line per API request. Nothing is
logged per record. Query text, abstracts, credentials and personal data are never logged.
`observability-reviewer` reviews every `backend/src/**` diff.

`op --log-format text` prints the same fields as one readable line per event, for reading logs locally.
JSON is the default everywhere, and CI, the API and anything collected use it. `--log-level` accepts
DEBUG, INFO, WARNING or ERROR in any case; anything else is a usage error (exit 2), never a traceback.

## CI (GitHub Actions): every workflow has `permissions: contents: read` and pins actions by SHA

| Workflow → required check(s) | Runs |
|---|---|
| `lint` → `lint` | `make lint` (ruff format/check, mypy --strict once `backend/src` exists, shellcheck, frontend prettier/eslint/tsc), then actionlint |
| `test` → `test` | pytest (unit, golden, differential@2k, contract); vitest; OpenAPI → TS types freshness |
| `claude-tooling` → `claude-tooling` | `make tooling`: roster lint, `.claude/README.md` and learnings index freshness, backlog hygiene (no Done task left in `tasks/`), every hook case table (`.claude/hooks/tests/`) and the tooling-script table (`.claude/scripts/tests/test-tooling-scripts.sh`) |
| `pr-gates` → `attribution`, `learnings`, `review-attested` | no AI authorship in commits or PR text; the branch adds or extends a learnings entry (unless labelled `no-learning`); the PR body attests APPROVE for the head sha |
| `nightly` (scheduled, not a PR check) | Three parallel jobs, each with its own time limit: the oracle-backed properties at 50,000 examples; the exhaustive tokenizer check (`OP_EXHAUSTIVE=1`) plus every other property at 50,000; and `make mutate` (every mutant in `.claude/scripts/mutants/*.json` killed or documented as equivalent). Differential@50k and full-corpus parity join it with the Tantivy engine (task-057, M4) |
| *(planned, M1+)* `e2e`, `bench` | Playwright; pytest-benchmark vs main |

`review-attested` is an **honesty check** against forgetting to review, not an access control. Anyone who
can edit the PR body could paste the marker. The access control is branch protection plus human review on
`main`. A same-repo `dev → main` promotion is exempt from `learnings` and `review-attested`. The exemption
checks the head repo, so a fork branch named `dev` cannot use it.

## Git and PR rules

- `feature → PR → dev → PR → main`. No direct commits, pushes or merges on `dev` or `main`
  (`enforce-pr-workflow.sh`, from Kreate). `main` also needs a second person's approval.
- Branch names: `<type>/<slug>` (`feat/`, `fix/`, `chore/`, `docs/`, `test/`).
- **Review before push:** `/review-gate` sends the diff to the required reviewers (routing table in the
  `review-gates` skill). Every finding is dispositioned, and `record-review.py` writes an APPROVE record for
  the exact sha. `require-review.sh` blocks `git push` / `gh pr create` without one. `/open-pr` attests it in
  the PR body for CI.
- **Learnings every time:** a PR adds or extends a `.claude/learnings/` entry (`/record-learnings`), unless
  labelled `no-learning`. Every session starts with the index loaded.
- **Keep everything current** (skill: `task-hygiene`): tasks, docs, specs and READMEs change in the same
  commit as the behaviour. Finished tasks leave `backlog/tasks/` via `backlog task complete <id>`.
- **No AI authorship** in commits or PRs (project decision 2026-09-25). `.claude/` is committed.
- Secrets (OpenReview credentials) live only in `.env` (gitignored, mode 600). `data/` is never committed.

## Deploy (M6, planned)

`deploy/compose.yml`: `api` (uvicorn, loads `data/indexes/current`) and `web` (Next.js standalone), with
Caddy in front for TLS. The data volume is read-only in `api`, except `records.sqlite`. Refreshing the index
means building a new `index_version` offline, switching the `current` symlink, and sending SIGHUP. Hosting is
still open (00, question 5).

---

## `.claude/` roster

The roster follows the Kreate model:
- **Skills** hold standards and domain knowledge.
- **Agents** do work and cite the skills. Reviewer, auditor and guardian agents are read-only.
- **Commands** are thin entry points.
- **Hooks** enforce the gates.

Kreate splits `.claude/` per project. Our parts share one query contract, so this repo uses **one root
`.claude/`** with names grouped by area.

**The authoritative list is [`.claude/README.md`](../../.claude/README.md).** It is generated from the
files' frontmatter by `.claude/scripts/roster_index.py`, and CI fails if it is stale. This spec deliberately
does not repeat the list, because a hand-kept copy is how counts drift. As of M0 there are **49 agents,
53 skills and 17 commands** (target range 25–150 of each), across these areas:
- global roles and process (including `learning-recorder` and the review gate);
- engineering standards (including `autolint`, `logging-standards`, `observability-reviewer`);
- ingestion;
- query language;
- search engine;
- backend API;
- frontend;
- human-centred design and HCI (UX designer and writer, HCI and user researchers, usability tester and
  auditor, data-viz designer);
- semantic layer;
- evaluation and research;
- ops.

New agents and skills are added when a milestone brings a new recurring task, never speculatively. Each
needs an area in `roster_index.py` and a path reference from something that uses it (the lint rejects
orphans).

The gate command is `/review-gate` rather than Kreate's `/code-review`, because a built-in `/code-review`
exists and could shadow the project command.

### Hooks (each with a case table under `.claude/hooks/tests/`, as in Kreate)

| Hook | Event | Blocks / does |
|---|---|---|
| `enforce-pr-workflow.sh` | PreToolUse Bash | `git commit`/`push`/`merge` on `main` or `dev`, and any write to those remote refs (from Kreate) |
| `require-review.sh` | PreToolUse Bash | `git push` of any unreviewed commit (every refspec source, `--all`); `gh pr create`/`new` without an APPROVE record for the head, or without an added or extended learnings entry |
| `block-ai-attribution.sh` | PreToolUse Bash | A message-writing git command or PR-writing gh command whose text (incl. heredocs, `--trailer`, `-F` files) has a Claude co-author trailer or "Generated with" footer; `.githooks/commit-msg` covers editor commits |
| `enforce-backlog-cli.sh` | PreToolUse Write/Edit/MultiEdit/NotebookEdit | Hand edits under `backlog/` (from Kreate; decision bodies are Edit-only) |
| `protect-data-dir.sh` | PreToolUse Write/Edit/MultiEdit/NotebookEdit/Bash | Any write into, move of or deletion of `data/snapshots/`, `data/indexes/` (or `data/` itself), incl. globs expanded against the filesystem (`rm -rf data*`, `*`), redirects, `cp`/`rsync`/`tee`/`dd`/`truncate`, `find -delete`, `sed -i`; `git clean -x/-X` and `git stash --all` (they remove gitignored `data/`); `git add -f data/`; and shell `mv`/`git mv`/`cp`/`rm`/redirects into `backlog/` (only the CLI moves tasks) |
| `autofix.sh` | PostToolUse Write/Edit/MultiEdit | Formats and fixes the edited file; reports what remains (never blocks) |
| `remind-token-contract.sh` | PostToolUse Write/Edit/MultiEdit | Editing `normalize.py` or the tokenizer → reminder to bump `TOKENIZER_VERSION` and run the parity and differential tests |
| `load-learnings.sh` | SessionStart | Puts `.claude/learnings/INDEX.md` into every session's context |

All command-parsing gates share `.claude/hooks/lib/cmdparse.py`, which parses commands the way bash splits
them:
- separators with or without spaces: `;` `&&` `||` `|` `&` `(` `)`, newlines, and process substitution
  `<(…)`/`>(…)`;
- shell reserved words at the start of a command (`if`/`then`/`elif`/`else`/`fi`, `while`/`until`/
  `do`/`done`, `{`/`}`, `!`, `esac`, `function`) are skipped;
- `VAR=val` assignments and the wrappers `env`, `command`, `builtin`, `exec`, `time`, `nohup`, `nice`,
  `sudo`, `timeout`, `stdbuf`, `xargs` and `watch` are skipped, each with its own table of options that take
  a value;
- command names are compared by basename (`/usr/bin/git`);
- one pass over the whole text carries quote state across lines, so a multi-line quoted message
  stays one word; `#` starts a comment only at the start of an unquoted word, as in bash; an unquoted
  `<<DELIM`/`<<'DELIM'` heredoc body is dropped unread (never `<<<`);
- redirections come out of argv as separate `(operator, target)` pairs;
- it follows `cd`, `-C`, `bash -c` and `eval`.

`enforce-pr-workflow.sh` uses the same tokenizer. A command the parser cannot read is **blocked**, never
allowed, when it looks like what a gate guards (fail closed). The threat model is honest mistakes, not
deliberate evasion.

### Mutation testing

`.claude/scripts/mutate.py` (`make mutate`, `make mutate-changed`, `--match <text>`) proves the case tables
have teeth. Each mutant in `.claude/scripts/mutants/*.json` breaks one piece of gate or tooling logic, and at
least one table must fail. Survivors are either fixed with a new row or documented as `equivalent`, with
the reason. Mutants run in parallel: the full set takes minutes, and `--changed` takes seconds. Reviews run
`make mutate-changed`; the nightly workflow runs everything. Never hand-roll a serial loop.

### Branch protection (GitHub)

`dev` and `main` require a PR, with these checks green: `lint`, `test`, `claude-tooling`, `attribution`,
`learnings`, `review-attested`. No force-push, no deletion, admins included, and conversations must be
resolved. `main` additionally requires 1 approving review. This was applied on 2026-09-25, after the repo was
made public (free-plan orgs can't protect private repos). `dev` is the default branch, and merged feature
branches are deleted automatically.
