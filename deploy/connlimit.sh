#!/bin/sh
# Per-source limits in front of Caddy on the host: load, check, show or remove deploy/connlimit.nft (TASK-067;
# deploy/README.md §Comparisons, spec 08 §Deploy). Linux with nftables, as root:
#   deploy/connlimit.sh check    parse the ruleset against this kernel without loading it (nft -c)
#   deploy/connlimit.sh apply    load it: replaces the table inet openproceedings_limits, touches no other table
#   deploy/connlimit.sh show     the loaded table, with its drop counters and the sources it tracks
#   deploy/connlimit.sh remove   delete the table (the limits are off)
# The ruleset is not persistent: load it at boot too (deploy/README.md §Comparisons says how). Never reload a
# host nftables.conf that starts with `flush ruleset` while Docker runs: it deletes Docker's tables as well.
set -eu
ruleset="$(dirname "$0")/connlimit.nft"
if [ "$#" -ne 1 ]; then
  echo "usage: $0 check|apply|show|remove" >&2
  exit 2
fi
if ! command -v nft >/dev/null 2>&1; then
  echo "$0: nft not found: this needs a Linux host with nftables" >&2
  exit 1
fi
case "$1" in
  check) nft -c -f "$ruleset" && echo "$ruleset parses" ;;
  apply) nft -f "$ruleset" && nft list table inet openproceedings_limits ;;
  show) nft list table inet openproceedings_limits ;;
  remove)
    if nft list table inet openproceedings_limits >/dev/null 2>&1; then
      nft delete table inet openproceedings_limits
    fi
    echo "per-source limits removed"
    ;;
  *)
    echo "usage: $0 check|apply|show|remove" >&2
    exit 2
    ;;
esac
