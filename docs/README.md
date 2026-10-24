# docs

The design and the evidence behind it. For running the project, start at the [README](../README.md). For
contributing, read [CONTRIBUTING](../CONTRIBUTING.md).

## Specs (`specs/`)

The specs are the design, and changes to them go through a PR (skill `spec-writing`). Read 00 first: its six
guarantees are the review standard for everything else.

| Spec | Covers |
|---|---|
| [00 Overview](specs/00-overview.md) | why the project exists, its scope, the six guarantees, milestones, open questions |
| [01 Ingestion](specs/01-ingestion.md) | sources and crawlers, the record schema, track and status classification, dedup, snapshots |
| [02 Query language](specs/02-query-language.md) | tokens, grammar, fields and default filters, Scholar/PoP mode, canonical form |
| [03 Search engine](specs/03-search-engine.md) | the Tantivy index, compilation, ranking, the reference matcher, `index_version` |
| [04 Backend API](specs/04-backend-api.md) | the `/api/v1` endpoints, search records and replay, exports, errors, rate limits |
| [05 Frontend](specs/05-frontend.md) | the web app: editor, builder, results, paper and record pages, exports, coverage and help |
| [06 Semantic layer](specs/06-semantic-layer.md) | shelved (decision-017); not in v1 |
| [07 Evaluation](specs/07-evaluation.md) | the test suites, the Scholar comparison, the coverage report and the M4 gate |
| [08 Ops and tooling](specs/08-ops-and-tooling.md) | the layout, the `op` CLI, CI, the merge queue, deploy, release, and the `.claude/` tooling and hooks |

## Everything else

| Directory | Holds |
|---|---|
| [`results/`](results/) | dated reports: coverage (`op eval coverage`, latest [2026-10-16](results/2026-10-16-coverage.md), with AAAI 2021's row re-counted at 1,697, regenerated on index `78d2e70310f3` with AIES 2026 (TASK-217); the 2026-10-11 report and the milestone-C as-built report of 2026-10-10 stay as history), the Scholar comparison (`op eval scholar`, with its `-review.csv` rows for a person), the OpenAlex fidelity audit (`op eval openalex`, [2026-10-16](results/2026-10-16-openalex-audit.md) on the final snapshot, with OpenAlex measured against `aaai_library`'s AAAI 1980–2008 abstracts; the 2026-10-11 report on the same snapshot and the 2026-10-10 report on the pre-`aaai_library` snapshot stay as history), benchmarks (the group-count report on the real corpus, [2026-10-11](results/2026-10-11-bench-group-counts.md), and the synthetic 80k report, [2026-10-11](results/2026-10-11-bench.md), every first page within the 100 ms budget since TASK-230, spec 03; schema 4's group-count regression, its bisect and TASK-230's measurements, [2026-10-11](results/2026-10-11-perf-regression.md); when normalizing in worker processes pays, behind `PARALLEL_FROM`, [2026-10-24](results/2026-10-24-parallel-normalize-crossover.md)), audits and data checks (the comparison proxy on the Docker stack: stalls, memory and refusals, [2026-10-16](results/2026-10-16-compare-proxy.md); the proxy's body limits on the other routes, the 413 race and HTTP/3 stalls, [2026-10-24](results/2026-10-24-proxy-body-limits.md); the stored string lengths behind decision-053's caps, [2026-10-22](results/2026-10-22-stored-string-lengths.md); the list counts and native-id lengths behind decision-054's and decision-055's bounds, [2026-10-22](results/2026-10-22-list-counts-and-native-ids.md)); `coverage-sources.md` and `coverage-causes.toml` feed the coverage report, `scholar-comparison-notes.md` and `scholar-comparison-strings.txt` the Scholar comparison |
| [`design/`](design/) | UX design docs and the copy deck behind spec 05 |
| [`plans/`](plans/) | written designs and implementation plans for multi-milestone work, before it is built into the specs |
| [`research/`](research/) | verified facts about the sources (OpenReview, the proceedings sites, ojs.aaai.org, and the AAAI/AIES/FAccT/IASEAI note with the dblp AAAI, ACM/Crossref and FAccT-site censuses of milestone B and the OpenAlex census and licence of milestone C) |
| [`releases.toml`](releases.toml) | each release's data table (spec 08 §Release) |

Decisions are Backlog.md records in [`../backlog/decisions/`](../backlog/decisions/). Tasks are in
[`../backlog/tasks/`](../backlog/tasks/) (open) and [`../backlog/completed/`](../backlog/completed/) (done), and
are read and changed only with the `backlog` CLI. The operator's deploy runbook is
[`../deploy/README.md`](../deploy/README.md).
