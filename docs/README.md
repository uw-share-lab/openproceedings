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
| [06 Semantic layer](specs/06-semantic-layer.md) | deferred to phase 2 (decision-017); not in v1 |
| [07 Evaluation](specs/07-evaluation.md) | the test suites, the Scholar comparison, the coverage report and the M4 gate |
| [08 Ops and tooling](specs/08-ops-and-tooling.md) | the layout, the `op` CLI, CI, the merge queue, deploy, release, and the `.claude/` tooling and hooks |

## Everything else

| Directory | Holds |
|---|---|
| [`results/`](results/) | dated reports: coverage (`op eval coverage`), the Scholar comparison (`op eval scholar`, with its `-review.csv` rows for a person), benchmarks, audits and data checks; `coverage-sources.md` and `coverage-causes.toml` feed the coverage report, `scholar-comparison-notes.md` and `scholar-comparison-strings.txt` the Scholar comparison |
| [`design/`](design/) | UX design docs and the copy deck behind spec 05 |
| [`plans/`](plans/) | written designs and implementation plans for multi-milestone work, before it is built into the specs |
| [`research/`](research/) | verified facts about the sources (OpenReview, the proceedings sites, ojs.aaai.org, and the AAAI/AIES/FAccT/IASEAI note with the dblp AAAI, ACM/Crossref and FAccT-site censuses of milestone B) |
| [`releases.toml`](releases.toml) | each release's data table (spec 08 §Release) |

Decisions are Backlog.md records in [`../backlog/decisions/`](../backlog/decisions/). Tasks are in
[`../backlog/tasks/`](../backlog/tasks/) (open) and [`../backlog/completed/`](../backlog/completed/) (done), and
are read and changed only with the `backlog` CLI. The operator's deploy runbook is
[`../deploy/README.md`](../deploy/README.md).
