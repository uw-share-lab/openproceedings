# v0.2.0: release preparation

This prepares `v0.2.0` under spec 08 §Release. `v0.1.0` was tagged on 2026-10-05 at `main` `e272aec5`. Since
then `dev` has added:

- **PR #109:** fixes to two property tests the v0.1.0 candidate nightly failed.
- **PR #111:** a contract test's frozen date.
- **PR #112, the v0.1.1 batch:**
  - TASK-188, 189 and 198: dedup and ingest rules (decisions 040, 044, 045).
  - TASK-190: ICML 2026 presentation (decision-042).
  - TASK-197: shared group-count collections.
  - decision-046: no back-merge after a release.
- **PR #113, the comparison batch:** TASK-184, 185, 186, 192, 194 and 195 (decision-043).
- **PR #114:** TASK-197's quiet re-measure, which closed decision-039's budget exception.

The release adds features, so it is a MINOR release (spec 08 §Versioning). It changes none of
`TOKENIZER_VERSION`, `SCHEMA_VERSION`, Tantivy or `QUERY_VERSION`.

Candidate: `dev` at `a18fd0ca` (PR #114's merge). Base: `main` at `e272aec5` (`v0.1.0`), which `dev` holds
through PR #110, 0.1.0's back-merge (left out of the changelog by design). From this release on there is no
back-merge (decision-046), so `dev` won't hold 0.2.0's promotion commit.

## 1. Readiness on `dev`

- **Required checks:** every candidate PR passed `lint`, `test`, `claude-tooling`, `attribution`, `learnings` and
  `review-attested` in `dev`'s merge queue.
- **`e2e`:** PR #113's run failed only the four visual tests whose Linux baselines changed on purpose. Those
  baselines were then committed from that run's artifact (`e0cb3559`); the final browser run is the promotion
  PR's. Locally, `make e2e` passed 64 of 64 on darwin.
- **`bench`:** passed on PRs #112, #113 and #114.
- **Nightly:** one was dispatched on the candidate itself, `37412309356` at `a18fd0ca`, on 2026-10-06; its result
  is in the promotion PR, and the promotion waits for it. The v0.1.0 candidate nightly (`37353576315`) failed
  one job, which PR #109 fixed and confirmed at the nightly profile.
- **Backlog:** no open Must finding. Follow-ups TASK-199 and TASK-200 are filed.
- **Coverage:** the M4 gate passes (§3).

## 2. Security gate

The `security-reviewer` reviewed `v0.1.0...origin/dev` at `a18fd0ca` on 2026-10-06. Verdict: **APPROVE**, with
no Must, one Should and two Nits.

- **What it probed:**
  - RIS upload and DOI handling: linear on hostile 32k-character lines;
  - `/parse` word forms: at most two renders plus a read-back;
  - `/search` group counts: no regression against v0.1.0 on a 10-group adversarial query;
  - the new `op serve` bounds: every value finite at the limits;
  - `/meta`, logging, ingest, the frontend's injection sinks, CI and branch protection.
- **Should:** `main` no longer requires a PR to be up to date (decision-046), so step 6 now also checks that
  the required checks are green on `main`'s push run for the exact sha being tagged. Spec 08 and the
  release-manager agent say so in this branch.
- **Nits:**
  - The comment in `.github/workflows/pr-gates.yml` claimed a second person's approval gates promotions. It is
    corrected here.
  - A per-record serialisation in `scholar_compare.py`, bounded but repeated, is TASK-200.

## 3. The index it is verified on

The served index `fd13d8d27535` (snapshot `2026-10-05-10b5a205a63f`, 133,629 records) stays the verified index,
because no version input changed. It was read only. These commands used the candidate code (`a18fd0ca`):

```sh
op index parity --index fd13d8d27535
op eval coverage --index fd13d8d27535 --check --out <scratch>
```

Both exited 0.

- **Parity:** all 133,629 records, 176,747 terms and 266,543 phrases checked, with 0 differences.
- **Coverage:** the M4 gate passes, with 45 of 46 gated cells within ±1% plus the owner-accepted ICLR 2013
  exception (decision-016).
- **Replay:** of the 14 development records, as for v0.1.0. All 14 are `reproduced` on their retained pin
  `05a0541717f6`. All 14 are `drifted` on `fd13d8d27535` alone, naming exactly `snapshot_hash`,
  `tokenizer_version` and `schema_version`. All 28 calls exited 0, with no refusal and no mismatch, and the
  source store's hashes were unchanged.

This release's ingest changes take effect at the next snapshot build. A real-cache rebuild with them (decision-045,
"Real-cache rebuild") changes 59 abstracts (decision-044) and no merge.

## 4. Release branch

`release/0.2.0` from `origin/dev` at `a18fd0ca`:

- **App version:** `backend/pyproject.toml` and `frontend/package.json` are `0.2.0`.
  - `uv lock` recorded the change.
  - The frontend workspace's version in `package-lock.json` was set to match. This is the one field
    `npm install --package-lock-only` would change; the local npm would also rewrite optional packages' `libc`
    fields.
- **`CITATION.cff`:** `version: 0.2.0`, `date-released: 2026-10-06`.
- **`docs/releases.toml`:** a new `0.2.0` table names `fd13d8d27535`. The tagged `0.1.0` table is unchanged.
- **`make changelog RELEASE=0.2.0`:** the 0.2.0 section lists PRs #109, #111, #112, #113 and #114, with no
  Breaking line and no changed-input callout.
- **Process:** spec 08 step 6, the release-manager agent and the `pr-gates.yml` comment, from §2.
- **Golden:** `test_combined_snapshot.py`'s `FILES_HASH` changes with the version, as at 0.1.0: the manifest
  records `openproceedings_version`, and set back to `0.1.0` in memory the files hash to the old value again;
  `SNAPSHOT_HASH` is unchanged.

## 5. Local tests

The release branch's `make test`, `make lint` and `make tooling` results are in the release PR.

## Remaining steps

These follow the release PR's merge into `dev`:

5. **Promotion:** `dev → main`, with this file's evidence.
6. **Tag:** `gh release create v0.2.0` on `main` the same UTC day (2026-10-06), after checking the required
   checks on `main`'s push run for that sha.
