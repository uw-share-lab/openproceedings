"""The TASK-209 replay check (docs/results/2026-10-07-bare-lt.md).

    python -I 2026-10-07-bare-lt-check.py replay <backend/src> <crawl cache clone> <out.jsonl>
        every cached crawl replayed (`crawl.replay_all`, what `op snapshot build` runs) with the `openproceedings`
        package from <backend/src> (old: `git archive <commit> backend/src`; new: this branch's), one sorted JSON
        line per record
    python -I 2026-10-07-bare-lt-check.py compare <old.jsonl> <new.jsonl>
        the records whose fields differ, per field and venue, each title or abstract change classified:
        `restored` when nothing but whitespace is removed and the text gains `<`s, else `other`
        (printed whole, for a person to read)

Run from an environment with the locked dependencies (`uv sync`); `replay` reads the clone only. Clone the cache
with `cp -cR data/cache <scratch>/cache` (APFS: instant, no space), never replay `data/` itself.
"""

from __future__ import annotations

import collections
import dataclasses
import difflib
import json
import sys
from pathlib import Path


def replay(src: Path, cache: Path, out: Path) -> None:
    sys.path.insert(0, str(src))
    import openproceedings

    assert Path(openproceedings.__file__).resolve().is_relative_to(src.resolve()), openproceedings.__file__
    from openproceedings.ingest.sources.crawl import replay_all

    records, _ = replay_all(cache)
    with out.open("w", encoding="utf-8") as f:
        for r in records:
            row = dataclasses.asdict(r) if dataclasses.is_dataclass(r) else r.model_dump(mode="json")
            f.write(json.dumps(row, sort_keys=True, default=str, ensure_ascii=False) + "\n")
    print(sys.version.split()[0], len(records), file=sys.stderr)


def classify(old: str | None, new: str | None) -> str:
    if old is None or new is None:
        return "other"
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, old, new, autojunk=False).get_opcodes():
        if tag != "equal" and (
            old[i1:i2].strip() or ("<" not in new[j1:j2] and new.count("<") <= old.count("<"))
        ):
            return "other"
    return "restored" if new.count("<") > old.count("<") else "other"


def compare(a: Path, b: Path) -> None:
    def load(path: Path) -> dict[str, dict]:
        with path.open(encoding="utf-8") as f:
            return {(r := json.loads(line))["id"]: r for line in f}

    old, new = load(a), load(b)
    print(f"records {len(old)} / {len(new)}; only in one: {len(old.keys() ^ new.keys())}")
    counts: collections.Counter[tuple[str, str, str]] = collections.Counter()
    others = []
    for rid in sorted(old.keys() & new.keys()):
        if old[rid] == new[rid]:
            continue
        for field in sorted(
            k for k in old[rid].keys() | new[rid].keys() if old[rid].get(k) != new[rid].get(k)
        ):
            kind = (
                classify(old[rid].get(field), new[rid].get(field)) if field in ("title", "abstract") else "-"
            )
            counts[(old[rid]["venue"], field, kind)] += 1
            if kind == "other":
                others.append((rid, field, old[rid].get(field), new[rid].get(field)))
    for key, n in sorted(counts.items()):
        print(*key, n)
    for rid, field, before, after in others:
        print(f"\nOTHER {rid} {field}\n  old: {before!r}\n  new: {after!r}")


if __name__ == "__main__":
    if sys.argv[1:2] == ["replay"] and len(sys.argv) == 5:
        replay(Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4]))
    elif sys.argv[1:2] == ["compare"] and len(sys.argv) == 4:
        compare(Path(sys.argv[2]), Path(sys.argv[3]))
    else:
        raise SystemExit(__doc__)
