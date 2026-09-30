# openproceedings

Exact, reproducible Boolean search over **NeurIPS, ICLR and ICML** titles and abstracts, for systematic reviews.

- **Title and abstract only.** It never searches the full text.
- **No stemming.** `benchmarking` matches `benchmarking`, not `benchmark`. Wildcards are opt-in (`benchmark*`, `model$`).
- **Track-aware.** Workshop, competition and rejected papers are indexed, but the default filters exclude them. Every search reports how many were excluded, which gives you the PRISMA "removed before screening" count.
- **Reproducible.** Every result carries an index version. Saved search records can be replayed.
- **Review-ready exports.** RIS (for Covidence), CSV, BibTeX and JSONL, with full abstracts.

## Status

| Milestone | What is built |
|---|---|
| M1 | The query language: tokenizer, parser, canonical form, defaults ([spec 02](docs/specs/02-query-language.md)) |
| M2 | RIS ingestion, snapshots, the Tantivy index, `op search` / `op export` ([spec 01](docs/specs/01-ingestion.md), [spec 03](docs/specs/03-search-engine.md)) |
| M3 | The `/api/v1` HTTP API (`op serve`; interactive docs at `/api/v1/docs`), search records (`op record save` / `replay`), and the web UI: query editor and builder, results, paper pages, exports, the coverage page and syntax help ([spec 04](docs/specs/04-backend-api.md), [spec 05](docs/specs/05-frontend.md)) |
| M4 | Crawlers for OpenReview (API v1 and v2), the NeurIPS proceedings, PMLR and the ICLR archive (`op ingest …`), and the coverage report with the M4 gate (`op eval coverage`, [spec 07](docs/specs/07-evaluation.md) §C). The first full crawl's report passes the gate: 43 of 44 gated cells within ±1% and one owner-accepted exception ([`docs/results/2026-09-29-coverage.md`](docs/results/2026-09-29-coverage.md)). |
| Next | Production deployment with Docker compose (`deploy/`, M6, TASK-065) and the public v1 release |
| Deferred | Semantic "near-miss" suggestions and re-sort (M5, [spec 06](docs/specs/06-semantic-layer.md)): phase 2, not in v1, which is Boolean search only (decision-017) |

**Abstracts on a public instance.** A public deployment shows every abstract, attributed to its source
(OpenReview, the NeurIPS proceedings or PMLR) with a link to it, and names a takedown contact; private, local
and development deployments may omit the contact. For the 2024+ conferences OpenReview's terms dedicate the
abstracts under CC0, and PMLR grants CC BY 4.0 (known from ICML 2017, v70); the other years rest on Canadian
fair dealing alone. Consulting the University of Waterloo copyright office before launch is recommended, not a
gate
([decision-018](backlog/decisions/decision-018%20-%20The-public-instance-serves-every-abstract-with-attribution-and-a-source-link-and-a-takedown-contact-on-public-instances-TASK-063.md),
spec 08 §Deploy). This is the project's decision, not legal advice.

Start with [`docs/specs/00-overview.md`](docs/specs/00-overview.md). Contributor workflow (branches, reviews, the
gates the tooling enforces) is in [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Quickstart

### 1. Prerequisites
- [uv](https://docs.astral.sh/uv/) (Python 3.12, pinned by `.python-version`)
- Node 22 (pinned by `.nvmrc`) and npm
- `shellcheck` if you will run `make lint` (`brew install shellcheck`)
- An [OpenReview](https://openreview.net) account, only to crawl OpenReview

### 2. Set up
```bash
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
A scholarmend RIS export can be imported too: `uv run op ingest ris path/to/mended.ris` (with its `resolved.json`
beside it).

### 4. Build a snapshot and an index
Both are immutable and named by their content. Each command prints JSON: pass the snapshot's `path` (or its
directory name) to the index build, and the index's `index_version` to the `current` link.
```bash
uv run op snapshot build                            # replays the cache into data/snapshots/<name>
uv run op index build --snapshot <snapshot path>    # builds data/indexes/<index_version>
cd data/indexes && ln -sfn <index_version> current && cd -   # make it the served index (-fn replaces an old link)
```
Check it from the command line: `uv run op search "trust AND calibration"` (add `--ids`, `--explain`, or
`uv run op export "…" --format ris --out results.ris`).

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
deployment must set its own; private and local ones may leave it unset (decision-018, spec 08 §Deploy). Unset, the footer links to this repository's issues page.

### 7. Reports
`uv run op eval coverage --index <index_version>` writes `docs/results/<date>-coverage.md`: indexed against
official accepted counts per venue, year and track, and the M4 gate verdict (`--check` makes a failing gate the
exit status).

## Tests and checks
```bash
make test    # backend (pytest, in parallel) and frontend (Vitest)
make lint    # exactly what CI's lint job runs
make e2e     # full-stack browser, accessibility and visual tests
make help    # every entry point
```
CI's `test` job runs the backend suite in parallel with Hypothesis properties at 200 examples; the nightly
workflow reruns it at 2,000 and every property at 50,000.

MIT © SHARE Lab, University of Waterloo
