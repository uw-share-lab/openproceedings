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

## Layout (monorepo)
- Root: `pyproject.toml` is the **uv workspace** root, with repo-wide ruff config and one `uv.lock`.
  `Makefile` has `sync`, `fmt`, `lint`, `tooling`, `test`, `e2e`, `openapi`, `changelog`, `hooks`, `mutate` and
  `mutate-changed` (`make help`). `CHANGELOG.md` is generated (`make changelog`; spec 08 §Release, decision-023).
- `backend/`: the uv workspace member, Python package `openproceedings` (`cli.py` → `op`, `search.py` (one
  ranked search, which `op search` and the API search route both run), `export.py`, `logs.py`,
  `diagnostics.py`, `vocab.py`, `storage.py`, `records.py` (search records: `ids_hash`, the append-only store, replay), `coverage.py` (the snapshot manifest's venue × year × track × status breakdown), `official_counts.py` (official accepted counts and the M4 gate), `takedowns.py` (the takedown list and log, decision-022) and `takedown_check.py` (`op takedown check`), `timestamps.py` (the API's one UTC `Z` timestamp form), `query/` (`normalize.py`, `mathsyms.py`, `lexer.py`, `parser.py`,
  `ast.py`, `canonical.py`, `defaults.py`, `clauses.py` (each filter field's clause for facet clicks), `groups.py` (a query's concept groups, for the search route's per-group counts, TASK-176), `wordforms.py` (where a `$` can be added to the terms the Scholar-mode no-stemming notice names, for the UI's "Add `$`"; TASK-175), `compat.py`), `engine/` (`protocol.py`, `reference.py`, `index.py`, `compile.py`, `tantivy_engine.py`, `exclusions.py`, `highlight.py`, `parity.py`), `ingest/`
  (`record.py`, `caps.py` (the ingest caps: 8 combining marks per run, 1,000-character titles, 20,000-character abstracts, flagged; decision-026), `classify.py`, `urls.py`, `volumes.py` + `pmlr_volumes.toml` (the PMLR volume table), `ris_offsets.toml` (each RIS cache entry's Publish or Perish UTC offset, read by `ris.py`; decision-025), `statuses.py` (statuses indexed per source), `ris.py`, `dedup.py`, `reconcile.py` (after dedup: OpenReview acceptance the crawled proceedings don't list → `unknown`, decision-005), `snapshot.py`, `status_check.py` (statuses a venue-year's sources can't supply, reported by the build), `sources/` (crawlers:
  `http.py` (the one HTTP layer every crawler shares: transport, host allowlist, pacing, retries, atomic cache with a per-`Policy` TTL, the `SourceError` hierarchy; plus the proceedings page fetcher), `common.py` (crawl reports, markers, and `Crawls`: the one ingest loop and the one replay), `openreview_client.py` (OpenReview's policy and login on top of `http.py`), `openreview_v2.py` and `openreview_v1.py` (per-year API v1 adapters) → `op ingest openreview`; `iclr.py`, `neurips.py`, `pmlr.py`, `crawl.py` → `op ingest iclr|neurips|pmlr`, and `crawl.replay_all`, what `op snapshot build` replays)), `api/` (`app.py`
  `create_app`, `config.py`, `state.py` (the served index and `pinned`, the one loader of
  other index_versions), `deps.py`, `errors.py`, `middleware.py`, `models.py` (the response
  contract), routers `search.py` (parse and search), `papers.py`, `records.py`, `meta.py`, `coverage.py`, `health.py`, `export.py`
  (streamed exports, `op export`'s writers), `server.py` → `op serve`, `openapi.py` → `op openapi`);
  `eval/` (`coverage_report.py` → `op eval coverage`, TASK-054; `scholar_compare.py` (a RIS set against a query's result on one index: matching by the merge rules, scope, and every disagreement's class; the one implementation, TASK-056/TASK-177) and `scholar_report.py` → `op eval scholar`; the other reports arrive with their tasks),
  no `semantic/` in v1: spec 06 is deferred to phase 2 by decision-017). Tests in `backend/tests/`; `uv run pytest` from the root.
- **API contract:** after changing a route or a response model, run `make openapi` and commit both
  `backend/tests/contract/openapi.json` (the snapshot) and `frontend/src/api/schema.ts` (generated from it;
  never hand-edited). A contract test and CI's `test` job fail while either is stale (`api-contract` skill).
- Root `package.json` is the **npm workspace** root (`workspaces: ["frontend"]`, one `package-lock.json`,
  dependencies hoisted to `./node_modules`; Node from `.nvmrc`).
- `frontend/`: Next.js App Router + TypeScript strict, `output: "standalone"`, Tailwind v4 + shadcn tokens
  (`src/app/globals.css`), `src/lib/search-state.ts` (the URL↔state reducer: `q` is the only result-set
  state), `src/api/spans.ts` (code-point spans → UTF-16), `src/api/schema.ts` (generated by `make openapi`),
  `src/api/client.ts` (the one typed client, `openapi-fetch` over `schema.ts`), `src/lib/security-headers.ts`
  (CSP and the other headers, set by `next.config.ts`), `src/lib/takedown-contact.ts` (the takedown contact from
  `NEXT_PUBLIC_TAKEDOWN_CONTACT`, checked by `next.config.ts`), `src/components/` (`site-nav.tsx`, `site-footer.tsx`
  (the takedown contact on every page, TASK-133), `theme-picker.tsx`,
  `theme-provider.tsx`, `providers.tsx` (API client + TanStack Query), `search/` (the workspace), `coverage/` and
  `help/` (the `/coverage` and `/help/syntax` pages, TASK-045; `coverage/coverage-line.tsx` is the home page's
  coverage line in the same words, TASK-110)), `src/editor/` (CodeMirror 6 + a token-only Lezer
  grammar whose tables and golden are generated from `lexer.py`; `codemirror-lezer` skill), `src/builder/` (the
  concept-group builder and the Text/Builder tabs: reads the server `ast`, writes the draft back only after an
  edit; its read golden is generated by `backend/tests/contract/test_frontend_builder_golden.py` and its write
  golden is checked there; TASK-043; after a search each group shows its wildcards' expansions, and a read-only
  query shows its parts that fit, dimmed, TASK-111; and each group's count alone from the search response's `groups`,
  while the draft is the searched query, TASK-176), `src/help/syntax-golden.json` (generated by
  `backend/tests/contract/help_golden.py`). The home and search pages have the editor (TASK-041); the search page
  also has the results, banner, sidebar and paging, and the paper page the full record (TASK-042); the search
  page's Export menu and Save, the record page and the methods text are `src/components/export/`,
  `src/components/record/` and `src/lib/{export,methods-text,replay-status}.ts` (TASK-044; tested against
  `record-fixture.json`, real API answers kept current by `test_frontend_record_fixture.py`). Tests are Vitest + Testing Library
  (`src/**/*.test.{ts,tsx}`); `npm test --workspace frontend`. Full-stack browser, accessibility and
  visual tests live in `frontend/e2e/`, backed by `backend/tests/e2e/`; run them with `make e2e`.
- `deploy/`: `compose.yml` (api + web + Caddy, plus the `ops` and `takedown-check` one-offs), `Caddyfile`, `api.Dockerfile`, `caddy.Dockerfile`, `index-permissions.sh`, `smoke-test.sh` (the stack over a fixture, by hand) and `README.md` (the operator's runbook), TASK-065; `web.Dockerfile` and `web-build-gate.sh` (the `web` image; a public build needs a takedown contact, TASK-136; built by CI's advisory `web-image` workflow, TASK-148); every base image digest-pinned (TASK-149). `backend/tests/deploy/fixture_data.py` writes the smoke test's data directory.
- `docs/specs` · `docs/{plans,results,design,usability,research}` (created as needed); `docs/README.md` indexes them.
- `backlog/`: Backlog.md, CLI only.
- `.claude/`: agents, skills, commands, hooks and learnings, all committed. The roster is in
  `.claude/README.md`.
- `data/`: gitignored; snapshots and indexes are immutable.

## Environment
- **uv** for Python. `uv sync` at the repo root; never `pip install` into the workspace.
- **npm** for the frontend: `npm ci --ignore-scripts` at the repo root (or `make sync`), never inside `frontend/`. Node 22
  (`.nvmrc`, as in CI).
- `scripts/setup-dev.sh` once per clone (git hooks, `.env`).

## Tooling (`.claude/`)
- **Agents** (`.claude/agents/`) do work. Reviewer, auditor and guardian agents are read-only.
- **Skills** (`.claude/skills/`) hold the standards and domain knowledge that agents cite.
- **Commands** (`.claude/commands/`) are entry points: `/review-gate`, `/open-pr`, `/record-learnings`,
  `/plan`, `/exactness-check`, …
- The roster is linted in CI (`make tooling`). A new agent, skill or command must pass the lint and be
  given an area in `.claude/scripts/roster_index.py`, which regenerates `.claude/README.md`.

## Keep everything current (rule, 2026-09-25; `.claude/skills/task-hygiene/SKILL.md`)
- **Backlog tasks, docs, specs, READMEs and every `.md` are updated continuously**, in the same commit as
  the change they describe. Never in a later catch-up PR.
- Tick acceptance criteria as you meet them. Note follow-ups when you find them and file them as tasks
  at the end of the branch, after rebasing onto `dev` (new ids are created last: `task-hygiene` §Ids).
- **When a task is Done, run `backlog task complete <id>`**, which moves it to `backlog/completed/`. CI fails
  on a Done task left in `backlog/tasks/`, and on two tasks or two decisions that share an id.
- `docs-reviewer` runs on every diff.

## Tests never call real APIs (rule, 2026-09-25)
No test, fixture, CI job or review script reaches OpenReview, Semantic Scholar, PMLR, Scholar or any other
live service. `backend/tests/conftest.py` refuses every non-loopback connection and DNS lookup for the whole
session (`NetworkBlockedError`, no opt-out): TCP and UDP to non-loopback addresses and every name lookup, forward or reverse.
It does not reach subprocesses or `multiprocessing` spawn children, so tests don't spawn network clients.
Its mutants are in `.claude/scripts/mutants/gates.json` (case table `test-network-guard.sh`). Crawler and client code is tested against recorded HTTP
fixtures under `backend/tests/fixtures/`; recording them is a separate, manual `op ingest` run, never a test.

## Code quality
- **Autolint** (`.claude/skills/autolint/SKILL.md`): `autofix.sh` formats and fixes each file as it's edited
  (ruff, prettier, eslint, shellcheck).
- `make lint` is exactly what CI's `lint` job runs. The pre-push hook runs `make lint` and `make tooling`.
  `make fmt` fixes the whole repo.
- **Logging** (`.claude/skills/logging-standards/SKILL.md`): structured JSON, one line per unit of work, and
  no query text, abstracts, credentials or personal data. `observability-reviewer` checks every
  `backend/src/**` diff.

## Enforced gates (hooks in `.claude/hooks/`, case tables in `.claude/hooks/tests/`)
| Hook | Enforces |
|---|---|
| `enforce-pr-workflow.sh` | `main` and `dev` take no direct commits (cherry-pick, revert, am and rebase included, and after a `checkout`/`switch` to them in the same command), pushes (glob and `:` refspecs included, and a refspec-less push whose repo config picks the target), merges or ref moves (`update-ref`, `reset`, `branch -f`/`-M`/`-C`, `checkout -B`, `switch -C`, `worktree add -B`, a fetch into them). A commit or push whose directory, refspec or branch it can't resolve (`cd "$X"`, `HEAD:$UNSET`) is refused, and so is a push after a checkout/switch/worktree add that writes an upstream, and an unparseable command with `git` and a write word in it. Flow: `feature → PR → dev → PR → main`. |
| `require-review.sh` | `git push` / `gh pr create` need an **APPROVE record for the exact HEAD sha**, written by `record-review.py` after `/review-gate`; `--tags`, glob refspecs and the matching refspec `:` are refused, and so is a refspec-less push whose config (`-c` or the repo's) picks what is pushed, and a push after any git command in the same call but one that moves no ref (status, log, diff, add, a fetch without a `src:dst` refspec or `--stdin`, …: push in its own call). `gh pr create` also needs an added or extended learnings entry. No record under `op-reviews/` is written by hand (Bash or a file tool). |
| `block-ai-attribution.sh` | No `Co-Authored-By: Claude` or "Generated with Claude Code" in commits, PRs or release notes, in the raw text or any word as bash reads it (`'Cl''aude'`), and in any file a `cat`/`head`/`tail`/`sed` or `-F` reads (variables put in; sed script files from `-f`/`--file` included, including bundled `-nf`; input filenames after `--` are literal); a message file it can't resolve, or another program run on a file in a `$(…)`, is refused (TASK-170). `.claude/` is committed; authorship is not. |
| `enforce-backlog-cli.sh` | No hand edits under `backlog/`. Use the `backlog` CLI. (Decision *bodies* may be edited, since the CLI can't write them.) |
| `protect-data-dir.sh` | `data/snapshots/` and `data/indexes/` are immutable. `data/` and any `takedowns/` directory are never committed. No shell edits under `backlog/`. Paths are judged after `~`, `$PWD`, `$(pwd)`, `$(git rev-parse …)`, `$(mktemp)`, `for` loop variables and other variables are resolved (when they can be; `~`, HOME, TMPDIR and USER also as '') and `cd`/`pushd`/`popd` followed, each against the worktree that contains it (case-blind); one it can't resolve (a redirect target too), or a command it can't parse, is refused where the main worktree has `data/`. `--output` files and `git format-patch`'s output directory are writes. |
| `remind-token-contract.sh` | Reminds you to bump `TOKENIZER_VERSION` and run the parity and differential suites after a tokenizer edit. |
| `load-learnings.sh` | Every session starts with `.claude/learnings/INDEX.md` in context. |
| `autofix.sh` | After every edit: formats and fixes the file, then reports what it couldn't fix. Never blocks. |

Every gate fails closed: a command it can't parse is refused where it matters, and an internal error exits 2
(a crash would exit 1, which Claude Code lets through). block-ai-attribution, require-review and protect-data-dir
also exit 2 when Python can't run (no python3), and read the payload on stdin, so a command past ARG_MAX is still
read; so does enforce-pr-workflow (TASK-172), which falls back to its text check when Python can't run (a git write word is refused). Every raw-text scan joins line continuations with cmdparse's one `join_continuations` (TASK-164). A command inside a `"$(…)"`,
backquotes or an unquoted heredoc body is checked like any other, and one with `~` or `$` is read again with
HOME/TMPDIR/USER as '' in every gate (`cd ~` stays put, and a `cd ~/<path>` that doesn't exist that way is a failed cd) (TASK-156). The case tables count only exit 2 as a block. Probes in them are data: `lint_probes.py` (in `make tooling`) refuses a row whose
probe, label or command holds a `$(…)` or backquote bash would run, and `.claude/scripts/probe_hook.py` feeds a reviewer's probe to a
hook or cmdparse from a file, never through a shell (TASK-169).

After editing any hook or tooling script, run `make tooling`. It runs every case table in
`.claude/hooks/tests/` and `.claude/scripts/tests/`, in parallel, in about 15 seconds. Then run
`make mutate-changed`, so each mutant of the logic you touched is killed by some row (spec 08 §Mutation
testing).

## Closing workflow (required, in this order; approvals are per-commit)
1. **Tests and lint green** locally, scaled by risk: the runs the `pr-workflow` skill §Local test runs table gives
   for what the diff touches (often the full `make test`), and always `make lint` and `make tooling`; CI's `test`
   job runs the full suite on every PR (pytest-xdist, properties at 200 examples; nightly reruns it at 2,000, the differential at 50,000). Never claim a pass you didn't run.
2. **Backlog current**: acceptance criteria checked and a final summary written. For finished tasks, run
   `backlog task complete <id>`.
3. **Docs as-built** in the same branch: specs, READMEs, skills and `.claude/README.md` (`docs-writer`).
4. **Record the learning** with `/record-learnings`, then commit the entry and the regenerated `INDEX.md`.
5. **`/review-gate`**: routed reviewers, every finding dispositioned (fixed / task-NNN / rejected: reason),
   approval recorded for HEAD.
6. **Push, then `/open-pr`** into `dev`. CI must pass: `lint`, `test`, `claude-tooling`, `attribution`,
   `learnings`, `review-attested`. A green PR goes into `dev`'s merge queue (`gh pr merge <n> --auto`; active
   since 2026-10-02, decision-027); it is not rebased just because `dev` moved (`pr-workflow` skill §Merge method).
7. **After it merges**, remove the PR's worktree (`git worktree remove`) and local branch. A worktree with
   uncommitted work is archived as a patch first, never deleted blind.

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
