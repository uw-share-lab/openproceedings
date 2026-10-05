# 08 — Ops and repo tooling

Status: **draft for review** · depends on: nothing · delivered in M0 (the roster grows with each milestone)

## Monorepo layout

```
openproceedings/
├── README.md  CLAUDE.md  AGENTS.md  CONTRIBUTING.md  LICENSE (MIT)  CHANGELOG.md (generated: §Release)
├── pyproject.toml  uv.lock      # uv WORKSPACE root: depends on the backend member; ruff, mypy-strict and pytest config; dev tools (ruff, mypy, pytest, hypothesis)
├── package.json  package-lock.json  .nvmrc   # npm WORKSPACE root (workspaces: ["frontend"]); deps hoisted to ./node_modules; Node 22
├── Makefile                     # sync · fmt · lint · tooling · test · e2e · openapi · changelog · hooks · mutate · mutate-changed
├── .claude/                     # committed: agents, skills, commands, hooks, learnings (roster: .claude/README.md)
├── .githooks/                   # commit-msg (attribution), pre-push (make lint + make tooling)
├── .github/                     # workflows (below), dependabot.yml
├── backend/                     # uv workspace member: Python package `openproceedings` (Python 3.12, .python-version)
│   ├── pyproject.toml
│   ├── src/openproceedings/
│   │   ├── ingest/              # 01: record.py, classify.py, urls.py, volumes.py (+ pmlr_volumes.toml), ris.py, dedup.py, snapshot.py (built); sources/ (M4 crawlers: http.py (the one HTTP layer), common.py, openreview_client.py, openreview_v2.py, openreview_v1.py, iclr.py, neurips.py, pmlr.py, crawl.py)
│   │   ├── query/               # 02: normalize.py, mathsyms.py, lexer.py, parser.py, ast.py, canonical.py, defaults.py, compat.py
│   │   ├── engine/              # 03: protocol.py, reference.py, index.py, compile.py, tantivy_engine.py, exclusions.py, highlight.py, parity.py
│   │   ├── semantic/            # 06 (deferred: phase 2, decision-017; not created)
│   │   ├── api/                 # 04: app.py, config.py, state.py, deps.py, errors.py, middleware.py, models.py, openapi.py, server.py; routers search.py, papers.py, meta.py, coverage.py, records.py, export.py, health.py
│   │   ├── eval/                # 07 report generators
│   │   ├── diagnostics.py       # error-code registry (one Diagnostic shape; error-diagnostics skill)
│   │   ├── vocab.py             # venue/track/status vocabularies (spec 01), shared by ingest and query
│   │   ├── logs.py              # the only place logging is configured (logging-standards skill)
│   │   ├── storage.py           # locks, staging, fsync and read-only sealing for snapshots and indexes
│   │   ├── export.py            # 04 exports (RIS, CSV, BibTeX, JSONL), shared by `op export` and the API
│   │   ├── search.py            # one ranked search, run by `op search` and `GET /search`
│   │   ├── records.py           # search records: ids_hash, the append-only store, replay (04 §Search records)
│   │   ├── coverage.py          # the snapshot manifest's venue × year × track × status breakdown (`GET /coverage`)
│   │   ├── timestamps.py        # the API's one timestamp form (UTC, `Z`)
│   │   ├── takedowns.py         # the takedown list and log (TASK-136, decision-022)
│   │   ├── takedown_check.py    # `op takedown check`: does a running API serve a listed abstract?
│   │   └── cli.py               # `op` entry point
│   └── tests/{unit,golden,differential,bench,contract,e2e,deploy,fixtures}/
├── frontend/                    # npm workspace member: Next.js App Router, output standalone (spec 05; skeleton TASK-039)
├── docs/{specs,plans,results,design,usability,research}/   # created as needed; docs/README.md: the index; docs/releases.toml: each release's data (§Release)
├── backlog/                     # Backlog.md: tasks, completed, docs, decisions — CLI only
├── deploy/                      # compose.yml, Caddyfile, api.Dockerfile, caddy.Dockerfile, index-permissions.sh, smoke-test.sh, README.md (the runbook) (TASK-065); web.Dockerfile, web-build-gate.sh (TASK-136)
└── data/                        # gitignored: cache/, snapshots/, indexes/, embeddings/, research/, records/ (records.sqlite), takedowns/ (list and log; under compose the list only, the log elsewhere: §Deploy)
```

**Environment:** uv for all Python. `uv sync` at the root installs every workspace member and the dev tools
into one `.venv` from one `uv.lock`. New Python packages join by adding their directory to
`[tool.uv.workspace] members`. npm for the frontend. `scripts/setup-dev.sh` once per clone.

## CLI (`op`)

| Command | Does |
|---|---|
| `op ingest openreview\|iclr\|neurips\|pmlr\|ris … [--offline]` | fetch sources (`--offline`: cache only, no network) |
| `op snapshot build [--takedowns <file>]` · `op snapshot diff <a> <b>` | build an immutable snapshot, or compare two. The build withholds every abstract on the takedown list (default `<data-dir>/takedowns/withheld.txt`, which may be absent until a snapshot, under the output directory or `<data-dir>/snapshots/`, has withheld an abstract: then it is required, as a file named with `--takedowns` always is; TASK-067; §Deploy, decision-022): a list that doesn't parse refuses it; its JSON names `withheld_ids` (the ids whose abstract it took out), `takedowns_followed` (a listed id this build holds under another id → that id, also withheld), `takedowns_unmatched` (listed ids it has no record of) and `takedowns_twins` (a twin of a withheld record → the id it is the twin of, also withheld: decision-029, TASK-163), the last three also said on stderr (a twin with what to list and log). The diff's `abstract_withheld` names the ids withheld (`added`) and no longer withheld (`lifted`) between the two. There is no prune or delete command: keep the snapshot of every index a search record pins (the versions `op index retire` refuses), since that record's exports read it to attribute each abstract and withhold every abstract without it (decision-021); a future prune command must refuse while a record pins an index built from the snapshot |
| `op index build --snapshot <dir\|name\|hash prefix> [--out <dir>]` · `op index parity --index <v> [--snapshot <id>]` · `op index retire <index_version> [--dry-run]` (TASK-085) | build an immutable index; check it holds `normalize()`'s tokens for its snapshot (local, over the real corpus); retire an old one: delete `<data-dir>/indexes/<index_version>/` under the indexes lock `op index build` holds: set aside as `.retiring-<index_version>` (no reader finds half an index, and no sweep deletes it), checked once more, then renamed to `.tmp-retire-<index_version>` (the commit point) and removed; the next build or retire sweeps a removal cut short. Refused, exit 1, one line to stderr, nothing touched: while any search record pins it (`RecordStore.pinned`, the count reported; a deleted pinned index would leave those records' replays permanently `drifted`), while `current` or any other symlink in `indexes/` points at it, when the record store can't be read, or when the name isn't an index_version directory directly under `indexes/` (the name is checked against the index_version format before any path is built, so `../x` never names a path). `--dry-run` runs the checks and reports the outcome with the same exit status, deleting nothing. Order: repoint `current` to the new version, SIGHUP the API, confirm `/api/v1/meta` reports the new version, then retire the old one (the API keeps serving the old version until its reload). It can't see an `op serve --index <index_version>` that serves the version by name: check what each running instance serves first. A promotion (`ln -sfn`) and a record save take no indexes lock, so after the rename the pins and every symlink's target are checked again and a hit, or anything raised (Ctrl-C included), renames the directory back and refuses or re-raises. If that rename-back fails, one ERROR `index_retire_restore_failed` names the `.retiring-` directory and the operator must `mv` it back to `<index_version>` before serving it or running another build or retire (no sweep touches it; until then every retire of that version, `--dry-run` included, is refused as `retire_cut_short`, whether `<index_version>` is absent or was rebuilt); what remains is the few syscalls between that check and the removal, after which a save or replay naming the version finds it absent. It says so when it waits for the lock. A chmod or removal that fails after the rename still retires the version (its name is gone) and reports `tmp_left`; a sweep that can't remove a leftover logs `tmp_sweep_failed` and carries on, so it never fails a later build. One log line: `index_retired` (INFO; WARNING with `tmp_left`), `index_retire_checked` (dry run) or `index_retire_refused` (WARNING; DEBUG for a malformed name, which is not logged), each with the version, the pinned count and the outcome or reason |
| `op search "<q>" [--mode scholar] [--explain \| --ids] [--engine tantivy\|reference] [--sort <s>] [--limit <n>] [--index <dir\|version>]` | ranked hits under a PRISMA header (default): searched time, index, crawl window (first to last fetch), tokenizer and query versions; a bootstrap-corpus caution when the index holds only RIS, or a caution that the sources are unknown when its snapshot isn't in the data dir or its hash differs; identified, removed by default filters (ineligible and unclassified), screened; the canonical and identification strings; every wildcard's expansion (its count and first 10 terms; every term with `--explain`); the sorted id set (`--ids`; `--engine reference` runs the oracle over the index's snapshot, `--ids` only); or the compiled query (`--explain`). Diagnostics go to stderr as user output; one `search_run` INFO line per run (task-030) |
| `op export "<q>" --format ris\|csv\|bibtex\|jsonl [--mode scholar] [--index <dir\|version>] [--out <file>]` | export the full matched set in id order (spec 04 §Exports), streamed to stdout or written whole to `--out` (never a partial file); the count is checked against the query's total. It verifies the index's snapshot to name each abstract's source (TASK-138); without it, every abstract is withheld and each record says so, with a warning on stderr and exit 0 (decision-021). It withholds the takedown list's abstracts as the API does (decision-022), under any other id the exported version holds a listed paper under (merges and globally unique native ids, `takedowns.same_paper`; a damaged snapshot's merges are skipped with a warning on stderr; TASK-067), and on its twins (the exported snapshot's and the current index's `twin` claims, TASK-163; a current index whose snapshot can't be read leaves its claims out, with one ERROR `takedown_twins_unavailable` and a warning on stderr), says on stderr how many records of the file it withheld, and a list that doesn't parse refuses it, as does a missing default list once a snapshot under `<data-dir>/snapshots/` has withheld an abstract (TASK-067) |
| `op takedown check --api <url> [--list <file>] [--log <file>]` (TASK-136) | ask a running API over HTTP (what is served, whatever the code path) whether it serves any listed abstract: on the served index, `/papers/{id}` (and its highlights for a query on the title) and the `/search` hit; on every index version `/meta` lists, every export format (one export per version, format and venue-year holding a listed id: filters only; a paper found in one format must be in all four), and one JSONL export per version and listed paper of its title in every venue and year (a record under another id with the same title and authors serving an abstract is a problem: TASK-067); each id a snapshot's `merges.csv` links to a listed paper whose `/papers` title differs (it is withheld as that paper: a suspect merge, TASK-067); each listed paper's twin (the union of its `twins` on served `/papers` and in every pinned version's JSONL export, independent of which version supplies its title and authors) the list doesn't name (the API withholds it too, so list and log it: TASK-163); and a listed id no loaded version holds. The list is always required (a missing one is never "nothing to check"; an empty one is). It also checks the takedown log: owned by the account running the check, mode 0600, each listed id's latest entry `withheld`, and each id whose latest entry is `withheld` listed (TASK-067). Prints each problem (ids, versions and formats, never text or requesters' details) and exits 1 on any, 0 otherwise; one `takedown_checked` log line with the counts. Run it as the operator's account, against the API itself (e.g. `http://127.0.0.1:8000` on the host), not through the proxy: it follows no redirect, and waits out a 429's `Retry-After` (each export costs the rate limit's export weight: about (cells × 4 + listed papers) × versions × `export_weight` tokens) |
| `op record save "<q>" [--mode scholar] [--index current\|<index_version>] [--json]` · `op record replay <id> [--index current\|<index_version>] [--json]` | freeze a search as a search record in `<data-dir>/records/records.sqlite` (the same functions as `POST /records`, `records.freeze` + `RecordStore.insert`: a record identical to the API's but for its id and time) and print its id, page and PRISMA summary, or the stored record (`--json`); replay one (the same function as `GET /records/{id}`, `records.replay`) on its own index when the data dir holds it, else on `--index` (default `current`), and print the status, `reproduced` / `drifted` / `mismatch`, the changed inputs and `+added / −removed`, or the API's `replay` block (`--json`). `--index` is a name under `<data-dir>/indexes`, never a directory: a record pins a version a replay must find by name. Left out, as serving policy: the rate limit, the save ceilings, and the verified-clause cap and candidate ceiling, so a CLI replay is never withheld (decision-010); the store's size cap and free-space floor (the API's defaults) apply (task-083) |
| `op serve [--host] [--port] [--index current\|<index_version>] [--cors-origin …] [--trusted-proxy …] [--rate-capacity] [--rate-refill] [--export-weight] [--no-rate-limit] [--pinned-indexes] [--max-verified-clauses] [--max-verification-candidates] [--max-verification-seconds] [--max-counted-groups] [--log-query-text]` | run the API (04 §Implementation notes, as built): one uvicorn process over `<data-dir>/indexes/<index>`; SIGHUP reloads it. `--pinned-indexes` (default 4) sizes the LRU of older index versions held open: size it to the versions the instance holds (TASK-067). With a non-loopback `--host`, or any `--trusted-proxy`, the takedown list is required (§Deploy, TASK-067): a missing `withheld.txt` fails the load. Refused as usage, each option named with the validator's reason: a trusted proxy wider than /8 or /32, `--no-rate-limit` with a non-loopback `--host` (§Deploy), and limits that could never be paid (decision-010) |
| `op embed build` (deferred with 06, decision-017; task-058) | build embeddings for the current index (06) |
| `op eval coverage [--index <v>] [--out <dir>] [--date YYYY-MM-DD] [--check]` (TASK-054) · `op eval scholar [--query <name>]` (planned, task-056) · `op eval audit` (planned, task-055) · `op eval near-miss` (deferred with 06, decision-017; task-061) | the 07 reports; `coverage` writes `docs/results/<date>-coverage.md` and `--check` exits 1 when the M4 gate fails; `near-miss` is 06's recall@25 |
| `op openapi [--out <file>]` | print the OpenAPI document, sorted and stable, without loading an index (task-040); `make openapi` writes it to `backend/tests/contract/openapi.json` and regenerates `frontend/src/api/schema.ts` from it |

`op search`, `op export` and `op record save` check raw query length before index I/O, then parse
with the selected index's tokenizer. Basic argument errors remain early. An unavailable index is
reported before semantic query errors because those errors depend on its tokenizer; diagnostics and
canonical hashes always describe the selected index's interpretation.

The CLI and the API call the same functions, so the CLI alone is enough to run a whole review.

## Error handling

- `op` exits non-zero on any error and prints the same `{code, message}` (with diagnostics and spans for a
  parse error) that the API would return (04 §Error handling). It never prints a stack trace for bad input.
- `op record replay` exits 3 on `mismatch` (`API_REPLAY_MISMATCH` is logged at ERROR) and zero on
  `reproduced` or `drifted`, so a script can tell a bug from drift; an unknown or malformed record id, or no
  index to replay on, is a refusal (1).
- A gate hook blocks with exit 2 and says why on stderr. The formatting and reminder hooks (`autofix.sh`,
  `remind-token-contract.sh`) never block; they report back to the agent instead.
- `make lint`, `make tooling` and every CI job fail on the first error; nothing is retried silently.

## Testing

- Every hook has a case table under `.claude/hooks/tests/`, and every tooling script one under
  `.claude/scripts/tests/` (the CI scripts, the network guard, `changelog.py`); `make tooling` and CI
  `claude-tooling` run them all.
- `make tooling` also runs the roster lint, the `.claude/README.md`, learnings-index and backlog checks, and
  the digest-pin check on `deploy/` (§Deploy).
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
| `test` → `test` | pytest under pytest-xdist at the `pr` Hypothesis profile (200 examples, 2 s deadline) (unit, golden, differential@200, contract; the 2,000-example `ci` profile runs nightly, TASK-127); vitest; `next build` (the standalone server must exist); OpenAPI snapshot and TS types freshness (`make openapi`, then `git diff --exit-code` on `backend/tests/contract/openapi.json` and `frontend/src/api/schema.ts`; unconditional, TASK-040) |
| `claude-tooling` → `claude-tooling` | `make tooling`: roster lint, `.claude/README.md` and learnings index freshness, backlog hygiene (no Done task left in `tasks/`, no task or decision id used twice: §Merge queue), digest-pinned `FROM`s in `deploy/` (`check_digest_pins.py`, §Deploy), every case table under `.claude/hooks/tests/` and `.claude/scripts/tests/` (the tooling scripts, the network guard, `changelog.py`) |
| `pr-gates` → `attribution`, `learnings`, `review-attested` | no AI authorship in commits or PR text; the branch adds or extends a learnings entry (unless labelled `no-learning`); the PR body attests APPROVE for the head sha. In a merge-queue build, `merge_group_gate.py` runs the same three checks on every PR in the group (§Merge queue) |
| `nightly` (scheduled daily, and `workflow_dispatch`; not a PR check) | Parallel jobs, each with its own time limit (TASK-057): the whole backend suite but the differential at the `ci` profile (2,000 examples) under pytest-xdist, synthetic-corpus parity (`test_parity.py`) included; every property at 50,000 examples as a 5-part `properties` matrix under pytest-xdist, split by measured time per test (the near-cap replay property alone, the other oracle-backed properties, `unit/engine`, `unit/ingest`, and the rest with the exhaustive tokenizer check, `OP_EXHAUSTIVE=1`); the year-edit property (`test_clauses.py`), which ran past 90 min unsplit, as 4 seeded `year-edits` jobs of 12,500 (`OP_YEAR_EDIT_SHARDS`); differential@50k as 8 independent jobs of 6,250 examples, each with its own `--hypothesis-seed`, which its log prints with a rerun command; `benchmarks`: the spec 03 benchmarks with their budgets, then the ~80k report into the run summary and a `bench-80k` artifact (a budget miss there is a warning annotation); and the mutation run (`mutate.py`, every mutant in `.claude/scripts/mutants/*.json` killed or documented as equivalent) as an 8-job `mutate` matrix (TASK-171): job i of n runs `mutate.py --shard i/n`, every n-th mutant from the i-th, so every mutant is checked every night (n is the matrix size, so adding a shard is one edit). Estimated from run 37017691575 (188 mutants in 140 min on a 4-CPU runner), the 694 mutants at TASK-171 need ~8.5 h of one runner, past GitHub's 6 h job cap, or ~65 min a shard of its 140; shard 1's first step prints the night's count, and shards are added before one nears 140 min. Shard 1's first step checks every mutant's pattern still exists (seconds), so a stale mutant anywhere fails the run each night; it also fails its own shard. A surviving or stale mutant fails its shard, and so does a shard cut off at 140 min, with an `::error::` giving about how many of its mutants it checked (the step runs with `shell: bash`, i.e. pipefail, so the pipe through `tee` keeps the status). Long pytest steps run verbose with `OP_EARLY_FAILURES=1` (a failure's report, Hypothesis blob included, is printed when the test fails) and are interrupted before their job's limit, so an overrun fails with an `::error::` and shows which test was still running. The run has 27 jobs, past GitHub's limit of 20 at once for a free organization, so 7 (and more while a PR's CI runs) queue until running jobs finish (the short ones, `suite-ci`, `benchmarks` and the `differential` shards, took under 25 min in run 37017691575); a job's time limit starts when it runs. Full-corpus parity stays local (decision-004) |
| `bench` → `bench` (advisory: not a required check yet) | pytest-benchmark on the 5k fixture index (`backend/tests/bench`, task-031): the PR's base and head on one runner; a minimum time over 20% slower than the base fails, and each benchmark asserts its spec 03 budget (p95). It becomes required once it has run green on a few PRs without false failures (runner noise); a maintainer adds it to `dev`'s required checks |
| `web-image` → `web-image` (advisory: not a required check) | Only on PRs into, and pushes to, `dev` and `main` that touch `deploy/**`, `frontend/**`, `package.json`, `package-lock.json`, `.dockerignore` or the workflow itself (a workflow-level `paths` filter; TASK-148). `docker build -f deploy/web.Dockerfile .` three times on the runner's Docker, pushing nothing: a `private` image, a `public` one with the placeholder contact `takedown@example.org`, and a `public` one with no contact, which passes only when the build fails at `web-build-gate.sh` with its message. It stays advisory because the filter skips it on other PRs, and a required check that never starts stays pending forever; making it required means dropping the filter for a changed-files step inside the job, so it always reports |
| `e2e` → `playwright` (advisory: not a required check yet) | `make e2e`: Playwright against the deterministic 5k fixture API (`backend/tests/e2e/`) and the standalone frontend: the spec 05 review flow, keyboard focus behavior, axe WCAG 2.2 AA in both themes at 1280 and 320 px, root reflow at 320 px, and platform-specific `/search` visual baselines in both themes on the fixed `ubuntu-24.04` CI label |

`review-attested` is an **honesty check** against forgetting to review, not an access control. Anyone who
can edit the PR body could paste the marker. The access control is branch protection plus human review on
`main`. A same-repo `dev → main` promotion is exempt from `learnings` and `review-attested`. The exemption
checks the head repo, so a fork branch named `dev` cannot use it.

### Merge queue (TASK-161, decision-027)

`lint`, `test`, `claude-tooling` and `pr-gates` also run on `merge_group`, so a merge-queue build reports
all six required checks under the same names. `test` takes its OpenAPI baseline from the group's
`base_sha`. A `merge_group` event carries no PR, so the three `pr-gates` jobs run
`.claude/scripts/merge_group_gate.py` (`review`, `learnings`, `attribution`) in place of their
`pull_request` steps. With the queue's MERGE method, the commits in `base_sha..head_sha` along first parents
are one two-parent merge per queued PR, oldest first: parent 1 is the previous queue commit (the first
one's is `base_sha`) and parent 2 is the PR's head. The script names each merge's PR from GitHub's subject,
`Merge pull request #N from …`, or else from the one open PR into `dev` whose head is parent 2. It checks
that the newest merge's PR is the `N` in the head ref, `refs/heads/gh-readonly-queue/dev/pr-N-<sha>`. A PR
ahead in the group may already be merged when a build's jobs run, for example on a re-run, because GitHub
merges an entry as soon as its own build is green. Such a PR counts only if this group's own queue commit
merged it (`merged` and `merge_commit_sha` = that merge). Then each job checks **every** PR in the group:

| Job | Passes when |
|---|---|
| `review-attested` | the PR is open (or merged by this group's queue commit), targets `dev`, its head is still parent 2, and its current body (read through the API, not an event snapshot) holds `<!-- op-review: <parent 2> APPROVE -->` |
| `learnings` | the PR is labelled `no-learning`, or its own diff (`parent 1...parent 2`) adds or extends a `YYYY-MM-DD-<slug>.md` entry directly in `.claude/learnings/`, the same rule as the `pull_request` job |
| `attribution` | no commit message in `base_sha..head_sha` (the queue's merges included), and no PR title or body, matches the attribution pattern |

The checks fail closed. Each of these fails the job: a head ref that isn't `dev`'s queue, a sha that isn't
40 hex characters, an empty range, a commit with other than two parents, a chain that doesn't start at
`base_sha`, a PR named twice, a merge with no resolvable PR, a failed `gh` call, and JSON of the wrong
shape. Each job starts with a step that fails on any event other than `pull_request` and `merge_group`, so
a job whose gate steps all skip can't pass. The jobs widen `permissions` to `pull-requests: read` to read
the PRs. The case table is `.claude/scripts/tests/test-merge-group-gate.sh`. Its last row checks this
wiring in `pr-gates.yml`, `test.yml`, `lint.yml` and `claude-tooling.yml`. The mutants are in
`.claude/scripts/mutants/merge-group.json`. The advisory `e2e`, `bench` and `web-image` workflows don't run
on `merge_group`, so the queue never waits for them. The combined result is first e2e-tested on `dev`'s
push run.

Because the queue doesn't require a PR to be up to date, two PRs that each ran `backlog task create` (or
`backlog decision create`) on the same `dev` get the same id under different filenames, and git sees no
conflict. `check_backlog.py` runs in `claude-tooling` on the PR (whose merge ref already holds `dev`) and
again in every queue build. It fails when two files in `backlog/tasks/` + `backlog/completed/` share a task
id or two in `backlog/decisions/` share a decision id, naming the files. It reads the frontmatter `id:` and compares
numbers (`TASK-075` = `task-75`; a subtask `12.1` is not `12`). A file also fails the check if it has no
frontmatter, an indented line before its first key, a top-level frontmatter line that isn't a plain `key:`, a
`- ` item or a comment (`{…}`, `? id`, `<<:`, a tag, anchor or escaped key, any of which could give YAML an
id the check doesn't see), no `id:` (Backlog.md doesn't read the filename; the filename prefix is still
compared), an unreadable id or two `id:` fields, or a frontmatter id that disagrees with its filename; so
does a missing `tasks/` or `completed/`. `backlog/archive/` is not compared, because Backlog.md
1.53 gives an archived task's id to the next new task. Ids created during a branch's work are therefore
created last, after rebasing onto `dev`, and on a clash the unmerged PR drops its id commit and creates the id
again (skill `task-hygiene`, §Ids). The rows are in `.claude/scripts/tests/test-tooling-scripts.sh` and the
mutants in `.claude/scripts/mutants/backlog.json`.

**Dependabot** (`.github/dependabot.yml`, weekly) watches `github-actions` (prefix `ci`), `uv` and `npm` (prefix
`deps`) and the `docker` base images in `deploy/` (prefix `build`). For each, minor and patch version updates
are grouped into one PR per ecosystem (a docker digest bump is not a version change and comes as its own PR),
and semver-major updates are ignored (`dependency-name: "*"`,
`version-update:semver-major`), so a major upgrade is a deliberate, hand-made PR; adopted 2026-10-01, after the
npm entry's first run opened six PRs, majors among them. The `uv` entry also ignores `tantivy` entirely
(§Release, "Upgrading Tantivy"), and the `docker` entry still bumps the base-image digests, which are not majors
(§Deploy). GitHub applies `ignore` to security updates too, so a vulnerability whose fix is a major, or any
Tantivy fix, shows up as a Dependabot alert and is fixed by a hand-made PR.

## Git and PR rules

- `feature → PR → dev → PR → main`. No direct commits, pushes or merges on `dev` or `main`
  (`enforce-pr-workflow.sh`, from Kreate). `main` requires green checks but no mandatory approving
  review under the solo-maintainer policy applied on 2026-10-03.
- **Merging into `dev` goes through the merge queue** (active since 2026-10-02; §Branch protection). Once a PR's
  checks are green, add it to the queue with `gh pr merge <n> --auto`. That needs the repository's
  "Allow auto-merge" setting. Without it, enqueue with GraphQL: `gh api graphql -f query='mutation($id:
  ID!) { enqueuePullRequest(input: {pullRequestId: $id}) { mergeQueueEntry { position } } }' -f id="$(gh
  pr view <n> --json id -q .id)"`. Don't rebase it onto a newer `dev`
  first. A PR that is behind `dev` needs no rebase, new review record or new attestation; the queue tests
  it on top of `dev`. Rebase only for a real conflict or a failed queue build, and then re-review and
  re-attest the new head as usual. A push to a queued PR removes it from the queue.
- Branch names: `<type>/<slug>` (`feat/`, `fix/`, `chore/`, `docs/`, `test/`).
- **Review before push:** `/review-gate` sends the diff to the required reviewers (routing table in the
  `review-gates` skill). Every finding is dispositioned, and `record-review.py` writes an APPROVE record for
  the exact sha. `require-review.sh` blocks `git push` / `gh pr create` without one. `/open-pr` attests it in
  the PR body for CI.
- **Learnings every time:** a PR adds or extends a `.claude/learnings/` entry (`/record-learnings`), unless
  labelled `no-learning`. Every session starts with the index loaded.
- **Keep everything current** (skill: `task-hygiene`): tasks, docs, specs and READMEs change in the same
  commit as the behaviour. Finished tasks leave `backlog/tasks/` via `backlog task complete <id>`. New task
  and decision ids created during the work are created last, after rebasing onto `dev` (§Merge queue).
- **No AI authorship** in commits or PRs (project decision 2026-09-25). `.claude/` is committed.
- Secrets (OpenReview credentials) live only in `.env` (gitignored, mode 600). `data/` is never committed.

## Deploy (M6: the web image, TASK-136, built in CI, TASK-148; compose, Caddy, the api image and the runbook, TASK-065; the host, TASK-064)

`deploy/compose.yml` (TASK-065): `api` (`op serve` from `deploy/api.Dockerfile`, loads `indexes/current`), `web`
(`deploy/web.Dockerfile`, Next.js standalone) and `caddy` (`deploy/caddy.Dockerfile`) in front for TLS: the site
name from `OP_DOMAIN`, Caddy's local CA for `localhost` and ACME for a real name. The operator's runbook (settings,
first start, promotion, retire, takedowns, what remains for the host) is `deploy/README.md`; nothing in `deploy/`
names a host or provider (00, question 5; TASK-064). Every container runs as a non-root user (`api` as `op-api`,
uid and gid 10001 by default, `OP_API_UID`/`OP_API_GID` when a host account already has them, never the
operator's account; `web` as `node`; `caddy` as uid 10002, binding 80 and 443 through
the container's `net.ipv4.ip_unprivileged_port_start`) with a read-only root filesystem, every capability dropped
and `no-new-privileges`; `api` and `web` are on an `internal` network with no route out, and `--trusted-proxy`
names Caddy's fixed address on it. `deploy/smoke-test.sh` runs the whole stack over a fixture (TLS, the users and
mounts, a promotion, refused and done retires, a takedown with `op takedown check`, no query in any log); it is
run by hand, not in CI. Caddy must not log query strings: `GET /api/v1/search?q=…` carries the query
(spec 04 §Implementation notes). **`op serve` must sit behind that proxy**, never face clients directly:
uvicorn (h11) has no request-header or slow-body timeout of its own, so the proxy's timeouts are what bound a
client that sends its request slowly; the app caps a body at 64 KiB (413 `API_BODY_TOO_LARGE`), uvicorn's
`limit_concurrency` (`ApiConfig.limit_concurrency`, default 256) bounds the connections one process holds,
and `timeout_keep_alive` (`keep_alive_seconds`, default 5) closes an idle one. The Caddyfile **must** set
(Caddy v2 directive names, checked against the Caddy docs 2026-09-27; `deploy/Caddyfile` sets them, with the site
name `{$OP_DOMAIN:localhost}`, a `Strict-Transport-Security` header from `OP_HSTS` on every response, default
`max-age=63072000` as the web app's own, with `includeSubDomains` left off until TASK-064 decides the domain, and
`skip_install_trust`):

```caddy
{
	log default {  # the runtime logger, which carries `http.log.error` (see below)
		format filter {
			request>uri delete
			request>headers>Referer delete
		}
	}
	servers {
		timeouts {
			read_header 5s   # a client's request line and headers (default: no timeout)
			read_body   10s  # its body (default: no timeout)
			idle        2m   # a keep-alive connection between requests
			# no `write` timeout: an export of the whole matched set streams for as long as it takes
		}
		max_header_size 64KB  # the API's own request-head limit (a 2,000-code-point q fits)
	}
}
openproceedings.example {
	request_body {
		max_size 64KB  # the API's own body cap: refuse larger before forwarding
	}
	reverse_proxy /api/* api:8000 {
		request_buffers 64KB  # read the whole (capped) body before opening the upstream request
	}
	log {
		format filter {  # never the query: GET /api/v1/search?q=… carries it, and so does a Referer
			request>uri delete
			request>headers>Referer delete
		}
	}
}
```

The site's `log` directive filters only the access log (`http.log.access`). A request that fails at the
proxy (a 502 while the API restarts, an upstream that resets mid-stream) is logged by `http.log.error`,
whose entry carries the same `request` object, `uri` and headers included, through Caddy's default runtime
logger, which the site directive never reaches; so the global `log default` above filters those fields
too (M3a review round 3; Caddy v2's error logger adds the loggable request to every error entry). Without it a restart would write every in-flight `q` to the proxy's log.

`read_header` and `read_body` bound a slow client at the proxy, so only whole requests reach uvicorn;
`request_buffers` makes the proxy read the body before it takes an upstream connection, so a client that
trickles its body holds a proxy goroutine, not one of the API's `limit_concurrency` slots. A connection
beyond `limit_concurrency` gets uvicorn's own plain 503, and uvicorn logs `Exceeded concurrency limit.`
(WARNING, through the JSON handler) once per refusal, not once per episode: a burst of refusals is a burst
of lines, so alert on their rate rather than on one. The proxy is also
the one trusted proxy (`--trusted-proxy <its address>`); a trusted network wider than /8 (IPv4) or /32 (IPv6)
is refused, as is `--no-rate-limit` with a non-loopback `--host`. Off loopback, or with a `--trusted-proxy`,
`<data-dir>/takedowns/withheld.txt` must exist before the first start (an empty file on a fresh instance), or
the load fails `takedowns_missing` (TASK-067). Swagger UI (`/api/v1/docs`, scripts from a
CDN) is off on a non-loopback `--host` unless `--docs` is passed; leave it off in production. `api` mounts `snapshots/` and `takedowns/` read-only, the
search records' directory `records/` read-write (a host directory, 0700 and owned by the API's uid, 10001 by default; `records.sqlite` and
the WAL files SQLite writes beside it; spec 04 §Search records), and `indexes/` read-write but closed by file modes: Tantivy opens an index only after taking
`.tantivy-meta.lock` for writing (so a `:ro` index mount fails to load), so each version directory is 0750 with
group `op-api` and only its two lock files group-writable (`deploy/index-permissions.sh`, run after each `op index
build`), and `indexes/` itself stays the operator's, 0755: the API can open an index and can't add, remove or
repoint anything. `snapshots/` holds each served index's snapshot (`/papers/{id}` reads provenance from it). Run
`op record save` and `op record replay` as the API's service user (`docker compose -f deploy/compose.yml exec api op record …`, or
`sudo -u <api user> op record …` outside compose): the store's directory is 0700 and `records.sqlite` 0600, so a record
saved as another user leaves a store (and WAL files) the API can't write, or can't read at all. Refreshing the index
means building a new `index_version` offline, switching the `current` symlink, and sending SIGHUP; an old
version no record pins can then be deleted with `op index retire <index_version>`, once `/api/v1/meta` reports
the new version (the API serves the old one until its reload; §CLI). In compose, retire runs only in the `ops`
service (root, with the record store and `indexes/`). On the host the operator can't read the API's store, so a
retire there refuses (`records_unreadable`): a store it can't read is never taken for "no pins", while a missing
one would be (`RecordStore.pinned`), which is why the store is a directory in the data directory rather than a
volume a host-side retire wouldn't see. `ops` keeps `CAP_CHOWN` because SQLite, run as root, gives each `-shm`
or `-wal` file it creates the database's owner, and without the capability leaves them root's, after which the
API can't save a record (reproduced, TASK-065); `smoke-test.sh` checks the store's owners after a retire.
**`records/` is the only copy of every search record**, and losing it also unpins every index: back it up
(`deploy/README.md` §Backups, SQLite's backup API as the API's user). Hosting is still open (00, question 5).

**What a public instance serves (decision-018; not legal advice).** Every abstract in the index, in results,
on paper pages and in exports. Before a deployment is public: (1) each record names the source of its abstract
and links to it, and a PMLR abstract appears with its citation and a link to the PMLR page (CC BY 4.0's
attribution terms; TASK-134 for the result list); (2) every page names a takedown contact (TASK-133). Private,
local and development deployments may omit the contact. A takedown withholds a record's abstract from every
index version the instance loads (the procedure below, decision-022). The unlicensed years rest on fair dealing alone; consulting the University of Waterloo copyright
office before launch is recommended (TASK-135), and TASK-069 records its outcome, if any, but does not wait on
it.

**Takedown contact (decision-018, TASK-133).** A publicly reachable instance **must** name a takedown contact;
private, local and development deployments may leave it unset. The frontend renders the footer on every page
either way (`frontend/src/components/site-footer.tsx`, the `contentinfo` landmark; copy deck FT-1 to FT-3).
The contact is set with `NEXT_PUBLIC_TAKEDOWN_CONTACT` when the `web` image is **built** (Next compiles
`NEXT_PUBLIC_*` in, as with `NEXT_PUBLIC_API_BASE_URL`): an email address (`takedown@example.org` or
`mailto:…`, ASCII letters, digits and `._+-` only) or an `http(s)` page (printable ASCII, no username or
password). `next.config.ts` checks it: a value that is set but unusable **fails the build**; unset, the footer
links to the project's issue tracker (`https://github.com/uw-share-lab/openproceedings/issues`) rather than
naming no one, and the production build (`next build`) warns that publicly reachable instances must set
`NEXT_PUBLIC_TAKEDOWN_CONTACT`. A build also declares what kind of instance it is with `OPENPROCEEDINGS_INSTANCE`
(TASK-136): `public` refuses to build without a contact (`next.config.ts`, `checkTakedownContactEnv`); `private`
and unset build with the fallback. The `web` image (`deploy/web.Dockerfile`, built from the repository root)
takes `NEXT_PUBLIC_TAKEDOWN_CONTACT`, `NEXT_PUBLIC_API_BASE_URL` and `OPENPROCEEDINGS_INSTANCE` as build
arguments; `OPENPROCEEDINGS_INSTANCE` has no default, and `deploy/web-build-gate.sh` refuses, before anything is
installed, a build that doesn't set it to `public` or `private` and a `public` one without a contact:

```
docker build -f deploy/web.Dockerfile --build-arg OPENPROCEEDINGS_INSTANCE=public \
  --build-arg NEXT_PUBLIC_TAKEDOWN_CONTACT=takedown@your.org --build-arg NEXT_PUBLIC_API_BASE_URL= -t openproceedings-web .
```

`.dockerignore` sends only what the images copy (the frontend, the backend package with the lockfiles, the
Caddyfile; never `data/`, a `takedowns/` directory or a `.env` file).
CI's advisory `web-image` workflow builds the image on every PR into, and push to, `dev` and `main` that
touches the paths §CI lists (`deploy/`, the frontend, the npm manifests, `.dockerignore`, the workflow): the private build, a public build with a placeholder contact, and a public build with no contact that
must fail at `web-build-gate.sh` (TASK-148).

**Base images are digest-pinned (TASK-149).** Every `FROM` in `deploy/` names its base image as
`name:tag@sha256:<digest>`, the tag kept for readers and the digest that of the multi-arch index (not of one
platform's manifest), so a rebuild uses the image that was reviewed; a `FROM` naming an earlier build stage, or
`scratch`, needs none. The same holds for every other image a build pulls: a `# syntax=` parser directive
(the BuildKit frontend; `web.Dockerfile` has none, so the builder's built-in one is used), `COPY --from=` and
`RUN --mount=…,from=`. `.claude/scripts/check_digest_pins.py` (`make tooling`, CI `claude-tooling`; case rows
in `test-tooling-scripts.sh`) reads every `*Dockerfile*` or `*Containerfile*` under `deploy/` as BuildKit does
(a BOM dropped, continuation lines glued, the `escape` directive honoured) and fails on any of those images
without a digest, or with an `ARG` in its name. Dependabot's `docker` entry for `/deploy` and its
subdirectories (weekly, prefix `build`; §CI, "Dependabot") bumps the `FROM` digests; it reads no other line, so a pinned `syntax`,
`COPY --from` or `RUN --mount` image (none today) is bumped by hand; a new Node major (`22-…` → `24-…`) is
ignored there, like every semver-major update (§CI), and done by hand along with `.nvmrc` and CI. A digest is resolved from the registry,
e.g. `docker buildx imagetools inspect node:22-bookworm-slim` (its top-level `Digest:`, with media type
`…image.index…`), which needs no running daemon.

The e2e suite
builds with the placeholder `takedown@example.org` (`frontend/playwright.config.ts`); `frontend/.env.example`
documents both variables.

**Takedown procedure (TASK-133's proposal, built by TASK-136; decision-022).**
- **Who receives a request:** the deployment's operator, at that contact. A request that arrives on the issue
  tracker through the footer's fallback goes to the project maintainers, who pass it to the operator of the
  deployment it names, or act on it for a deployment they run. Fallback requests are **public** (GitHub issues
  are), so the footer asks requesters to leave out personal details (FT-3); a public instance sets its own
  contact.
- **What is removed:** the record's `abstract`, and with it its abstract claims (their values are the text).
  The record stays and is still matched on its title, as a record with a missing abstract is (01 §Error
  handling). What *matches* on an index version that still holds the text doesn't change (below).
- **The takedown list,** `<data-dir>/takedowns/withheld.txt` (`openproceedings/takedowns.py`): UTF-8 (a leading
  byte order mark is ignored; an invisible character in an id refuses the list), one record id per line, blank lines and everything after `#` ignored (`op:iclr:2024:AbCd1234  # 2026-09-30, see the
  log`). Ids only: the API's service user reads it (the file 0644, or 0640 with the API's group; the
  `takedowns/` directory 0755, or 0750 with that group; a list the API can't read fails its load). A line that
  isn't one record id makes the whole list unusable: `op snapshot build` and `op export` refuse, and the API
  keeps what it serves (at startup it serves nothing, 503). A missing file fails the load (`takedowns_missing`)
  when `op serve` runs on a non-loopback host or with a `--trusted-proxy` (`ApiConfig.takedown_list_required`: every
  public instance), when
  the API already applies a non-empty list, or when any snapshot under `<data-dir>/snapshots/` withheld an
  abstract (a `current` rolled back to an index from before the first takedown included; TASK-067); `op snapshot
  build` and `op export` refuse a missing default list on the same evidence, and `op takedown check` always needs the list. So
  an unmounted or renamed `takedowns/` never lifts every takedown silently; empty the file to lift them all, and
  keep the empty file. Otherwise (a local instance with no takedown history) a missing file is an empty list. Every index load and swap (`index_loaded`, `index_swapped`) logs `takedowns_list` (`present`/`absent`). Never committed:
  `.gitignore` ignores every `takedowns/` directory and `protect-data-dir.sh` refuses `git add` of a path
  through one.
- **How it is applied.** (1) Log the request (below). (2) Add the id to the list and send the API SIGHUP: from
  that reload, every index version it loads, the served one and each pinned one (a search record's replay and
  exports, `/export?index_version=`), withholds the abstract at serve time (below), under the listed id and any
  other id that version holds the paper under (TASK-067, `takedowns.same_paper`): an id linked to a listed one by
  any snapshot's `merges.csv` (a duplicate some build merged), or with its native id when that native id is
  globally unique (an OpenReview forum id or a PMLR volume key: the paper before a venue or year was corrected;
  `takedowns.global_native`), transitively. A NeurIPS or ICLR proceedings hash (`nips-…`, `iclr-…`) links
  nothing: it names one paper only within its venue-year (measured, TASK-067: a NeurIPS hash is md5 of a
  per-year paper number, and the 2026-09-29 snapshot has 1,281 hashes naming two to five papers each; ICLR
  proceedings hashes collided across years in the 2026-09-23 snapshot). It follows a **twin** link too (TASK-163,
  owner decision 2026-10-02): a record whose `twin` claim names a listed id, or that a listed record's claim names
  (decision-029: an ICLR 2017 workshop-listing copy and its conference submission, two records of one paper,
  never merged), in the served snapshot's claims or the version's own, transitively with the merges, so a
  takedown of either copy withholds the abstract on both. **List and log both ids** (one `withheld` entry each,
  the same requester and basis): `op snapshot build` names each twin it withheld (`takedowns_twins`) and `op
  takedown check` reports a listed paper's twin the list lacks. So listing the paper's current id also withholds it on an
  older version that holds it as a merged-away duplicate or under its pre-rekey forum id. The merges are read
  from every snapshot on disk, older dedup rules included (accepted: a merge is the project's own verdict that
  two records are one paper, and `op takedown check` names a merged id whose title differs). A snapshot whose
  merges.csv doesn't match its manifest leaves its own merges out, every other snapshot's still applying: the
  list still applies (one ERROR `takedown_merges_unavailable` per damaged snapshot, naming it), and `op takedown
  check` reports it. The API re-reads the list on
  every load and SIGHUP, even when `current` hasn't moved, and a reload whose new index fails to load still
  applies a new list to the index it keeps serving. The reload runs in the background: confirm it with the
  `takedowns_reloaded` line (logged after `index_load_failed` too, when a new index failed but the list was
  applied), then run `op takedown check --api
  http://127.0.0.1:8000`, which passes on serve-time withholding alone, before any rebuild. (3) Run `op snapshot
  build`: it withholds every listed abstract after dedup and reconcile, whatever the cache supplies (a recrawl
  can't bring one back), so the new snapshot, and its `snapshot_hash` and `index_version`, no longer hold it; its
  manifest names the ids whose abstract it took out (`withheld`) and counts them per venue-year and track
  (`abstract_withheld`, `abstract_withheld_by_track`, not counted in `abstract_missing`), and `op snapshot diff`
  names them (`abstract_withheld.added`). A listed record that had no abstract changes nothing in the snapshot
  (serve time marks it). A listed id this build holds under another id (merged into another record, or a forum
  or PMLR id rekeyed by a corrected venue or year) is followed: the new id's abstract is withheld too and the build says so
  (`takedowns_followed`); add the new id to the list, log a `withheld` entry for it (the same requester and
  basis), and **keep the old one**, which older index versions still
  hold. A twin of a withheld record (its `twin` claim, decision-029) is withheld too, and the build names it
  (`takedowns_twins`: the twin → the listed or followed id it is the twin of; on stderr, what to add when the list
  lacks it): list it and log it as above. A listed id the build has no record of (a paper gone from its sources) is reported
  (`takedowns_unmatched`), never refused: keep it listed while any loaded version holds it. (4) `op index build`,
  promote the new `index_version` as for any refresh (switch `current`, SIGHUP), and record it in the log as
  `first_index_version`. (5) Run `op takedown check` again: exit 0 means no loaded version serves a listed
  abstract, under the listed id or another (for each listed paper and version it also exports the paper's
  title in every venue and year, and a record under another id with the same title and authors that carries
  an abstract is a problem: list that id too; and a listed paper's twin the list doesn't name is a problem: list
  and log it too, TASK-163). Run it after every promotion while the list names anything.
- **At serve time, on every loaded version** (decision-022): `/search` hits have `abstract` null, no abstract
  highlight spans, `abstract_source` null and `abstract_withheld: true`; `/papers/{id}` has no abstract and no
  abstract claim, no abstract spans, and `abstract_withheld: true`; every export format (served, pinned by
  `index_version` or by a search record, and `op export`) leaves the abstract out and says so in the record
  (RIS `N1` and BibTeX `abstract_withheld` = "Abstract withheld: removed from this site at a rights holder's request, so no abstract is exported (decision-022).", CSV and JSONL `abstract_withheld` true with `abstract_withheld_reason` `takedown`);
  `/coverage` counts `abstract_withheld` apart from `abstract_missing`; the UI says "Abstract removed from this
  site at a rights holder's request", and each export response counts such records in `X-Abstracts-Withheld`
  (the web app says how many, EX-E9). An abstract the served snapshot itself withheld is marked the same way.
- **Older index versions still match on it (the oracle leak, accepted: decision-022).** Indexes are immutable,
  a search record pins the index it was run on, and `op index retire` refuses a pinned version (TASK-085). A
  pinned version keeps matching on the text it holds, so replaying a saved search there returns the same ids
  (guarantee 4): the paper is still a hit, and `/papers?q=` still says `matched: true`, but no word, span or
  excerpt of the text is shown. A version no record pins can be retired to end even that.
- **The takedown log** (default `<data-dir>/takedowns/log.jsonl`; under compose outside the data directory, as
  the end of this bullet says), on the deployment host, outside the repository (owner,
  2026-09-30): owned by the operator's account (not the API's service user), mode 0600, never committed, and
  kept out of image build contexts (`.dockerignore`), since it holds requesters' details. One JSON object per
  request, exactly these keys: `record_id`, `received` (date), `requester` (name and contact), `basis` (what
  they state), `decision` (`withheld`, `declined` or `lifted`), `applied` (date, or null), `first_index_version`
  (the first `index_version` built without the abstract, or null until then). Update an entry's `applied` and
  `first_index_version` in place as the steps complete. The API never reads it; `op takedown check` (run as the
  operator's account) fails when it is owned by another account, readable by others, malformed, when a listed
  id's latest entry isn't `withheld`, or when an id whose latest entry is `withheld` isn't listed (a line
  dropped from the list; TASK-067). A search record's deletion (the search-records skill's runbook) is logged
  elsewhere, not here. **In the compose deployment (TASK-065)** the `api` container mounts `<data-dir>/takedowns/`
  read-only, and that directory holds only `withheld.txt`. It mounts the directory, not the file alone, because
  an editor that saves by renaming would otherwise leave the container reading the old list after a SIGHUP. The
  container runs as `op-api` (uid 10001 by default, `OP_API_UID`), never as root or as the operator's account. The log therefore lives
  in its own directory outside the data directory, for example `/srv/openproceedings/takedown-log/log.jsonl`
  (0700 and 0600, the operator's). The compose `takedown-check` service reads it there, through `--log`, running
  as the operator's uid against `http://api:8000` on the internal network (`deploy/README.md` §Takedowns). On a
  host without compose, the default `<data-dir>/takedowns/log.jsonl` stays valid, as long as the API's user
  can't read it.
- **Lifting a takedown:** append a `lifted` entry (its `applied` date too), remove the line, SIGHUP; versions that still
  hold the text show it again. A snapshot built while the id was listed keeps it withheld (and marked): rebuild
  and promote as in steps 3 and 4 to bring it back on the served index. `op takedown check` reads each id's
  latest log entry, so a listed id whose latest entry is `lifted` or `declined` is a problem.

## Release (M6; decision-023, TASK-066)

A release is a commit on `main`, reached by a `dev → main` promotion PR, and tagged `vX.Y.Z`. It holds the
code at that commit (the backend package and the frontend, one version), its `CHANGELOG.md` section, and its
table in `docs/releases.toml`: the index it was verified on. It holds no data: snapshots and indexes are never
committed or attached to a release (00 §Open questions 1, closed by decision-018: the corpus is never
committed). **Code and data ship separately:** a release never changes which `index_version` an instance
serves, and promoting an index is the §Deploy runbook, run on its own and recorded in the next release's Data
section. The one exception is a release that changes `TOKENIZER_VERSION`, `SCHEMA_VERSION` or Tantivy: it is
verified on, and deployed with, a new index built using its current versions. Supported older tokenizer/schema
indexes remain available for pinned-record replay (spec 03 §Versioning); unsupported versions or an
incompatible Tantivy build are refused by `engine/tantivy_engine.py` `unservable`. Nothing here depends on where an instance is
hosted (00, question 5). The first release is tagged once TASK-065 (deploy) is done.

**Versioning.** One semver version for the app, `MAJOR.MINOR.PATCH`:

| Version | Lives in | Changes when |
|---|---|---|
| app `X.Y.Z` | `backend/pyproject.toml` and `frontend/package.json` `version`, kept equal (also recorded in `uv.lock` and `package-lock.json`), and `CITATION.cff`'s `version` with its `date-released`; `op --version` and the snapshot manifest's `openproceedings_version` report it | once per release, on its release branch |
| `TOKENIZER_VERSION`, `SCHEMA_VERSION` | the code; inputs to `index_version` (03 §Versioning) | the `index-versioning` bump rules |
| Tantivy | the exact `tantivy==` pin in `backend/pyproject.toml` and `uv.lock`; each index manifest's `tantivy_version` (not an `index_version` input) | a dependency upgrade, which always bumps `SCHEMA_VERSION` too, so the release gets a new `index_version` it can build and serve (a replay reports it as `schema_version`). Always by hand: Dependabot's `uv` entry ignores `tantivy` (below) |
| `QUERY_VERSION` | the code; in `canonical_hash` and every search record (04) | the `index-versioning` bump rules |
| `index_version` | the data: `data/indexes/<index_version>/` | a new snapshot, or a tokenizer, schema or ranking change |

- **MAJOR:** a breaking change to the `/api/v1` contract (that is a new `/api/v2`), the `op` CLI, an export
  format or the search-record store. Before 1.0.0 these bump MINOR.
- **MINOR:** new features, and any change of `TOKENIZER_VERSION`, `SCHEMA_VERSION`, Tantivy or
  `QUERY_VERSION`. Records replay as `reproduced` on retained supported pins while their query inputs match;
  replay against changed inputs reports `drifted`, naming those changes (guarantee 4).
- **PATCH:** fixes that change none of those four.
- The first tag is `v0.1.0`. Versions stay `0.y.z` until the owner declares the v1 release (M6), `1.0.0`.

**Upgrading Tantivy (TASK-150).** Dependabot's `uv` entry in `.github/dependabot.yml` has an `ignore` entry
`{dependency-name: tantivy}` with no `update-types`, so it never opens a PR that bumps the pin on its own: merged alone, such a PR
would leave `dev` unable to serve the current index (`unservable`, `tantivy_version_mismatch`) or to build a new
`index_version` for it, and only `changelog.py --release` would notice, at release time. An `ignore` was chosen
over a CI check that compares `uv.lock`'s Tantivy with `SCHEMA_VERSION`: it closes the gap with no new gate to
maintain, and the upgrade is rare and needs a person anyway (a rebuilt index, parity). The upgrade is one
hand-made PR: bump the `tantivy==` pin in `backend/pyproject.toml`, `uv lock`, bump `SCHEMA_VERSION`
(`engine/index.py`), then rebuild and verify an index with the new code (§Deploy runbook; index-versioning
skill).

The app version never enters `index_version` or `canonical_hash`. A search record pins `index_version`,
`tokenizer_version` and `query_version`, not the app version. It replays as `reproduced` while its index is
kept, the running code can serve that index (supported tokenizer/schema versions and compatible Tantivy) and its
`QUERY_VERSION` matches. Replay using changed inputs reports `drifted`, naming those changes; an unavailable
or unsupported index with no usable fallback is refused (04 §Search records). So a record
saved under an earlier release can reproduce on the current reader when its pin is supported and its query
inputs match. An incompatible pin requires the matching historical release's tag, which is why tags and
retention (step 8) matter (guarantee 4).

**`CHANGELOG.md`** is generated, never hand-edited: `make changelog` (on a release branch,
`make changelog RELEASE=X.Y.Z`) runs `.claude/scripts/changelog.py`, whose case table is
`.claude/scripts/tests/test-changelog.sh` and whose mutants are `.claude/scripts/mutants/changelog.json`.
- **Input:** every merged PR from the REST API (`gh api`), the `vX.Y.Z` tags and `docs/releases.toml`
  (`--prs <file>` reads the PR list from a file instead). No dates, authors or clock: the same inputs give the
  same bytes, in any clone (the repository name is compared without case).
- **Counted:** PRs merged into `dev`, and into `main` except this repo's `dev → main` promotions (they repeat
  what `dev` lists). Never this repo's `release/*` branches, which carry only release bookkeeping (the version
  bump, the data table and this file before the promotion; the back-merge after the tag). Not PRs into any
  other base.
- **Sections:** a PR belongs to the oldest tag whose history holds its merge commit; with `--release X.Y.Z`,
  `HEAD` counts as that version's tag. A PR no tag holds is Unreleased.
- **Groups**, by the title's Conventional Commits type: `feat` → Added; `docs`, `refactor`, `perf`, `revert`
  → Changed; `fix` → Fixed; `chore`, `test`, `ci`, `build`, `style` and Dependabot's `deps` → Internal. A title without one of these
  types takes its head branch's `<type>/` prefix instead, else Changed. A known `type!:` is marked
  **Breaking**. Each line is the title's description (a scope first) and a link to the PR, in merge order.
- **Data:** each release's section ends with its `docs/releases.toml` table (`index_version`,
  `snapshot_hash`, `tokenizer_version`, `schema_version`, `tantivy_version`, `query_version`) and its
  replay compatibility conditions. A release whose four versions differ from the previous release's
  starts with a changed-input callout and is refused as a PATCH. The table alone does not classify older
  pins: retained supported indexes can reproduce when `QUERY_VERSION` matches.
- **With `--release`**, a Tantivy change without a `SCHEMA_VERSION` change is refused, and the table must
  match the code at `HEAD` (the three constants and the Tantivy `uv.lock`
  pins) and the manifest of the index it names, `<--data-dir>/indexes/<index_version>/manifest.json`
  (default `data/`), so a hand-copied table can't hide a version change.
- **Refuses** (exit 1, nothing written): a release with no data table or a table that disagrees with the code
  or its index; a `--release` version the two manifests don't both carry or that isn't newer than the latest
  tag; a merge commit the clone lacks, once there is a tag or `--release` to place it against
  (`git fetch origin --tags`); malformed input; and a PR title or note with an AI-attribution marker (checked
  on the plain text: format and other default-ignorable characters dropped, whitespace collapsed, and NFKC
  for the check; titles and notes render the same plain text), an `@`-mention, an email address or a URL (release notes
  name roles and link only PRs; an npm scope such as `@types/node` and a pin such as `next@15.1.0` pass; edit
  a refused title through the REST API).
- `--check` exits 1 when the file differs; `--notes X.Y.Z` prints one release's section (the release notes).
  No CI job runs it, because it reads GitHub and every merge would make the file stale. Between releases its
  Unreleased section lags `dev`; any PR may refresh it.

**Checklist** (`release-manager`; paste each command's result into the promotion PR):
1. **Readiness on `dev`.** The required checks are green on its head, and so are `e2e`, `bench`, the
   latest `web-image` run on `dev` and a `nightly` run from the last day. `backlog task list --plain` shows no open Must finding. The latest
   `docs/results/*-coverage.md` passes the M4 gate.
2. **Security gate.** `security-reviewer` (`/security-review`) over `origin/main...origin/dev`, every finding
   dispositioned as in `/review-gate`. Before the first release a public instance serves, TASK-067 (the
   pre-release security review) is Done.
3. **The index it is verified on**, under a local data dir: the served index when the release changes none of
   `TOKENIZER_VERSION`, `SCHEMA_VERSION` and Tantivy, else a new one built by the release's code (§Deploy
   runbook, with `op snapshot diff <old> <new>` reviewed). Run, with the release's code: the golden and
   contract suites; `op index parity --index <v>`; `op eval coverage --index <v> --check --out <scratch>`
   (so no report lands in the tree); and `op record replay <id> --json` on a sample of search records from a
   copy of the target instance's `records/records.sqlite`, only records whose pinned index is present in the
   local data dir (copy it, or leave the record out: replay runs a record on the index it pins when that
   index is present and supported, else falls back to a usable `--index`, potentially reporting `drifted`
   because of that fallback). Required: every sampled record on a retained supported pin with matching
   query inputs reports `reproduced`; replay against changed inputs reports `drifted`, naming exactly those
   changes. A refused replay must be resolved; a `mismatch` (exit 3, `API_REPLAY_MISMATCH`) blocks the release.
4. **Release branch.** From here until the tag exists, nothing else merges into `dev`. `git switch -c
   release/X.Y.Z origin/dev`; set `version` to `X.Y.Z` in `backend/pyproject.toml` and
   `frontend/package.json`, then `uv lock` and `npm install --package-lock-only --ignore-scripts`; in
   `CITATION.cff` set `version: X.Y.Z` (the release version, exactly) and `date-released:` to the day the tag
   is planned for (step 6), so the tagged file is the one "Cite this repository" shows for it; add
   `[releases."X.Y.Z"]` to `docs/releases.toml` from step 3's index manifest
   (`data/indexes/<v>/manifest.json`) and the code's `QUERY_VERSION` (never edit a released table); `make
   changelog RELEASE=X.Y.Z`, which checks the table against that manifest (so run it in the checkout that
   holds `data/`, or set `OP_DATA_DIR` (read as by `op`) or `DATA_DIR=<dir>` to step 3's data dir; a fresh
   worktree has no `data/`), and read the section (a changed-input callout, a Breaking
   line). Then `/record-learnings`, `/review-gate` and `/open-pr` into `dev`, and merge it.
5. **Promotion.** `gh pr create --base main --head dev --title "chore: promote dev to main for X.Y.Z"
   --body-file <the readiness evidence>`, not `/open-pr` (it pushes and attests, and a promotion does
   neither; `require-review.sh` exempts exactly this command, and CI exempts a same-repo promotion from
   `learnings` and `review-attested`). `main`'s branch protection requires green checks and `dev` up to date
   with `main` (step 7).
   Its approving-review count is zero under the owner's solo-maintainer policy applied on 2026-10-03;
   reviews remain optional, and required checks are never bypassed.
   Merge with a merge commit.
6. **Tag and notes.** First, the `v*` tag rulesets (§Branch protection; applied 2026-10-01) must be in place:
   `gh api repos/<owner>/<name>/rulesets --jq '.[] | select(.target == "tag") | .name'` lists them, one name
   per line and possibly more than one (today `Release tags: immutable` and `Release tags: maintainers only
   create`); paste the output into the back-merge PR (step 7), since the promotion PR has merged. On
   `origin/main`, `CITATION.cff`'s `version` must be `X.Y.Z` and its `date-released` today's date (UTC); if
   either is not, don't tag: re-run step 4 with the corrected date (a new release branch and promotion), since
   a tag's `CITATION.cff` is never edited after. Then `git
   fetch origin` and check out `origin/main`; `python3 .claude/scripts/changelog.py
   --check --release X.Y.Z` passes (the promotion holds exactly the PRs the file lists; with `OP_DATA_DIR` or
   `--data-dir` naming step 3's data dir when this checkout doesn't hold `data/`); `python3 .claude/scripts/changelog.py --release X.Y.Z
   --notes X.Y.Z > notes.md` (the same `--data-dir`); `gh release create vX.Y.Z --target
   "$(git rev-parse origin/main)" --title X.Y.Z --notes-file notes.md`, which creates the tag on GitHub
   (`require-review.sh` blocks an agent's `git push` of a tag, since `main`'s merge commit has no per-sha
   record; `block-ai-attribution.sh` scans the notes). No assets. Then `git fetch origin --tags` and check that
   `git rev-parse vX.Y.Z^{commit}` is that sha.
7. **Back-merge.** `main` now holds the promotion's merge commit, which `dev` lacks, and the next promotion
   can't merge until `dev` has it. `git switch -c release/X.Y.Z-back-merge origin/dev && git merge --no-ff
   origin/main` (no file changes), `/review-gate`, `git push -u origin release/X.Y.Z-back-merge` (the review
   record covers the merge commit), then `gh pr create --base dev --title "chore: back-merge main after
   X.Y.Z" --body-file <file> --label no-learning` and `record-review.py APPROVE <dispositions> --attest`.
   Merge it with a merge commit, never `--squash` or `--rebase`, which would leave `main`'s commit out of
   `dev`, which means adding it to the merge queue (`gh pr merge <n> --auto`; the queue's method is MERGE). Then check
   `git fetch origin && git merge-base --is-ancestor origin/main origin/dev`. On `dev`,
   `python3 .claude/scripts/changelog.py --check` then passes.
8. **Retention.** Keep every index and snapshot a search record pins (`op index retire` refuses a pinned
   index; §CLI). Supported older tokenizer/schema pins can still reproduce when `QUERY_VERSION` matches.
   Unsupported versions or incompatible Tantivy require the matching historical release; a changed
   `QUERY_VERSION` reports `drifted` even when the index remains supported. Keep the pinned data in all
   cases. To find the historical release for a
   record, match its pinned index's manifest (`tokenizer_version`, `schema_version`, `tantivy_version`) and the
   record's `query_version` against the releases' Data sections.
9. **After.** Deploying the release, and promoting an index, follow §Deploy and its runbook, `deploy/README.md` (together, for a release that
   changes `TOKENIZER_VERSION`, `SCHEMA_VERSION` or Tantivy).

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
| `enforce-pr-workflow.sh` | PreToolUse Bash | `git commit` (and `cherry-pick`, `revert`, `am`, `rebase`, `commit-tree`), `push`, `merge`, `pull --no-ff` and a `reset` to anything but HEAD or the upstream on `main` or `dev` (the branch of the `--git-dir`/`GIT_DIR=` repo, an `export`ed or `set -a` one too, when one is named, and the branch a `checkout`/`switch` earlier in the same command left checked out); any write to those remote refs (`HEAD:heads/dev`, glob refspecs and the matching refspec `:`/`+:` included); a move of the local ones (`update-ref`, `branch -f`/`-M`/`-C`, `checkout -B`, `switch -C`, `worktree add -B`, a fetch or pull into them other than `fetch origin dev:dev`); a refspec-less push whose config picks the destination (`git -c` `remote.<name>.push`/`.mirror`, `push.default`, `remote.pushDefault`; the repo's config, read with `git config --get-regexp`: any `remote.<name>.push`, a true `.mirror`, `push.default=matching`, or `push.default=upstream` to a protected upstream; or config it can't read: `--config-env`, `-c include.path`, `GIT_CONFIG_*`, `GIT_COMMON_DIR`); an alias under config it can't read, a git command after a `git config` that writes an alias, include, push key or upstream (or a `remote add --mirror`, `remote set-branches`, `branch -u`, or a redirect/tee/`sed -i`/cp/mv/ln into a git config file) in the same command, a push after a `checkout`/`switch`/`worktree add` that creates a branch with an upstream (`-t`, a remote-tracking start point), and an ambiguous abbreviated option; a commit, merge, reset or push whose directory, `-C`, git dir, refspec or branch it can't resolve (`cd "$X"`, a `cd` to a missing directory, `HEAD:$UNSET`); a push, add, commit, rm or mv run by `xargs` (from Kreate). It reads the command with the shared cmdparse walk (`cd`/`pushd`/`popd`, `$` words, a word that expands to nothing dropped, a command with `~` or `$` also read with HOME/TMPDIR/USER as '' (`cd ~` then stays put), a git command inside `"$(…)"`, backquotes or an unquoted heredoc body read like any other, redirects apart, `--track <remote>/<b>` and `-qt`, `checkout <b> --`, `checkout -p`, repos keyed by absolute git dir); a command it can't parse (or that crashes the parser) is refused when its text has `git` and a write word (`push`, `commit`, `merge`, `reset`, `rebase`, `cherry-pick`, `revert`, `am`, `branch`, `update-ref`, `checkout`, `switch`, `worktree`, `fetch`, `pull`); without python3, a text check that also refuses a commit or push next to `-C`, `cd`, `pushd`, `--git-dir`/`GIT_DIR` |
| `require-review.sh` | PreToolUse Bash, Write/Edit/MultiEdit/NotebookEdit | `git push` of any unreviewed commit (every refspec source, `--all`, the `--git-dir` repo's HEAD); `--tags`, glob refspecs and the matching refspec `:`/`+:`; a refspec-less push whose config chooses the refspec (`git -c` push keys, `remote.<name>.mirror`, `push.followTags`; in the repo's config any `remote.<name>.push`, a true `.mirror` or `push.followTags`, `push.default=matching`; or config it can't read, `GIT_COMMON_DIR` included); an alias under config it can't read, and a git command after a `git config` (or a write into a git config file) that sets an alias, include, push key or upstream in the same command; a push or `gh pr create` after any git command in the same call other than one that moves no ref (status, log, diff, show, rev-parse, add, push, config, a fetch without a `<src>:<dst>` refspec or `--stdin`, …): `branch -f`, `fetch . +x:feat` and `worktree add -B` move what is pushed as surely as a commit; a remote or refspec it can't resolve, or a push after a `cd` it couldn't follow; a push run by `xargs`; `gh pr create`/`new` without an APPROVE record for the head, or without an added or extended learnings entry; any hand write, copy, move or deletion of a review record under `op-reviews/` (Bash or a file tool), globs expanded, and a write whose `cd`/redirect target it can't read (`$…`, a glob) hints at one (`op-rev…`, `.git`, git-dir), or a word of the writing command does in a path component (read with the variables it can resolve put in, the tail of an unquoted `$(…)/op-revie?s/x` included, and a component mixing an unresolvable `$` with `op-`/`rev`), or after a variable is set to a path-shaped part of one (`d=op-reviews`, `d=reviews`); an option's attached value (`--output=op-reviews/<sha>`) is read as a path; inline message values (`-m`, `--message`, `--trailer` of git commit/merge/tag/notes/revert/cherry-pick/stash; `--body`, `--title`, `--notes` of gh pr/issue/release create/edit/comment/review; never a word starting with `-`) are text, not paths; a command it can't parse that mentions a push, `gh` or a review record; any command it can't check (an internal error) |
| `block-ai-attribution.sh` | PreToolUse Bash | A message-writing git command, PR-writing gh command or `gh release create`/`edit` whose text (incl. heredocs, `--trailer`, `-F`, `--body-file` and `--notes-file` files, and files read by `cat`, `head`, `tail` or `sed` (the whole file is scanned, not the lines they print; sed script files from `-f`/`--file` included, including bundled `-nf`; input filenames after `--` are literal), `< file`, `$(cat file)` or `$(< file)`; a file word is read with its variables put in, `F=msg.txt; … "$(cat "$F")"`) has a Claude co-author trailer or "Generated with" footer, in the raw text or in any word as bash reads it (`'Cl''aude'`, `$'…'`, a variable set in the command), the command also read with HOME/TMPDIR/USER as '' (a command it can't parse is scanned as raw text and, when it tokenizes, as words; one it can't check at all is refused); `.githooks/commit-msg` covers editor commits |
| `enforce-backlog-cli.sh` | PreToolUse Write/Edit/MultiEdit/NotebookEdit | Hand edits under `backlog/`, the path normalised first (relative to the call's cwd, `//`, `./`, `..` and symlinks resolved, any case) (from Kreate; decision bodies are Edit-only); a path it can't read (an internal error) is refused |
| `protect-data-dir.sh` | PreToolUse Write/Edit/MultiEdit/NotebookEdit/Bash | Any write into, move of or deletion of `data/snapshots/`, `data/indexes/` (or `data/` itself, or a directory above them: `rm -rf .`, `rm -rf ../<repo>`, `find . -delete`), incl. globs expanded against the filesystem (`rm -rf data*`, `*`), case-blind paths (APFS: `Data/`), redirects, `cp`/`rsync`/`tee`/`dd`/`truncate`/`unlink`, `find -delete`/`-exec`, `sed -i`/`perl -i`/`ruby -i`/`awk -i inplace`, `rsync --remove-s…` (`--remove-source-files`, `--remove-sent-files`, and any unique prefix, `--rem`, as openrsync reads it; `--del` for `--delete`) from them, a `git log`/`diff`/`format-patch` `--output` into them, `git format-patch` writing its patches into them (`-o`/`--output-directory` or a unique prefix, `format.outputDirectory`, else the directory it runs in; refused where `data/` is when that config can't be read), a command inside `"$(…)"`, backquotes or an unquoted heredoc body, every target judged against the worktree that contains it, case-blind (`rm -rf ../<main>/data/snapshots` or `../<MAIN>/data` from a worktree), every path judged after `~`/`~+`/`~-`, `$PWD`, `$(pwd)`, `$(git rev-parse --show-toplevel)`, `$(git rev-parse --git-common-dir)`/`--git-dir`, `$(mktemp)` (a path in the temp dir, unknown when the command sets or unsets `TMPDIR`), a `for` loop's variable (each of its words, not when the loop can exit early), `$HOME` and other variables are resolved (from the call's cwd and earlier assignments, `unset` ones empty; from the hook's environment only HOME, TMPDIR and USER, each also checked as '' (`~` too, so `cd ~` with HOME '' stays put), where `"$TMPDIR"/*` is not globbed as `/*`) and `cd`/`pushd`/`popd` followed (`-P` physically; a missing target, CDPATH or `cd -` to an unknown directory leaves it unknown), and a path that decides a check but can't be resolved (`rm -rf "$UNSET/x"`, a relative path after `cd "$UNSET"`, a redirect to `"$(echo data)/…"`) refused where `data/` is (this worktree, the call's, or their repository's main worktree); any command it can't parse, where the main worktree has `data/` or the repo has `backlog/`, and any it can't check at all (an internal error); `git clean -x/-X` and `git stash --all` (`-a` in any short cluster too; they remove gitignored `data/`); `git add -f data/`, and any forced add that git's own dry run says would stage `data/` or a `takedowns/` path (`-fA`, `-f .`, `':/data'`, `'*.jsonl'`); a forced whole-tree add, `--pathspec-from-file` or undryable add (the dry run never starts the repo's `core.fsmonitor` program); `git update-index --add` of those paths (`--cacheinfo=` too); `git add` (forced or not) of any path through a `takedowns/` directory (the takedown list and log, TASK-136); shell `mv`/`git mv`/`cp`/`rm`/`dd of=`/redirects into `backlog/` and `sed -i`/`perl -i`/`ruby -i`/`awk -i inplace` of backlog files other than decision bodies (only the CLI moves tasks); and `rm`/`mv`/`git add`/… run through `xargs` (its arguments are unseen) in a repo with `data/` or `backlog/` |
| `autofix.sh` | PostToolUse Write/Edit/MultiEdit | Formats and fixes the edited file; reports what remains (never blocks). prettier and eslint are skipped while a config or `package.json` is uncommitted, and prettier is handed the tracked `frontend/.prettierrc.json` (`--config`), so it never loads an untracked nested one |
| `remind-token-contract.sh` | PostToolUse Write/Edit/MultiEdit | Editing `normalize.py` or the tokenizer → reminder to bump `TOKENIZER_VERSION` and run the parity and differential tests |
| `load-learnings.sh` | SessionStart | Puts `.claude/learnings/INDEX.md` into every session's context |

All command-parsing gates share `.claude/hooks/lib/cmdparse.py`, which parses commands the way bash splits
them:
- separators with or without spaces: `;` `&&` `||` `|` `&` `(` `)`, newlines, and process substitution
  `<(…)`/`>(…)`;
- shell reserved words at the start of a command (`if`/`then`/`elif`/`else`/`fi`, `while`/`until`/
  `do`/`done`, `{`/`}`, `!`, `esac`, `function`, `coproc`) are skipped;
- `VAR=val` assignments and the wrappers `env`, `command`, `builtin`, `exec`, `time`, `nohup`, `nice`,
  `sudo`, `timeout`, `stdbuf`, `xargs` and `watch` are skipped, each with its own table of options that take
  a value; the assignments are kept, and a command run by `xargs` is marked, because the words xargs appends
  are invisible (`xargs_hides_args` flags `rm`, `mv` and `git push`/`add`/`commit`/`rm`/`mv` run that way;
  `require-review.sh` and `enforce-pr-workflow.sh` refuse them);
- command names are compared by basename (`/usr/bin/git`), and a `git-<sub>` program
  (`$(git --exec-path)/git-push`) is `git <sub>`;
- `export VAR=…`, `VAR=…; export VAR` and `declare -x` reach every later command's assignments (`GIT_DIR`),
  and so does every assignment while `set -a` / `set -o allexport` is on;
- one pass over the whole text carries quote state across lines, so a multi-line quoted message
  stays one word; `#` starts a comment only at the start of an unquoted word, as in bash; an unquoted
  `<<DELIM`/`<<'DELIM'` heredoc body is dropped (never `<<<`; an unquoted DELIM's body is read for command
  substitutions first); `$'…'` is decoded (`\x64`, `\144`,
  `\u0065`, …), over several lines too, and `$"…"` read as `"…"` anywhere in a word; `"$X"a` is `${X}a`;
- unquoted braces are expanded as bash does (`HEAD:d{e,}v` is `HEAD:dev HEAD:dv`, `{a..c}`, nesting), with
  quoted or escaped braces and `${…}` left literal and empty words dropped (`git push origin {,}` names no
  refspec); past 4,096 words, or 256 brace groups in one word, a parse error (which every gate refuses);
- redirections come out of argv as separate `(operator, target)` pairs;
- the command substitutions the words would hide (a `$(…)` inside double quotes, `$((…) )` included, backquotes
  outside single quotes, those in an unquoted heredoc body) are walked before the command holding them, each as
  a subshell, their bodies read as bash reads them (nested quotes, heredocs, `case` patterns: a `case <word> in` opens one
  wherever it starts, and an unbalanced `case`/`esac`, or a body ending in a `case` with its `esac` after the end, is a parse error; `$((…))` whose inner `(` closes at its end is
  arithmetic, read as text), and the word keeps
  its text; an unquoted `$(…)` is split into commands by its parentheses (TASK-156);
- `for v in <words>; do …; done` is read once per word with `v` set to it (up to 64 words and 20,000 unrolled
  tokens per command; past either, without `in`, or with a `break`/`continue`/`return`/`exit` in the body, `$v`
  stays unknown);
- it follows `cd`, `pushd`, `popd`, `-C`, `bash -c` (with the assignments before it exported to it, and what
  it sets kept inside it) and `eval`; a `cd` target goes through `expand_word` (`~`, `~+`, `~-`, `$PWD`,
  `$(pwd)`, `$(git rev-parse --show-toplevel)`, `$(git rev-parse --git-common-dir|--git-dir|--absolute-git-dir)`,
  `$(mktemp [-d] [-t prefix])` (a path in the temp dir; unknown when the command sets or unsets `TMPDIR`), `$HOME`, variables: set or `unset` earlier in the command, else
  only HOME, TMPDIR and USER from the hook's environment (unset there: ''), which a gate also reads as '';
  `~` is $HOME when set, else the passwd home, as bash reads it, and unknown after `HOME=`/`unset HOME`), `cd -P` resolves
  symlinks, and a target it can't resolve, one that doesn't exist, a relative one under CDPATH, or `cd -` back
  to an unknown directory marks the directory unknown (and, after such a `cd`, the one `cd -` returns to, unless
  it was already the current one: a failed `cd` keeps OLDPWD);
- a git alias is replaced by what git runs for it, whether set with `git -c alias.<name>=…` or in the repo's
  config, and a `!shell` alias by the commands in its text; a builtin is never looked up, as git never lets
  an alias shadow one. A git command's `-c` settings and its `--git-dir` or `GIT_DIR=` are read too. When git
  would also read config the parser can't (`--config-env`, `-c include.path`/`includeIf.*.path`, a
  `GIT_CONFIG_*`, `GIT_CONFIG_PARAMETERS`, `GIT_COMMON_DIR`, `HOME` or `XDG_CONFIG_HOME` assignment), a
  subcommand that isn't a builtin raises `FailClosed`, which every gate refuses, and the push gates refuse a
  refspec-less push; so does a git command after a `git config` in the same command that writes an alias, an
  include, a push key or an upstream (`branch.<b>.merge`), a `git remote add --mirror`, `git remote
  set-branches` or `git branch -u`/`--track`, or a redirect, `tee`, `sed -i`, `cp`/`mv`/`ln` into a git config
  file (`.git/config`, `config.worktree`, `~/.gitconfig`, `$XDG_CONFIG_HOME/git/config`) (the parser read the
  config before it was written), and so does a `git push` after a `checkout`/`switch`/`worktree add` that creates
  a branch with an upstream (`-t`/`--track`, or a remote-tracking start point, unless `--no-track`);
- an abbreviated long option is written out in full, as git reads it (`git add --forc` is `--force`, `git push
  --al` is `--all`), from a table of every long option of the subcommands the gates read (`GIT_LONG_OPTS`,
  from `git <sub> --git-completion-helper-all`, git 2.42 plus the options CI's newer git lists); an ambiguous
  one (`git push --a`) raises `FailClosed`. `.claude/scripts/tests/test-git-long-opts.sh` compares the table
  with the installed git and notes drift either way, so it holds on any git version: an abbreviation is
  expanded only when unique in the table, and every option a gate checks is in it, so an option the table
  lacks can at worst over-block, never let a gated option through. It fails only when that premise breaks: a
  `--option` a gate hook names, which this git lists for a tabled subcommand, missing from the table.

`enforce-pr-workflow.sh` uses the same walk. A command the parser cannot read is **blocked**, never
allowed, when it looks like what a gate guards (fail closed); protect-data-dir refuses every one in a repo
with `data/` or `backlog/`. A gate that hits an error it doesn't expect (a recursion limit, an undecodable
character) exits 2, never 1: Claude Code lets a hook's other exit codes through, so a crash would fail open.
block-ai-attribution, require-review and protect-data-dir run their check as `python3 -c "$PROG"` with the
payload on stdin (an environment variable fails past ARG_MAX, about 1 MB, with exit 126) and exit 2 on any status
but 0 (no python3 is 127); enforce-pr-workflow passes its payload on stdin too (TASK-172) and, when its verdict is empty, falls back to
its text check (a git write word is refused). Every gate walks a command with `~` or `$` a second time with
HOME, TMPDIR and USER read as '' (TASK-156).
Every raw-text scan (require-review's and enforce-pr-workflow's parse-failure nets, block-ai-attribution's
text scans, cmdparse's case cut-short check) joins line continuations with the one `cmdparse.join_continuations`
that `preprocess` uses: a backslash-newline is deleted outside single quotes, `$'…'`, comments and quoted-delimiter
heredoc bodies, and in text it can't scan to the end (an unclosed quote) every one is deleted (TASK-164).
block-ai-attribution refuses a message file it can't resolve (an unknown variable, a relative path after a
`cd` it couldn't follow) and a command substitution that runs any other program on a file or an unresolvable
word (`$(awk 1 msg.txt)`); one that reads no file (`$(date)`) passes (TASK-170). When enforce-pr-workflow
refuses a commit that stayed in a protected checkout because a `cd ~/…` fails with HOME '', its message says to
name the target with an absolute `git -C` path (TASK-173).
`.claude/hooks/tests/test-parser-boundaries.sh` checks the exact joined text after an unquoted joined delimiter or a tab-prefixed `<<-` delimiter, plus the production worktree-root comparison with differing case on every platform (the filesystem-based APFS rows also remain).
The case tables count only exit 2 as a block. The threat model is honest mistakes, not
deliberate evasion.

### Mutation testing

`.claude/scripts/mutate.py` (`make mutate`, `make mutate-changed`, `--match <text>`) proves the case tables
have teeth. Each mutant in `.claude/scripts/mutants/*.json` breaks one piece of gate or tooling logic, and at
least one table must fail. Survivors are either fixed with a new row or documented as `equivalent`, with
the reason. Mutants run in parallel, each against a copy of every case table: the full set (694 at TASK-171) takes hours (188 in 140 min on a 4-CPU runner, nightly run 37017691575), and `--changed` only the mutants of the files a diff touches. `--shard i/n` runs every n-th selected mutant from the i-th (1 <= i <= n), so n shards partition the set the same way every run; `--list` prints the selected labels and runs nothing. Reviews run
`make mutate-changed`; the nightly workflow runs every mutant as 8 shards in parallel jobs (§CI).
Hook probes stay data (TASK-169): `.claude/scripts/lint_probes.py` (in `make tooling`)
fails on a case-table row whose probe, label or command holds a `$(…)` or backquote bash would run while the
table runs, and `.claude/scripts/probe_hook.py` feeds one probe, from a file or one argument, to a hook or to
cmdparse without a shell (`sandbox` runs it for real only in a removed mktemp directory that is HOME too).
Never hand-roll a serial loop.

### Branch protection (GitHub)

`dev` and `main` require a PR, with these checks green: `lint`, `test`, `claude-tooling`, `attribution`,
`learnings`, `review-attested`. No force-push, no deletion, admins included, and conversations must be
resolved. `main` additionally requires the branch up to date with it (so each
promotion is followed by §Release step 7's back-merge). The owner changed only `main`'s required
approving-review count from 1 to 0 on 2026-10-03 for the solo-maintainer workflow; optional reviews remain
available. Required checks and all other protection settings were preserved. This protection was
applied on 2026-09-25, after
the repo was made public (free-plan orgs can't protect private repos). `dev` is the default branch, and
merged feature branches are deleted automatically.

**`dev`'s merge queue** (TASK-161, decision-027) replaces "require branches to be up to date" on `dev`. A
maintainer applied it on 2026-10-02 with the commands in decision-027 (the first queued PR was #81):

- the repository setting "Allow auto-merge", which `gh pr merge <n> --auto` needs;
- a branch ruleset `dev: merge queue` on `refs/heads/dev` with one `merge_queue` rule: merge method MERGE,
  ALLGREEN grouping, up to 5 entries built and merged at once, and a 60-minute check timeout;
- `strict: false` on `dev`'s classic required checks.

The six required checks don't change, and they apply to the queue's builds too.
`gh api repos/<owner>/<name>/rules/branches/dev` shows the `merge_queue` rule (`merge_queue` in its `type`s).

Release tags are protected by two active tag rulesets on `refs/tags/v*`, applied
by a maintainer on 2026-10-01 (TASK-151), before the first release tag: **`Release tags: maintainers only
create`** restricts creating a matching tag (bypass: the maintain and admin repository roles), and **`Release
tags: immutable`** blocks updating and deleting one, with no bypass actor (a ruleset's bypass list covers every
rule in it, hence two rulesets). A moved tag would silently re-section `CHANGELOG.md` and break "run that
release's tag" for an old search record. §Release step 6 checks they are in place; its check prints one name
per tag ruleset, so more than one name is expected.
