"""The TASK-208 checks (docs/results/2026-10-07-python-upgrade.md), run under each interpreter in turn.

    python -I 2026-10-07-python-upgrade-check.py replay <crawl cache clone> <out.jsonl>
        every cached crawl replayed (`crawl.replay_all`, what `op snapshot build` runs), one sorted JSON line per
        record; compare two runs' files with `cmp`
    python -I 2026-10-07-python-upgrade-check.py fuzz <html.py> <out.jsonl> <seed> <count>
        a copy of `ingest/sources/html.py` (old or new, loaded from its path) over seeded random malformed markup:
        `text_of`, `node_text(parse(…))` and `metas` per string

Both need an environment with the openproceedings package installed (`uv sync`); `replay` reads the clone only.
Clone the cache with `cp -cR data/cache <scratch>/cache` (APFS: instant, no space), never replay `data/` itself.
"""

from __future__ import annotations

import dataclasses
import importlib.util
import json
import random
import sys
from pathlib import Path

ATOMS = [
    "<", ">", "</", "<!--", "-->", "--", "<!", "<?", "?>", "<![CDATA[", "]]>", "a", "p", "q", " ", "x=", '"', "'",
    "=", "/", "$", "&amp;", "&#39;", "&", ";", "<p>", "</p>", "<i>", "</i>", "<script>", "</script>", "<br/>",
    '<meta name="t" content="v">', "\n", "k<n", "abc", "<!doctype", "<a href='x'>", "</a>", "<title>", "</title>",
    "<textarea>", "</textarea>", "<xmp>", "</xmp>", "<iframe>", "<noembed>", "<noframes>", "<plaintext>", "<style>",
    "</style>", "--!>", "<li>", "</li>", "==",
]  # fmt: skip


def replay(cache: Path, out: Path) -> None:
    from openproceedings.ingest.sources.crawl import replay_all

    records, _ = replay_all(cache)
    with out.open("w", encoding="utf-8") as f:
        for r in records:
            row = dataclasses.asdict(r) if dataclasses.is_dataclass(r) else r.model_dump(mode="json")
            f.write(json.dumps(row, sort_keys=True, default=str, ensure_ascii=False) + "\n")
    print(sys.version.split()[0], len(records), file=sys.stderr)


def fuzz(html_py: Path, out: Path, seed: int, count: int) -> None:
    spec = importlib.util.spec_from_file_location("html_under_test", html_py)
    assert spec is not None and spec.loader is not None
    h = importlib.util.module_from_spec(spec)
    sys.modules["html_under_test"] = h
    spec.loader.exec_module(h)
    rng = random.Random(seed)
    with out.open("w", encoding="utf-8") as f:
        for _ in range(count):
            s = "".join(rng.choice(ATOMS) for _ in range(rng.randint(0, 25)))
            try:
                row = [h.text_of(s), h.node_text(h.parse(s)), h.metas(s, "t")]
            except Exception as e:  # recorded, so two runs compare their failures too
                row = ["ERR", type(e).__name__]
            f.write(json.dumps([s, row]) + "\n")
    print(sys.version.split()[0], count, file=sys.stderr)


if __name__ == "__main__":
    if sys.argv[1:2] == ["replay"] and len(sys.argv) == 4:
        replay(Path(sys.argv[2]), Path(sys.argv[3]))
    elif sys.argv[1:2] == ["fuzz"] and len(sys.argv) == 6:
        fuzz(Path(sys.argv[2]), Path(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5]))
    else:
        raise SystemExit(__doc__)
