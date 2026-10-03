# First main promotion: release preparation

This prepares the first `0.1.0` code candidate under spec 08 §Release. It does not tag a release,
deploy an instance, change a served index, or complete TASK-065/066/067's deployment-dependent criteria.
The application candidate is `07fe70f0fb6b18202f819149088cfcc54b75ef00`; the release branch adds
bookkeeping and evidence without changing the tokenizer, schema, query semantics, or dependencies.

## Candidate readiness

Required `dev` workflows succeeded at the candidate: test `37129423771`, lint `37129423741`, tooling
`37129423852`, and browser tests `37129423823`. The README PR's benchmark run `37128632284` succeeded
at its source `5d68c64d`; the later merge contains the same application code. The latest path-triggered
`dev` web-image run `37094029695` succeeded at `457c2278`; it is explicitly earlier build evidence,
not a build of the candidate SHA. The release PR reruns its applicable required and advisory checks.

The corrected full nightly [37115476175](https://github.com/uw-share-lab/openproceedings/actions/runs/37115476175)
succeeded in all 27 jobs on `8d273d6118f410857c8098ca01678ecf466d12f2` on 2026-10-03. That commit is
an ancestor of the candidate; the backend, frontend, tooling scripts and workflows are unchanged
between them. The intervening changes are README, learning and mutation task/results records.
This is scoped ancestry evidence, not a claim that the nightly ran on the candidate SHA.

The later-created scheduled run `37123261384` used older `5ff69202`. Its ingestion job failed on the
known surrogate-containing Unicode fixture seed, which `8d273d61` fixed with `surrogatepass` and a
permanent counterexample. The corrected ingestion job passed 1,521 tests. Preserve the old failure;
do not infer source freshness from run creation order or describe the old run as passing.

## Whole-application security review

The security reviewer inspected `origin/main...origin/dev`: main `0b31ebc425c3b27611550c116f1e3907330ff878`
to candidate `07fe70f0`, 1,086 changed paths. Verdict: **APPROVE**, no Must, Should or Nit findings.
The scope included credentials/logs/fixtures, crawler authentication and URL policy, API limits and
SQLite, hostile-input costs, takedown aliases and pinned versions, rendering, dependency locks,
deployment permissions, CI and hook anti-evasion.

Fresh verification: `make tooling` exited 0; 404 focused security tests passed in 19.68 seconds.
The production npm audit reported zero vulnerabilities. The full npm audit reported a development-only
`braces` advisory through ESLint's glob dependency chain, with no patched release at review time and no
public-request input path established. The reviewer documented that qualification without claiming
exhaustive vulnerability absence or recommending an unrelated ESLint downgrade.
Detailed local report: `/tmp/main-promotion-security-review.md`; raw checks:
`/tmp/main-promotion-security-{tooling,tests}.log`, their `.exit` files, and
`/tmp/main-promotion-security-cost.json`.

## Copied real-data index

The source is the local immutable snapshot `2026-09-29-d552baa07aed`, copied without hardlinks or
symlinks to live data into `/tmp/openproceedings-main-promotion-data`. The original data directory was
not opened by a reader, modified, promoted or retired. Its older index `05a0541717f6` was copied too.
The snapshot hash remains `d552baa07aed6bd754720c7ef17bc7d9ef7a645531fb95d6bc4174c2eacf91b8`.
`op snapshot diff` between the existing sealed copy and the new copy reports no changes.

| Field             | Verified candidate index                |
| ----------------- | --------------------------------------- |
| index_version     | `5cc8e14c2f9a`                          |
| documents         | 95,877                                  |
| tokenizer_version | `3`                                     |
| schema_version    | `3`                                     |
| tantivy_version   | `0.26.2`                                |
| query_version     | `2` (code, not an index-manifest input) |

Commands used the candidate code and the isolated `OP_DATA_DIR`, with heavy work serialized:

```sh
op index build --snapshot 2026-09-29-d552baa07aed
op index parity --index 5cc8e14c2f9a
op eval coverage --index 5cc8e14c2f9a --check --out /tmp/main-promotion-coverage
```

All three exited 0. Parity checked all 95,877 records, 133,865 terms and 191,123 phrases, with zero
differences. Coverage passed M4: 43/44 gated cells within ±1%, one existing owner-accepted exception
(ICLR 2013, decision-016), zero gaps, zero unclassified records and no stale causes or exceptions.
Build/parity/coverage logs are `/tmp/main-promotion-index-build.log`,
`/tmp/main-promotion-index-parity.log` and `/tmp/main-promotion-coverage.log`; copy provenance is
`/tmp/openproceedings-main-promotion-data/source-copy.json`. The data is never committed.

## Record replay and release-branch checks

This is first-instance, code-only preparation: hosting is unconfigured (TASK-064), and the source local
data directory has no `records/records.sqlite` or `current` pointer. No existing deployed target instance
has been identified, so there are no established target-instance records to sample. If an existing
instance is later identified, its consistent records backup and retained pins must be verified before
deploying this code; the development proof below does not substitute for that backup.

Supplementary development replay used 14 actual rows from the existing tokenizer diagnostic store,
copied into two independent directories before SQLite access. Its WAL was empty, its copied integrity
check returned `ok`, and source database/WAL/SHM hashes were identical before copying, after copying
and after replay. No rows were manufactured. Every row pinned supported old index `05a0541717f6`.

| Check                                   | Outcome                                         |
| --------------------------------------- | ----------------------------------------------- |
| Retained old index, all 14 records      | `reproduced`, IDs and exclusions match          |
| New-only `5cc8e14c2f9a`, all 14 records | `drifted`: exactly tokenizer 2→3 and schema 2→3 |
| Changed corpus, ranking or query inputs | None                                            |
| Added/removed IDs on new-only replay    | 0/0 for every record, membership-identical      |
| All 28 `op record replay --json` calls  | Exit 0, no refused replay or mismatch           |

The source is a **development diagnostic store, not a target-instance backup**. Raw per-record JSON,
exit/status assertions and source hashes are in `/tmp/main-promotion-development-replay-evidence/summary.json`
and its adjacent files. Controller: `/tmp/main-promotion-development-replay.py`; report:
`/tmp/main-promotion-development-replay-report.md`. These commands used the application candidate;
the release bookkeeping changes no replay implementation or version inputs.

The initial release-branch full suite found one expected-metadata regression: 6,756 backend tests passed,
three optional tests skipped, and the combined-snapshot whole-directory golden failed after the app-version
bump. The corpus hash was unchanged. Replacing only the manifest's `openproceedings_version` from `0.1.0`
to `0.0.0` in memory restored the exact old golden
`7bd50d624d41edad56d819d8898b028359b71d0589dd701c042479e57c2a1e2a`.
The deliberate new golden is `ce0f3eba928ece23dac50e7a9808f19cefb87d7e9bbab8f6b3032792c7f3d6cd`;
the strict all-files assertion is retained. Raw diagnosis:
`/tmp/main-promotion-snapshot-version-diagnosis.json`; initial failure:
`/tmp/main-promotion-release-test.log`. The targeted test then passed in 2.73 seconds
(`/tmp/main-promotion-snapshot-version-green.log`).

The fresh `make test` run passed the entire backend: **6,757 passed, three optional skips**, in 205.46
seconds, including golden and contract suites. Its aggregate exit was 2 because Vitest could not start:
the local installation had used a temporarily regenerated lockfile missing native optional bindings.
The tracked npm lockfile was restored unchanged, `npm ci --ignore-scripts --include=optional` succeeded,
and the native binding loaded. Then **all 4,724 frontend tests in 41 files passed**, exit 0, in 7.22 seconds.
No backend source changed between those runs. Thus both full suites passed, but the failed aggregate
command is not misreported as exit 0. Raw logs: `/tmp/main-promotion-release-test-final.log`,
`/tmp/main-promotion-release-npm-ci-repair.log` and `/tmp/main-promotion-release-frontend-final.log`.
The PR's required CI test job must independently pass the complete command on its final head.

Final local lint and tooling exited 0; the generated changelog's `--check --release 0.1.0` passed against
the copied index. Raw lint/tooling: `/tmp/main-promotion-release-lint-final.log` and
`/tmp/main-promotion-release-tooling-final.log`, the latter with an explicit `.exit` file.

## Remaining release boundary

The citation's `2026-10-03` date is provisional release metadata. Before any later tag, spec 08 step 6
requires its version and date to match the actual tag day on `main`, with another bookkeeping PR and
promotion if necessary. Promotion requires a second person's approving GitHub review; no self-approval
or branch-protection bypass. Tagging, public hosting and deployed checks remain separate work.

## Compatibility wording correction before merge

Final documentation audit found three Should findings: spec 03's short engine summary refused all
non-current schema/tokenizer versions, and spec 08 said version-changing code could not serve older
indexes and all older records must drift. Related release-manager and generated changelog wording
shared that obsolete assumption. Decisions 030/033 and the actual retained-pin replay proof establish
support for older schema/tokenizer forms when query inputs match.

The specs and release guidance now distinguish retained supported pins from replay against changed
inputs. Decision 023 retains its original accepted history with a dated clarification. The generator
no longer claims a first tag excludes development records or infers every older record's status from
release tables. MINOR-bump, Tantivy/schema-bump and fresh current-index verification rules are unchanged.
The revised real generator case table first failed ten expected assertions, then passed all 133;
five additional mutants restore the former incorrect claims. Raw logs are
`/tmp/main-promotion-compatibility-{red,green}.log`. These corrections do not change application runtime
or index data.

The official `make mutate-changed` run completed with **48 killed, zero survivors, zero stale patterns,
exit 0**. All 48 expected labels occur in order and every regression was detected by `test-changelog.sh`;
the final implementation, case table and mutant definitions match the recorded verification-input hashes.
Raw evidence: `/tmp/main-promotion-compatibility-mutation.log`, its `.exit` file and
`/tmp/main-promotion-compatibility-mutation-summary.json`. The older nightly's 773-mutant proof remains
historical evidence for its pinned source; the five new cases bring the repository definitions to 778.

A complete post-correction `make test` exited 0: **6,757 backend tests passed, three optional skips**, in
192.77 seconds, and **4,724 frontend tests passed in 41 files**, in 6.35 seconds. This completed aggregate
run follows the earlier installation repair; it does not erase those earlier failed commands. Raw
evidence: `/tmp/main-promotion-compatibility-test.log` and its `.exit` file. Lint and generated-changelog
freshness checks also exited 0 (`/tmp/main-promotion-compatibility-lint.log` and
`/tmp/main-promotion-compatibility-changelog-check.log`, each with an `.exit` file).

Closing gates before merge also include final tooling, verification of the resulting evidence/task edits,
exact-commit review and PR checks. The main PR triggers fresh private/public image builds; its API
additivity check explicitly permits main's pre-backend scaffold to lack a released contract, while
still refusing an unavailable baseline or a backend whose contract snapshot is missing.
