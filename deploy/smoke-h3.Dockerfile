# An HTTP/3 client for deploy/smoke-test.sh --compare only (TASK-257): curl with HTTP/3, which neither macOS's
# curl nor the curl images (curlimages/curl, Alpine's) are built with; Debian trixie's is (nghttp3 over
# OpenSSL's QUIC). Never part of the stack: the smoke test builds it under its own tag, runs it on the stack's
# edge network against caddy:443 over UDP, and removes it on exit. The base is digest-pinned like every `FROM`
# in deploy/ (TASK-149); the curl package is trixie's current one at build time.

FROM debian:trixie-slim@sha256:62bd423aeee912639ca8ee681c2b762cb3e25137e0a92b20be455898a9f034ad
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && curl --version | grep -q 'Features:.* HTTP3'
USER 65534:65534
