#!/bin/sh
# The web image's build gate (TASK-136, decision-018; spec 08 §Deploy): every build of the `web` image says
# whether the instance is public, and a public one names a takedown contact. Run by deploy/web.Dockerfile
# before anything is installed; next.config.ts checks the same (and the contact's form) during `next build`.
#   OPENPROCEEDINGS_INSTANCE      public | private (required: there is no default)
#   NEXT_PUBLIC_TAKEDOWN_CONTACT  required when public: an email address or an http(s) page
set -eu
instance="${OPENPROCEEDINGS_INSTANCE:-}"
contact="$(printf '%s' "${NEXT_PUBLIC_TAKEDOWN_CONTACT:-}" | tr -d '[:space:]')"
case "$instance" in
  public)
    if [ -z "$contact" ]; then
      echo "web image: OPENPROCEEDINGS_INSTANCE=public needs NEXT_PUBLIC_TAKEDOWN_CONTACT (--build-arg" \
        "NEXT_PUBLIC_TAKEDOWN_CONTACT=takedown@your.org): a public instance names a takedown contact" \
        "(decision-018, spec 08 §Deploy)" >&2
      exit 1
    fi
    ;;
  private) ;;
  *)
    echo "web image: set --build-arg OPENPROCEEDINGS_INSTANCE=public (a publicly reachable instance; it needs" \
      "NEXT_PUBLIC_TAKEDOWN_CONTACT) or =private (a private, local or development one)" >&2
    exit 1
    ;;
esac
echo "web image: a $instance instance${contact:+, takedown contact set}"
