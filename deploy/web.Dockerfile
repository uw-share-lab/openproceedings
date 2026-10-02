# The `web` image: the Next.js standalone server (spec 05, spec 08 §Deploy). Build from the repository root:
#   docker build -f deploy/web.Dockerfile \
#     --build-arg OPENPROCEEDINGS_INSTANCE=public \
#     --build-arg NEXT_PUBLIC_TAKEDOWN_CONTACT=takedown@your.org \
#     --build-arg NEXT_PUBLIC_API_BASE_URL= \
#     -t openproceedings-web .
# NEXT_PUBLIC_* values are compiled in by `next build`, so they are build arguments, not runtime environment.
# OPENPROCEEDINGS_INSTANCE has no default: every build says whether the instance is public, and a public one
# can't be built without a takedown contact (decision-018; deploy/web-build-gate.sh, then next.config.ts).
# Base images are pinned by the digest of their multi-arch index, with the tag kept for readers; Dependabot's
# `docker` entry bumps the digests (spec 08 §Deploy, TASK-149; .claude/scripts/check_digest_pins.py checks it).
# The compose file, TLS and the api image are TASK-065.

FROM node:22-bookworm-slim@sha256:43ac6c60b8f89723f746e8a92ce91abd5017e627ce1ddfe4238355d3a30b772c AS build
ARG OPENPROCEEDINGS_INSTANCE
ARG NEXT_PUBLIC_TAKEDOWN_CONTACT=""
ARG NEXT_PUBLIC_API_BASE_URL=""
ENV OPENPROCEEDINGS_INSTANCE=${OPENPROCEEDINGS_INSTANCE} \
    NEXT_PUBLIC_TAKEDOWN_CONTACT=${NEXT_PUBLIC_TAKEDOWN_CONTACT} \
    NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL} \
    NEXT_TELEMETRY_DISABLED=1
WORKDIR /repo
COPY deploy/web-build-gate.sh deploy/
RUN sh deploy/web-build-gate.sh
COPY package.json package-lock.json ./
COPY frontend/package.json frontend/
RUN npm ci --ignore-scripts --no-audit --no-fund
COPY frontend/ frontend/
RUN npm run build --workspace frontend

FROM node:22-bookworm-slim@sha256:43ac6c60b8f89723f746e8a92ce91abd5017e627ce1ddfe4238355d3a30b772c
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 HOSTNAME=0.0.0.0 PORT=3000
WORKDIR /app
COPY --from=build --chown=node:node /repo/frontend/.next/standalone ./
COPY --from=build --chown=node:node /repo/frontend/.next/static ./frontend/.next/static
USER node
EXPOSE 3000
CMD ["node", "frontend/server.js"]
