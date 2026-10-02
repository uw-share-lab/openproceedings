# openproceedings

Exact, reproducible Boolean search over **NeurIPS, ICLR and ICML** titles and abstracts, built for systematic
reviews. Reviews of ML research need a search they can report: a query string, a date and a hit count that
anyone can run again. Google Scholar can't give that: it searches full text, stems terms, mixes workshop
papers into the results, and its results drift. Neither can OpenReview, which has no Boolean search.

## Guarantees

Every part of the system is held to six guarantees ([spec 00](docs/specs/00-overview.md) §Guarantees is
authoritative):

1. **Exact.** A term matches only its exact normalized token: case-folded, NFKC, marks (accents) folded, split on
   punctuation. No stemming, synonyms, stopwords or fuzziness. `benchmarking` doesn't match `benchmark`, and
   suffixes match only through a wildcard you write (`benchmark*`, `model$`).
2. **Title and abstract only.** No other text is searched. Metadata is reached only through filter fields
   that you write.
3. **Filters live in the query.** A UI filter and the same filter typed in the query are one clause, so a
   saved query string describes its whole result set.
4. **Reproducible.** Every response states its `index_version`. The same canonical query on the same
   `index_version` returns the same set of ids.
5. **Ranking never changes membership.** Field-weighted BM25 only orders the matched set.
6. **Transparent.** Wildcard expansions, warnings and every exclusion count are shown, never applied silently.

## What it does

- **Boolean search** ([spec 02](docs/specs/02-query-language.md)): `AND`, `OR` and `NOT` in uppercase,
  parentheses, `"quoted phrases"`, `a NEAR/5 b`, the suffix wildcards `*` (zero or more characters) and `$`
  (zero or one), and the fields `title:`, `abstract:`, `venue:`, `year:` (`2020..2024`), `track:` and
  `status:`. The web app has a query editor with live diagnostics, a concept-group builder, and a syntax help
  page (`/help/syntax`).
- **Scholar and Publish or Perish syntax** (`mode=scholar`, `op search --mode scholar`): `|`, `source:`
  (mapped to `venue:`) and PoP's `$` are accepted. Each rewrite is reported, so an existing review string runs
  unchanged or comes back with a precise explanation.
- **Default filters with exclusion accounting**: workshop, competition and rejected papers are indexed too.
  A query without a `track:` clause gets `track:(main OR datasets_benchmarks OR position)`, and one without a
  `status:` clause gets `status:accepted`, both written out in the canonical string; write your own clause to
  include the others. Every search reports what the defaults removed, each record counted once: the ineligible
  records are PRISMA's "removed before screening: marked ineligible by automation tools", and the
  unclassified ones (track or status `unknown`) are reported apart, under "other reasons"
  ([skill](.claude/skills/prisma-reporting/SKILL.md)).
- **Search records and replay** ([spec 04](docs/specs/04-backend-api.md) §Search records): saving a search
  freezes its canonical query, `index_version` and sorted ids into an immutable record with its own page.
  Replaying it later reports `reproduced`, `drifted` (with what changed and the ids added or removed) or
  `mismatch`. The web app also writes a methods paragraph you can copy.
- **Exports with provenance**: RIS (checked against Covidence), CSV, BibTeX and JSONL of the entire matched
  set. Each record names the source of its abstract and links to it.
- **Coverage page** (`/coverage`, `GET /api/v1/coverage`, `op eval coverage`): indexed counts per venue, year,
  track and status, compared with official accepted counts ([spec 07](docs/specs/07-evaluation.md) §C).
- **Takedowns** ([decision-022](backlog/decisions/decision-022%20-%20A-takedown-withholds-an-abstracts-display-not-its-matching-on-every-loaded-index-version-the-takedown-list-and-log-live-in-the-data-directory-TASK-136.md)):
  a listed abstract is withheld from every index version the instance serves, in results, paper pages and
  exports, and marked as removed. `op takedown check` verifies a running instance.
- **One CLI, `op`**, runs the same functions as the API: `op ingest`, `op snapshot build|diff`,
  `op index build|parity|retire`, `op search`, `op export`, `op record save|replay`, `op serve`,
  `op eval coverage`, `op takedown check` and `op openapi` ([spec 08](docs/specs/08-ops-and-tooling.md) §CLI).

**Abstracts on a public instance.** A public deployment shows every abstract, attributed to its source
(OpenReview, the NeurIPS proceedings or PMLR) with a link to it, and names a takedown contact. Private, local
and development deployments may leave the contact out. For the 2024+ conferences, OpenReview's terms dedicate
the abstracts under CC0, and PMLR grants CC BY 4.0 (known from ICML 2017, v70). The other years rest on
Canadian fair dealing alone. Consulting the University of Waterloo copyright office before launch is
recommended, not a gate
([decision-018](backlog/decisions/decision-018%20-%20The-public-instance-serves-every-abstract-with-attribution-and-a-source-link-and-a-takedown-contact-on-public-instances-TASK-063.md),
spec 08 §Deploy). Older index versions that saved searches pin still match on a withheld abstract's words,
so those searches replay the same ids (decision-022). This is the project's decision, not legal advice.

## Status

| Milestone | What is built |
|---|---|
| M1 | The query language: tokenizer, parser, canonical form, defaults ([spec 02](docs/specs/02-query-language.md)) |
| M2 | RIS ingestion, snapshots, the Tantivy index, `op search` / `op export` ([spec 01](docs/specs/01-ingestion.md), [spec 03](docs/specs/03-search-engine.md)) |
| M3 | The `/api/v1` HTTP API (`op serve`), search records, and the web UI: query editor and builder, results, paper pages, exports, the coverage page and syntax help ([spec 04](docs/specs/04-backend-api.md), [spec 05](docs/specs/05-frontend.md)) |
| M4 | Crawlers for OpenReview (API v1 and v2), the NeurIPS proceedings, PMLR and the ICLR archive (`op ingest …`), and the coverage report with the M4 gate (`op eval coverage`, [spec 07](docs/specs/07-evaluation.md) §C). The first full crawl's report passes the gate: 43 of 44 gated cells are within ±1%, and the one other cell is an exception the owner accepted ([`docs/results/2026-09-29-coverage.md`](docs/results/2026-09-29-coverage.md)). |
| M6 (in progress) | Deployment: Docker Compose with Caddy for TLS, and the api, web and caddy images, verified locally ([`deploy/`](deploy/README.md), TASK-065). Still to come: the hosting choice (TASK-064), the first tagged release, then the public v1 launch. Releases follow [spec 08](docs/specs/08-ops-and-tooling.md) §Release (one semver version, decision-023), and the release notes are the generated [`CHANGELOG.md`](CHANGELOG.md) |
| Deferred | Semantic "near-miss" suggestions and re-sort (M5, [spec 06](docs/specs/06-semantic-layer.md)): phase 2, not v1. v1 is Boolean search only (decision-017) |


## Quickstart

### 1. Prerequisites
- git and GNU make
- [uv](https://docs.astral.sh/uv/) (it fetches Python 3.12, pinned by `.python-version`, if you don't have it)
- Node 22 (pinned by `.nvmrc`) and npm
- `shellcheck` if you will run `make lint` (`brew install shellcheck` or `apt-get install shellcheck`)
- An [OpenReview](https://openreview.net) account, only to crawl OpenReview

### 2. Set up
```bash
git clone https://github.com/uw-share-lab/openproceedings.git && cd openproceedings
scripts/setup-dev.sh   # git hooks and a .env skeleton
make sync              # uv sync (backend) + npm ci --ignore-scripts (frontend)
uv run op --help       # the CLI
```
To crawl OpenReview, put `OPENREVIEW_USERNAME` and `OPENREVIEW_PASSWORD` in `.env` (gitignored).

### 3. Get papers into the cache
Everything is written under `data/` (gitignored; move it with `$OP_DATA_DIR` or the global flag, as in
`uv run op --data-dir <dir> ingest …`). Crawls are polite (1 request/s per host, OpenReview within its hourly
budget) and restartable: pages already cached are never fetched again. Try `--dry-run` first: for the
proceedings it reads only the index pages and reports what a crawl would fetch; for OpenReview it reports what
is cached, with no network. Page counts are from the 2026-09-29 dry runs
([`docs/results/2026-09-29-proceedings-dry-runs.md`](docs/results/2026-09-29-proceedings-dry-runs.md)); times
are lower bounds at the default `--delay` of 1 s: a crawler waits at least that long between requests to a
host, plus each response's own time.
```bash
uv run op ingest neurips --year 2013                       # one small year: 360 papers, at least 6 minutes
uv run op ingest neurips --year 2013-2025                  # the NeurIPS proceedings (26,019 pages, over 7 h)
uv run op ingest pmlr --year 2013-2025                     # ICML via PMLR (14,281 pages, at least 3.9 h)
uv run op ingest iclr --year 2014-2016                     # the ICLR archive years
uv run op ingest openreview --venue ICLR --years 2013-2025 # also NeurIPS 2021-2025, ICML 2023-2025
```
#### Import an existing Google Scholar RIS collection

If you already have Scholar exports, you can start with those papers instead of crawling whole venues.
OpenProceedings imports scholarmend's **`mended.ris` and the matching `resolved.json` beside it**. Keep both
files together: the JSON supplies the identity, venue, track and status evidence the importer needs.

For raw `.ris` exports, first prepare a single file or a directory of files with
[scholarmend](https://github.com/uw-share-lab/scholarmend):

```bash
uv tool run --from scholarmend==0.1.5 scholarmend --input /path/to/scholar-exports --out /path/to/mended --abstracts
```

This preparation can fetch metadata; see scholarmend's README for credentials, caching and `--offline`.
If you already have its outputs, skip preparation. Then, from the OpenProceedings checkout:

```bash
# A separate data directory keeps this collection separate from any proceedings crawls.
export OP_DATA_DIR="$PWD/data/scholar-collection"
uv run op ingest ris /path/to/mended/mended.ris
# Multiple prepared exports are accepted; each needs its own matching resolved.json.
# uv run op ingest ris /path/to/first/mended.ris /path/to/second/mended.ris
```

Read the import report before continuing. Only identifiable, in-scope records are imported; unresolved,
ambiguous, conflicting or out-of-scope entries are counted as skipped. Imported counts can therefore be
lower than the original Scholar count, and snapshot deduplication can reduce them further. Keep the original
exports and scholarmend's report for your review audit. This importer currently covers ICLR, NeurIPS and ICML;
it does not index arbitrary RIS records from other venues.

For the local Trust-Evals workspace, the raw exports are in `../Trust-Evals-LitReview/corpus/`.
The existing combined prepared collection is `../scholarmend/out-covidence-2020-2026/mended.ris` with its
adjacent `resolved.json`; it contains 1,833 RIS entries. These are local inputs, not files distributed with
OpenProceedings. To use that collection, replace `/path/to/mended/mended.ris` above with that path.

Continue with steps 4–6 below, keeping `OP_DATA_DIR` set in each terminal that builds or serves this collection.
After building the index, filter and export, for example:

```bash
uv run op search 'trust AND calibration AND year:2020..2026'
uv run op export 'trust AND calibration AND year:2020..2026' --format ris --out screened-scholar.ris
```

The query searches the imported collection. Default filters retain accepted main, datasets/benchmarks and
position papers; use explicit `track:` and `status:` clauses when your review includes other categories.
The UI exposes the same filters and exports. With this separate data directory, the export stays within your
Scholar-derived collection. `source:` is a Scholar-compatible venue alias, not a filter for import provenance.

### 4. Build a snapshot and an index
Both are immutable and named by their content. Each command prints JSON: pass the snapshot's `path` (or its
directory name) to the index build, and the index's `index_version` to the `current` link.
```bash
uv run op snapshot build                            # replays the cache into data/snapshots/<name>
uv run op index build --snapshot <snapshot path>    # builds data/indexes/<index_version>
cd "${OP_DATA_DIR:-data}/indexes" && ln -sfn <index_version> current && cd - # serve this index (-fn replaces an old link)
```
Check it from the command line: `uv run op search "trust AND calibration"` (add `--ids` or `--explain`), and
export the whole matched set with `uv run op export "trust AND calibration" --format ris --out results.ris`.
On the 2013 NeurIPS crawl alone that query matches nothing; try `"neural AND network"`.

### 5. Run the API
```bash
uv run op serve --cors-origin http://localhost:3000   # http://127.0.0.1:8000, serves data/indexes/current
```
`curl http://127.0.0.1:8000/api/v1/healthz` should report `"index_loaded": true`. The interactive API docs are
at <http://127.0.0.1:8000/api/v1/docs>. `--index <index_version>` serves another index; `--cors-origin` lets
the development UI (another origin) call the API.

### 6. Run the UI
Development (hot reload), in a second terminal:
```bash
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000 npm run dev --workspace frontend   # http://localhost:3000
```
Production build (the API URL is compiled in at build time, so set it before building):
```bash
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000 npm run build --workspace frontend
PORT=3000 HOSTNAME=127.0.0.1 npm run start --workspace frontend   # open http://localhost:3000
```
Open the UI at the origin you allowed with `--cors-origin` (`http://localhost:3000`, not `http://127.0.0.1:3000`):
the browser treats the two as different origins.
With `NEXT_PUBLIC_API_BASE_URL` unset, the UI calls the API on its own origin (behind one reverse proxy).
`NEXT_PUBLIC_TAKEDOWN_CONTACT` (also compiled in at build time) is the address or page the footer gives rights
holders for removing an abstract, e.g. `NEXT_PUBLIC_TAKEDOWN_CONTACT=takedown@example.org`; a publicly reachable
deployment must set its own; private and local ones may leave it unset (decision-018, spec 08 §Deploy). Unset, the footer links to this repository's (public) issues page; a value that is
neither a plain email address nor an http(s) URL fails the build. `OPENPROCEEDINGS_INSTANCE=public` makes a
missing contact fail the build too, and the `web` image requires it: `docker build -f deploy/web.Dockerfile
--build-arg OPENPROCEEDINGS_INSTANCE=public --build-arg NEXT_PUBLIC_TAKEDOWN_CONTACT=takedown@your.org .`
(`private` for a private, local or development one).

### 7. Reports
`uv run op eval coverage --index <index_version>` writes `docs/results/<date>-coverage.md`: indexed against
official accepted counts per venue, year and track, and the M4 gate verdict (`--check` makes a failing gate the
exit status).

## Run it with Docker Compose

`deploy/compose.yml` runs the API, the web app and Caddy (TLS) over a data directory you have built (step 4
above). The services run as non-root users with read-only root filesystems, and the API has no route out. The
API runs as uid 10001, so first give it read access to the index, create its record store, and create the
takedown list (empty is fine; behind the proxy the API won't load without it):

```bash
sudo deploy/index-permissions.sh data/indexes <index_version> 10001   # Linux only; Docker Desktop: skip
sudo install -d -o 10001 -g 10001 -m 0700 data/records          # Docker Desktop: mkdir -m 0700 data/records
mkdir -p data/takedowns && touch data/takedowns/withheld.txt
OP_DATA_HOST=$PWD/data OP_INSTANCE=private docker compose -f deploy/compose.yml up -d --build --wait
```

If `data/records/` already holds a store from step 5's `op serve`, its files are yours, not uid 10001's, and
the API can't open them: give the whole directory to the API (`sudo chown -R 10001:10001 data/records`) or
start from an empty one. With the default `OP_DOMAIN=localhost`, Caddy serves https://localhost from its own
local CA. A real domain gets a Let's Encrypt certificate. The runbook, [`deploy/README.md`](deploy/README.md),
covers the settings, promoting and retiring an index, takedowns, and what remains for a real host.
`deploy/smoke-test.sh` runs the whole stack over a throwaway fixture and checks it end to end.

## Tests and checks
```bash
make test      # backend (pytest, in parallel) and frontend (Vitest)
make lint      # exactly what CI's lint job runs (ruff, mypy --strict, shellcheck, prettier, eslint, tsc)
make tooling   # the .claude/ roster, backlog and digest-pin checks, and every hook's case table
make e2e       # full-stack browser, accessibility and visual tests (Playwright)
make help      # every entry point (openapi, changelog, mutate, …)
```
CI runs `lint`, `test`, `claude-tooling` and the PR gates on every PR and every merge-queue build. Its `test`
job runs the backend suite in parallel with Hypothesis properties at 200 examples. The nightly workflow reruns
the suite at 2,000 examples, every property and the differential (Tantivy against the reference matcher) at
50,000, the benchmarks, and the mutation run over the gate scripts ([spec 08](docs/specs/08-ops-and-tooling.md)
§CI). No test reaches a live service: the test session refuses every non-loopback connection.

## Contributing

[`CONTRIBUTING.md`](CONTRIBUTING.md) has the walkthrough. In short:

- The flow is `feature → PR → dev → PR → main`. Nobody commits or pushes to `dev` or `main` directly.
- Before a push, the routed reviewers check the diff (`/review-gate`, the
  [`review-gates`](.claude/skills/review-gates/SKILL.md) skill). Every finding gets a disposition, and
  `record-review.py` records an approval for the exact commit, which the PR body attests. Each PR also adds a
  learnings entry (`.claude/learnings/`).
- A green PR goes into `dev`'s merge queue with `gh pr merge <n> --auto`. The queue tests it on top of `dev`,
  so there is no need to rebase when `dev` moves.
- Commits and PRs carry no AI attribution (no `Co-Authored-By` trailers for an AI, no "Generated with" footers).
  Hooks and CI reject it.
- Tasks live in Backlog.md and are changed only through the `backlog` CLI. Docs, specs and tasks change in the
  same commit as the behaviour they describe.

## Where things are

| What | Where |
|---|---|
| Specs (the design; 00 first) | [`docs/specs/`](docs/specs/) |
| Decisions | [`backlog/decisions/`](backlog/decisions/) |
| Tasks (open and done) | [`backlog/tasks/`](backlog/tasks/), [`backlog/completed/`](backlog/completed/): `backlog task list --plain` |
| Results and reports (coverage, benchmarks, audits) | [`docs/results/`](docs/results/) |
| UX design docs | [`docs/design/`](docs/design/) |
| Deployment and the operator's runbook | [`deploy/`](deploy/README.md) |
| Release notes | [`CHANGELOG.md`](CHANGELOG.md) (generated), [`docs/releases.toml`](docs/releases.toml) |
| Agents, skills, hooks and learnings | [`.claude/`](.claude/README.md) |
| Notes for coding agents | [`CLAUDE.md`](CLAUDE.md), [`AGENTS.md`](AGENTS.md) |

## Citing

If you use openproceedings in a review, cite it with [`CITATION.cff`](CITATION.cff) (GitHub's "Cite this
repository" button renders it). Save each search as a search record, and report the record's link, its
`index_version` (records and exports name it) and the openproceedings release (`op --version`). A saved record
keeps its index from being retired, so the search can be replayed on that instance. A version no record pins
may be retired, and a later release that changes the tokenizer or schema replays older records as `drifted`,
saying what changed.

MIT © SHARE Lab, University of Waterloo
