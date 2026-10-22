# A release's version bump must not let the local toolchain rewrite the lockfiles

**Key lesson:** On a release branch, change only the app's own version line in `uv.lock` and `package-lock.json`, then check them with the pinned tools (`uvx --from uv==<pin> uv lock --check`, and CI's `npm ci`). Running `uv lock` and `npm install --package-lock-only` locally can rewrite fields that have nothing to do with the release.

- **Date:** 2026-10-19 · **Task:** v0.4.0 release · **Area:** release
- **Artifacts:** `uv.lock`, `package-lock.json`, `docs/specs/08-ops-and-tooling.md` §Release step 4 (now says to edit the version lines by hand)

## What we set out to do
Bump the app version to 0.4.0 on `release/0.4.0`, as step 4 says: set `version` in `backend/pyproject.toml` and
`frontend/package.json`, then `uv lock` and `npm install --package-lock-only --ignore-scripts`.

## What we learned
- **npm rewrote the whole lockfile.** The local npm dropped every `"libc": ["glibc"]` field from the optional
  native packages: about 146 lines across `package-lock.json`, against a one-line version change. CI's npm keeps
  those fields, so the release PR would have carried an unrelated lockfile rewrite.
- **uv bumped the lockfile's format.** Re-locking with the local uv (Homebrew 0.13.0, the same version as the pin)
  changed `revision = 3` to `revision = 5` along with the version. The same uv's `uv lock --check` accepts
  `revision = 3` as it is, so only a re-lock writes the newer revision.
- **The narrow edit is enough.** The app's own entry is one `version` line in each lockfile: the `frontend`
  workspace entry in `package-lock.json`, and the `openproceedings` package in `uv.lock`. Edited by hand,
  `uvx --from 'uv==0.13.0' uv lock --check` passes, and the diff is exactly the release.

## Dead ends — don't repeat these
- Committing whatever `uv lock` and `npm install --package-lock-only` produce, without reading the lockfile
  diff. Check that the diff is one version line per file before going on.

## Addendum — 2026-10-21
v0.4.2: the version bump also moves the combined-snapshot golden (`FILES_HASH` in
`backend/tests/unit/ingest/test_combined_snapshot.py`), because the snapshot manifest records
`openproceedings_version`. The release-manager agent asks for proof that only that field moved it, and this is how
the proof was run:
- **Patch the name the snapshot module bound.** `ingest/snapshot.py` does `from openproceedings import
  __version__`, so the probe sets `monkeypatch.setattr(snapshot, "__version__", "0.4.1")`. Patching
  `openproceedings.__version__` changes nothing after import.
- **Put the probe under some checkout's `backend/tests/`.** It needs `tests.unit.ingest.test_combined_snapshot`'s `combined()`,
  `files_hash()` and the session `conftest.py` (the network guard). Run on its own from the scratchpad, it fails
  with `ModuleNotFoundError: tests`. This release copied it into the worktree, ran it and deleted it. The
  `qa-auditor`'s route is better because it never dirties the worktree: `git archive HEAD backend pyproject.toml`
  into a mktemp directory, put the probe under that copy's `backend/tests/`, and run it from the copy's root with the
  worktree's `.venv` python (which still imports the worktree's code, so keep the worktree clean).
- **Result.** With 0.4.1 the build hashed to `661ad734…`, the old value, and `SNAPSHOT_HASH` was unchanged. With
  0.4.2 it hashed to `03e68379…`. So the new `FILES_HASH` and its provenance comment went in with the release commit.

**Propagated to:** `.claude/agents/release-manager.md` (§How you work, step 2: how to run the in-memory check).

## Addendum — 2026-10-21 (v0.4.3)
- **The owner's day is not the tag day.** The owner asked for 0.4.3 on 2026-10-21 (EDT), and the branch was cut at
  00:09 UTC on 2026-10-22. `CITATION.cff`'s `date-released` is the UTC day the tag is created (spec 08 §Release step
  6 checks it against today's UTC date), so it says 2026-10-22, not the day of the request. With a 3-hour candidate
  nightly still to run, the tag lands hours later on that UTC day; a branch cut late in the UTC day has to plan for
  the tag falling after 00:00 UTC.
- **A fresh worktree has no root `node_modules/`.** `make test` stops at `frontend-deps` ("run make sync (npm ci)")
  until `npm ci --ignore-scripts` runs in the worktree. It left both lockfiles unchanged here; check
  `git status` after it all the same.
- **The `git archive` probe route works as written** in `release-manager` step 2. With `__version__` patched to
  0.4.2, the copy's probe hashed the snapshot to `03e68379…` (the value before), and `SNAPSHOT_HASH` was unchanged.
  The worktree stayed clean, and the new `FILES_HASH` is `b2cfbda7…`.

**Propagated to:** none new. `release-manager` §How you work already says to promote and tag on one UTC day, and
`2026-09-27-npm-workspace-hoists-node-modules-to-the-root.md` covers the root `node_modules/` gate.

## Addendum — 2026-10-22 (v0.5.0)
- **MINOR vs PATCH is the release manager's call; `changelog.py` doesn't make it.** Since v0.4.3, `dev` gained #192
  (`feat(ingest)`, TASK-279, decision-053) and Dependabot #187/#188, with `TOKENIZER_VERSION` 3, `SCHEMA_VERSION` 4,
  `QUERY_VERSION` 2 and Tantivy 0.26.2 unchanged. Spec 08 §Release (Versioning) says MINOR for new features, so this
  is 0.5.0, not 0.4.4. `changelog.py` refuses a PATCH only when one of those four versions changes
  (`... : not a patch release`, around line 393); a `feat` PR in the Added section does not stop a PATCH. Read the
  release's Added section (or the PR titles in the merge commits' bodies, `git log --first-parent --format=%b
  origin/main..origin/dev`; the subjects are only "Merge pull request #N …") before choosing the number: a `feat`
  title means at least MINOR.
- **A parallel reviewer must not use the main checkout.** The security review (spec 08 §Release step 2) ran as a
  background agent while step 3 (golden and contract suites, parity, coverage) ran in the main checkout. The
  reviewer ran `git checkout --detach origin/main` there by mistake, and went back to `dev` seconds later. Step 3
  might have read v0.4.3's tracked files in that window, so step 3 was re-run on a confirmed-clean `dev`
  2e99d3be: 2,669 passed, 1 skipped; parity 0 differences over 173,518 records; coverage `--check` exit 0, M4 PASS
  81 of 82. Brief a release's reviewer to read other trees with `git show <ref>:<path>` or `git diff`, or in a
  `git worktree add --detach` of its own, never with a checkout in the shared one.
- **Read `CITATION.cff` whole, not just its two release lines.** Its title, abstract and keywords still named only
  NeurIPS, ICLR and ICML, though AAAI, AIES, FAccT and IASEAI have been in scope since 0.3.0 (decision-049) and
  `README.md` lists all seven with their start years; five releases (0.3.0–0.4.3) shipped it that way because step 4
  edits only `version` and `date-released`. The UX review of this branch caught it, and 0.5.0's file now matches the
  README; so does `backend/pyproject.toml`'s `description`, which had the same three venues.
- **The `git archive` probe route worked again.** With `__version__` patched to 0.4.3 the copy hashed to
  `b2cfbda7…` (the value before), `SNAPSHOT_HASH` unchanged; the new `FILES_HASH` is `e6906934…`.

**Propagated to:** `.claude/agents/release-manager.md` (§How you work, step 1: the security reviewer keeps off the
shared checkout; step 2: choose MINOR or PATCH from the release's Added section, not from `changelog.py`; and step 1's
release-branch summary: check `CITATION.cff`'s title, abstract and keywords, and `backend/pyproject.toml`'s
`description`, against the README's venues and years).
