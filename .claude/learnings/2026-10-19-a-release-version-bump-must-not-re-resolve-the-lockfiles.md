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
- **Put the probe under `backend/tests/`.** It needs `tests.unit.ingest.test_combined_snapshot`'s `combined()`,
  `files_hash()` and the session `conftest.py` (the network guard). Run from the scratchpad, it fails with
  `ModuleNotFoundError: tests`. Copy it in, run it, then delete it before committing.
- **Result.** With 0.4.1 the build hashed to `661ad734…`, the old value, and `SNAPSHOT_HASH` was unchanged. With
  0.4.2 it hashed to `03e68379…`. So the new `FILES_HASH` and its provenance comment went in with the release commit.

**Propagated to:** `.claude/agents/release-manager.md` (§How you work, step 2: how to run the in-memory check).
