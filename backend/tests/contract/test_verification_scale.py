"""The verification limits against the round-3 exploit and the user's real review queries (M3a review gate;
decision-010), at scale.

The exploit: 8 clauses, each a word NEAR itself, so every document holding the word is a candidate in each
field. On the synthetic 80k index it held the only verification slot for 63 s (each clause ~3.2 s a field),
so every other verified query got `API_BUSY`. The candidate ceiling (`max_verification_candidates`, default
300,000 at ~40 µs a candidate: ~12 s) refuses it (686,684) before anything is verified. The clause cap
(`max_verified_clauses`, default 16) is only a backstop: every published Trust-Evals string must be served,
in both modes, the heaviest being `main-2-pop` in Scholar mode (10 verified clauses; 247,793 candidates and
10.2 s of cold verification on the synthetic 80k index).

In CI the 5k fixture stands in for 80k with the candidate ceiling scaled by the same factor (5k/80k: 18,750):
the fixture's text is the 80k corpus's generator at the same word frequencies, so each count scales with the
index. The real 80k run is opt-in (`OP_BENCH_80K=1`: it builds an 80k index in a temporary directory, ~40 s)
and runs the true defaults.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from openproceedings.api.config import ApiConfig
from openproceedings.query.parser import parse

from tests.contract.conftest import Store, build, make_app
from tests.fixtures.corpus.synthetic_5k import records
from tests.golden.test_trust_evals import STRINGS

SEARCH = "/api/v1/search"
DEFAULT_CEILING = ApiConfig(data_dir=Path("x")).max_verification_candidates
SCALED = DEFAULT_CEILING * 5_000 // 80_000
# the reviewer's shape: 8 self-NEARs of common words (4 words × 2 distances)
EXPLOIT = " OR ".join(f"({w} NEAR/{k} {w})" for w in ("a", "the", "model", "4o") for k in (50, 49))
# the same shape at the new clause cap: 16 self-NEARs
EXPLOIT_16 = " OR ".join(f"({w} NEAR/{k} {w})" for w in ("a", "the", "model", "4o") for k in (50, 49, 48, 47))
# review queries whose position checks read far less (one verified clause each, or none)
NORMAL = ("trust NEAR/5 model", '"trust calibrat*"', "trust NEAR/5 model*", '"large language model*"')


def wide(width: int, stem: str) -> str:
    return '"' + " ".join([stem] * width) + '"'


def cold_ms(c: TestClient, q: str) -> float:
    """A served query's cold verification time, from its access line's `verify_ms` (the slot time)."""
    engine = c.app.state.index.engine  # type: ignore[attr-defined]
    engine.verified.clear()
    engine.compiled.clear()
    engine.faceted.clear()
    started = time.perf_counter()
    r = c.get(SEARCH, params={"q": q})
    assert r.status_code == 200, r.text[:300]
    return (time.perf_counter() - started) * 1000


def width_is_free(c: TestClient, stem: str, widths: tuple[int, ...]) -> dict[int, float]:
    """Round 4: a wildcard phrase's cold time doesn't grow with its width (its candidates don't, and the
    token sets are built once per clause); each width is admitted and served. Before, a 300-item `rel*`
    phrase took 84 s at 80k against 3.8 s for 2 items, all admitted as one clause."""
    times = {w: cold_ms(c, wide(w, stem)) for w in widths}
    narrow = times[widths[0]]
    assert all(t < 2 * narrow + 500 for t in times.values()), times
    return times


def refused_fast(c: TestClient, q: str, clauses: int) -> None:
    engine = c.app.state.index.engine  # type: ignore[attr-defined]

    def never(*_a: object) -> object:
        pytest.fail("the exploit reached verification")

    read, engine.read = engine.read, never
    try:
        started = time.perf_counter()
        r = c.get(SEARCH, params={"q": q})
        elapsed = time.perf_counter() - started
    finally:
        engine.read = read
    assert r.status_code == 422 and r.json()["error"]["code"] == "API_QUERY_TOO_COSTLY", r.text
    assert len(r.json()["error"]["diagnostics"]) == clauses
    assert elapsed < 1.0, elapsed  # counted from the inverted index, not verified


def every_trust_evals_string_is_served(c: TestClient) -> None:
    """Every published Trust-Evals string, in both modes, is a 200. The one exception is a string that doesn't
    parse in a mode (main-2-pop's `AI$` in native mode): the query language refuses that, never the API's
    limits, so it is the parse's own 422."""
    served = 0
    for name, q in STRINGS.items():
        if not q.strip():
            continue
        for mode in ("native", "scholar"):
            r = c.get(SEARCH, params={"q": q, "mode": mode})
            errors = parse(q, mode).errors
            if errors:
                assert (r.status_code, r.json()["error"]["code"]) == (422, errors[0].code), (name, mode)
            else:
                assert r.status_code == 200, (name, mode, r.text[:300])
                served += 1
    assert served >= len([q for q in STRINGS.values() if q.strip()])  # at least one mode of each


def test_the_exploit_is_refused_and_every_review_query_served_at_the_scaled_ceiling(store: Store) -> None:
    with TestClient(make_app(store.indexes.parent, max_verification_candidates=SCALED)) as c:
        refused_fast(c, EXPLOIT, 8)
        refused_fast(c, EXPLOIT_16, 16)
        for q in NORMAL:
            assert c.get(SEARCH, params={"q": q}).status_code == 200, q
        every_trust_evals_string_is_served(c)
        width_is_free(c, "tru*", (2, 20, 100, 300))


def test_main_2_pop_needs_more_than_the_old_cap_of_8() -> None:
    """Why the clause cap is 16 (decision-010): the heaviest real string has 10 verified clauses."""
    from openproceedings.engine.compile import verified_clauses

    assert len(verified_clauses(parse(STRINGS["main-2-pop"], "scholar").effective_ast)) == 10


@pytest.mark.skipif(os.environ.get("OP_BENCH_80K") != "1", reason="builds an 80k index: set OP_BENCH_80K=1")
def test_the_exploit_is_refused_and_every_review_query_served_at_80k(tmp_path: Path) -> None:
    version = build(list(records(80_000, (120, 250))), tmp_path / "snapshots", "big", tmp_path / "indexes")
    (tmp_path / "indexes" / "current").symlink_to(version)
    config = ApiConfig(data_dir=tmp_path)
    assert (config.max_verified_clauses, config.max_verification_candidates) == (16, 300_000)  # the defaults
    with TestClient(make_app(tmp_path)) as c:
        refused_fast(c, EXPLOIT, 8)
        refused_fast(c, EXPLOIT_16, 16)
        for q in NORMAL:
            assert c.get(SEARCH, params={"q": q}).status_code == 200, q
        every_trust_evals_string_is_served(c)
        width_is_free(c, "rel*", (2, 20, 100, 200, 300))
