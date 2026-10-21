# The api image carries no uv: check a uv bump through the `uv` build stage

**Key lesson:** `deploy/api.Dockerfile` copies uv into its builder stage only, so `docker run <api image> uv --version` fails ("executable file not found"); confirm a uv bump with `docker build --target uv` and `docker run --rm <that image> --version` (the stage's entrypoint is uv itself), and let the full build's `uv sync --locked` prove the new uv reads the lockfile.

- **Date:** 2026-10-19 · **Task:** TASK-270 · **Area:** deploy
- **Artifacts:** `deploy/api.Dockerfile` (`FROM ghcr.io/astral-sh/uv:… AS uv`, `COPY --from=uv /uv /usr/local/bin/uv`)

## What we set out to do
Prove the hand-made uv 0.13.0 → 0.13.1 bump before its 7-day hold clears, so the PR only waits on the date.
2026-10-20: it merged a day early, at 6.4 days, when the owner waived the rest of the hold to ship it in
v0.4.1 (TASK-270).

## What we learned
- **The runtime image has no uv.** It runs the synced `.venv`; uv is a build tool there. A version check on the
  final image is a false failure, not a broken bump.
- **The `uv` stage is the uv image itself.** Its entrypoint is `uv`, so pass `--version`, not `/uv --version`.
- **`docker_digest.py --base origin/dev --head origin/<dependabot branch>` dates the hold exactly:** it prints how
  many days ago the digest was first attested, so the merge day is known ahead of time.

## Dead ends — don't repeat these
- `docker run --entrypoint uv <api image>` and `docker run <uv stage> /uv --version`.

## Addendum — 2026-10-21
**A newer patch can be left with no PR at all.** Dependabot rebased #162 from 0.13.1 to 0.13.4 while it waited
(uv 0.13.2, 0.13.3 and 0.13.4 all shipped on 2026-10-20). It closed #162 when #175 (the by-hand 0.13.1) merged, so
nothing was open for 0.13.4. The list of open PRs is therefore not a list of pending uv bumps. After merging a
by-hand uv PR, compare the pin with uv's latest release (`gh api repos/astral-sh/uv/releases --jq '.[0].tag_name'`),
and look up a closed Dependabot PR's final title before calling its version handled. 0.13.4 was then done by hand
(TASK-277) the same way as #175: one digest from ghcr.io, its astral-sh attestation, all 11 setup-uv steps, and the
uv stage built and run with `--version`.
