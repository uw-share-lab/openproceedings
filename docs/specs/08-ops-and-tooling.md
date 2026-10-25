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
├── backend/                     # uv workspace member: Python package `openproceedings` (Python 3.12.15, pinned by .python-version)
│   ├── pyproject.toml
│   ├── src/openproceedings/
│   │   ├── ingest/              # 01: record.py, classify.py, urls.py, volumes.py (+ pmlr_volumes.toml), dblp_table.py (+ dblp_icml.toml), dblp_aaai_table.py (+ dblp_aaai.toml), acm_table.py (+ acm_proceedings.toml), facct_site.toml, ris.py, dedup.py, snapshot.py (built); sources/ (M4 crawlers: http.py (the one HTTP layer), common.py, openreview_client.py, openreview_v2.py, openreview_v1.py, iclr.py, neurips.py, pmlr.py, dblp.py, dblp_aaai.py, ojs.py, crossref.py, facct_site.py, crawl.py)
│   │   ├── query/               # 02: normalize.py, mathsyms.py, lexer.py, parser.py, ast.py, canonical.py, defaults.py, compat.py
│   │   ├── engine/              # 03: protocol.py, reference.py, index.py, compile.py, tantivy_engine.py, exclusions.py, highlight.py, parity.py
│   │   ├── semantic/            # 06 (shelved, decision-017; not created)
│   │   ├── api/                 # 04: app.py, config.py, state.py, deps.py, errors.py, middleware.py, models.py, openapi.py, server.py; routers search.py, papers.py, meta.py, coverage.py, records.py, export.py, compare.py (`POST /compare`, TASK-177), health.py
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

**Python pin (TASK-208).** `.python-version` names one exact CPython patch release, 3.12.15, which uv installs
for development and for every CI job (every `setup-uv` step installs the uv `deploy/api.Dockerfile` pins:
§CI "Dependabot"; a local uv must be 0.12.22 or later to know 3.12.15). `requires-python` (both `pyproject.toml`s, recorded in `uv.lock`) is `>=3.12.12`, the first 3.12
with the fix for CVE-2025-6069 (quadratic time in `html.parser.HTMLParser` on malformed input, which every
crawler parses pages with; CPython issue #135462, fixed in 3.12.12, 3.13.6 and 3.14.0). That floor still admits
3.13.0-3.13.5, which lack the fix: the guarantee is the exact pin, checked by `test_python_pin.py`. The api
image's `FROM python:3.12.15-slim-bookworm` names the same release (§Deploy).
`backend/tests/unit/test_python_pin.py` holds them together and fails on an interpreter without the fix; a patch
upgrade moves `.python-version`, the image tag and digest together (Dependabot's `docker` entry proposes the
image half; its PR fails that test until `.python-version` follows, and the weekly routine leaves it for the
owner, §CI "The weekly routine"). The minor stays 3.12 (security fixes until
2028-10), so ruff's `py312` and mypy's `3.12` targets don't move; a new minor is a hand-made PR.

The fix also changed how the parser reads malformed markup, so extracted text can depend on the release.
`ingest/sources/html.py` keeps two of those readings as 3.12.9 had them. At the end of the input, 3.12.9's `close`
kept an unterminated construct as text and 3.12.12+ drops it, which would cut `for all p<q we show` to `for all p`
in a fragment: `_feed_all` hands such a tail to the parser as text when it holds no `>` (linear on either release).
And 3.12.12+ reads `title`, `textarea`, `xmp`, `iframe`, `noembed`, `noframes` and `plaintext` bodies as raw text,
so one unclosed `<title>` would swallow a listing's later rows: `_RawTextParser` keeps raw text to `script` and
`style`. Since TASK-209 a `<` that doesn't start a real tag never reaches the parser as one (`escape_bare_lt`,
spec 01 §Pipeline step 2), which also takes an unterminated quoted value (`a <b x='y > c`) out of the parser's
hands: it stays text on every release. The rest is left to the parser, which 3.12.12+ reads differently: an unterminated construct whose tail
holds a `>` (a comment, a `<![CDATA[`), the empty comment
`<!-->` and `--!>`, `</script x>` as an end tag, an end tag with a quoted `>` in it, and some malformed attributes
(`href==x` keeps the second `=` in the value). In the track paths such a change can only drop a listing entry (an
unparsed link is skipped and counted, a lost section fails its count check), never reclassify one. The evidence
(`docs/results/2026-10-07-python-upgrade.md`): the whole crawl cache replays to byte-identical records under 3.12.9
and 3.12.15; an index built from the same snapshot has identical segment bytes and the same `index_version`; and
over 200,000 seeded malformed strings the new `html.py` on 3.12.9 gives the old text and metas, while on 3.12.15 one
in five still differs, nearly all through `<!` constructs.

## CLI (`op`)

| Command | Does |
|---|---|
| `op ingest openreview\|iclr\|neurips\|pmlr\|dblp\|ojs\|crossref\|aaai-library\|openalex\|ris … [--offline]` | fetch sources (`--offline`: cache only, no network). `ojs` (decision-049) harvests ojs.aaai.org's AAAI, AIES and IASEAI journals through OAI-PMH (`--journal AAAI\|AIES\|IASEAI`, repeatable, default all; `--dry-run`, `--offline`, `--refresh`, `--delay`, never under 3 s on that host; spec 01 §Sources). `op snapshot build` replays every marked crawl from the cache in one order: OpenReview API v2, v1, then the ICLR archive, NeurIPS, PMLR, dblp (ICML), OJS, dblp's AAAI 1980–2008 markers and Crossref last (`crawl.replay_all`; a full run orders …, ojs, crossref). Milestone B (decision-049) adds: `op ingest dblp --venue AAAI` (AAAI 1980–2008 from the pinned release; `--venue ICML` is the default), `op ingest pmlr --venue FAccT` (FAccT 2018, v81), and `op ingest crossref` (`--venue FAccT|AIES` and `--year`, both repeatable; `--dry-run`, `--offline`, `--refresh`, `--delay`, never under 1 s on that host), which reads FAccT 2019+ and AIES 2018–2023 from Crossref's `/works` and, for FAccT 2022, 2025 and 2026, the official abstract pages of facctconference.org. The design's separate `facct-site` target is folded into `crossref`: the pages are fetched and joined inside `op ingest crossref`, not by a command of their own. **`CROSSREF_MAILTO`** (`.env`, or the environment) is optional: it names a contact in Crossref's User-Agent (the polite pool); unset or blank, the public pool is used; a malformed value stops the crawl (`bad_contact`); the address is never committed, logged, cached or put in a URL. **`op ingest openalex`** (milestone C, decision-049; `--dry-run`, `--offline`, `--refresh`, `--delay`, never under 1 s) is **last in a full crawl**: it reads the other crawls' records from the cache to find the AAAI, AIES and FAccT records with no abstract, looks them up in OpenAlex (by DOI in batches of 50; AAAI 1980–2008 through the listings of `ingest/openalex_sources.toml`) and pins what it read as a content-addressed extract plus a marker under `<data-dir>/cache/openalex`; it is not a `crawl.SOURCES` member, so `op snapshot build` does not replay it with the other crawls but fills from the marked extract after dedup (spec 01 §Pipeline 4). A full run orders …, ojs, crossref, openalex. A full crawl is about 53 requests, a small part of a keyless day's budget. **`OPENALEX_API_KEY`** (`.env`, or the environment) is optional: it raises the daily budget and goes in an `Authorization` request header only, never in a URL, cache entry, claim, log line or error; a malformed value stops the crawl (`bad_key`). No contact address is sent to OpenAlex, so `CROSSREF_MAILTO` is not reused. **`op ingest aaai-library`** (TASK-232, decision-051; `--dry-run`, `--offline`, `--refresh`) caches the Internet Archive capture of each old aaai.org paper page `ingest/aaai_library.toml` pins (AAAI 1980–2008, about 4,607 captures) from `web.archive.org` only, never aaai.org, one request at least every 3 s with the generic User-Agent, each capture's SHA-1 checked against the table, then writes a marker under `<data-dir>/cache/aaai_library`; it needs no other crawl first and is not a `crawl.SOURCES` member: `op snapshot build` reads the cached captures after dedup and before the OpenAlex fill (spec 01 §Pipeline 4). A full harvest takes at least 3.8 hours; run it detached. `scripts/aaai_library_census.py` (two CDX requests) rewrites the table. The scheduled crawl of TASK-202 runs every source in scope, each driven by its table |
| `op snapshot build [--takedowns <file>]` · `op snapshot diff <a> <b>` (snapshot directories) | build an immutable snapshot, or compare two. The build withholds every abstract on the takedown list (default `<data-dir>/takedowns/withheld.txt`, which may be absent until a snapshot, under the output directory or `<data-dir>/snapshots/`, has withheld an abstract: then it is required, as a file named with `--takedowns` always is; TASK-067; §Deploy, decision-022): a list that doesn't parse refuses it; its JSON names `withheld_ids` (the ids whose abstract it took out), `takedowns_followed` (a listed id this build holds under another id → that id, also withheld), `takedowns_unmatched` (listed ids it has no record of) and `takedowns_twins` (a twin of a withheld record → the id it is the twin of, also withheld: decision-029, TASK-163), the last three also said on stderr (a twin with what to list and log). The build fills AAAI 1980–2008 records from the cached archive captures of AAAI's own paper pages when `op ingest aaai-library` marked a harvest (`sources.aaai_library.fills`; TASK-232), then AAAI, AIES and FAccT records that still have no abstract from the marked OpenAlex extract, both after dedup and before the takedown list (milestone C; a snapshot with no marker has no fill), and the manifest says so (`sources.openalex.fills`, `abstract_openalex`). The diff's `abstract_withheld` names the ids withheld (`added`) and no longer withheld (`lifted`) between the two; since milestone C it also lists, as `abstract_kind`, each id whose derived kind differs (`[old, new]`) and counts them in `abstract_kind_transitions` (`{"none->openalex": n}`). There is no prune or delete command: keep the snapshot of every index a search record pins (the versions `op index retire` refuses), since that record's exports read it to attribute each abstract and withhold every abstract without it (decision-021); a future prune command must refuse while a record pins an index built from the snapshot |
| `op index build --snapshot <dir\|name\|hash prefix> [--out <dir>]` · `op index parity --index <v> [--snapshot <id>]` · `op index retire <index_version> [--dry-run]` (TASK-085) | build an immutable index; check it holds `normalize()`'s tokens for its snapshot (local, over the real corpus); retire an old one: delete `<data-dir>/indexes/<index_version>/` under the indexes lock `op index build` holds: set aside as `.retiring-<index_version>` (no reader finds half an index, and no sweep deletes it), checked once more, then renamed to `.tmp-retire-<index_version>` (the commit point) and removed; the next build or retire sweeps a removal cut short. Refused, exit 1, one line to stderr, nothing touched: while any search record pins it (`RecordStore.pinned`, the count reported; a deleted pinned index would leave those records' replays permanently `drifted`), while `current` or any other symlink in `indexes/` points at it, when the record store can't be read, or when the name isn't an index_version directory directly under `indexes/` (the name is checked against the index_version format before any path is built, so `../x` never names a path). `--dry-run` runs the checks and reports the outcome with the same exit status, deleting nothing. Order: repoint `current` to the new version, SIGHUP the API, confirm `/api/v1/meta` reports the new version, then retire the old one (the API keeps serving the old version until its reload). It can't see an `op serve --index <index_version>` that serves the version by name: check what each running instance serves first. A promotion (`ln -sfn`) and a record save take no indexes lock, so after the rename the pins and every symlink's target are checked again and a hit, or anything raised (Ctrl-C included), renames the directory back and refuses or re-raises. If that rename-back fails, one ERROR `index_retire_restore_failed` names the `.retiring-` directory and the operator must `mv` it back to `<index_version>` before serving it or running another build or retire (no sweep touches it; until then every retire of that version, `--dry-run` included, is refused as `retire_cut_short`, whether `<index_version>` is absent or was rebuilt); what remains is the few syscalls between that check and the removal, after which a save or replay naming the version finds it absent. It says so when it waits for the lock. A chmod or removal that fails after the rename still retires the version (its name is gone) and reports `tmp_left`; a sweep that can't remove a leftover logs `tmp_sweep_failed` and carries on, so it never fails a later build. One log line: `index_retired` (INFO; WARNING with `tmp_left`), `index_retire_checked` (dry run) or `index_retire_refused` (WARNING; DEBUG for a malformed name, which is not logged), each with the version, the pinned count and the outcome or reason |
| `op search "<q>" [--mode scholar] [--explain \| --ids] [--engine tantivy\|reference] [--sort <s>] [--limit <n>] [--index <dir\|version>]` | ranked hits under a PRISMA header (default): searched time, index, crawl window (first to last fetch), tokenizer and query versions; a bootstrap-corpus caution when the index holds only RIS, or a caution that the sources are unknown when its snapshot isn't in the data dir or its hash differs; identified, removed by default filters (ineligible and unclassified), screened; the canonical and identification strings; every wildcard's expansion (its count and first 10 terms; every term with `--explain`); the sorted id set (`--ids`; `--engine reference` runs the oracle over the index's snapshot, `--ids` only); or the compiled query (`--explain`), then each concept group's `total` (alone) and `total_without` under the bounds `/search` counts them under (`ApiConfig`'s `max_counted_groups`, `max_counted_terms`, `max_counted_ids`, `group_count_wait_seconds` and `group_count_grace_seconds` defaults), or the `not_counted` reason (spec 04 §SearchResponse, `groups`; TASK-194). Diagnostics go to stderr as user output; one `search_run` INFO line per run (task-030) |
| `op export "<q>" --format ris\|csv\|bibtex\|jsonl [--mode scholar] [--index <dir\|version>] [--out <file>]` | export the full matched set in id order (spec 04 §Exports), streamed to stdout or written whole to `--out` (never a partial file); the count is checked against the query's total. It verifies the index's snapshot to name each abstract's source (TASK-138); without it, every abstract is withheld and each record says so, with a warning on stderr and exit 0 (decision-021). It withholds the takedown list's abstracts as the API does (decision-022), under any other id the exported version holds a listed paper under (merges and globally unique native ids, `takedowns.same_paper`; a damaged snapshot's merges are skipped with a warning on stderr; TASK-067), and on its twins (the exported snapshot's and the current index's `twin` claims, TASK-163; a current index whose snapshot can't be read leaves its claims out, with one ERROR `takedown_twins_unavailable` and a warning on stderr), says on stderr how many records of the file it withheld, and a list that doesn't parse refuses it, as does a missing default list once a snapshot under `<data-dir>/snapshots/` has withheld an abstract (TASK-067) |
| `op takedown check --api <url> [--list <file>] [--log <file>]` (TASK-136) | ask a running API over HTTP (what is served, whatever the code path) whether it serves any listed abstract: on the served index, `/papers/{id}` (and its highlights for a query on the title) and the `/search` hit; on every index version `/meta` lists, every export format (one export per version, format and venue-year holding a listed id: filters only; a paper found in one format must be in all four), and one JSONL export per version and listed paper of its title in every venue and year (a record under another id with the same title and authors serving an abstract is a problem: TASK-067); each id a snapshot's `merges.csv` links to a listed paper whose `/papers` title differs (it is withheld as that paper: a suspect merge, TASK-067); each listed paper's twin (the union of its `twins` on served `/papers` and in every pinned version's JSONL export, independent of which version supplies its title and authors) the list doesn't name (the API withholds it too, so list and log it: TASK-163); and a listed id no loaded version holds. The list is always required (a missing one is never "nothing to check"; an empty one is). It also checks the takedown log: owned by the account running the check, mode 0600, each listed id's latest entry `withheld`, and each id whose latest entry is `withheld` listed (TASK-067). Prints each problem (ids, versions and formats, never text or requesters' details) and exits 1 on any, 0 otherwise; one `takedown_checked` log line with the counts. Run it as the operator's account, against the API itself (e.g. `http://127.0.0.1:8000` on the host), not through the proxy: it follows no redirect, and waits out a 429's `Retry-After` (each export costs the rate limit's export weight: about (cells × 4 + listed papers) × versions × `export_weight` tokens) |
| `op record save "<q>" [--mode scholar] [--index current\|<index_version>] [--json]` · `op record replay <id> [--index current\|<index_version>] [--json]` | freeze a search as a search record in `<data-dir>/records/records.sqlite` (the same functions as `POST /records`, `records.freeze` + `RecordStore.insert`: a record identical to the API's but for its id and time) and print its id, page and PRISMA summary, or the stored record (`--json`); replay one (the same function as `GET /records/{id}`, `records.replay`) on its own index when the data dir holds it, else on `--index` (default `current`), and print the status, `reproduced` / `drifted` / `mismatch`, the changed inputs and `+added / −removed`, or the API's `replay` block (`--json`). `--index` is a name under `<data-dir>/indexes`, never a directory: a record pins a version a replay must find by name. Left out, as serving policy: the rate limit, the save ceilings, and the verified-clause cap and candidate ceiling, so a CLI replay is never withheld (decision-010); the store's size cap and free-space floor (the API's defaults) apply (task-083) |
| `op serve [--host] [--port] [--index current\|<index_version>] [--cors-origin …] [--trusted-proxy …] [--rate-capacity] [--rate-refill] [--export-weight] [--no-rate-limit] [--pinned-indexes] [--max-verified-clauses] [--max-verification-candidates] [--max-verification-seconds] [--max-counted-groups] [--max-counted-terms] [--max-counted-ids] [--compare\|--no-compare] [--compare-max-body-bytes] [--compare-max-records] [--compare-max-line-chars] [--compare-max-results] [--compare-max-response-bytes] [--compare-max-seconds] [--compare-upload-seconds] [--comparison-slots] [--compare-cooldown-factor] [--compare-upload-weight] [--compare-token-ms] [--log-query-text]` | run the API (04 §Implementation notes, as built): one uvicorn process over `<data-dir>/indexes/<index>`; SIGHUP reloads it. `--pinned-indexes` (default 4) sizes the LRU of older index versions held open: size it to the versions the instance holds (TASK-067). With a non-loopback `--host`, or any `--trusted-proxy`, the takedown list is required (§Deploy, TASK-067): a missing `withheld.txt` fails the load. Refused as usage, each option named with the validator's reason: a trusted proxy wider than /8 or /32, `--no-rate-limit` with a non-loopback `--host` (§Deploy), limits that could never be paid (decision-010), and a comparison flag (TASK-184) out of its field's range or not finite (the ranges: body and answer caps 1024 to 1 GiB, records and results 1 to 1,000,000, a line 64 to 16,777,216 code points, work and upload over 0 to 3,600 s, slots 1 to 16, cooldown factor 0 to 1,000, upload weight 1 to 100, token price at least 1 ms; a finite but extreme value overflowed the pause or the debit, or lifted the bound the flag is: security gate, batch B). The comparison flags set `POST /compare`'s caps (defaults: 16 MiB body, 5,000 records, 32,768-code-point lines, 5,000 results, 16 MiB answer, 60 s of work, 30 s for the upload, 1 slot; each stated in `GET /meta` `limits.compare`) and its costs, which `/meta` doesn't state (`--compare-cooldown-factor` 3, 0 for no pause; `--compare-upload-weight` 4; `--compare-token-ms` 500); 04 §Comparing with a RIS file and `deploy/README.md` §Comparisons say what each bounds |
| `op embed build` (shelved with 06, decision-017; archived task-058) | build embeddings for the current index (06) |
| `op eval coverage [--index <v>] [--out <dir>] [--date YYYY-MM-DD] [--check]` (TASK-054) · `op eval scholar --ris <file>… [--query-file <file>…] [--name <name>…] [--query <string>] [--mode native\|scholar] [--years LO..HI] [--venues V,…] [--index <v>] [--out <dir>] [--date YYYY-MM-DD] [--notes <file>] [--answers <name>] [--check]` (TASK-056) · `op eval openalex [--snapshot S] [--aaai-sample N] [--title-sample N] [--seed N] [--offline] [--out DIR] [--date D] [--ruling TEXT]` (milestone C) · `op eval audit` (planned, task-055) · `op eval near-miss` (shelved with 06, decision-017; archived task-061) | the 07 reports; `coverage` writes `docs/results/<date>-coverage.md` and `--check` exits 1 when the M4 gate fails; `scholar` writes `docs/results/<date>-scholar-comparison.md` and `<date>-scholar-comparison-review.csv` (07 §B; default strings: the Trust-Evals fixture; `--check` exits 1 on any `our_bug`); `openalex` writes `docs/results/<date>-openalex-audit.md` (07 §G): OpenAlex's abstracts against the official ones, and a check of the title-route attaches; always keyless, `--offline` replays the cache with no request and the same bytes; `near-miss` is 06's recall@25 |
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
  `.claude/scripts/tests/` (the CI scripts, the network guard, `changelog.py`, the `/dependabot-review`
  scripts); `make tooling` and CI `claude-tooling` run them all.
- `make tooling` also runs the roster lint, the `.claude/README.md`, learnings-index and backlog checks, the
  digest-pin check on `deploy/` (§Deploy), the file-mode check on what `scripts/setup-dev.sh` makes executable
  (`check_file_modes.py`, TASK-241), the CI uv pin check (`check_uv_pin.py`, §CI "Dependabot", TASK-252), the bash 3.2 parse check (`check_old_bash.py`:
  `bash -n` on every Makefile `SHELL_FILES` script when /bin/bash is bash 3.x, as on a Mac; skipped elsewhere, CI
  included; TASK-267), and the
npm manifest/lock check (`npm_specs.py`, §CI "Dependabot"), the probe lint and the mutant vetting (`mutate.py
--check`, §Mutation testing, TASK-254).
- CLI commands are covered by the suites of the spec they call (07); the CLI adds only argument-parsing
  and exit-code tests.

## Code quality: autolint (skill: `autolint`)

Modelled on the lab's naturalschema repo:
1. `.claude/hooks/autofix.sh` (PostToolUse) formats and fixes each file as it's edited: ruff for Python,
   prettier and eslint for the frontend, and shellcheck (report only) for shell. It reports anything it can't
   fix back to the agent and never blocks.
2. `make fmt` fixes the whole repo. `make lint` is check-only and is exactly what CI runs.
3. `.githooks/pre-push` runs `make lint` and `make tooling`, so a push never surprises CI. In a cloud
   `/dependabot-review` clone it refuses every push (the no-dependency-code marker; a cloud run is notify-only,
   §CI "Dependabot").

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
| `lint` → `lint` | `make lint` (ruff format/check, mypy --strict on `backend/src` and on the `/dependabot-review` scripts and their case table, shellcheck, frontend prettier/eslint/tsc), then actionlint |
| `test` → `test` | pytest under pytest-xdist at the `pr` Hypothesis profile (200 examples, 2 s deadline) (unit, golden, differential@200, contract; the 2,000-example `ci` profile runs nightly, TASK-127); vitest; `next build` (the standalone server must exist); OpenAPI snapshot and TS types freshness (`make openapi`, then `git diff --exit-code` on `backend/tests/contract/openapi.json` and `frontend/src/api/schema.ts`; unconditional, TASK-040) |
| `claude-tooling` → `claude-tooling` | `make tooling`: roster lint, `.claude/README.md` and learnings index freshness, backlog hygiene (no Done task left in `tasks/`, no task or decision id used twice: §Merge queue), digest-pinned `FROM`s in `deploy/` (`check_digest_pins.py`, §Deploy), every tracked file `scripts/setup-dev.sh` makes executable committed 100755, so a fresh clone's setup leaves the tree clean (`check_file_modes.py`, TASK-241), every CI `setup-uv` step's `version` equal to the api image's uv (`check_uv_pin.py`, §CI "Dependabot", TASK-252), every shell script parsing with /bin/bash when it is bash 3.x, as on a Mac; skipped otherwise (`check_old_bash.py`, TASK-267), the npm manifests' dependency specs equal to the lock's workspace entries (`npm_specs.py`, §CI "Dependabot"), every case table under `.claude/hooks/tests/` and `.claude/scripts/tests/` (the tooling scripts, the network guard, `changelog.py`, the `/dependabot-review` scripts, the no-dependency-code marker's guards in `test-no-dep-code.sh`) |
| `pr-gates` → `attribution`, `learnings`, `review-attested` | no AI authorship in commits or PR text; the branch adds or extends a learnings entry (unless labelled `no-learning`); the PR body attests APPROVE for the head sha. In a merge-queue build, `merge_group_gate.py` runs the same three checks on every PR in the group (§Merge queue) |
| `pr-gates` → `pr-base` (required on `main` only, since 2026-10-21; decision-052) | a PR into `main` is the same-repo `dev → main` promotion; any other, a fork's included, fails and is told to target `dev`. It passes on a PR into `dev` and in a merge-queue build. Its wiring and its gate, run on four heads, are checked by `test-merge-group-gate.sh` |
| `nightly` (scheduled daily, and `workflow_dispatch`; not a PR check) | Parallel jobs, each with its own time limit (TASK-057): the whole backend suite but the differential at the `ci` profile (2,000 examples) under pytest-xdist, synthetic-corpus parity (`test_parity.py`) included; every property at 50,000 examples as a 5-part `properties` matrix under pytest-xdist, split by measured time per test (the near-cap replay property alone, the other oracle-backed properties, `unit/engine`, `unit/ingest`, and the rest with the exhaustive tokenizer check, `OP_EXHAUSTIVE=1`); the year-edit property (`test_clauses.py`), which ran past 90 min unsplit, as 4 seeded `year-edits` jobs of 12,500 (`OP_YEAR_EDIT_SHARDS`); differential@50k as 12 independent jobs of 4,166 or 4,167 examples, exactly 50,000 between them (`OP_DIFFERENTIAL_SHARD` is each job's index; the remainder goes to the first shards) (8 until 2026-10-11, when the group-count property made a shard run past its 110 minutes), each with its own `--hypothesis-seed`, which its log prints with a rerun command; `benchmarks`: the spec 03 benchmarks with their budgets, then the ~80k report into the run summary and a `bench-80k` artifact (a budget miss there is a warning annotation); and the mutation run (`mutate.py`, every mutant in `.claude/scripts/mutants/*.json` killed or documented as equivalent) as a 16-job `mutate` matrix (TASK-171; 8 until 2026-10-06, 12 until 2026-10-19): job i of n runs `mutate.py --shard i/n`, every n-th mutant from the i-th, so every mutant is checked every night (n is the matrix size, so adding a shard is one edit). Estimated from run 37017691575 (188 mutants in 140 min on a 4-CPU runner), the 694 mutants at TASK-171 need ~8.5 h of one runner, past GitHub's 6 h job cap, or ~65 min a shard of its 140 at 8 shards (2026-10-06: 778 mutants took 77–123 min a shard at 8, so 12); shard 1's first step prints the night's count, and shards are added before one nears 140 min. With 997 mutants (2026-10-09/10) four shards ran past 140 min, every mutant running all 13 case tables; since then a mutant runs the tables that name its file first and stops at the first failure, about a third of the time (§Mutation testing), so 12 shards had the room again; 16 since 2026-10-19, when the cmdparse mutants took a shard past 140 min again (§Mutation testing). Shard 1's first step vets every mutant (`mutate.py --check`, seconds: stale, ambiguous or uncompilable, §Mutation testing), so such a mutant anywhere fails the run each night; it also fails its own shard. A surviving or unrunnable mutant fails its shard, and so does a shard cut off at 140 min, with an `::error::` giving about how many of its mutants it checked (the step runs with `shell: bash`, i.e. pipefail, so the pipe through `tee` keeps the status). Long pytest steps run verbose with `OP_EARLY_FAILURES=1` (a failure's report, Hypothesis blob included, is printed when the test fails) and are interrupted before their job's limit, so an overrun fails with an `::error::` and shows which test was still running. The run has 40 jobs (`resolve` and 39 test jobs), past GitHub's limit of 20 at once for a free organization, so 20 (and more while a PR's CI runs) queue until running jobs finish (the short ones, `suite-ci`, `benchmarks` and the `differential` shards, took under 25 min in run 37017691575); a job's time limit starts when it runs. A scheduled run uses the default branch's copy of the workflow (`main`'s, since 2026-10-21) and tests `dev`'s head; a dispatched run uses the workflow from, and tests, the ref it was dispatched on (decision-052). A first `resolve` job reads that one sha (`git ls-remote` of `dev` on a schedule, else `github.sha`) and writes it to the run's summary, and every other job checks it out, so jobs that queue for hours still test one commit, and a scheduled run, listed under the default branch's sha, names the one it tested (`test-default-branch.sh` checks the wiring and runs `resolve`'s script with a fake `git`). Full-corpus parity stays local (decision-004) |
| `bench` → `bench` (advisory: not a required check yet) | pytest-benchmark on the 5k fixture index (`backend/tests/bench`, task-031): the PR's base and head on one runner; a minimum time over 20% slower than the base fails, and each benchmark asserts its spec 03 budget (p95). It becomes required once it has run green on a few PRs without false failures (runner noise); a maintainer adds it to `dev`'s required checks |
| `web-image` → `web-image` (advisory: not a required check) | Only on PRs into, and pushes to, `dev` and `main` that touch `deploy/**`, `frontend/**`, `package.json`, `package-lock.json`, `.dockerignore` or the workflow itself (a workflow-level `paths` filter; TASK-148). `docker build -f deploy/web.Dockerfile .` three times on the runner's Docker, pushing nothing: a `private` image, a `public` one with the placeholder contact `takedown@example.org`, and a `public` one with no contact, which passes only when the build fails at `web-build-gate.sh` with its message. It stays advisory because the filter skips it on other PRs, and a required check that never starts stays pending forever; making it required means dropping the filter for a changed-files step inside the job, so it always reports |
| `e2e` → `playwright` (advisory: not a required check yet) | `make e2e`: Playwright against the deterministic 5k fixture API (`backend/tests/e2e/`) and the standalone frontend: the spec 05 review flow, keyboard focus behavior, axe WCAG 2.2 AA in both themes at 1280 and 320 px, root reflow at 320 px, and platform-specific `/search` visual baselines in both themes on the fixed `ubuntu-24.04` CI label |

`review-attested` is an **honesty check** against forgetting to review, not an access control. Anyone who
can edit the PR body could paste the marker. The access control is branch protection: only the
maintainers (write access) can merge or queue a PR. A same-repo `dev → main` promotion is exempt from `learnings` and `review-attested`. The exemption
checks the head repo, so a fork branch named `dev` cannot use it.

### Merge queue (TASK-161, decision-027)

`lint`, `test`, `claude-tooling` and `pr-gates` also run on `merge_group`, so a merge-queue build reports
all six required checks under the same names. `test` takes its OpenAPI baseline from the group's
`base_sha`. A `merge_group` event carries no PR, so the `attribution`, `learnings` and `review-attested` jobs run
`.claude/scripts/merge_group_gate.py` (`review`, `learnings`, `attribution`) in place of their
`pull_request` steps (`pr-base` passes). With the queue's MERGE method, the commits in `base_sha..head_sha` along first parents
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

**Dependabot** (`.github/dependabot.yml`, weekly, each version update held back 7 days after its release by
`cooldown`, for docker only on Docker Hub (below); security updates aren't; `target-branch: dev` on every
ecosystem, since Dependabot otherwise opens version updates against the default branch, decision-052;
`test-default-branch.sh`) watches `github-actions` (prefix `ci`),
`uv` and `npm` (prefix `deps`) and the `docker` base images in `deploy/` (prefix `build`). For each, minor and patch
version updates are grouped into one PR per ecosystem (a docker digest bump is not a version change and comes as its
own PR), and semver-major updates are ignored (`dependency-name: "*"`, `version-update:semver-major`), so a major
upgrade is a deliberate, hand-made PR; adopted 2026-10-01, after the npm entry's first run opened six PRs, majors
among them. The `uv` entry also ignores `tantivy` entirely (§Release, "Upgrading Tantivy"), and the `docker` entry
still bumps the base-image digests, which are not majors (§Deploy), and ignores a new `python` minor
(`version-update:semver-minor`): the api image's tag names the patch release `.python-version` pins, so a patch bump
arrives as a PR that must move `.python-version` too, and a minor is done by hand (§Monorepo layout, "Python pin").
It also ignores an `astral-sh/uv` minor (`ghcr.io/astral-sh/uv`, the api image's uv stage): while uv is 0.x a minor
is a breaking release (0.13.0 shipped "Breaking changes"; PR #132), so it is upgraded by hand like a major (the rule
goes once uv reaches 1.0), and only its patches and digest bumps arrive here; `docker_digest.py` stops any 0.x minor
of an image as well, and the weekly routine reports a newer uv minor (`prs.py uv-release`) or a uv advisory to the
owner. uv 0.12.24 → 0.13.0 was done by hand on 2026-10-16, once 0.13.0 was 7 days old, with `docker_digest.py`'s age
and attestation check run locally; 0.13.0 → 0.13.1 by hand on 2026-10-20, at 6.4 days, by the owner's explicit
waiver of the 7-day age for this pin (the digest and its astral-sh attestation verified; TASK-270), to ship in
v0.4.1 (Dependabot's PR #162 moved the tag alone, so it was remade by hand with the workflows and closed);
0.13.1 → 0.13.4 by hand on 2026-10-21, under a day after its release, by the owner's explicit waiver of the 7-day age
for this pin, since 0.13.4 is a security release (GHSA-hq85-5cpj-mr62: uv's bundled root certificates; the digest and its
astral-sh attestation verified; TASK-277; #162 had been moved to 0.13.4 before it
closed, so no Dependabot PR was open for it). **The api image's uv and CI's move together** (owner decision 2026-10-17,
TASK-252): every `astral-sh/setup-uv` step under `.github/` names that release (`with: { version: "X.Y.Z" }`), so CI
runs the reviewed uv under the same 7-day hold instead of setup-uv's newest (on 2026-10-16 CI ran uv 0.13.1, two
days old, while the image pinned 0.13.0), and `check_uv_pin.py` (in `make tooling`, so in `claude-tooling`) fails
while any step differs from the image's `ghcr.io/astral-sh/uv` tag, or names no version. It also refuses the other
installs it has patterns for (pip, pip3 or pipx installing or running uv, a package manager's `install … uv`, the
astral.sh installer, any `astral-sh/uv` path such as a release download or a `container:` image, `uv self update`)
and a job that runs `uv` before its setup-uv step; it can't see a uv that a script or `make` runs, an install it has
no pattern for, or a setup-uv step skipped by its `if:` (the docstring lists them). A uv bump is one hand
PR that changes `deploy/api.Dockerfile` and every workflow's `version`. A Dependabot docker PR moving the tag alone
fails `claude-tooling`, and since `prs.py check` allows a docker PR only Dockerfiles, the owner remakes it by hand
and closes Dependabot's; a digest-only bump keeps the tag and passes. A Dependabot `github-actions` bump of the
setup-uv action leaves its `version` input alone, but a new release can change what its inputs mean, so its
reviewer reads the new `action.yml`'s `version`, `version-file` and `manifest-file`.
A docker image's
`cooldown` holds only on Docker Hub, and only when Docker Hub's API answers: Dependabot dates a tag from that API
and otherwise skips the cooldown, saying "Cooldown could not be applied" in the PR body (it opened PR #132 about 20
hours after uv 0.13.0's release). So `prs.py check` stops a PR with that notice. It gives no date for any ghcr.io
tag or digest update, so every `ghcr.io/astral-sh/uv` PR, patch and digest bumps included, carries the notice and is
left for the owner; `docker_digest.py`'s attestation age (below) is the evidence the owner decides on, and the hold
should Dependabot ever date ghcr.io. GitHub applies `ignore` to security updates too, so a vulnerability whose fix
is a major, or any Tantivy fix, shows up as a Dependabot alert and is fixed by a hand-made PR. Docker images get
neither alerts nor security updates (the Advisory Database has no docker ecosystem).

A Dependabot PR is reviewed and merged like any other (review gate, attestation, merge queue), with these checks
added. Read the upstream release notes of every bumped package: a security release is not always in `npm audit`
yet. Check the supply chain: the lock's resolved URLs stay on the registry, the integrity hashes match it, no
package or install script is new, and the publisher is the one that published the previous version. For a docker
bump, the registry resolves the tag to the pinned index digest, and a ghcr.io image is attested by the previous
pin's publisher (source repository and signing workflow) and is at least 7 days old by the earliest verified
timestamp of those attestations (`docker_digest.py`). For npm, every entry in `frontend/package.json`
equals `packages["frontend"]` in `package-lock.json`: Dependabot's npm updater can write a caret there (PR #124's
`eslint-config-next`, PR #100's Vitest), and `npm ci` accepts it. `.claude/scripts/dependabot/npm_specs.py` checks
it on every PR (`make tooling`, CI `claude-tooling`; TASK-212): each spec in the four dependency sections of
`package.json` and `frontend/package.json` must be written exactly as the lock's `packages[""]` and
`packages["frontend"]` hold it (same string, same JSON type), none missing and none extra; it exits 1 naming
each mismatch, and also on a file it can't read, a manifest with no lock entry (or the reverse), a section that
isn't an object, a root `workspaces` entry other than `frontend` (add it to the script's `WORKSPACES`), a
`--root` that isn't a directory, and a checkout with neither file (so a routine that forgets `--root .` fails on
dev's copy's scratch directory instead of reading it as a match); case rows in `test-tooling-scripts.sh`.
`npm_lock.py` reports the same mismatches, from the same function, as FIX lines (a section that isn't an object,
or a workspace entry missing from the lock, is a PROBLEM). Run `npm audit --omit=dev` (in a cloud run with
`--package-lock-only`, *Cloud and local*) and report any advisory
that predates the bump. A lockfile edit runs under the `.nvmrc` Node, because an older npm drops the `libc`
fields. Docs that state a bumped version move in the same PR.

**The weekly routine** (decision-048, TASK-211). A scheduled Claude Code routine (a cloud session on a fresh clone,
no access to the owner's machine) runs `/dependabot-review` (`.claude/commands/dependabot-review.md`) once a week,
**notify-only** (the owner's decision, 2026-10-16): it runs every check a cloud session can and reports through its
run summary and push notification, and makes no GitHub write (no comment, label, PR-body edit or attestation, no
queueing or auto-merge, no push). Merging is always a local `/dependabot-review` run from a maintainer's clone, which
runs the same procedure in full (*Cloud and local*). What follows describes the procedure; the writes in it (the
comment, label, attestation, push and queueing) are a local run's.
Its checks are scripted in `.claude/scripts/dependabot/` and run from `dev`'s copy, never the PR branch's. `prs.py
check` gates each PR before anything of it runs: open, by Dependabot, into `dev`, its head still the sha fetched,
its head branch a plain `dependabot/<ecosystem>/…` name, every changed file one its ecosystem touches (computed by
git, and GitHub's file and commit lists equal to git's), every commit Dependabot's with a signature GitHub verified,
and no "Cooldown could not be applied" notice in its body. The checkers then run the checks above, and the shape of
the change: `uv_lock.py`, `npm_lock.py`, `docker_digest.py` and `actions_pins.py` allow no change in a file beyond
its dependency versions and pins (no script, build requirement, `RUN` line or `permissions:` rides along).
`restore_libc.py` repairs dropped `libc` fields; `prs.py` also checks the environment (`preflight`), lists the PRs,
reads CI's results for a PR head (`ci`), queues them (locally; `queue` refuses in a cloud session) and watches the
queue. Locally the routine then runs the tests
the ecosystem calls for (without the GitHub credential in their environment; `.githooks/pre-push` strips it from its
`make lint` and `make tooling` as well); in the cloud it runs none of the PR's dependency code and reads CI's results
instead (*Cloud and local*). Then come the reviewers, the dispositions, the review record and attestation (`record-review.py --attest --pr <n> --repo
<owner>/<name>`), the `no-learning` label unless something was learned, and `prs.py queue <n> --head <sha>`. It
fixes what the PR itself can fix: a manifest/lock pin, dropped `libc` fields, a doc that states the old version, a
review finding. It may merge, through the queue only, a PR that passes all of that. It never merges, and leaves open
with a comment for the owner, a PR with:

- a commit that isn't Dependabot's, a file outside its ecosystem, or a change beyond versions and pins;
- an integrity, hash or URL mismatch, or a file off the registry;
- a new publisher, or provenance the previous version had and the new one lacks;
- a new install script, or a new or removed package;
- a uv or npm release, or a ghcr.io image, younger than 7 days (the `cooldown` every ecosystem sets holds version
  updates back that long, so a uv or npm one is a security update, which ignores it; a ghcr.io image's age is the
  earliest verified `gh attestation verify` timestamp by the previous pin's publisher, since Dependabot dates
  docker tags only on Docker Hub), or one with no such attestation (no verified timestamp, a new publisher, an
  unattested previous pin), a docker image on any other registry, which nothing dates, or a PR whose body says
  Dependabot couldn't apply its cooldown; for actions and Docker Hub images the hold is otherwise the `cooldown`;
- a docker digest the registry doesn't resolve to, or a failed `gh attestation verify`;
- a red required check it can't fix, or a Must it can't fix;
- in the cloud, a CI check (`lint`, `test`, `claude-tooling`, `playwright`, `bench`, and `web-image` when it runs)
  red, missing or still running after an hour on step 1's head (`prs.py ci`); nothing is rerun there;
- locally, a red local test it can't fix, unless the PR's base is behind `dev` and the test was fixed there since. The
  routine then checks, in its own run: that `dev` hasn't changed the PR's files since the base; that `make test`
  passes in full on `dev` with the PR's files (the tree the merge queue builds); that a named commit on `dev`,
  not in the PR's head, changes that test or the code it checks, and that the commit or its PR (opened by a
  person) names the test; that every other red test is resolved; and that CI's `test` on the head it queues is
  green. It lists the waiver for the owner (`/dependabot-review` step 5, "A red test on a stale base");
- any semver-major, a docker image's 0.x minor, anything touching `tantivy`, or a new Python release, patch or
  minor: a patch changes how the crawlers parse pages (§Monorepo layout, "Python pin"), and the crawl-cache replay
  that shows records unchanged needs the owner's `data/`. A new digest for the same `python` tag is merged like
  any other.

The owner may accept one of these hard stops on a PR, and a local run then goes on with it: the decision is
recorded as a comment on the PR saying exactly what it covers, the checks run again on the head to be attested,
and only that head is attested (procedure §10, "When the owner accepts a hard stop"). `npm_lock.py`'s
`OWNER_ACCEPTED` lists the new npm packages accepted that way, each as `name@version` with that comment's URL, added
by an ordinary PR into `dev`. Such a package, at that version and under its own name only, is an `ok` line naming
the comment, its publisher and its provenance, and is still checked against the registry, cooldown included; an
install script on it is still a hard stop (TASK-262).

The checkers (and `prs.py check`) print `ok`, `FIX` (the routine repairs it) or `PROBLEM` (a hard stop) per finding,
and exit 0, 3 (only FIX lines), 1 (a PROBLEM) or 2 (the check couldn't run, also a hard stop). Every outside call
goes through `git`, `curl`, `npm` or `gh`, so the case table `.claude/scripts/tests/test-dependabot.sh` (in `make
tooling`) runs them against fakes; the mutants are in `.claude/scripts/mutants/dependabot.json`. The run ends with a
summary for its log: locally merged, left open (with the reason), not reviewed, and what the owner should look at;
in the cloud ready for a local run (with the fixes it must make), hard stops (with their evidence), not reviewed,
and what the owner should look at (procedure §11). The gates stay on for Dependabot PRs; exempting `dependabot[bot]`
from `learnings` and `review-attested` was considered and rejected (decision-048). Decision-048 set the routine's
credential as a fine-grained token: this repository only, `contents`, `pull requests`, `issues` and `actions` read
and write, nothing else (no `administration`, no `workflows`). As built, the credential depends on where the command
runs: locally it is the maintainer's own `gh` login; in the cloud it is the Claude GitHub App's installation (*Cloud
and local*), whose repository selection and permissions take the token's place as the bound (the selection is
checked locally; in the cloud step 0 checks the proxy's session binding). A workflow change runs with the
repository's secrets once it merges, so a local run reviews and attests a github-actions PR but leaves the queueing
to the owner, by hand after reading it (`gh pr merge <n> --auto --match-head-commit <sha>`), named in its summary;
`prs.py queue` refuses one. The pre-push hook and the autofix hook run their tools without the token.

*Cloud and local* (TASK-213). A Claude Code cloud session refuses every GitHub GraphQL call with HTTP 403 ("GitHub
GraphQL is not available from Claude Code sessions; …"), so `gh pr list`, `view`, `checks` and `merge` all fail
there, and its token is a network secret: `GH_TOKEN` and `GITHUB_TOKEN` hold placeholders (`gh auth status` calls
them invalid) and an egress proxy adds the real token to requests for api.github.com, so no process in the session
holds it. GitHub records the session's writes as the Claude GitHub App's (`performed_via_github_app: claude`), so
the App must be installed for this repository. Without it every write answers 403 "Resource not accessible by
integration": the first scheduled run (2026-10-13) reviewed #142 and #143 over REST but could post nothing, until
the owner installed the App that day. The App sets its own permissions. As read on 2026-10-13 they are actions,
checks, contents, discussions, issues, pull requests, repository hooks and `workflows` write, plus administration,
members and merge queues read, and the installation covered all of `uw-share-lab`'s repositories. The installation
must cover only this repository (the owner set it so on 2026-10-13, `repository_selection: selected`). A cloud
session can't read it: its proxy refuses the paths outside `repos/...` probed so far (`gh api user/installations`
and `installation/repositories` answer HTTP 403 "This GitHub API path is not available: sessions are bound to their
configured repositories"; probe, 2026-10-13, TASK-243). So `prs.py preflight` checks the reach by mode
(decision-048, TASK-243 AC6 addendum): **in the cloud** the session binding, requiring both of the proxy's own 403s
word for word, `gh api user/installations` refused with that message and `gh api repos/astral-sh/uv` (a public
repository the session isn't bound to) refused with "GitHub access to this repository is not enabled for this
session", and stopping the run on any other answer, a 200 included; **locally** the installation, reading `gh api
orgs/uw-share-lab/installations` (an org owner's call), printing the Claude App installation's repository selection
and permissions, and stopping the run unless the selection is `selected` (no `claude` installation at all, or a list
whose length isn't its `total_count`, stops it too). The selected repository list itself can't be read with a `gh`
login (it needs a GitHub App user token), so the selection is what is checked. The GitHub Advisory Database calls
(`gh api advisories?…`, step 0's uv query and step 2's per-package queries) are outside `repos/` too, and the proxy
refuses them: the 2026-10-16 run's `gh api 'advisories?ecosystem=pip&affects=uv&per_page=100'` answered HTTP 403
"This GitHub API path is not available: sessions are bound to their configured repositories" (TASK-247). So a cloud
run reports the advisories as not checked (step 0's uv query under "for the owner"; a per-package query as "checked
only locally" on that PR's line, which doesn't keep it from "ready for a local run"), and the local run that merges
a PR makes the queries itself. Because that credential has `workflows` and repository-hooks write, which can't be
removed, **a cloud run executes none of the PR's dependency code** (the owner's decision, 2026-10-13, decision-048):
no `uv sync`, `uv run` or `npm ci` of the PR's locks, no `make lint`, `make test` or `make e2e`, no smoke test, no
`npm audit signatures` (it needs the installed tree), and no reviewer running any of them. It keeps what runs none
of it: `dev`'s checkers (standard-library Python, `git`, `curl`, `npm view`, `gh`), the registry, provenance and
advisory checks, `npm audit --package-lock-only`, the release notes, the reviewers reading diffs, the docs checks,
and `make tooling` and `make mutate-changed` (the repo's own scripts, with the environment step 0 installs from
`dev` before any PR is fetched). For test, lint and e2e evidence it runs `prs.py ci <n> --head <sha>`: over REST,
the latest GitHub Actions run of each of `lint`, `test`, `claude-tooling`, `playwright` and `bench` on that head,
plus `web-image` when the PR touches a path it runs on, must be `success` (GitHub Actions runs them without the
App's credential; a check by any other app doesn't count, since the App can write checks). It waits up to 9 minutes
per call (exit 4 while a check still runs: the routine calls it again on the same head, up to an hour in all); red,
missing or still running is a hard stop for the owner, never rerun in the cloud. A cloud run reads it once per PR
and reports it; a local run reads CI's `test` before the body and again before `prs.py queue` when step 5's
stale-base waiver applies. `prs.py preflight` makes the rule a guard: in the cloud it writes `op-no-dep-code` in the
clone's git directory, and while that is there `make sync`, `fmt`, `lint`, `test`, `e2e` and `openapi` refuse (the
Makefile's `dep-code-allowed`), `scripts/setup-dev.sh` skips its `uv sync`, and `.githooks/pre-push` refuses every
push; locally it removes a marker it finds (case table `test-no-dep-code.sh`, rows in `dependabot_cases.py`).
Because the guard lives in the checked-out tree, a PR based on an older `dev` would bring back unguarded copies: in
a cloud clone `core.hooksPath` points at `dev`'s hooks extracted into the run directory (`setup-dev.sh` leaves it
while the marker is there), and `prs.py check` stops a head whose `Makefile`, pre-push hook or `setup-dev.sh` lacks
the guard (the cloud summary lists it as "rebase needed (`@dependabot rebase`)" for the local run). When `git
rev-parse` fails (so the marker can't be checked), the Makefile's dependency targets and the pre-push hook refuse
rather than run. Commands typed directly (`uv run`, `npm ci`, `npx`) have no such guard; the procedure and its
reviewer prompt keep them out. Locally nothing changed: the routine runs `make test` and the rest, and step 5's
stale-base waiver (which runs `make test` on the merged tree) is local only. **Sigstore can't run in the cloud**, so
every ghcr.io PR is the owner's there: `gh attestation verify` can't start a verifier ("no valid Sigstore verifiers
could be initialized", 2026-10-13) because the proxy answers Forbidden for Sigstore's TUF hosts
(`tuf-repo-cdn.sigstore.dev`, `tuf-repo.github.com`), and the attestation API of another organisation's repository
is refused ("not enabled for this session"), so no offline route exists either (probe, 2026-10-13).
`docker_digest.py` fails closed and its PROBLEM line gives that reason; locally it verifies as before. The uv
release check of step 0 (`prs.py uv-release`) meets the same binding: a `repos/astral-sh/uv` call refused with the
"not enabled for this session" 403 (which only the cloud proxy sends) is not a stop but "check uv's latest release
by hand" for the owner. `actions_pins.py` meets it too: a new pin's tag ref is in another repository, so in the
cloud it can't be resolved and the checker's PROBLEM line says why; every github-actions PR (each brings a new pin)
is the owner's there. **A cloud run is notify-only** (the owner's decision, 2026-10-16, decision-048): it makes no
GitHub write, so no comment, label, PR-body edit, attestation, queueing or push leaves a cloud session. The
evidence: on 2026-10-16 (session cse_014uvWwXsnPaQKx5UQf2fD6u) a comment the cloud posted with `gh api … -F
body=@file` came back with a generated-by footer naming Claude Code appended on the server side (as on 2026-10-13),
a cloud `PATCH` kept it, and only a `PATCH` from the owner's machine removed it; the cloud's queueing route (CCR)
and a cloud push were never exercised (TASK-243). The scripts enforce what they can: `prs.py queue` refuses in a
cloud session before any call, `record-review.py --attest` refuses in a clone holding the no-dependency-code marker,
and the pre-push hook refuses every push while it is there; the `gh api` writes (comments, labels, the body `PATCH`,
step 9's close/reopen and run cancel/rerun) are kept out by the procedure. `record-review.py --attest --pr` also
refuses wherever GraphQL is refused as a cloud session refuses it, marker or not. These guards stop an honest run's
mistakes, not a steered one: the session still holds the App's credential, with pull-request and checks write, so it
could write an attestation marker (a check run under a required check's name no longer counts: since 2026-10-17
`dev`'s required checks accept only GitHub Actions', TASK-251, §Branch protection); only the installation's scope
(this repository) bounds a steered run. A local run reads
back every comment and PR body it writes and removes anything added (cheap, though a write from the owner's machine
hasn't gained a footer). The procedure uses REST only (`gh api repos/<repo>/...`) and checks auth with a
repository-scoped call (`gh api repos/uw-share-lab/openproceedings`; the proxy refuses paths outside `repos/`, so
`gh api user` may fail there). `prs.py preflight` tells the environment by asking GraphQL for the viewer: the
session's 403 message is **cloud**, an answer is **local** (a maintainer's clone with a real `gh` login), anything
else stops the run; in the cloud it also requires that `gh` has no stored login (a file dependency code could read).
Locally `prs.py queue` runs `gh pr merge <n> --auto --match-head-commit <sha>`, reads the PR again and turns
auto-merge off again (`--disable-auto`) if the head moved, GitHub shows nothing set to merge, or a failed call left
it set; the merge queue's `review-attested` check also requires each PR's body to attest the exact head it merges,
and the routine attested only the head it reviewed (decision-048). Dependency code left running locally could defeat
both with the maintainer's login; the routine looks for leftover dependency processes before it queues, which
catches accidents but not code that hides itself, so what bounds it is that only registry-verified versions run. The
routine runs `record-review.py` from `dev`'s copy, like the checkers, because a PR branch based on an older `dev`
carries an older recorder. `prs.py watch` polls REST: the PR's `merged` and `auto_merge`, the timeline's latest
merge-queue event, the queue's `gh-readonly-queue/dev/pr-<n>-<sha>` build branch, and the check runs, and names a
queue build run that hangs so the local run can cancel and rerun it through the Actions REST endpoints.

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
- Secrets (OpenReview credentials, and the optional `OPENALEX_API_KEY` and `CROSSREF_MAILTO`) live only in `.env` (gitignored, mode 600). `data/` is never committed.

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
mounts, a promotion, refused and done retires, a takedown with `op takedown check`, the 64 KiB body cap and the
proxy's refusals below, no query in any log; with `--compare`, the comparison overlay below, HTTP/3 stalls
included; on its own Compose project and internal network, so a running deployment is never touched); it is run by hand, not in CI. Caddy must not log
query strings: `GET /api/v1/search?q=…` carries the query (spec 04 §Implementation notes). **`op serve` must sit
behind that proxy**, never face clients directly:
uvicorn (h11) has no request-header or slow-body timeout of its own, so the proxy's timeouts are what bound a
client that sends its request slowly; the app caps a body at 64 KiB (413 `API_BODY_TOO_LARGE`), uvicorn's
`limit_concurrency` (`ApiConfig.limit_concurrency`, default 256) bounds the connections one process holds,
and `timeout_keep_alive` (`keep_alive_seconds`, default 5) closes an idle one. The Caddyfile **must** set
(Caddy v2 directive names, checked against the Caddy docs 2026-09-27; defaults re-checked for 2.11.7 on 2026-10-16;
`deploy/Caddyfile` sets them, with the site name `{$OP_DOMAIN:localhost}`, a `Strict-Transport-Security` header
from `OP_HSTS` on every response, default `max-age=63072000` as the web app's own, with `includeSubDomains` left
off until TASK-064 decides the domain, and `skip_install_trust`):

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
			read_header 5s   # a client's request line and headers (default: 1m)
			read_body   {$OP_READ_BODY:10s}  # its body (default: no timeout); a timeout of the whole server
			idle        2m   # a keep-alive connection between requests
			# no `write` timeout: an export of the whole matched set streams for as long as it takes; Caddy's
			# stall-only `write_idle` (default 1m since 2.11.6) still cuts a client that stops reading for a minute
			# (`read_body_idle`, also 1m, doesn't fire first while `read_body` is at most 1m; leave it non-zero: it is
			# what sets the per-request read deadline, the only one an HTTP/3 stream gets)
		}
		max_header_size 64KiB  # the API's own request-head limit (a 2,000-code-point q fits)
		protocols h1 h2 h3     # comparisons on or off (TASK-257)
	}
}
(compare-off) {
	request_body {
		max_size 64KiB  # the API's own body cap (65,536 bytes; Caddy's 64KB is 64,000): refuse larger first
	}
}
(compare-on) { … }  # deploy/compose.yml + deploy/compare.yml only: below
openproceedings.example {
	import compare-{$OP_COMPARE:off}
	@overcap expression <a Content-Length of 1 to 18 digits> && <its value> > 65536
	error @overcap 413     # a declared length over the cap, before any of the body is read (TASK-259)
	@chunked {
		path /api/*
		header Transfer-Encoding *
	}
	respond @chunked "Send the request with a Content-Length." 411  # any method (TASK-255)
	reverse_proxy /api/* api:8000 {
		request_buffers 65537  # one byte over the cap: read every capped body whole before opening the upstream request
	}
	handle_errors {            # an error the proxy answers itself (502, 504, a web path's 413): HSTS, no Server
		…
	}
	handle_errors 413 {        # the same, and on /api/* the API's own envelope and headers (Connection: close on HTTP/1.x only)
		…
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
trickles its body holds a proxy goroutine, not one of the API's `limit_concurrency` slots. Caddy buffers only
up to `request_buffers` and then streams the rest, and opens the upstream request even after the body's read
failed (found in TASK-183), so the other routes are closed three ways (TASK-255, TASK-259; measured in
`docs/results/2026-10-24-proxy-body-limits.md`): `request_buffers` is one byte over the 64 KiB cap, so a body
within it is read whole and an unsized HTTP/2 body that stops at the cap waits in the proxy (at `64KiB` it was
streamed on and held an API connection until `read_body`, for any method: the API's `BodyLimit` reads a
`GET`'s body too); a chunked HTTP/1.1 request gets 411 (one over the cap that then stalled held an API
connection until `read_body`, since Go's server reads on from a body being closed); and a declared length over
the cap gets the proxy's 413 before any of it is read (forwarded, the API's refusal from the header raced the
proxy's sending and reached the client as a 502 in 9 of 300 tries under load). Every proxy 413 from the 64 KiB cap is
the API's own `API_BODY_TOO_LARGE` envelope (`handle_errors 413`), so the client gets one answer. The web
app's paths share the cap and the 413 and need no more (measured 2026-10-24): it takes no request body (no
server actions or route handlers), answers without reading one, and drops a connection whose client is still
sending after its 5 s keep-alive, as after any request, so the proxy passes its bodies on unbuffered and
`smoke-test.sh` checks that a stalled one holds no web connection. Every response the proxy writes from an
error (a 502, a 504, a web path's 413) carries the site's HSTS and no `Server` header (`handle_errors`; the
site's `header` directive runs only on routes that answer normally). A connection
beyond `limit_concurrency` gets uvicorn's own plain 503, and uvicorn logs `Exceeded concurrency limit.`
(WARNING, through the JSON handler) once per refusal, not once per episode: a burst of refusals is a burst
of lines, so alert on their rate rather than on one. The proxy is also
the one trusted proxy (`--trusted-proxy <its address>`); a trusted network wider than /8 (IPv4) or /32 (IPv6)
is refused, as is `--no-rate-limit` with a non-loopback `--host`. Off loopback, or with a `--trusted-proxy`,
`<data-dir>/takedowns/withheld.txt` must exist before the first start (an empty file on a fresh instance), or
the load fails `takedowns_missing` (TASK-067). Comparisons with a reviewer's own RIS file (`POST /compare`,
TASK-177, decision-035; 04 §Comparing with a RIS file) are an operator's choice: on by default only for a loopback `--host`
with no `--trusted-proxy`, off here unless `op serve --compare` is added to the `api` command. Turning them on
for a public instance means accepting uploads of up to 16 MiB from anyone (read in memory for the one
request, one at a time, never stored or logged; the caps, the slots and the pause are `op serve` flags, TASK-184), about 80 MB more memory for the served index's match table,
and comparisons that each hold a slot for up to a minute of CPU (one network at most a quarter of the time:
04 §Comparing with a RIS file, Cost). "Loopback" is what `op serve` binds, not who can reach it: run on
127.0.0.1 behind a proxy on the same host **without** `--trusted-proxy`, it takes itself for a local instance,
and then refuses a comparison (403) to every request the proxy forwards (one carrying `X-Forwarded-For`,
`X-Forwarded-Host`, `X-Forwarded-Proto`, `X-Real-IP`, `Forwarded`, `Via` or `CF-Connecting-IP`) and to every
page not on that machine (a non-loopback `Origin`), and `/meta` doesn't offer them to those requests (04
§Comparing with a RIS file); a proxy that sets none of those headers, in front of a client that sends no
`Origin`, would still offer comparisons to everyone it serves. So a proxied instance always passes
`--trusted-proxy` (as `compose.yml` does) or `--no-compare`. On this stack comparisons are turned on by the
overlay `deploy/compare.yml` (TASK-183): `op serve --compare`, and for the proxy `OP_COMPARE=on`, which imports
the `compare-on` snippet: the 64KiB cap scoped to `@rest` (anything but a `POST` to `/api/v1/compare`; a site-wide
cap would wrap the handle and refuse the file first; any other method there is an ordinary API request, which the
API answers 405, where a chunked `PUT` once entered the handle past its length checks, TASK-268), and for a `POST`
to `/api/v1/compare` alone a `request_body` and
`request_buffers` of 16MiB (Caddy's `16MB` is 16,000,000 bytes, under the API's 16,777,216), a 411 for a
`POST` with no `Content-Length` (past `request_buffers` Caddy streams the rest of a body, so an unsized file
that went over the cap and stalled held the API's slot until its upload timeout), a 400 for a length that
isn't 1 to 18 plain digits and a 413 for one over 16 MiB, before any of the file is read (forwarded, the API's
refusal raced the proxy's sending and reached the client as a 502 in one smoke run of five), each plain text,
not the API's error envelope; HTTP/3 kept on (TASK-257: Caddy's HTTP/3 server gets `read_body` through the
per-request read deadline it sets since 2.11.6: at `read_body` 60s an HTTP/3 upload that stalls, sending
nothing, is closed by QUIC's 30 s idle timeout (measured: 30.89 s, 504), and one that trickles is cut at
`read_body` (60.07 to 60.14 s; a stall was cut at `read_body` only with `read_body 20s`); unlike HTTP/1.1, the proxy then
forwards what it read, which the API refuses within half a second, 408 or 429, never comparing it); a longer `read_body` (`OP_READ_BODY`, 60s there), which is the server's timeout for every request (Caddy has no per-path one); and
a memory limit on the `caddy` container (`OP_CADDY_MEM_LIMIT`, 1g, with `GOMEMLIMIT` 800MiB). With the proxy
buffering the file, a slow upload holds a proxy goroutine and about 50 MiB of its memory (measured: Caddy's
buffer doubles to 32 MiB to hold 16, plus the buffers it outgrew until Go collects them), never the API's
comparison slot, and `read_body` cuts it; with no limit on how many arrive at once, the memory limit bounds
the proxy, which past it is killed and restarted, dropping every connection it held, searches included, for a
few seconds (24 uploads held at once reached the edge of 1 GiB, peaks 890 to 998 MiB, and 32 did not fit;
Caddy as built limits neither connections nor uploads per client. The owner decided on 2026-10-17 (TASK-256, option
(c)) that the cap will be a per-source connection limit in front of Caddy at the host, for example nftables
`connlimit`, on TCP and UDP 443 (QUIC: HTTP/3 is on, TASK-257), set once TASK-064 chooses the host; there is no
custom Caddy build. It caps the connections one address holds, not its uploads (HTTP/2 and HTTP/3 carry many
on one connection); many addresses together can still reach the memory limit, which then restarts the proxy as now. Until
it is set it is not built, and TASK-256 stays open for it).
`deploy/smoke-test.sh --compare` checks all of this, and decision-035 makes passing it on the host a
condition of any public instance enabling comparisons; it passed on Docker Desktop on 2026-10-16
(`deploy/README.md` §Comparisons; the measurements are in `docs/results/2026-10-16-compare-proxy.md`).
Swagger UI (`/api/v1/docs`, scripts from a
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
office (TASK-135) gates the project's own public launch since 2026-10-16 (decision-018 addendum): TASK-069 waits on its outcome.

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
`name:tag@sha256:<digest>`, the tag kept for readers (the api image's `python` tag names the patch release
`.python-version` pins, and a bump of it fails `test_python_pin.py` until `.python-version` follows: "Python pin")
and the digest that of the multi-arch index (not of one platform's manifest), so a rebuild uses the image that was
reviewed; a `FROM` naming an earlier build stage, or `scratch`, needs none. The same holds for every other image a
build pulls: a `# syntax=` parser directive (the BuildKit frontend; `web.Dockerfile` has none, so the builder's
built-in one is used), `COPY --from=` and `RUN --mount=…,from=`. `.claude/scripts/check_digest_pins.py` (`make
tooling`, CI `claude-tooling`; case rows in `test-tooling-scripts.sh`) reads every `*Dockerfile*` or
`*Containerfile*` under `deploy/` as BuildKit does (a BOM dropped, continuation lines glued, the `escape` directive
honoured) and fails on any of those images without a digest, or with an `ARG` in its name. Dependabot's `docker`
entry for `/deploy` and its subdirectories (weekly, prefix `build`; §CI, "Dependabot") bumps the `FROM` digests; it
reads no other line, so a pinned `syntax`, `COPY --from` or `RUN --mount` image (none today) is bumped by hand; a
new Node major (`22-…` → `24-…`) is ignored there, like every semver-major update (§CI), and done by hand along with
`.nvmrc` and CI. A digest is resolved from the registry, e.g. `docker buildx imagetools inspect
node:22-bookworm-slim` (its top-level `Digest:`, with media type `…image.index…`), which needs no running daemon;
where that hangs, the registry answers directly (a token from `auth.docker.io`, then a `HEAD` on
`/v2/library/<name>/manifests/<tag>` with the OCI index `Accept` header returns `docker-content-digest`).

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
  bump, the data table and this file before the promotion). Not PRs into any
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
   latest `web-image` run on `dev` and a `nightly` run from the last day that tested `dev`'s head: one dispatched
   on it (`gh workflow run nightly --ref dev`, whose `headSha` is `origin/dev`), or a scheduled run whose summary
   names that sha (a scheduled run is listed under the default branch's sha, decision-052). `backlog task list --plain` shows no open Must finding. The latest
   `docs/results/*-coverage.md` passes the M4 gate.
2. **Security gate.** `security-reviewer` (`/security-review`) over `origin/main...origin/dev`, every finding
   dispositioned as in `/review-gate`. Before the first release a public instance serves, TASK-067 (the
   pre-release security review) is Done.
3. **The index it is verified on**, under a local data dir: the served index when the release changes none of
   `TOKENIZER_VERSION`, `SCHEMA_VERSION` and Tantivy, else a new one built by the release's code (§Deploy
   runbook, with `op snapshot diff <old snapshot dir> <new snapshot dir>` reviewed). Run, with the release's code: the golden and
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
   `frontend/package.json`, and by hand on the app's own `version` line in each lockfile (the `openproceedings`
   package in `uv.lock`, the `frontend` workspace entry in `package-lock.json`), never by re-resolving them: a
   local `uv lock` or `npm install --package-lock-only` can rewrite unrelated fields (the lockfile `revision`,
   npm's `libc` fields), so check with `uvx --from 'uv==<CI's pin>' uv lock --check` and read the lockfile diff,
   one line per file (0.4.0's learning); in
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
   `learnings` and `review-attested`). The promotion passes `pr-base`, which `main` requires: a PR into `main`
   from any other head fails it. `main`'s branch protection requires green checks, not `dev` up to date
   with `main` (decision-046, step 7).
   Its approving-review count is zero under the owner's solo-maintainer policy applied on 2026-10-03;
   reviews remain optional, and required checks are never bypassed.
   Merge with a merge commit.
6. **Tag and notes.** First, the `v*` tag rulesets (§Branch protection; applied 2026-10-01) must be in place:
   `gh api repos/<owner>/<name>/rulesets --jq '.[] | select(.target == "tag") | .name'` lists them, one name
   per line and possibly more than one (today `Release tags: immutable` and `Release tags: maintainers only
   create`); add the output to the merged promotion PR as a comment (`gh pr comment <n>`). On
   `origin/main`, `CITATION.cff`'s `version` must be `X.Y.Z` and its `date-released` today's date (UTC); if
   either is not, don't tag: re-run step 4 with the corrected date (a new release branch and promotion), since
   a tag's `CITATION.cff` is never edited after. Then `git
   fetch origin` and check out `origin/main`; `lint`, `test` and `claude-tooling` (and `e2e`) are green on `main`'s push run for that
   exact sha (`gh run list --branch main --commit "$(git rev-parse origin/main)"`; the other required checks run
   only on pull requests; paste it into the promotion PR's comment), and if one is red, don't tag: `main` doesn't
   require a PR up to date (decision-046), so its merged tree may be untested; `python3 .claude/scripts/changelog.py
   --check --release X.Y.Z` passes (the promotion holds exactly the PRs the file lists; with `OP_DATA_DIR` or
   `--data-dir` naming step 3's data dir when this checkout doesn't hold `data/`); `python3 .claude/scripts/changelog.py --release X.Y.Z
   --notes X.Y.Z > notes.md` (the same `--data-dir`); `gh release create vX.Y.Z --target
   "$(git rev-parse origin/main)" --title X.Y.Z --notes-file notes.md`, which creates the tag on GitHub
   (`require-review.sh` blocks an agent's `git push` of a tag, since `main`'s merge commit has no per-sha
   record; `block-ai-attribution.sh` scans the notes). No assets. Then `git fetch origin --tags` and check that
   `git rev-parse vX.Y.Z^{commit}` is that sha.
7. **No back-merge** (decision-046). `main` holds the promotion's merge commit, which `dev` lacks, and that is
   fine: `main` doesn't require `dev` up to date, the next promotion merges cleanly (that commit changes no
   file `dev` lacks), and `changelog.py` places each PR by its tag's own history, never `dev`'s. After the tag,
   `git fetch origin --tags`; on `dev`, `python3 .claude/scripts/changelog.py --check` passes, unless a PR
   merged into `dev` after the release branch was cut, whose Unreleased entry any later PR's `make changelog`
   adds (§`CHANGELOG.md`). Releases through 0.1.0 used a `release/X.Y.Z-back-merge` PR (#102, #104, #110).
8. **Retention.** Keep every index and snapshot a search record pins (`op index retire` refuses a pinned
   index; §CLI). Supported older tokenizer/schema pins can still reproduce when `QUERY_VERSION` matches.
   Unsupported versions or incompatible Tantivy require the matching historical release; a changed
   `QUERY_VERSION` reports `drifted` even when the index remains supported. Keep the pinned data in all
   cases. To find the historical release for a
   record, match its pinned index's manifest (`tokenizer_version`, `schema_version`, `tantivy_version`) and the
   record's `query_version` against the releases' Data sections. The code serves index schemas 3 and 4 (spec 03
   §Versioning). Schema 2 was retired in milestone C, once `op index retire --dry-run` showed no search record pinned
   any of the four schema-2 indexes the data directory held (05a0541717f6, 6508b8cf66ff, a7cfd04b656f and
   c76d7f26ee06); they were deleted from the real data directory on 2026-10-10. A schema-3 index is not rebuilt: an
   OpenAlex-filled snapshot cannot be indexed at schema 3 (the build refuses it), so promoting one needs an index
   at schema 4 (`op index build` writes schema 4), after which the schema-3 index stays until no record pins it.
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
does not repeat the list, because a hand-kept copy is how counts drift. At TASK-211 (2026-10-07) there are
**49 agents, 53 skills and 18 commands** (target range 25–150 of each), across these areas:
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
- ops (including `/dependabot-review`, the weekly Dependabot routine, §CI).

New agents and skills are added when a milestone brings a new recurring task, never speculatively. Each
needs an area in `roster_index.py` and a path reference from something that uses it (the lint rejects
orphans).

The gate command is `/review-gate` rather than Kreate's `/code-review`, because a built-in `/code-review`
exists and could shadow the project command.

### Hooks (each with a case table under `.claude/hooks/tests/`, as in Kreate)

| Hook | Event | Blocks / does |
|---|---|---|
| `enforce-pr-workflow.sh` | PreToolUse Bash | `git commit` (and `cherry-pick`, `revert`, `am`, `rebase`, `commit-tree`), `push`, `merge`, `pull --no-ff` and a `reset` to anything but HEAD or the upstream on `main` or `dev` (the branch of the `--git-dir`/`GIT_DIR=` repo, an `export`ed or `set -a` one too, when one is named, and the branch a `checkout`/`switch` earlier in the same command left checked out); any write to those remote refs (`HEAD:heads/dev`, glob refspecs and the matching refspec `:`/`+:` included); a move of the local ones (`update-ref`, `branch -f`/`-M`/`-C`, `checkout -B`, `switch -C`, `worktree add -B`, a fetch or pull into them other than `fetch origin dev:dev`); a refspec-less push whose config picks the destination (`git -c` `remote.<name>.push`/`.mirror`, `push.default`, `remote.pushDefault`; the repo's config, read with `git config -z --get-regexp` (NUL records, so a value can't forge a key; the remote name keeps its case, so `remote.Origin` can't hide behind `remote.origin`): any `remote.<name>.push`, a true `.mirror`, `push.default=matching`, or `push.default=upstream` to a protected upstream; or config it can't read: `--config-env`, `-c include.path`, `GIT_CONFIG_*`, `GIT_COMMON_DIR`); an alias under config it can't read, a git command after a `git config` that writes an alias, include, push key or upstream (or a `remote add --mirror`, `remote set-branches`, `branch -u`, or a redirect/tee/`sed -i`/cp/mv/ln into a git config file) in the same command, a push after a `checkout`/`switch`/`worktree add` that creates a branch with an upstream (`-t`, a remote-tracking start point), and an ambiguous abbreviated option; a commit, merge, reset or push whose directory, `-C`, git dir, refspec or branch it can't resolve (`cd "$X"`, a `cd` to a missing directory, `HEAD:$UNSET`); a push, add, commit, rm or mv run by `xargs` (from Kreate). It reads the command with the shared cmdparse walk (`cd`/`pushd`/`popd`, `$` words, a word that expands to nothing dropped, a command with `~` or `$` also read with HOME/TMPDIR/USER as '' (`cd ~` then stays put), a git command inside `"$(…)"`, backquotes or an unquoted heredoc body read like any other, redirects apart, `--track <remote>/<b>` and `-qt`, `checkout <b> --`, `checkout -p`, repos keyed by absolute git dir); a command it can't parse (or that crashes the parser) is refused when its text has `git` and a write word (`push`, `commit`, `merge`, `reset`, `rebase`, `cherry-pick`, `revert`, `am`, `branch`, `update-ref`, `checkout`, `switch`, `worktree`, `fetch`, `pull`); without python3, a text check that also refuses a commit or push next to `-C`, `cd`, `pushd`, `--git-dir`/`GIT_DIR` |
| `require-review.sh` | PreToolUse Bash, Write/Edit/MultiEdit/NotebookEdit | `git push` of any unreviewed commit (every refspec source, `--all`, the `--git-dir` repo's HEAD); `--tags`, glob refspecs and the matching refspec `:`/`+:`; a refspec-less push whose config chooses the refspec (`git -c` push keys, `remote.<name>.mirror`, `push.followTags`; in the repo's config any `remote.<name>.push`, a true `.mirror` or `push.followTags`, `push.default=matching`; or config it can't read, `GIT_COMMON_DIR` included); an alias under config it can't read, and a git command after a `git config` (or a write into a git config file) that sets an alias, include, push key or upstream in the same command; a push or `gh pr create` after any git command in the same call other than one that moves no ref (status, log, diff, show, rev-parse, add, push, config, a fetch without a `<src>:<dst>` refspec or `--stdin`, …): `branch -f`, `fetch . +x:feat` and `worktree add -B` move what is pushed as surely as a commit; a remote or refspec it can't resolve, or a push after a `cd` it couldn't follow; a push run by `xargs`; `gh pr create`/`new` without an APPROVE record for the head, or without an added or extended learnings entry; any hand write, copy, move or deletion of a review record under `op-reviews/` (Bash or a file tool), globs expanded, and a write whose `cd`/redirect target it can't read (`$…`, a glob) hints at one (`op-rev…`, `.git`, git-dir), or a word of the writing command does in a path component (read with the variables it can resolve put in, the tail of an unquoted `$(…)/op-revie?s/x` included, and a component mixing an unresolvable `$` with `op-`/`rev`), or after a variable is set to a path-shaped part of one (`d=op-reviews`, `d=reviews`); an option's attached value (`--output=op-reviews/<sha>`) is read as a path; inline message values (`-m`, `--message`, `--trailer` of git commit/merge/tag/notes/revert/cherry-pick/stash; `--body`, `--title`, `--notes` of gh pr/issue/release create/edit/comment/review; never a word starting with `-`) are text, not paths; a command it can't parse that mentions a push, `gh` or a review record; any command it can't check (an internal error) |
| `block-ai-attribution.sh` | PreToolUse Bash | A message-writing git command, PR- or issue-writing gh command (`pr`/`issue` `create` (alias `new`), `edit`, `comment`, `close`, `reopen`, plus `pr review`/`merge`), `gh release create`/`edit`, or a `gh api` call that sends text (`--input`; a `-f`/`-F`/`--field`/`--raw-field` unless the method is GET, where gh puts fields in the query string; a method other than GET; a bundled `-iF` too; TASK-243) whose text (incl. heredocs, `--trailer`, `-F`, `--body-file` and `--notes-file` files, `gh api`'s `-F key=@file` and `--input` files (every file the call reads into a message, these, `< file` and a reader's, is read whole, and one it can't read whole, missing, not a regular file, unreadable or over 1 MB, is refused; `/dev/null` is empty), and files read by `cat`, `head`, `tail` or `sed` (the whole file is scanned, not the lines they print; sed script files from `-f`/`--file` included, including bundled `-nf`; input filenames after `--` are literal), `< file`, `$(cat file)` or `$(< file)`; a file word is read with its variables put in, `F=msg.txt; … "$(cat "$F")"`) has a Claude co-author trailer or a "Generated with"/"Generated by" footer naming an AI tool (the shared pattern, identical in the hook, `.githooks/commit-msg`, `pr-gates.yml`, `merge_group_gate.py` and `changelog.py`, checked by a row in `test-openproceedings-gates.sh`), in the raw text or in any word as bash reads it (`'Cl''aude'`, `$'…'`, a variable set in the command), the command also read with HOME/TMPDIR/USER as '' (a command it can't parse is scanned as raw text and, when it tokenizes, as words, and refused when it may be a writer: git and a message verb, gh `pr`/`issue`/`release` and a write verb, or any `gh api`, TASK-266; one it can't check at all is refused); `.githooks/commit-msg` covers editor commits |
| `enforce-backlog-cli.sh` | PreToolUse Write/Edit/MultiEdit/NotebookEdit | Hand edits under `backlog/`, the path normalised first (relative to the call's cwd, `//`, `./`, `..` and symlinks resolved, any case) (from Kreate; decision bodies are Edit-only); a path it can't read (an internal error) is refused |
| `protect-data-dir.sh` | PreToolUse Write/Edit/MultiEdit/NotebookEdit/Bash | Any write into, move of or deletion of `data/snapshots/`, `data/indexes/` (or `data/` itself, or a directory above them: `rm -rf .`, `rm -rf ../<repo>`, `find . -delete`), incl. globs expanded against the filesystem (`rm -rf data*`, `*`), case-blind paths (APFS: `Data/`), redirects, `cp`/`rsync`/`tee`/`dd`/`truncate`/`unlink`, `find -delete`/`-exec`, `sed -i`/`perl -i`/`ruby -i`/`awk -i inplace`, `rsync --remove-s…` (`--remove-source-files`, `--remove-sent-files`, and any unique prefix, `--rem`, as openrsync reads it; `--del` for `--delete`) from them, a `git log`/`diff`/`format-patch` `--output` into them, a file `sudo -e`/`--edit` or `sudoedit` edits in them (with `-R`/`--chroot`, which it can't place, refused; TASK-269), `git format-patch` writing its patches into them (`-o`/`--output-directory` or a unique prefix, `format.outputDirectory`, else the directory it runs in; refused where `data/` is when that config can't be read), a command inside `"$(…)"`, backquotes or an unquoted heredoc body, every target judged against the worktree that contains it, case-blind (`rm -rf ../<main>/data/snapshots` or `../<MAIN>/data` from a worktree), every path judged after `~`/`~+`/`~-`, `$PWD`, `$(pwd)`, `$(git rev-parse --show-toplevel)`, `$(git rev-parse --git-common-dir)`/`--git-dir`, `$(mktemp)` (a path in the temp dir, unknown when the command sets or unsets `TMPDIR`), a `for` loop's variable (each of its words, not when the loop can exit early), `$HOME` and other variables are resolved (from the call's cwd and earlier assignments, `unset` ones empty; from the hook's environment only HOME, TMPDIR and USER, each also checked as '' (`~` too, so `cd ~` with HOME '' stays put), where `"$TMPDIR"/*` is not globbed as `/*`) and `cd`/`pushd`/`popd` followed (`-P` physically; a missing target, CDPATH or `cd -` to an unknown directory leaves it unknown), and a path that decides a check but can't be resolved (`rm -rf "$UNSET/x"`, a relative path after `cd "$UNSET"`, a redirect to `"$(echo data)/…"`) refused where `data/` is (this worktree, the call's, or their repository's main worktree); any command it can't parse (anywhere, since TASK-244: a nested value that failed to parse once ended the check early), and any it can't check at all (an internal error); `git clean -x/-X` and `git stash --all` (`-a` in any short cluster too; they remove gitignored `data/`); `git add -f data/`, and any forced add that git's own dry run says would stage `data/` or a `takedowns/` path (`-fA`, `-f .`, `':/data'`, `'*.jsonl'`); a forced whole-tree add, `--pathspec-from-file` or undryable add (the dry run never starts the repo's `core.fsmonitor` program); `git update-index --add` of those paths (`--cacheinfo=` too); `git add` (forced or not) of any path through a `takedowns/` directory (the takedown list and log, TASK-136); shell `mv`/`cp`/`rm`/`dd of=`/redirects into `backlog/`, `sed -i`/`perl -i`/`ruby -i`/`awk -i inplace` of backlog files other than decision bodies, `touch`/`sponge` there, `cp -R`/`rsync`/`ditto` whose copy lands there (`dest/<name>`, or each entry of a `src/` and of every `ditto` source), `cp`/`mv`/`ln`/`install -t <dir>` into it (each read with its own GNU option table, `COPY_OPTIONS`: `--target-directory` by exact name or unique prefix, another option's value such as `-S X`, `-St` or `--suffix X` never read as `-t`, an ambiguous long option refused; and `mv -t <dir>` makes `<dir>` the destination, not a source, TASK-253), `patch` (not `--dry-run`) and `tar -x` (an `x` in any short cluster)/`unzip` into `backlog/`, a worktree root or above, `find -fprint`/`-fprint0`/`-fprintf`/`-fls` into it, and `find -delete` or `-exec`/`-execdir`/`-ok` running anything but a reader (`grep`, `cat`, …; `rg --pre` is no reader) from `backlog/`, a worktree root or above, BSD `find -f <path>` starts included and GNU's leading `-D <arg>`/`-O<n>` skipped (only the CLI moves tasks); every git command that writes `backlog/` files in the worktree or the index by pathspec (TASK-244): `git restore` (but `--staged` alone, which unstages), `git checkout [<commit>] -- <path>`, `git reset <commit> -- <path>` (one whose tree isn't HEAD's; a word that is neither a commit nor a path is a tree-ish) and `git reset --hard`/`--merge`/`--keep`, `-p` with no path (the whole tree), `git rm`, `git mv` (not `-n`), `git clean` (not `-n`; no path is the directory it runs in; `-e backlog` keeps it unless a `!` pattern follows, and not under `-X`, where `-e` adds to what is deleted), `git stash push -- <path>`, `git apply`/`git am` (the paths `git apply --numstat` reads with its `-p`/`--directory`/`--include`/`--exclude`/`--recount`, plus both sides of each rename and copy, C-unquoted; a patch on stdin or one git can't read is refused, and so is one in a call with other commands: the patch is read before they run; `am --continue`/`--skip`/`--abort` are not), `git merge-file` (its first file, not with `-p`), `git checkout-index` (`<top>/<prefix><path>`; `-a`), `git update-index` (`--cacheinfo`, `--stdin`, `--index-info`; flag-only forms such as `--assume-unchanged` write nothing), `git read-tree --prefix` or `-u`; under `--literal-pathspecs`/`GIT_LITERAL_PATHSPECS` a `:` word is a plain path, never an exclude; a relative `--work-tree` is read after `-C`; a path-valued option written with a `$` (`--prefix=$P`) is unresolved; the same pathspecs into `data/`, `data/snapshots` or `data/indexes` are refused (`IMMUTABLE`; `git clean`'s are the older `-x`/`-X` rule's, plus `-e data` undone by a later `!` exclude that names `data` or a glob, and `find` starts the older check misreads: `-f`, `-O`/`-D`, a cluster such as `-Lx`); a command git runs from its own words is checked as a command, from the worktree's top, up to four levels: the `-c` value of a command setting (`core.pager`, `pager.*`, `core.editor`, `sequence.editor`, `diff.external`, diff/merge drivers, filters, `alias.*`, `core.sshCommand`, `credential.helper`, …; `-c user.name="O'Brien"` is no command), `GIT_PAGER`/`PAGER`/`GIT_EDITOR`/`EDITOR`/`VISUAL`/`GIT_SEQUENCE_EDITOR`/`GIT_EXTERNAL_DIFF`/`GIT_SSH_COMMAND`/`GIT_ASKPASS`, `rebase --exec`/`-x` (in a cluster, or abbreviated: rebase, difftool and grep options are read as git abbreviates them), `bisect run`, `submodule foreach`, `grep -O<cmd>`, `difftool -x`/`--extcmd`, each `filter-branch --*-filter` and `--setup`, and a `git config [--file f] [set] <key> <value>` value for those keys; a `git apply` in a call with another command is refused unless the other is a `cd` or a report-only `git apply --check`/`--stat`/`--numstat`; a pathspec reaches `backlog/` when it is in it, is the worktree root (from a subdirectory, `..`), is a git glob whose fixed directory is either (`'*.md'`, `'b*'`), or is `:` magic (`:/`, `:(top)…`), unless an exclude names `backlog` itself, case-exact as git matches it (`':!backlog'`); `--pathspec-from-file`, stdin, and a pathspec, `-C` or work tree it can't resolve (or any built one after a `cd` it couldn't follow) are refused in a repo with `backlog/`, as is every other unresolvable path word or redirect target there; a file every matched path of which is in conflict may be settled (`checkout --theirs`, `restore --ours`; `git add -u` accepts a deletion, while `git rm` there stays refused by the older rule), unless git is pointed at another repository (`--git-dir`, `--work-tree`); branch and commit operations (checkout/switch a branch, rebase, merge, cherry-pick, `reset --soft`/`--mixed` without paths, `git stash` without a pathspec) and reads are not pathspec writes (`git rm -n`/`git mv -n` of a backlog path stay refused by the older rule); these TASK-244 checks are added blocks only, in `backlog_guard`, which runs before every older check and can't turn a refusal into an allow; and `rm`/`mv`/`git add`/`git restore`/… run through `xargs` (its arguments are unseen; every subcommand above, so `xargs git stash drop` is refused too) in a repo with `data/` or `backlog/`; a payload it can't read (not a JSON object, a tool it isn't wired to, no command, cwd or file path), a cwd that isn't a directory and a repository `git rev-parse` can't read are refused; paths are judged after symlinks are resolved, so a symlinked worktree or HOME doesn't change a verdict. It is a best-effort guard against mistakes, not a security boundary: an obfuscated command (`git${IFS}rm`, a config or hook script written earlier, a git command named through a wrapper it doesn't strip) may bypass it; the backstop is git history plus review |
| `autofix.sh` | PostToolUse Write/Edit/MultiEdit | Formats and fixes the edited file; reports what remains (never blocks). prettier and eslint are skipped while a config or `package.json` is uncommitted, and prettier is handed the tracked `frontend/.prettierrc.json` (`--config`), so it never loads an untracked nested one |
| `remind-token-contract.sh` | PostToolUse Write/Edit/MultiEdit | Editing `normalize.py` or the tokenizer → reminder to bump `TOKENIZER_VERSION` and run the parity and differential tests |
| `load-learnings.sh` | SessionStart | Puts `.claude/learnings/INDEX.md` into every session's context |

Beside the hooks, `.claude/settings.json` sets Claude Code's own `attribution` to nothing (`commit` and `pr`
empty, `sessionUrl` false), meant to keep Claude Code from adding a trailer, footer or session link to a commit or
a PR description (TASK-242). It doesn't hold for a cloud session's GitHub writes: a comment the cloud posted on
2026-10-16 still gained a generated-by footer on the server side (TASK-243), so the cloud `/dependabot-review` run is
notify-only (decision-048), and a local run reads back every comment and PR body it writes and removes anything
added.

All command-parsing gates share `.claude/hooks/lib/cmdparse.py`, which parses commands the way bash splits
them:
- separators with or without spaces: `;` `&&` `||` `|` `&` `(` `)`, newlines, and process substitution
  `<(…)`/`>(…)`;
- shell reserved words at the start of a command (`if`/`then`/`elif`/`else`/`fi`, `while`/`until`/
  `do`/`done`, `{`/`}`, `!`, `esac`, `function`, `coproc`) are skipped;
- `VAR=val` assignments and the wrappers `env`, `command`, `builtin`, `exec`, `time`, `nohup`, `nice`,
  `sudo`, `timeout`, `stdbuf`, `xargs`, `watch`, `xcrun`, `caffeinate`, `arch`, `doas`, `flock` and
  `unbuffer` are skipped, each with its own table of options that take a value (TASK-248: `arch -e
  NAME=value` and `-d NAME` set and unset as `env` does; `flock`'s lock file is read as a `>>` redirect of
  its own, in the directory flock runs in, since flock creates it (`flock N` alone is a descriptor), and its
  `-c`/`--command '<cmd>'` as `sh -c '<cmd>'`). The getopt wrappers (`env`, `sudo`, `nice`, `timeout`, `doas`,
  `caffeinate`, `flock`) are read with every option each takes, GNU's and BSD's (`GETOPT_WRAPPERS`): a short group
  whose value-taking letter takes the rest of the word or else the next word (`sudo -nu root`, `flock -nw5`), a
  long option by its unique prefix (`flock --wai 5`), `--` ending the options, `env -` as `env -i` and `nice -5` (also `--5`
  and `-+5`) as `nice -n 5`; an unknown or ambiguous option, a value with nowhere to come from, or another option after flock's
  lock file than `-c`/`--command` is a ParseError, since the command can't be told (TASK-253). `env -S '<words>'`
  is read as more of env's own words, options included. `sudo -e`/`--edit` and `sudoedit` (read with sudo's options)
  run no command: each word after the options is a file they edit, yielded as a `>>` redirect of its own, as flock's
  lock file is (with `-D`, from both the shell's directory and `-D`'s, since which one sudo opens it from isn't told;
  with `-R`/`--chroot` a ParseError, since the files are inside the chroot; TASK-269). `env -C dir` and `sudo -D dir` move only the command they
  run (`Argv.chdir`), never a later one, and that command's redirects are still opened where the shell is: they
  are yielded first as a command of none in the shell's directory, as `sh -c`'s and `eval`'s are (`env -C /tmp
  true > f` writes `./f`, and `X=d; env -C /tmp true > $X/f` writes `./d/f`); a
  directory they name with `$`, `~` or a backquote leaves the directory where it was, marked unknown, as an
  unresolvable `cd` does. The assignments are kept, and a command run by `xargs` is marked, because the words xargs appends
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
  it sets kept inside it) and `eval`, whose own redirects (`sh -c '…' >> f`, `eval … >> f`) are yielded first as a
  command of none, so a write through them is seen (TASK-253); a `cd` target goes through `expand_word` (`~`, `~+`, `~-`, `$PWD`,
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
allowed, when it looks like what a gate guards (fail closed); protect-data-dir refuses every one, anywhere
(TASK-244). A gate that hits an error it doesn't expect (a recursion limit, an undecodable
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
word (`$(awk 1 msg.txt)`); one that reads no file (`$(date)`) passes (TASK-170). It also refuses a message file a
command or reader reads that it can't read whole (TASK-243): the call may write that file before it runs (`cp draft.md
body.md && gh pr comment 1 --body-file body.md`, or `--body "$(cat body.md)"`); in the reading with HOME/TMPDIR/USER
as '' a path that isn't a file is skipped, since the first reading checked the real one. A file the call writes before
sending it (a `>`/`>>` target, a `tee` argument, a `cp`/`mv`/`install`/`ln` destination) is judged by its writer: text
in the command (`cat > f <<'EOF'`, `printf '…' > f`, `tee f <<< '…'`, with no unknown variable; a heredoc counts only
when every heredoc in the call has a quoted delimiter, or the call has no `$` or backquote) is scanned as that text,
and the file is read too when it exists (the write may append, not run, or run alongside); any other writer
(`cp`/`mv`/`install`/`ln`, `jq … > f`, `… | tee f`, a group's `{ …; } > f`) or an unresolvable write target is refused
(only when the call sends a file). A write after the call's last sender doesn't count. A writer file option with no value
(`--body-file <(…)`, which the walk drops) is refused, and so is a command it can't parse that names gh or git and a
message-file option or a reader (`cat`, `$(< f)`), rather than let that file through unread; and so is any command it
can't parse that may be a writer (git and a message verb, gh `pr`/`issue`/`release` and a write verb, any `gh api`),
whose options (a file option held in a variable) can't be read (TASK-266). When a gh writer reads
its text from a pipe (`--body-file -`, `--input -`, `-F body=@-`, with no `<`, `<<` or `<<<` of its own), any other
program in the call but gh run on a file is refused too (`jq -Rs '{body: .}' msg.md | gh api … --input -`, `git diff
--no-index /dev/null msg.md | gh …`). Known limitations, left to CI's attribution check: inline interpreter code that
opens a file, a `git tag`/`git notes` message fed from a pipe, a program's own output-file option (`sort -o`, `curl
-o`, `dd of=`, `sed -i`), and other shell obfuscation. When enforce-pr-workflow
refuses a commit that stayed in a protected checkout because a `cd ~/…` fails with HOME '', its message says to
name the target with an absolute `git -C` path (TASK-173).
`.claude/hooks/tests/test-parser-boundaries.sh` checks the exact joined text after an unquoted joined delimiter or a tab-prefixed `<<-` delimiter, plus the production worktree-root comparison with differing case on every platform (the filesystem-based APFS rows also remain).
The case tables count only exit 2 as a block. The threat model is honest mistakes, not
deliberate evasion.

### Mutation testing

`.claude/scripts/mutate.py` (`make mutate`, `make mutate-changed`, `--match <text>`) proves the case tables
have teeth. Each mutant in `.claude/scripts/mutants/*.json` breaks one piece of gate or tooling logic, and at
least one table must fail. Survivors are either fixed with a new row or documented as `equivalent`, with
the reason. A mutant must be runnable as written (TASK-254): its `old` text occurs exactly once in each of its files
(`STALE` when it is gone, `AMBIGUOUS` when it occurs more than once, since only the first would change), and its
edit must not stop a file compiling that compiled (`UNCOMPILABLE`: a table that runs the file would "kill" it for
the compile error alone), where a `.py` file is compiled, a `.json` file parsed, and a shell script (by suffix or
`#!` line) read with `bash -n` with each `<<'PY'` heredoc in it compiled as Python. Such a mutant fails the run
without running a table; `mutate.py --check` vets every selected mutant that way in seconds and runs no table
(`make tooling` and the nightly's first shard run it). A table's `# mutate-scope:` path that doesn't exist is
refused (exit 2), since the table would then never run for the file it meant. A mutant's `also` lists more files that get the same edit: text kept identical in several files (the
shared AI-attribution pattern, whose identity row would kill any one-file mutant) is mutated in all of them (TASK-243). Mutants run in parallel, each in a copy of the repo: the full set (997 on 2026-10-10) takes hours of one runner, and `--changed` only the mutants of the files a diff touches. A mutant is killed when any table fails, so it runs first the tables that name its file (its name, or its stem as a word, in the table or in a helper beside it that the table names), then the rest only if those all pass, and each phase stops at its first failure: the verdict of running every table (a survivor runs them all) in about a third of the time on the nightly logs of 2026-10-09/10. A table that runs past its timeout (10x its own baseline time, at least 60 s) is stopped with everything it started (its own process group) and run again alone: if it hangs again it has hung under the mutant, an infinite loop, and the mutant is `TIMEOUT`, which counts as killed; if not, that run's verdict stands, since a table slowed by the other jobs is not a hang. A table whose header comment declares the files it exercises (`# mutate-scope: <file> …`, repo-relative paths exactly as a mutant's `file`) runs only for a mutant that changes one of them, so a table that fails for some other reason, such as load, is never credited with another file's mutant (TASK-238: `test-mutate-run.sh`, which runs only `mutate.py`, was credited with 15 of 17 `docker_digest.py` mutants on a loaded machine; it declares `mutate.py`, and its timing checks are bounded by the sleeps they tell apart, so it passes beside 8 parallel mutant runs; `test-dependabot.sh`, credited under load with a `mutate.py` mutant, declares the `/dependabot-review` scripts, and `test-mutate-shard.sh`, `test-merge-group-gate.sh` and `test-changelog.sh` declare the script (and workflows) each runs: TASK-254). `--table-timeout` sets one timeout for every table, and is refused (exit 2) under 10x any table's baseline, where a slow survivor would count as killed. Ctrl-C, CI's `timeout --signal=INT` and SIGTERM stop the running tables too. `.claude/scripts/tests/test-mutate-run.sh` is the case table for all this. `--shard i/n` runs every n-th selected mutant from the i-th (1 <= i <= n), so n shards partition the set the same way every run; `--list` prints the selected labels and runs nothing. Reviews run
`make mutate-changed`; the nightly workflow runs every mutant as 16 shards in parallel jobs (§CI; 8 until 2026-10-06 and 12 until 2026-10-19, each time because a shard ran past its 140 minutes).
Hook probes stay data (TASK-169): `.claude/scripts/lint_probes.py` (in `make tooling`)
fails on a case-table row whose probe, label or command holds a `$(…)` or backquote bash would run while the
table runs, and `.claude/scripts/probe_hook.py` feeds one probe, from a file or one argument, to a hook or to
cmdparse without a shell (`sandbox` runs it for real only in a removed mktemp directory that is HOME too).
Never hand-roll a serial loop.

### Branch protection (GitHub)

`dev` and `main` require a PR, with these checks green: `lint`, `test`, `claude-tooling`, `attribution`,
`learnings`, `review-attested`, and on `main` also `pr-base` (applied 2026-10-21, TASK-271). On both branches each
must come from GitHub Actions (app_id 15368, applied
2026-10-17: `dev` by TASK-251, `main` by TASK-258): a check run of the same name from another app, such as the Claude
GitHub App the routine runs under (decision-048), doesn't count. They are required in the classic branch protection
only (the `dev: merge queue` ruleset has no status-check rule, and `main` has no rulesets); the commands, the
evidence and the rollback (`app_id: -1`, any app, with the branch in the API path) are in decision-027's 2026-10-17
addendum. No force-push, no deletion, admins included, and conversations must be
resolved. `main` required the branch up to date with it until 2026-10-06, when the owner turned that off
(decision-046), so a release needs no back-merge (§Release step 7). The owner changed only `main`'s required
approving-review count from 1 to 0 on 2026-10-03 for the solo-maintainer workflow; optional reviews remain
available. Required checks and all other protection settings were preserved. This protection was
applied on 2026-09-25, after
the repo was made public (free-plan orgs can't protect private repos). `main` has been the default branch since
2026-10-21, right after v0.4.1 was tagged (decision-052, TASK-271), so a visitor, a clone and a fork land on released
code; `pr-base` (app_id 15368) joined `main`'s required checks in the same step. `dev` stays the integration branch: a PR from a fork targets
it, and only the maintainers (write access) can merge. Dependabot's version updates target `dev` (`target-branch`) and the
scheduled nightly tests `dev`'s head (the `resolve` job), since both read the default branch (§CI). Merged feature branches are
deleted automatically.

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
