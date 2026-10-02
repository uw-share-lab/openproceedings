#!/bin/sh
# Let the `api` container open an index version and nothing more (deploy/README.md §Permissions; TASK-065).
#   deploy/index-permissions.sh <indexes directory> <index_version> [gid]   (default $OP_API_GID, else 10001)
# Run it after `op index build`, before pointing `current` at the version, as root or as an account in the
# group (default gid 10001, the api image's op-api). `op index build` leaves a version directory 0700, its files
# 0444 and Tantivy's two lock files 0644, all owned by the account that built it. Tantivy opens an index only
# after taking `.tantivy-meta.lock` for writing, so the API's user needs write access to that file (and the
# writer's), but not to the directory: with the directory 0750 and group-owned by op-api, the API can read
# every file and write the two lock files, and can't add, remove or rename anything.
set -eu
if [ "$#" -lt 2 ] || [ "$#" -gt 3 ]; then
  echo "usage: $0 <indexes directory> <index_version> [gid]" >&2
  exit 2
fi
indexes=$1
version=$2
gid=${3:-${OP_API_GID:-10001}} # the api image's gid: compose.yml's OP_API_GID
case "$version" in
  *[!0-9a-f-]* | -* | "")
    echo "$0: $version is not an index_version name (0-9, a-f and -)" >&2
    exit 2
    ;;
esac
dir="$indexes/$version"
if [ ! -d "$dir" ] || [ -L "$dir" ]; then
  echo "$0: $dir is not an index directory" >&2
  exit 1
fi
# run as root, so never follow a symlink: one planted in the directory would point chgrp or chmod elsewhere
if [ -n "$(find "$dir" -mindepth 1 -type l -print -quit)" ]; then
  echo "$0: $dir holds a symlink; an index holds none: check it before serving it" >&2
  exit 1
fi
chgrp -R -h "$gid" "$dir"
chmod 0750 "$dir"
for lock in "$dir/.tantivy-meta.lock" "$dir/.tantivy-writer.lock"; do
  if [ -L "$lock" ]; then # checked again right before use: chmod follows a symlink
    echo "$0: $lock is a symlink" >&2
    exit 1
  fi
  [ -e "$lock" ] || : >"$lock"
  chgrp -h "$gid" "$lock"
done
# -type f never matches a symlink, so a lock swapped for one after the check above is left alone
find "$dir" -maxdepth 1 -type f -name '.tantivy-*.lock' -exec chmod 0660 {} +
echo "$dir: group $gid, directory 0750, lock files 0660"
