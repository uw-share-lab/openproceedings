# The api image carries no uv: check a uv bump through the `uv` build stage

**Key lesson:** `deploy/api.Dockerfile` copies uv into its builder stage only, so `docker run <api image> uv --version` fails ("executable file not found"); confirm a uv bump with `docker build --target uv` and `docker run --rm <that image> --version` (the stage's entrypoint is uv itself), and let the full build's `uv sync --locked` prove the new uv reads the lockfile.

- **Date:** 2026-10-19 · **Task:** TASK-270 · **Area:** deploy
- **Artifacts:** `deploy/api.Dockerfile` (`FROM ghcr.io/astral-sh/uv:… AS uv`, `COPY --from=uv /uv /usr/local/bin/uv`)

## What we set out to do
Prove the hand-made uv 0.13.0 → 0.13.1 bump before its 7-day hold clears, so the PR only waits on the date.

## What we learned
- **The runtime image has no uv.** It runs the synced `.venv`; uv is a build tool there. A version check on the
  final image is a false failure, not a broken bump.
- **The `uv` stage is the uv image itself.** Its entrypoint is `uv`, so pass `--version`, not `/uv --version`.
- **`docker_digest.py --base origin/dev --head origin/<dependabot branch>` dates the hold exactly:** it prints how
  many days ago the digest was first attested, so the merge day is known ahead of time.

## Dead ends — don't repeat these
- `docker run --entrypoint uv <api image>` and `docker run <uv stage> /uv --version`.
