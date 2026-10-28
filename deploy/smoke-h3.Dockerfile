# An HTTP/3 client for deploy/smoke-test.sh, in both modes (TASK-257; the HTTP/3 413 row runs on every smoke run):
# curl with HTTP/3, which neither macOS's curl nor the curl images (curlimages/curl, Alpine's) are built with;
# Debian trixie's is (nghttp3 over OpenSSL's QUIC). Never part of the stack: the smoke test builds it under its own
# tag, runs it on the stack's edge network against caddy:443 over UDP, and removes it on exit. The base is
# digest-pinned like every `FROM` in deploy/ (TASK-149).
#
# The packages are pinned too: apt reads the Debian archive as it was at the snapshot the base image was built
# from (the image's own debian.sources names it), so curl and every library it pulls in are the same on each
# build, and curl's exact version is asked for besides. A pin against deb.debian.org alone would stop building
# at the next curl security update (the security archive keeps only the latest). Over http, as the image's
# own sources are: the image has no CA certificates yet, and apt checks the archive's signatures either way;
# `Check-Valid-Until: no` because a snapshot's Release files are past their expiry date. When Dependabot bumps
# the digest, move SNAPSHOT to the new image's (`grep snapshot /etc/apt/sources.list.d/debian.sources`) and
# CURL to that snapshot's curl.

FROM debian:trixie-slim@sha256:62bd423aeee912639ca8ee681c2b762cb3e25137e0a92b20be455898a9f034ad
ARG SNAPSHOT=20261020T213255Z
ARG CURL=8.14.1-2+deb13u7
RUN printf '%s\n' \
      'Types: deb' "URIs: http://snapshot.debian.org/archive/debian/${SNAPSHOT}" 'Suites: trixie trixie-updates' \
      'Components: main' 'Signed-By: /usr/share/keyrings/debian-archive-keyring.pgp' 'Check-Valid-Until: no' '' \
      'Types: deb' "URIs: http://snapshot.debian.org/archive/debian-security/${SNAPSHOT}" 'Suites: trixie-security' \
      'Components: main' 'Signed-By: /usr/share/keyrings/debian-archive-keyring.pgp' 'Check-Valid-Until: no' \
      >/etc/apt/sources.list.d/debian.sources \
    && apt-get update \
    && apt-get install -y --no-install-recommends "curl=${CURL}" "libcurl4t64=${CURL}" ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && curl --version | grep -q 'Features:.* HTTP3'
USER 65534:65534
