"""Run with the PR's code: (1) count snapshot records whose tokens change between tokenizers 2 and 3; (2) build a
tokenizer-3 index of the same snapshot in the scratch dir; (3) replay every record saved by origin/dev's code:
on its own (pinned, tokenizer-2) index, and on the tokenizer-3 index alone."""

import json
import sys
import time
from collections import Counter
from pathlib import Path

from openproceedings.engine.index import build_index
from openproceedings.engine.tantivy_engine import TantivyEngine
from openproceedings.ingest.snapshot import iter_records
from openproceedings.query.normalize import normalize
from openproceedings.records import RECORDS_DIR, RecordStore, replay


def main():
    data, saved, old_version, snapshot = (
        Path(sys.argv[1]),
        json.loads(Path(sys.argv[2]).read_text()),
        sys.argv[3],
        Path(sys.argv[4]),
    )
    report = {}
    changed = Counter()
    examples = []
    n = 0
    for r in iter_records(snapshot):
        n += 1
        for field in ("title", "abstract"):
            text = getattr(r, field) or ""
            a, b = normalize(text, "2"), normalize(text, "3")
            if a != b:
                changed[field] += 1
                if len(examples) < 40:
                    gone, new = Counter(a) - Counter(b), Counter(b) - Counter(a)
                    examples.append(
                        {"id": r.id, "field": field, "only_2": sorted(gone), "only_3": sorted(new)}
                    )
        changed["records"] += any(
            normalize(getattr(r, f) or "", "2") != normalize(getattr(r, f) or "", "3")
            for f in ("title", "abstract")
        )
    report["records"] = n
    report["changed"] = dict(changed)
    report["examples"] = examples
    t = time.monotonic()
    built = build_index(snapshot, data / "indexes", workers=2)
    report["new_index"] = built.index_version
    report["build_s"] = round(time.monotonic() - t)
    old = TantivyEngine(data / "indexes" / old_version)
    new = TantivyEngine(built.path)
    assert (old.tokenizer_version, new.tokenizer_version) == ("2", "3")
    store = RecordStore(data / RECORDS_DIR)
    replays = {}
    for name, info in saved["records"].items():
        record = store.get(info["record_id"])
        own = replay(record, new, lambda v: old if v == old_version else None, data)
        alone = replay(record, new, lambda v: None, data)
        replays[name] = {
            "own": own.status,
            "own_index": own.engine.index_version,
            "alone": alone.status,
            "changed": [(c.input, c.recorded, c.current) for c in alone.changed],
            "added": len(alone.added or ()),
            "removed": len(alone.removed or ()),
        }
    report["replays"] = replays
    print(json.dumps(report, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
