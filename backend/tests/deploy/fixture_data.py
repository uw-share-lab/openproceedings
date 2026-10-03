"""Write a data directory for the deploy smoke test (`deploy/smoke-test.sh`, TASK-065): the synthetic 5k fixture
corpus (`big`), its first 300 records (`small`) and its first 100 (`spare`) as three snapshots and three
indexes, `indexes/current` → `big`, and an empty `takedowns/withheld.txt` (an instance off loopback refuses to
load without one, TASK-067). Three indexes, so the smoke test can promote `small` over `big`, see a retire of
`big` refused while a search record pins it, and retire `spare`, which nothing serves or pins.

    PYTHONPATH=backend uv run python -m tests.deploy.fixture_data <empty directory>   # from the repository root

Prints `{"big": <index_version>, "small": <index_version>, "spare": <index_version>}`. The directory must not
exist or be empty; nothing outside it is written.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from tests.contract.conftest import attributed, build
from tests.fixtures.corpus.synthetic_5k import records


def write(data: Path) -> dict[str, str]:
    if data.exists() and any(data.iterdir()):
        raise SystemExit(f"{data} is not empty")
    corpus = list(records())
    big = build(corpus, data / "snapshots", "big", data / "indexes", attributed)
    small = build(corpus[:300], data / "snapshots", "small", data / "indexes", attributed)
    spare = build(corpus[:100], data / "snapshots", "spare", data / "indexes", attributed)
    (data / "indexes" / "current").symlink_to(big)
    (data / "takedowns").mkdir()
    (data / "takedowns" / "withheld.txt").write_text("", encoding="utf-8")
    return {"big": big, "small": small, "spare": spare}


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: python -m tests.deploy.fixture_data <empty directory>")
    print(json.dumps(write(Path(sys.argv[1]))))


if __name__ == "__main__":
    main()
