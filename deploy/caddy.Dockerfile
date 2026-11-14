# The `caddy` image: Caddy with this project's Caddyfile, run as an unprivileged user (spec 08 §Deploy;
# TASK-065). deploy/compose.yml builds it from the repository root. It is a Dockerfile, not a bare `image:` in
# compose.yml, so the base image is digest-pinned and checked like every other `FROM` in deploy/ (TASK-149;
# .claude/scripts/check_digest_pins.py) and Dependabot's `docker` entry bumps it.
# Binding 80 and 443 as a non-root user needs no capability: compose.yml sets the container's
# net.ipv4.ip_unprivileged_port_start to 0. The base image gives the binary the file capability
# cap_net_bind_service=ep, and with every capability dropped (compose.yml) the kernel refuses to exec a binary
# whose file capability it can't grant (EPERM), so it is removed (`setcap -r`; the image ships setcap).

FROM caddy:2.11.8-alpine@sha256:f6228111e5fafa1a5238258d0858e103f10599b8d1659a146e7726681a002bb9
RUN addgroup -S -g 10002 caddy \
    && adduser -S -D -H -u 10002 -G caddy -s /sbin/nologin caddy \
    && chown caddy:caddy /data /config \
    && setcap -r /usr/bin/caddy
COPY --chown=root:root deploy/Caddyfile /etc/caddy/Caddyfile
USER 10002:10002
