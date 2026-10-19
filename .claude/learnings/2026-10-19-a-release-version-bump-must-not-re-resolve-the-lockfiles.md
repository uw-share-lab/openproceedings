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
