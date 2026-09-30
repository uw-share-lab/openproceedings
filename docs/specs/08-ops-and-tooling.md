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
│   │   └── cli.py               # `op` entry point
│   └── tests/{unit,golden,differential,bench,contract,e2e,fixtures}/
├── frontend/                    # npm workspace member: Next.js App Router, output standalone (spec 05; skeleton TASK-039)
├── docs/{specs,plans,results,design,usability,research}/   # created as needed; docs/releases.toml: each release's data (§Release)
├── backlog/                     # Backlog.md: tasks, completed, docs, decisions — CLI only
├── deploy/                      # (M6, planned) Dockerfiles, compose.yml
└── data/                        # gitignored: cache/, snapshots/, indexes/, embeddings/, research/, records/ (records.sqlite)
```

**Environment:** uv for all Python. `uv sync` at the root installs every workspace member and the dev tools
into one `.venv` from one `uv.lock`. New Python packages join by adding their directory to
`[tool.uv.workspace] members`. npm for the frontend. `scripts/setup-dev.sh` once per clone.

## CLI (`op`)

| Command | Does |
|---|---|
| `op ingest openreview\|iclr\|neurips\|pmlr\|ris … [--offline]` | fetch sources (`--offline`: cache only, no network) |
| `op snapshot build` · `op snapshot diff <a> <b>` | build an immutable snapshot, or compare two. There is no prune or delete command: keep the snapshot of every index a search record pins (the versions `op index retire` refuses), since that record's exports read it to attribute each abstract and withhold every abstract without it (decision-021); a future prune command must refuse while a record pins an index built from the snapshot |
| `op index build --snapshot <dir\|name\|hash prefix> [--out <dir>]` · `op index parity --index <v> [--snapshot <id>]` · `op index retire <index_version> [--dry-run]` (TASK-085) | build an immutable index; check it holds `normalize()`'s tokens for its snapshot (local, over the real corpus); retire an old one: delete `<data-dir>/indexes/<index_version>/` under the indexes lock `op index build` holds: set aside as `.retiring-<index_version>` (no reader finds half an index, and no sweep deletes it), checked once more, then renamed to `.tmp-retire-<index_version>` (the commit point) and removed; the next build or retire sweeps a removal cut short. Refused, exit 1, one line to stderr, nothing touched: while any search record pins it (`RecordStore.pinned`, the count reported; a deleted pinned index would leave those records' replays permanently `drifted`), while `current` or any other symlink in `indexes/` points at it, when the record store can't be read, or when the name isn't an index_version directory directly under `indexes/` (the name is checked against the index_version format before any path is built, so `../x` never names a path). `--dry-run` runs the checks and reports the outcome with the same exit status, deleting nothing. Order: repoint `current` to the new version, SIGHUP the API, confirm `/api/v1/meta` reports the new version, then retire the old one (the API keeps serving the old version until its reload). It can't see an `op serve --index <index_version>` that serves the version by name: check what each running instance serves first. A promotion (`ln -sfn`) and a record save take no indexes lock, so after the rename the pins and every symlink's target are checked again and a hit, or anything raised (Ctrl-C included), renames the directory back and refuses or re-raises. If that rename-back fails, one ERROR `index_retire_restore_failed` names the `.retiring-` directory and the operator must `mv` it back to `<index_version>` before serving it or running another build or retire (no sweep touches it; until then every retire of that version, `--dry-run` included, is refused as `retire_cut_short`, whether `<index_version>` is absent or was rebuilt); what remains is the few syscalls between that check and the removal, after which a save or replay naming the version finds it absent. It says so when it waits for the lock. A chmod or removal that fails after the rename still retires the version (its name is gone) and reports `tmp_left`; a sweep that can't remove a leftover logs `tmp_sweep_failed` and carries on, so it never fails a later build. One log line: `index_retired` (INFO; WARNING with `tmp_left`), `index_retire_checked` (dry run) or `index_retire_refused` (WARNING; DEBUG for a malformed name, which is not logged), each with the version, the pinned count and the outcome or reason |
| `op search "<q>" [--mode scholar] [--explain \| --ids] [--engine tantivy\|reference] [--sort <s>] [--limit <n>] [--index <dir\|version>]` | ranked hits under a PRISMA header (default): searched time, index, crawl window (first to last fetch), tokenizer and query versions; a bootstrap-corpus caution when the index holds only RIS, or a caution that the sources are unknown when its snapshot isn't in the data dir or its hash differs; identified, removed by default filters (ineligible and unclassified), screened; the canonical and identification strings; every wildcard's expansion (its count and first 10 terms; every term with `--explain`); the sorted id set (`--ids`; `--engine reference` runs the oracle over the index's snapshot, `--ids` only); or the compiled query (`--explain`). Diagnostics go to stderr as user output; one `search_run` INFO line per run (task-030) |
| `op export "<q>" --format ris\|csv\|bibtex\|jsonl [--mode scholar] [--index <dir\|version>] [--out <file>]` | export the full matched set in id order (spec 04 §Exports), streamed to stdout or written whole to `--out` (never a partial file); the count is checked against the query's total. It verifies the index's snapshot to name each abstract's source (TASK-138); without it, every abstract is withheld and each record says so, with a warning on stderr and exit 0 (decision-021) |
| `op record save "<q>" [--mode scholar] [--index current\|<index_version>] [--json]` · `op record replay <id> [--index current\|<index_version>] [--json]` | freeze a search as a search record in `<data-dir>/records/records.sqlite` (the same functions as `POST /records`, `records.freeze` + `RecordStore.insert`: a record identical to the API's but for its id and time) and print its id, page and PRISMA summary, or the stored record (`--json`); replay one (the same function as `GET /records/{id}`, `records.replay`) on its own index when the data dir holds it, else on `--index` (default `current`), and print the status, `reproduced` / `drifted` / `mismatch`, the changed inputs and `+added / −removed`, or the API's `replay` block (`--json`). `--index` is a name under `<data-dir>/indexes`, never a directory: a record pins a version a replay must find by name. Left out, as serving policy: the rate limit, the save ceilings, and the verified-clause cap and candidate ceiling, so a CLI replay is never withheld (decision-010); the store's size cap and free-space floor (the API's defaults) apply (task-083) |
| `op serve [--host] [--port] [--index current\|<index_version>] [--cors-origin …] [--trusted-proxy …] [--rate-capacity] [--rate-refill] [--export-weight] [--no-rate-limit] [--max-verified-clauses] [--max-verification-candidates] [--max-verification-seconds] [--log-query-text]` | run the API (04 §Implementation notes, as built): one uvicorn process over `<data-dir>/indexes/<index>`; SIGHUP reloads it. Refused as usage, each option named with the validator's reason: a trusted proxy wider than /8 or /32, `--no-rate-limit` with a non-loopback `--host` (§Deploy), and limits that could never be paid (decision-010) |
| `op embed build` (deferred with 06, decision-017; task-058) | build embeddings for the current index (06) |
| `op eval coverage [--index <v>] [--out <dir>] [--date YYYY-MM-DD] [--check]` (TASK-054) · `op eval scholar [--query <name>]` (planned, task-056) · `op eval audit` (planned, task-055) · `op eval near-miss` (deferred with 06, decision-017; task-061) | the 07 reports; `coverage` writes `docs/results/<date>-coverage.md` and `--check` exits 1 when the M4 gate fails; `near-miss` is 06's recall@25 |
| `op openapi [--out <file>]` | print the OpenAPI document, sorted and stable, without loading an index (task-040); `make openapi` writes it to `backend/tests/contract/openapi.json` and regenerates `frontend/src/api/schema.ts` from it |

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
| `test` → `test` | pytest under pytest-xdist at the `pr` Hypothesis profile (200 examples, 2 s deadline) (unit, golden, differential@200, contract; the 2,000-example `ci` profile runs nightly, TASK-127); vitest; `next build` (the standalone server must exist); OpenAPI snapshot and TS types freshness (`make openapi`, then `git diff --exit-code` on `backend/tests/contract/openapi.json` and `frontend/src/api/schema.ts`; unconditional, TASK-040) |
| `claude-tooling` → `claude-tooling` | `make tooling`: roster lint, `.claude/README.md` and learnings index freshness, backlog hygiene (no Done task left in `tasks/`), every case table under `.claude/hooks/tests/` and `.claude/scripts/tests/` (the tooling scripts, the network guard, `changelog.py`) |
| `pr-gates` → `attribution`, `learnings`, `review-attested` | no AI authorship in commits or PR text; the branch adds or extends a learnings entry (unless labelled `no-learning`); the PR body attests APPROVE for the head sha |
| `nightly` (scheduled, not a PR check) | Four parallel jobs, each with its own time limit: the whole backend suite at the `ci` profile (2,000 examples) under pytest-xdist; the oracle-backed properties at 50,000 examples; the exhaustive tokenizer check (`OP_EXHAUSTIVE=1`) plus every other property at 50,000; and `make mutate` (every mutant in `.claude/scripts/mutants/*.json` killed or documented as equivalent). Differential@50k gets its own job in task-057 (M4); full-corpus parity stays local (decision-004) |
| `bench` → `bench` (advisory: not a required check yet) | pytest-benchmark on the 5k fixture index (`backend/tests/bench`, task-031): the PR's base and head on one runner; a minimum time over 20% slower than the base fails, and each benchmark asserts its spec 03 budget (p95). It becomes required once it has run green on a few PRs without false failures (runner noise); a maintainer adds it to `dev`'s required checks |
| `e2e` → `playwright` (advisory: not a required check yet) | `make e2e`: Playwright against the deterministic 5k fixture API (`backend/tests/e2e/`) and the standalone frontend: the spec 05 review flow, keyboard focus behavior, axe WCAG 2.2 AA in both themes at 1280 and 320 px, root reflow at 320 px, and platform-specific `/search` visual baselines in both themes on the fixed `ubuntu-24.04` CI label |

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
Caddy in front for TLS. Caddy must not log query strings: `GET /api/v1/search?q=…` carries the query
(spec 04 §Implementation notes). **`op serve` must sit behind that proxy**, never face clients directly:
uvicorn (h11) has no request-header or slow-body timeout of its own, so the proxy's timeouts are what bound a
client that sends its request slowly; the app caps a body at 64 KiB (413 `API_BODY_TOO_LARGE`), uvicorn's
`limit_concurrency` (`ApiConfig.limit_concurrency`, default 256) bounds the connections one process holds,
and `timeout_keep_alive` (`keep_alive_seconds`, default 5) closes an idle one. The Caddyfile **must** set
(Caddy v2 directive names, checked against the Caddy docs 2026-09-27):

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
is refused, as is `--no-rate-limit` with a non-loopback `--host`. Swagger UI (`/api/v1/docs`, scripts from a
CDN) is off on a non-loopback `--host` unless `--docs` is passed; leave it off in production. The data volume is read-only in `api`, except the `records/` directory
(`records/records.sqlite` and the WAL files SQLite writes beside it; spec 04 §Search records), and it
holds each served index's snapshot beside it (`/papers/{id}` reads provenance from it). Run `op record save`
and `op record replay` against that data volume as the API's service user (`sudo -u <api user> op record …`
or the `api` container's own user): the store's directory is 0700 and `records.sqlite` 0600, so a record
saved as another user leaves a store (and WAL files) the API can't write, or can't read at all. Refreshing the index
means building a new `index_version` offline, switching the `current` symlink, and sending SIGHUP; an old
version no record pins can then be deleted with `op index retire <index_version>`, once `/api/v1/meta` reports
the new version (the API serves the old one until its reload; §CLI). Hosting is
still open (00, question 5).

**What a public instance serves (decision-018; not legal advice).** Every abstract in the index, in results,
on paper pages and in exports. Before a deployment is public: (1) each record names the source of its abstract
and links to it, and a PMLR abstract appears with its citation and a link to the PMLR page (CC BY 4.0's
attribution terms; TASK-134 for the result list); (2) every page names a takedown contact (TASK-133). Private,
local and development deployments may omit the contact. TASK-133's proposed takedown procedure, not yet
decided, withholds the record's abstract from the next `index_version`; older versions that search records pin
still serve it, because `op index retire` refuses a pinned version, and TASK-133 settles how a takedown
reaches them. The unlicensed years rest on fair dealing alone; consulting the University of Waterloo copyright
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
`NEXT_PUBLIC_TAKEDOWN_CONTACT`. The e2e suite
builds with the placeholder `takedown@example.org` (`frontend/playwright.config.ts`); `frontend/.env.example`
documents both variables.

**Takedown procedure (proposed by TASK-133; nothing below is automated yet).**
- **Who receives a request:** the deployment's operator, at that contact. A request that arrives on the issue
  tracker through the footer's fallback goes to the project maintainers, who pass it to the operator of the
  deployment it names, or act on it for a deployment they run. Fallback requests are **public** (GitHub issues
  are), so the footer asks requesters to leave out personal details (FT-3); a public instance sets its own
  contact.
- **What is removed:** the record's `abstract` only, from the next `index_version`. The record stays and is
  still matched on its title, as a record with a missing abstract is (01 §Error handling).
- **How it is applied, as built: by hand, and not yet per record.** No `op` command or build step withholds
  one abstract today. `op snapshot build` replays the crawl cache as fetched, a snapshot can't be edited (its
  files are hash-checked against `snapshot_hash`, and `data/snapshots/` is write-protected), and the next
  crawl would fetch the abstract again. Until the tooling below exists, the operator acknowledges the
  request, logs it, and, if the abstract has to go before then, takes the public instance offline. With the
  tooling, the operator adds the record id to the deployment's takedown list, runs `op snapshot build` (which
  sets `abstract` to `null` for each listed id and counts them in the manifest), then `op index build`, and
  promotes the new `index_version` as for any refresh (switch `current`, SIGHUP).
- **Older index versions keep the abstract.** Indexes are immutable, and a search record pins the index it
  was run on: the API loads that version for the record's replay and its exports (`/export?record_id=`, or
  `?index_version=`), and `op index retire` refuses to retire a version any record pins (TASK-085: it
  reports the count and deletes nothing).
  So a new `index_version` alone leaves the abstract retrievable through exports from a pinned older one.
  The procedure closes this at serve time: the API applies the takedown list to every response that carries
  an abstract (search hits, `/papers/{id}`, exports), whatever index version answers. That changes what is
  shown, not what matches: a pinned version still matches on the abstract it holds, so a record's ids and its
  replay are unchanged (guarantee 4), and each withheld abstract is marked as withheld, not shown as missing
  (guarantee 6). This is not built (see below).
- **How it is recorded:** in a takedown log the operator keeps outside git (it holds the requester's
  details): the record id, the date received, the requester and the basis they give, the decision, the date
  applied and the first `index_version` without the abstract. With the tooling, the snapshot manifest also
  counts withheld abstracts, so `/coverage` shows them and a snapshot diff names the records whose abstract
  went.
- **Missing tooling** (TASK-136; decision-018 requires the contact; the removal this procedure proposes needs
  this tooling before a public launch): a takedown list
  read by `op snapshot build` (its place and format, and whether `snapshot_hash` covers it); the withheld
  count in the manifest and on `/coverage`; the serve-time withholding above, applied to every index version
  the API loads, with a withheld marker distinct from missing; a decision on pinned versions still matching on
  withheld text; replay and record-page behaviour; a check that no listed id's abstract is served; a web-image
  build ARG and required-variable gate for public deploys; and where the operator's log lives.

## Release (M6; decision-023, TASK-066)

A release is a commit on `main`, reached by a `dev → main` promotion PR, and tagged `vX.Y.Z`. It holds the
code at that commit (the backend package and the frontend, one version), its `CHANGELOG.md` section, and its
table in `docs/releases.toml`: the index it was verified on. It holds no data: snapshots and indexes are never
committed or attached to a release (00 §Open questions 1, closed by decision-018: the corpus is never
committed). **Code and data ship separately:** a release never changes which `index_version` an instance
serves, and promoting an index is the §Deploy runbook, run on its own and recorded in the next release's Data
section. The one exception is a release that changes `TOKENIZER_VERSION`, `SCHEMA_VERSION` or Tantivy: its
code can't serve an index built with the old ones (spec 03; `engine/tantivy_engine.py` `unservable`), so it is
verified on, and deployed with, an index its own code built. Nothing here depends on where an instance is
hosted (00, question 5). The first release is tagged once TASK-065 (deploy) is done.

**Versioning.** One semver version for the app, `MAJOR.MINOR.PATCH`:

| Version | Lives in | Changes when |
|---|---|---|
| app `X.Y.Z` | `backend/pyproject.toml` and `frontend/package.json` `version`, kept equal (also recorded in `uv.lock` and `package-lock.json`); `op --version` and the snapshot manifest's `openproceedings_version` report it | once per release, on its release branch |
| `TOKENIZER_VERSION`, `SCHEMA_VERSION` | the code; inputs to `index_version` (03 §Versioning) | the `index-versioning` bump rules |
| Tantivy | `uv.lock`; each index manifest's `tantivy_version` (not an `index_version` input) | a dependency upgrade, which always bumps `SCHEMA_VERSION` too, so the release gets a new `index_version` it can build and serve (a replay reports it as `schema_version`) |
| `QUERY_VERSION` | the code; in `canonical_hash` and every search record (04) | the `index-versioning` bump rules |
| `index_version` | the data: `data/indexes/<index_version>/` | a new snapshot, or a tokenizer, schema or ranking change |

- **MAJOR:** a breaking change to the `/api/v1` contract (that is a new `/api/v2`), the `op` CLI, an export
  format or the search-record store. Before 1.0.0 these bump MINOR.
- **MINOR:** new features, and any change of `TOKENIZER_VERSION`, `SCHEMA_VERSION`, Tantivy or
  `QUERY_VERSION`: search records saved under the previous release then replay as `drifted`, never
  `reproduced` (guarantee 4 is kept by saying so, never by hiding it).
- **PATCH:** fixes that change none of those four.
- The first tag is `v0.1.0`. Versions stay `0.y.z` until the owner declares the v1 release (M6), `1.0.0`.

The app version never enters `index_version` or `canonical_hash`. A search record pins `index_version`,
`tokenizer_version` and `query_version`, not the app version. It replays as `reproduced` while its index is
kept, the running code can serve that index (same `TOKENIZER_VERSION`, `SCHEMA_VERSION` and Tantivy) and its
`QUERY_VERSION` matches; otherwise as `drifted`, naming the changed inputs (04 §Search records). So a record
saved under an earlier release with other versions is reproduced by running that release's tag on the index
the record pins, which is why tags and retention (step 8) matter (guarantee 4).

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
  `snapshot_hash`, `tokenizer_version`, `schema_version`, `tantivy_version`, `query_version`) and which
  saved search records still reproduce. A release whose four versions differ from the previous release's
  starts with a `drifted` callout, and is refused as a PATCH.
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
1. **Readiness on `dev`.** The required checks are green on its head, and so are `e2e`, `bench` and a
   `nightly` run from the last day. `backlog task list --plain` shows no open Must finding. The latest
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
   index is present, else falls back to `--index` and reports `drifted` for no real change). Required: with the four versions
   unchanged, every sampled record whose index is kept reports `reproduced`; with any changed, `drifted`,
   naming exactly the changed inputs; a `mismatch` (exit 3, `API_REPLAY_MISMATCH`) blocks the release.
4. **Release branch.** From here until the tag exists, nothing else merges into `dev`. `git switch -c
   release/X.Y.Z origin/dev`; set `version` to `X.Y.Z` in `backend/pyproject.toml` and
   `frontend/package.json`, then `uv lock` and `npm install --package-lock-only --ignore-scripts`; add
   `[releases."X.Y.Z"]` to `docs/releases.toml` from step 3's index manifest
   (`data/indexes/<v>/manifest.json`) and the code's `QUERY_VERSION` (never edit a released table); `make
   changelog RELEASE=X.Y.Z`, which checks the table against that manifest (so run it in the checkout that
   holds `data/`, or set `OP_DATA_DIR` (read as by `op`) or `DATA_DIR=<dir>` to step 3's data dir; a fresh
   worktree has no `data/`), and read the section (a `drifted` callout, a Breaking
   line). Then `/record-learnings`, `/review-gate` and `/open-pr` into `dev`, and merge it.
5. **Promotion.** `gh pr create --base main --head dev --title "chore: promote dev to main for X.Y.Z"
   --body-file <the readiness evidence>`, not `/open-pr` (it pushes and attests, and a promotion does
   neither; `require-review.sh` exempts exactly this command, and CI exempts a same-repo promotion from
   `learnings` and `review-attested`). `main`'s branch protection needs one approving review from a second
   person (never self-approved, never bypassed; admins included) and `dev` up to date with `main` (step 7).
   Merge with a merge commit.
6. **Tag and notes.** `git fetch origin` and check out `origin/main`; `python3 .claude/scripts/changelog.py
   --check --release X.Y.Z` passes (the promotion holds exactly the PRs the file lists; with `OP_DATA_DIR` or
   `--data-dir` naming step 3's data dir when this checkout doesn't hold `data/`); `python3 .claude/scripts/changelog.py --release X.Y.Z
   --notes X.Y.Z > notes.md` (the same `--data-dir`); `gh release create vX.Y.Z --target
   "$(git rev-parse origin/main)" --title X.Y.Z --notes-file notes.md`, which creates the tag on GitHub
   (`require-review.sh` blocks an agent's `git push` of a tag, since `main`'s merge commit has no per-sha
   record; `block-ai-attribution.sh` scans the notes). The `v*` tag ruleset (§Branch protection) must already
   be in place: `gh api repos/<owner>/<name>/rulesets --jq '.[] | select(.target == "tag") | .name'` lists
   it; paste the output into the promotion PR. No assets. Then `git fetch origin --tags` and check that
   `git rev-parse vX.Y.Z^{commit}` is that sha.
7. **Back-merge.** `main` now holds the promotion's merge commit, which `dev` lacks, and the next promotion
   can't merge until `dev` has it. `git switch -c release/X.Y.Z-back-merge origin/dev && git merge --no-ff
   origin/main` (no file changes), `/review-gate`, `git push -u origin release/X.Y.Z-back-merge` (the review
   record covers the merge commit), then `gh pr create --base dev --title "chore: back-merge main after
   X.Y.Z" --body-file <file> --label no-learning` and `record-review.py APPROVE <dispositions> --attest`.
   Merge it with a merge commit (`gh pr merge <n> --merge`, never `--squash` or `--rebase`, which would leave
   `main`'s commit out of `dev`), then check `git fetch origin && git merge-base --is-ancestor origin/main
   origin/dev`. On `dev`, `python3 .claude/scripts/changelog.py --check` then passes.
8. **Retention.** Keep every index and snapshot a search record pins (`op index retire` refuses a pinned
   index; §CLI). After a release that changes `TOKENIZER_VERSION`, `SCHEMA_VERSION` or Tantivy, its code
   can't serve the older pinned indexes (after a `QUERY_VERSION`-only change it still serves them, and
   replay reports `drifted`), but the release each record was saved under still can: keep them. To find that release for a
   record, match its pinned index's manifest (`tokenizer_version`, `schema_version`, `tantivy_version`) and the
   record's `query_version` against the releases' Data sections.
9. **After.** Deploying the release, and promoting an index, follow §Deploy (together, for a release that
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
| `enforce-pr-workflow.sh` | PreToolUse Bash | `git commit`/`push`/`merge` on `main` or `dev`, and any write to those remote refs (from Kreate) |
| `require-review.sh` | PreToolUse Bash | `git push` of any unreviewed commit (every refspec source, `--all`); `gh pr create`/`new` without an APPROVE record for the head, or without an added or extended learnings entry |
| `block-ai-attribution.sh` | PreToolUse Bash | A message-writing git command, PR-writing gh command or `gh release create`/`edit` whose text (incl. heredocs, `--trailer`, `-F`, `--body-file` and `--notes-file` files) has a Claude co-author trailer or "Generated with" footer; `.githooks/commit-msg` covers editor commits |
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
resolved. `main` additionally requires 1 approving review and the branch up to date with it (so each
promotion is followed by §Release step 7's back-merge). This was applied on 2026-09-25, after the repo was
made public (free-plan orgs can't protect private repos). `dev` is the default branch, and merged feature
branches are deleted automatically. **Before the first release tag**, a maintainer adds a tag ruleset on `v*`:
only maintainers create one, and none is updated or deleted (a moved tag would silently re-section
`CHANGELOG.md`); §Release step 6 checks it is in place.
