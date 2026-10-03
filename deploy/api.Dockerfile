# The `api` image: `op serve` (spec 04, spec 08 §Deploy; TASK-065). Build from the repository root:
#   docker build -f deploy/api.Dockerfile -t openproceedings-api .
# deploy/compose.yml builds it and runs it behind Caddy. The image holds the backend package and its locked
# dependencies only: no data, no tests, no dev tools. Its user, op-api (uid and gid 10001 by default), is neither root nor
# the operator's account that owns the takedown log (TASK-065 AC #3). `/data/records`, where compose mounts the
# record store (its one writable directory, a host directory 0700 owned by uid 10001), is created here with the
# same owner and mode.
# Base images are pinned by the digest of their multi-arch index, the tag kept for readers (TASK-149;
# .claude/scripts/check_digest_pins.py checks it, Dependabot's `docker` entry bumps the FROM digests).

FROM ghcr.io/astral-sh/uv:0.11.18@sha256:78bc42400d77b0678ba95765305c826652ed5431f399257271dda681d0318f03 AS uv

FROM python:3.12-slim-bookworm@sha256:54c85f3c47607a77f32adec749d3c81d1348bf25833671f512b26a9b6d778cb3 AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /repo
COPY pyproject.toml uv.lock ./
COPY backend/pyproject.toml backend/LICENSE backend/
# the locked dependencies first (a cached layer while only the code changes), then the package itself,
# installed as a wheel (--no-editable), so the runtime stage needs no source tree
RUN uv sync --locked --no-dev --no-install-workspace
COPY backend/src backend/src
RUN uv sync --locked --no-dev --no-editable

FROM python:3.12-slim-bookworm@sha256:54c85f3c47607a77f32adec749d3c81d1348bf25833671f512b26a9b6d778cb3
# op-api's uid and gid: 10001 unless the host already uses it for another account (compose passes
# OP_API_UID/OP_API_GID; deploy/README.md §Permissions)
ARG OP_API_UID=10001
ARG OP_API_GID=10001
RUN groupadd --system --gid "$OP_API_GID" op-api \
    && useradd --system --uid "$OP_API_UID" --gid op-api --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin op-api \
    && install -d -o op-api -g op-api -m 0700 /data/records
COPY --from=build /app/.venv /app/.venv
ENV PATH=/app/.venv/bin:$PATH OP_DATA_DIR=/data PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
USER op-api:op-api
EXPOSE 8000
ENTRYPOINT ["op"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8000"]
