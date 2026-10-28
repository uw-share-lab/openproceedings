"""The most authors and keywords on one record or claim, and the longest native id of each form, over one snapshot;
whether decision-054's list caps change any record, and whether every record is still valid under decision-055's
native-id bounds (TASK-280, TASK-281). Read-only: it opens the snapshot's records.jsonl and writes nothing.

    uv run python docs/results/2026-10-22-list-counts-and-native-ids-check.py data/snapshots/<snapshot>

`iter_records` validates every line as a `PaperRecord` with this checkout's code, so a record whose id breaks a bound
stops it with a `SnapshotError` naming the line.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

from openproceedings.ingest.caps import LIST_CAPS, cap_record, is_trimmed
from openproceedings.ingest.record import MAX_NATIVE_DIGITS, MAX_NATIVE_KEY, RECORD_SCHEMA_VERSION
from openproceedings.ingest.snapshot import iter_records


def _parts(native: str) -> dict[str, int]:
    """The length of each bounded part of a native id, by form."""
    form, _, rest = native.partition("-")
    if form == "pmlr":
        volume, _, key = rest.partition("-")
        return {"pmlr volume digits": len(volume.removeprefix("v")), "pmlr key": len(key)}
    if form == "dblp":
        return {"dblp key": len(rest)}
    if form == "ojs":
        return {"ojs article digits": len(rest)}
    if form == "doi":
        toc, _, n = rest.partition(".")
        return {"doi toc digits": len(toc), "doi number digits": len(n)}
    return {}


def main(snapshot: Path) -> None:
    most: dict[str, int] = defaultdict(int)
    longest: dict[str, int] = defaultdict(int)
    with (snapshot / "records.jsonl").open(encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            longest["id"] = max(longest["id"], len(r["id"]))
            for part, n in _parts(r["id"].split(":", 3)[3]).items():
                longest[part] = max(longest[part], n)
            for field in LIST_CAPS:
                most[f"{field} (record)"] = max(most[f"{field} (record)"], len(r[field]))
            for c in r["provenance"]:
                if c["field"] in LIST_CAPS:
                    most[f"{c['field']} (claim)"] = max(most[f"{c['field']} (claim)"], len(c["value"]))
    print(f"code: record schema {RECORD_SCHEMA_VERSION}, key bound {MAX_NATIVE_KEY}, digit bound {MAX_NATIVE_DIGITS}")
    for name in sorted(most):
        print(f"most {name}: {most[name]} (cap {LIST_CAPS[name.split()[0]]})")
    for name in sorted(longest):
        print(f"longest {name}: {longest[name]}")

    records = changed = flagged = 0
    for record in iter_records(snapshot):  # each line validated with this checkout's bounds
        records += 1
        flagged += is_trimmed(record)
        changed += cap_record(record) is not record
    print(f"records={records} valid={records} changed={changed} flagged={flagged}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
