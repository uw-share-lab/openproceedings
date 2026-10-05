# v0.1.0: release preparation

This prepares the first tag, `v0.1.0`, under spec 08 §Release. The `0.1.0` code candidate was promoted to
`main` on 2026-10-03 (PR #101, `docs/results/2026-10-03-release-preparation.md`) but never tagged: its
`CITATION.cff` was dated 2026-10-03, and step 6 refuses a tag on any other UTC day. The owner decided on
2026-10-04 to tag after the review-comparison batch (TASK-056, 175–182) merged. That batch is PR #105, and
TASK-196's re-measure is PR #106. This release branch re-dates `CITATION.cff` to 2026-10-05, points the
untagged `0.1.0` data table at the index this release is verified on, and regenerates `CHANGELOG.md`. It
changes no application code, version or dependency.

Candidate: `dev` at `63da2318` (PR #106's merge). Base: `main` at `d8eec5fd`.

## 1. Readiness on `dev`

- **Required checks at `63da2318`, in `dev`'s merge queue:** all green. These were test `37351340289`, lint
  `37351340188`, claude-tooling `37351340283` and pr-gates `37351340172`.
- **Advisory checks:** `bench` passed on PR #106's head (`37349851173`), on a base that includes group counts.
  The `web-image` push run at `63da2318` (`37352990475`) passed. The `e2e` push run there (`37352990725`) was
  still running when this was written; its result is in the promotion PR. Both were green at PR #105's merge,
  `bed0a6cb`.
- **Nightly:** the scheduled nightly `37337202193` (still running when this was written) is on `142f3e0e` (`dev` before PR #105) on 2026-10-05.
  Its result is in the promotion PR. The previous nightly, `37204685351` (2026-10-04, same sha), passed
  all jobs. Neither tested PR #105 or #106, so a nightly was also dispatched on the candidate itself
  (`37353576315`, `63da2318`). The promotion waits for it.
- **Backlog:** `backlog task list --plain` shows no open Must finding. TASK-197, the one known budget miss,
  is a recorded exception (decision-039), not a Must.
- **Coverage:** the M4 gate passes on this release's index (§3).

## 2. Security gate

The `security-reviewer` reviewed `origin/main...origin/dev` at `bed0a6cb` on 2026-10-05. Verdict:
**APPROVE**, with no Must and no Should findings.

- **Scope:** the compare upload path, middleware and config; the `op serve` defaults; the group-count
  workers; the ingest title handling; fixtures and scrubbing; the committed review CSVs; and the
  frontend's link, download and render code.
- **Tests:** the compare, compare-review and search-with-compare contract tests passed (161) in a detached
  worktree.
- **The one Nit:** `deploy/README.md` understated a comparison slot's memory peak for non-ASCII text. PR #106
  fixed it, and its own gate's security-reviewer approved the wording.
- **Prior findings:** none from PR #105's gate were re-raised. SEC-183 stays deferred to TASK-183, since
  `/compare` is off on the deploy stack.

TASK-067 (the pre-release security review) is still In Progress. Step 2 requires it to be Done only before
the first release a public instance serves, and no instance is hosted (TASK-064), so it doesn't block this
tag. It must be Done before any deployment of `v0.1.0`.

`63da2318` adds only PR #106 to the reviewed range: docs, a bench report and a test. Its gate's
security-reviewer approved it.

## 3. The index it is verified on

The served index is `fd13d8d27535`, built on 2026-10-05 from snapshot `2026-10-05-10b5a205a63f` (133,629
records). This release changes none of `TOKENIZER_VERSION`, `SCHEMA_VERSION` or Tantivy, so that index is
the one verified. It was read only, never modified, promoted or retired.

| Field             | Verified index                                                     |
| ----------------- | ------------------------------------------------------------------ |
| index_version     | `fd13d8d27535`                                                     |
| snapshot_hash     | `10b5a205a63f964496b9b572321785cf4c845c49fac4bf6cbdf5ab3dfe4cbe76` |
| documents         | 133,629                                                            |
| tokenizer_version | `3`                                                                |
| schema_version    | `3`                                                                |
| tantivy_version   | `0.26.2`                                                           |
| query_version     | `2` (code)                                                         |

These commands used the candidate code (`dev` at `63da2318`, before this branch's bookkeeping):

```sh
op index parity --index fd13d8d27535
op eval coverage --index fd13d8d27535 --check --out <scratch>
```

Both exited 0.

- **Parity:** all 133,629 records, 176,747 terms and 266,543 phrases checked, with 0 differences.
- **Coverage:** passes the M4 gate. 45 of 46 gated cells are within ±1%, plus one owner-accepted exception
  (ICLR 2013 main, decision-016). There are 0 gaps, 0 unclassified records, no stale causes or exceptions,
  and 2 unresolved records. These are an ICLR 2018 and an ICLR 2021 paper whose OpenReview signals disagree
  on acceptance, so their status is `unknown` (decision-020; TASK-113 flags them).
- **Golden and contract suites:** they ran inside the full `make test` on PR #106's branch (§5).

### Record replay

Hosting is still unconfigured (TASK-064), so there is no target instance and no `records/records.sqlite`
to sample. As on 2026-10-03, a supplementary replay used the 14 real rows of the development tokenizer
diagnostic store. The rows were copied into two scratch data directories. The copy passed
`integrity_check`, and the source's SHA-256 hashes were identical before and after.

| Replay                                                    | Outcome                                                                                                         |
| --------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| On each record's retained pin `05a0541717f6` (14)          | `reproduced`, ids and exclusions match                                                                          |
| On `fd13d8d27535` alone, `--index fd13d8d27535` (14)       | `drifted`, naming exactly `snapshot_hash` (corpus), and `tokenizer_version` and `schema_version` 2 → 3 (method)     |
| All 28 `op record replay --json` calls                     | exit 0, no refused replay, no mismatch                                                                          |

On the new index, 2 of the 14 records keep identical membership. The other 12 gain 2–44 ids and lose 0–18,
which the corpus change (the 2026 crawl and dedup) accounts for, and their replays name that change. The
per-record JSON, exit codes and source hashes are kept outside the repository, in `/private/tmp/claude-501/-Users-jeevanparmar-school-Research-Ferguson/06380199-f19b-4b93-b3e2-45129af1a2e2/scratchpad/release/replay/`.

## 4. Release branch

`release/0.1.0` from `origin/dev` at `63da2318`:

- **`CITATION.cff`:** `date-released: 2026-10-05`; the version stays `0.1.0`.
- **App version:** `backend/pyproject.toml` and `frontend/package.json` are already `0.1.0`.
  - `uv lock` resolved with no change.
  - `npm install --package-lock-only --ignore-scripts` under the local npm 10.8.2 stripped the `libc` fields
    of optional native packages. The version is unchanged, so the tracked lockfile was restored unchanged,
    as on 2026-10-03.
- **`docs/releases.toml`:** the untagged `0.1.0` table now names `fd13d8d27535` and its snapshot. No
  released (tagged) table is edited.
- **`make changelog RELEASE=0.1.0`:**
  - The output covers 95 PRs. It has no Breaking line and no changed-input callout, since this is the
    first tag.
  - The Data section names `fd13d8d27535`, checked against `data/indexes/fd13d8d27535/manifest.json`.

## 5. Local tests

- **PR #106's branch, `make test` (both suites):** backend 7,418 passed and 3 optional skipped; frontend
  4,842 passed in 46 files. This branch changes only `CITATION.cff`, `docs/releases.toml`, `CHANGELOG.md`,
  this file and a learnings addendum; its own `make test` was running when this was written, and its result
  is in the release PR.
- **TASK-196 known exception:** PR #106 re-measured group-count latency at a 1-minute load under 5. Every
  Trust-Evals string is within spec 03's 100 ms budget except a cold first page of `main-2-pop` with its
  counts (p95 190.1 ms). That is spec 03's exception "as measured" (decision-039), and TASK-197 brings it
  under the budget.

## Remaining steps

These follow the release PR's merge into `dev`.

5. **Promotion:** `dev → main`, with this file's evidence.
6. **Tag:** `gh release create v0.1.0` on `main` the same UTC day (2026-10-05). First check `CITATION.cff`,
   the tag rulesets and `changelog.py --check --release 0.1.0`.
7. **Back-merge:** `main` back into `dev`.
