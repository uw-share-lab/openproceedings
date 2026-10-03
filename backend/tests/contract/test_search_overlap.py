"""A cold position-verified `/search` with one verification slot (the default) is never refused against itself
now that its facets are counted on a worker thread (task-088; M3a review gate round 2): `search.run` compiles
the effective tree, verifying each clause in the request's own thread, before the worker starts, and the
worker's facet tree (the same clauses, less its top-level filters) finds them verified. Verification is slowed
here so that a worker which verified on its own would overlap the page's and be refused (503 `API_BUSY`)."""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest
from fastapi.testclient import TestClient
from openproceedings.query.parser import parse

from tests.contract.conftest import Store, make_app

SEARCH = "/api/v1/search"
# position-verified (a wildcard phrase, a term NEAR itself), each with defaults inserted, so the facet
# tree (without the default filters) differs from the effective tree
COLD = ['"trust calibrat*"', "trust NEAR/3 trust", '"calibrat* model" year:2020..2024 OR "language model*"']


@pytest.mark.parametrize("q", COLD)
def test_a_cold_verified_search_takes_one_slot_and_is_served(store: Store, q: str) -> None:
    with TestClient(make_app(store.indexes.parent, verification_slots=1)) as c:
        engine = c.app.state.index.engine  # type: ignore[attr-defined]
        read, gate = engine.read, engine.verification_gate
        threads: list[str] = []

        def slow(*args: Any) -> Any:
            time.sleep(0.2)  # a worker verifying too would be inside this window, and refused
            return read(*args)

        @contextmanager
        def counted() -> Iterator[None]:
            threads.append(threading.current_thread().name)
            with gate():
                yield

        engine.read, engine.verification_gate = slow, counted
        try:
            r = c.get(SEARCH, params={"q": q})
        finally:
            engine.read, engine.verification_gate = read, gate
        assert r.status_code == 200, r.text
        assert threads and len(set(threads)) == 1  # every cold clause verified in one thread, the request's
        assert not any(name.startswith("op-facets") for name in threads)
        ast = parse(q).effective_ast
        assert ast is not None
        assert r.json()["facets"] == engine.facets(ast)  # the worker's counts are the engine's
