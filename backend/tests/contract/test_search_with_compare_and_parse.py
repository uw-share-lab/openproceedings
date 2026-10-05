"""`/search` with its group counts (TASK-176), `/compare` (TASK-177) and `/parse` with its `word_forms`
(TASK-175) at once on one served engine: the batch's three features share its `compiled`, `verified` and
`faceted` memos, and each answer must be the one it gives alone (task-080's rules: a memo cleared under a
request costs a recomputation, never a different answer)."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from openproceedings.engine.tantivy_engine import TantivyEngine
from openproceedings.query.parser import parse
from openproceedings.search import run

from tests.contract.test_compare import app_of, corpus_dir, the_file
from tests.contract.test_compare import post as compare_post
from tests.contract.test_search import SEARCH

__all__ = ["corpus_dir"]  # the comparison corpus fixture, shared with test_compare.py

PARSE = "/api/v1/parse"
Q = '("language model$" OR trust*) AND (benchmark OR evaluation) NOT survey'


def answered(r: Any) -> Any:
    assert r.status_code == 200, r.text
    return r


def test_search_with_groups_a_comparison_and_a_parse_at_once_each_give_their_solo_answer(
    corpus_dir: Path,
) -> None:
    """Two threads searching (with group counts), one comparing and one parsing, while another clears the
    served engine's memos as a busy instance trims them. Each search's ids, scores, facets and `excluded` are
    those of a plain `run` on a second engine nothing else touches, every comparison's the solo one (its
    `total` that search's), every parse the solo bytes (`word_forms` included); group counts, when given, the
    solo ones, and otherwise `busy` or `timed_out`."""
    # a slot for each thread's cold verifications (a cleared `verified` makes every one cold): the default one
    # slot answers the others 503 API_BUSY at once, which is that limit's contract, not this test's
    with app_of(corpus_dir, verification_slots=8) as c:
        served = c.app.state.index.served.engine  # type: ignore[attr-defined]
        apart = TantivyEngine(corpus_dir / "indexes" / served.index_version)
        plain = run(apart, parse(Q), limit=200, facets=True)
        assert plain.total > 0 and plain.facets is not None

        def searched() -> dict[str, Any]:
            return dict(answered(c.get(SEARCH, params={"q": Q, "limit": 200})).json())

        def compared() -> dict[str, Any]:
            return dict(answered(compare_post(c, the_file(), Q)).json())

        def parsed() -> bytes:
            return bytes(answered(c.post(PARSE, json={"q": Q, "mode": "scholar"})).content)

        solo_search, solo_compare, solo_parse = searched(), compared(), parsed()
        assert solo_search["groups"]["not_counted"] is None and len(solo_search["groups"]["counts"]) == 2
        assert solo_compare["total"] == plain.total and b'"word_forms"' in solo_parse
        searches: list[dict[str, Any]] = []
        compares: list[dict[str, Any]] = []
        parses: list[bytes] = []
        errors: list[BaseException] = []
        stop = threading.Event()

        def repeat[T](job: Callable[[], T], n: int, into: list[T]) -> Callable[[], None]:
            def body() -> None:
                try:
                    for _ in range(n):
                        into.append(job())
                except BaseException as e:  # reported below, in the test's thread
                    errors.append(e)

            return body

        def trimming() -> None:
            while not stop.is_set():
                served.compiled.clear(), served.faceted.clear(), served.verified.clear()
                time.sleep(0.002)

        trimmer = threading.Thread(target=trimming)
        threads = [
            threading.Thread(target=repeat(searched, 10, searches)),
            threading.Thread(target=repeat(searched, 10, searches)),
            threading.Thread(target=repeat(compared, 3, compares)),
            threading.Thread(target=repeat(parsed, 20, parses)),
        ]
        trimmer.start()
        for t in threads:
            t.start()
        for t in threads:
            t.join(300)
        stop.set()
        trimmer.join()
    assert errors == [] and (len(searches), len(compares), len(parses)) == (20, 3, 20)
    for got in searches:
        assert got["total"] == plain.total
        assert [(h["id"], h["score"]) for h in got["hits"]] == [(h.id, h.score) for h in plain.hits]
        assert got["facets"] == plain.facets and got["excluded"] == plain.excluded.to_json()
        if got["groups"]["not_counted"] is None:
            assert got["groups"] == solo_search["groups"]
        else:
            assert got["groups"]["not_counted"] in ("busy", "timed_out")
    assert all(got == solo_compare for got in compares)
    assert all(got == solo_parse for got in parses)
