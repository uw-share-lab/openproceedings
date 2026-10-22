"""The longest value of each stored string field decision-053 caps, over one snapshot, and whether the ingest caps
change any of its records (TASK-279). Read-only: it opens the snapshot's records.jsonl and writes nothing.

    uv run python docs/results/2026-10-22-stored-string-lengths-check.py data/snapshots/<snapshot>

Lengths are counted in NFKD, as `ingest/caps.py` counts them. Every claim is read, losing claims included.
"""

from __future__ import annotations

import json
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

from openproceedings.ingest.caps import cap_record, is_trimmed
from openproceedings.ingest.snapshot import iter_records


def _length(value: str) -> int:
    return len(value) if value.isascii() else len(unicodedata.normalize("NFKD", value))


def main(snapshot: Path) -> None:
    longest: dict[str, int] = defaultdict(int)
    lists: dict[str, int] = defaultdict(int)

    def see(field: str, value: object) -> None:
        if isinstance(value, str):
            longest[field] = max(longest[field], _length(value))

    with (snapshot / "records.jsonl").open(encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            see("id", r["id"])
            see("venue_id_raw", r.get("venue_id_raw"))
            for key in ("authors", "keywords"):
                lists[key] = max(lists[key], len(r.get(key) or ()))
                for item in r.get(key) or ():
                    see(key, item)
            for slot, value in (r.get("urls") or {}).items():
                see(f"urls.{slot}", value)
            for c in r.get("provenance") or ():
                field, value = c["field"], c["value"]
                if field in ("authors", "keywords"):
                    for item in value:
                        see(field, item)
                elif field.startswith("urls.") or field in ("venue_id_raw", "invitation"):
                    see(field, value)
                see("claim url", c.get("url"))
                see("claim evidence", c.get("evidence"))
    for field in sorted(longest):
        print(f"longest {field}: {longest[field]}")
    for key in sorted(lists):
        print(f"most {key} on one record: {lists[key]}")

    records = changed = flagged = 0
    for record in iter_records(snapshot):
        records += 1
        flagged += is_trimmed(record)
        changed += cap_record(record) is not record
    print(f"records={records} changed={changed} flagged={flagged}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
