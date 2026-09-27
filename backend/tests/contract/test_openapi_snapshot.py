"""The committed OpenAPI snapshot is the contract as shipped (spec 04 §Conventions, api-contract skill).

Any change to a route, a parameter or a response model changes `backend/tests/contract/openapi.json`, so it
shows up in the PR diff; this test fails until the snapshot (and `frontend/src/api/schema.ts`, generated
from it) is regenerated with `make openapi`.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path

from openproceedings.api.openapi import REGENERATE, SNAPSHOT, openapi_document, render

ROOT = Path(__file__).resolve().parents[3]
HTTP_METHODS = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}


def test_the_committed_snapshot_matches_the_live_schema() -> None:
    committed = (ROOT / SNAPSHOT).read_text(encoding="utf-8")
    assert render() == committed, (
        f"the API contract changed but {SNAPSHOT} did not: run `{REGENERATE}` and commit "
        f"{SNAPSHOT} and frontend/src/api/schema.ts (review the diff under the api-contract versioning rules)"
    )


def test_the_snapshot_is_stable_text() -> None:
    """Sorted keys, no server URL and no timestamp: re-rendering the parsed file gives the same bytes."""
    committed = (ROOT / SNAPSHOT).read_text(encoding="utf-8")
    doc = json.loads(committed)
    assert render(doc) == committed
    assert "servers" not in doc


def test_every_operation_id_is_unique() -> None:
    """openapi-typescript keys `operations` by operationId; a repeated id is an invalid document (it was
    GET and HEAD /healthz sharing one)."""
    ids = Counter(
        op["operationId"]
        for item in openapi_document()["paths"].values()
        for method, op in item.items()
        if method in HTTP_METHODS
    )
    assert [i for i, n in ids.items() if n > 1] == []


def test_op_openapi_prints_the_same_bytes_under_any_hash_seed(tmp_path: Path) -> None:
    """Set iteration order (route methods, for one) follows PYTHONHASHSEED; the document must not."""
    outputs = set()
    for seed in ("0", "1", "4242"):
        out = tmp_path / f"openapi-{seed}.json"
        env = {**os.environ, "PYTHONHASHSEED": seed}
        subprocess.run(
            [sys.executable, "-m", "openproceedings", "openapi", "--out", str(out)],
            check=True,
            env=env,
            cwd=tmp_path,  # no data directory, no index: the document needs neither
            capture_output=True,
        )
        outputs.add(out.read_text(encoding="utf-8"))
    assert outputs == {render()}
