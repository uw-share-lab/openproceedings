"""Rate-limit findings of the M3a review gate, round 6: a client that honours Retry-After after a refused
per-clause charge is admitted on its next try, and only debt still owed keeps a bucket from eviction."""

from __future__ import annotations

from typing import Any

import pytest
from openproceedings.api.errors import ApiError
from openproceedings.api.middleware import BUCKETS, TokenBucket, charge, take_all


def test_a_client_that_honours_retry_after_is_admitted_on_its_next_try() -> None:
    now = [0.0]
    client = TokenBucket(10, 1.0, 100, clock=lambda: now[0])
    network = TokenBucket(40, 4.0, 100, clock=lambda: now[0])
    held = [(client, "c"), (network, "n")]
    assert take_all(held, 9) == 0  # the client has 1 token left
    assert take_all(held, 1) == 0  # the middleware's weight, then the query's up-front verified charge:
    scope: dict[str, Any] = {BUCKETS: (held, 1.0, 1.0)}
    with pytest.raises(ApiError) as refused:
        charge(scope, 6.0)
    now[0] += float(refused.value.headers["Retry-After"])  # the client waits exactly as told
    assert take_all(held, 1) == 0  # and on its next try the weight and the whole charge both fit
    charge({BUCKETS: (held, 1.0, 1.0)}, 6.0)


def test_the_first_retry_after_covers_the_whole_cost_not_the_shortfall() -> None:
    now = [0.0]
    client = TokenBucket(10, 1.0, 100, clock=lambda: now[0])
    held = [(client, "c")]
    assert take_all(held, 10) == 0  # empty
    now[0] += 1.0
    assert take_all(held, 1) == 0  # the middleware's weight: 0 left
    with pytest.raises(ApiError) as refused:
        charge({BUCKETS: (held, 1.0, 1.0)}, 6.0)
    assert refused.value.headers["Retry-After"] == "6"  # the retry pays 1 again, then 5 more


def test_a_repaid_debt_does_not_protect_a_bucket_from_eviction() -> None:
    now = [0.0]
    bucket = TokenBucket(10, 1.0, 2, clock=lambda: now[0])
    bucket.debit("repaid", 15)  # -5
    now[0] += 100.0  # repaid long ago (refill 1 a second), though never touched since
    bucket.take("b", 1)
    bucket.take("c", 1)  # over max_clients: the oldest not still owing goes, and that is `repaid`
    assert "repaid" not in bucket._buckets


def test_a_debt_still_owed_keeps_protecting_its_bucket() -> None:
    now = [0.0]
    bucket = TokenBucket(10, 1.0, 2, clock=lambda: now[0])
    bucket.debit("owing", 115)  # -105
    now[0] += 100.0  # still -5
    bucket.take("b", 1)
    bucket.take("c", 1)
    assert "owing" in bucket._buckets and "b" not in bucket._buckets
