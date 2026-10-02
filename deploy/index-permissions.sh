#!/bin/sh
# Let the `api` container open an index version and nothing more (deploy/README.md §Permissions; TASK-065).
#   deploy/index-permissions.sh <indexes directory> <index_version> [gid]
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
gid=${3:-10001}
case "$version" in
  *[!0-9a-f]* | "")
    echo "$0: $version is not an index_version (hexadecimal)" >&2
    exit 2
    ;;
esac
dir="$indexes/$version"
if [ ! -d "$dir" ] || [ -L "$dir" ]; then
  echo "$0: $dir is not an index directory" >&2
  exit 1
fi
chgrp -R "$gid" "$dir"
chmod 0750 "$dir"
for lock in "$dir/.tantivy-meta.lock" "$dir/.tantivy-writer.lock"; do
  [ -f "$lock" ] || : >"$lock"
  chgrp "$gid" "$lock"
  chmod 0660 "$lock"
done
echo "$dir: group $gid, directory 0750, lock files 0660"
