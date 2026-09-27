"""The verification-candidate ceiling against the round-3 exploit (M3a review gate; decision-010), at scale.

The exploit: 8 clauses (the cap), each a word NEAR itself, so every document holding the word is a candidate
in each field. On the synthetic 80k index it held the only verification slot for 63 s (each clause ~3.2 s a
field) and cost 60 tokens against a 60 s refill, so every other verified query got `API_BUSY`. A normal
review query's position checks read a small share of that. The ceiling (`max_verification_candidates`,
default 200,000 at ~40 µs a candidate: ~8 s) refuses the exploit before anything is verified, and serves
the normal ones.

In CI the 5k fixture stands in for 80k with the ceiling scaled by the same factor (5k/80k: 12,500): the
fixture's text is the 80k corpus's generator at the same word frequencies, so each count scales with the
index. The real 80k run is opt-in (`OP_BENCH_80K=1`: it builds a ~80k index in a temporary directory, a few
minutes) and runs the default ceiling.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from openproceedings.api.config import ApiConfig

from tests.contract.conftest import Store, build, make_app
from tests.fixtures.corpus.synthetic_5k import records
from tests.golden.test_trust_evals import STRINGS

SEARCH = "/api/v1/search"
# the reviewer's shape: 8 self-NEARs of common words (4 words × 2 distances), at the clause cap
EXPLOIT = " OR ".join(f"({w} NEAR/{k} {w})" for w in ("a", "the", "model", "4o") for k in (50, 49))
# review queries whose position checks read far less (one verified clause each, or none)
NORMAL = ("trust NEAR/5 model", '"trust calibrat*"', "trust NEAR/5 model*", '"large language model*"')
SCALED = 200_000 * 5_000 // 80_000


def refused_fast(c: TestClient) -> None:
    engine = c.app.state.index.engine  # type: ignore[attr-defined]

    def never(*_a: object) -> object:
        pytest.fail("the exploit reached verification")

    read, engine.read = engine.read, never
    try:
        started = time.perf_counter()
        r = c.get(SEARCH, params={"q": EXPLOIT})
        elapsed = time.perf_counter() - started
    finally:
        engine.read = read
    assert r.status_code == 422 and r.json()["error"]["code"] == "API_QUERY_TOO_COSTLY", r.text
    assert len(r.json()["error"]["diagnostics"]) == 8
    assert elapsed < 1.0, elapsed  # counted from the inverted index, not verified


def served(c: TestClient) -> None:
    for q in NORMAL:
        assert c.get(SEARCH, params={"q": q}).status_code == 200, q
    for name, q in STRINGS.items():  # no Trust-Evals string is refused for its verification cost
        if not q.strip():
            continue
        for mode in ("native", "scholar"):
            r = c.get(SEARCH, params={"q": q, "mode": mode})
            code = r.json()["error"]["code"] if r.status_code != 200 else None
            assert code != "API_QUERY_TOO_COSTLY", (name, mode, r.text[:300])


def test_the_exploit_is_refused_and_review_queries_served_at_the_scaled_ceiling(store: Store) -> None:
    with TestClient(make_app(store.indexes.parent, max_verification_candidates=SCALED)) as c:
        refused_fast(c)
        served(c)


@pytest.mark.skipif(os.environ.get("OP_BENCH_80K") != "1", reason="builds an 80k index: set OP_BENCH_80K=1")
def test_the_exploit_is_refused_and_review_queries_served_at_80k(tmp_path: Path) -> None:
    version = build(list(records(80_000, (120, 250))), tmp_path / "snapshots", "big", tmp_path / "indexes")
    (tmp_path / "indexes" / "current").symlink_to(version)
    assert ApiConfig(data_dir=tmp_path).max_verification_candidates == 200_000  # the default, as served
    with TestClient(make_app(tmp_path)) as c:
        refused_fast(c)
        served(c)
