"""`GET /api/v1/search`'s `abstract_source` (TASK-134; decision-018): each hit names where its abstract came
from (the claim's `source`, the publishing site `origin`) and links to that page, from what the served
snapshot's reader computed at load (spec 04 §SearchResponse)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from openproceedings.api.search import page_attributions
from openproceedings.diagnostics import InternalError
from openproceedings.ingest.dedup import Attribution

from tests.contract.conftest import Store, attributed, build, make_app
from tests.fixtures.corpus.synthetic_5k import records

SEARCH = "/api/v1/search"
QUERIES = ["trust", "trust AND calibrat*"]
EVERY = "status:(accepted OR rejected OR withdrawn OR unknown)"
PAGE_HOST = {
    "pmlr": "https://proceedings.mlr.press/",
    "neurips_proceedings": "https://proceedings.neurips.cc/",
    "iclr_proceedings": "https://proceedings.iclr.cc/",
}


@pytest.fixture(scope="module")
def client(tmp_path_factory: pytest.TempPathFactory) -> Iterator[TestClient]:
    """The app over every 3rd fixture record as `attributed` makes it (all three venues, some abstracts
    missing, some also claimed by `ris`, some claimed by `ris` alone)."""
    data = tmp_path_factory.mktemp("attributed") / "data"
    version = build(list(records())[::3], data / "snapshots", "attributed", data / "indexes", attributed)
    (data / "indexes" / "current").symlink_to(version)
    with TestClient(make_app(data)) as c:
        yield c


def hits(client: TestClient, q: str) -> list[dict[str, Any]]:
    r = client.get(SEARCH, params={"q": q, "limit": 200})
    assert r.status_code == 200, r.text
    found: list[dict[str, Any]] = r.json()["hits"]
    return found


def every_venue(client: TestClient) -> list[dict[str, Any]]:
    """200 hits of each venue (a page sorted by id alone would hold only the first venues)."""
    return [h for v in ("ICLR", "ICML", "NeurIPS") for h in hits(client, f"{EVERY} venue:{v}")]


def expected(h: dict[str, Any]) -> dict[str, Any]:
    """What `attributed` gave the hit, from its own urls: a direct claim, or `ris` naming its route."""
    if h["urls"]["forum"] is not None:
        origin, url = "openreview", h["urls"]["forum"]  # the forum, never the API listing
    else:
        url = h["urls"]["proceedings"]
        origin = next(o for o, host in PAGE_HOST.items() if url.startswith(host))
    direct = {"openreview": "openreview_v2", "pmlr": "pmlr", "neurips_proceedings": "neurips_proceedings"}
    ris_only = h["abstract_source"]["source"] == "ris"
    return {"source": "ris" if ris_only else direct[origin], "origin": origin, "url": url}


@pytest.mark.parametrize("q", [*QUERIES, EVERY])
def test_every_abstract_is_attributed_to_its_site_and_page(client: TestClient, q: str) -> None:
    page = every_venue(client) if q == EVERY else hits(client, q)
    assert {h["venue"] for h in page} == {"ICLR", "ICML", "NeurIPS"}, "the page covers every source"
    for h in page:
        if h["abstract"] is None:
            assert h["abstract_source"] is None
        else:
            assert h["abstract_source"] == expected(h), h["id"]


def test_an_abstract_that_came_through_ris_names_its_real_origin_and_links_it(client: TestClient) -> None:
    """Most served abstracts are `ris` claims (the Google Scholar bootstrap): the claim's evidence names the
    proceedings page or the OpenReview API it came from, so the hit names that site and links its page."""
    via = [h for h in every_venue(client) if (h["abstract_source"] or {}).get("source") == "ris"]
    origins = {h["abstract_source"]["origin"] for h in via}
    assert origins == {"neurips_proceedings", "iclr_proceedings", "pmlr", "openreview"}
    assert all(h["abstract_source"]["url"] for h in via)


def test_a_pmlr_abstract_links_to_its_pmlr_page(client: TestClient) -> None:
    """PMLR's CC BY 4.0 terms: a citation (the hit's title, authors, venue and year) and a link to PMLR."""
    pmlr = [h for h in every_venue(client) if (h["abstract_source"] or {}).get("origin") == "pmlr"]
    assert pmlr
    for h in pmlr:
        assert h["abstract_source"]["url"].startswith(PAGE_HOST["pmlr"])
        assert h["authors"] and h["title"] and h["venue"] == "ICML" and h["year"]


@pytest.fixture
def store_client(store: Store) -> Iterator[TestClient]:
    with TestClient(make_app(store.indexes.parent)) as c:
        yield c


def test_a_hit_without_a_claim_for_its_abstract_names_no_source(store_client: TestClient) -> None:
    """The 5k contract corpus has no abstract claims: `abstract_source` is sent, and null, never guessed."""
    page = hits(store_client, "trust")
    assert page and any(h["abstract"] is not None for h in page)
    assert all("abstract_source" in h and h["abstract_source"] is None for h in page)


class _Records:
    def __init__(self, attributions: dict[str, Attribution | None]) -> None:
        self.attributions = attributions


def test_page_attributions_is_a_lookup_and_a_missing_record_is_an_internal_error() -> None:
    known = Attribution("ris", None, None)
    got = page_attributions(_Records({"a": known, "b": None}), ["a", "b"])  # type: ignore[arg-type]
    assert got["b"] is None
    assert got["a"] is not None and (got["a"].source, got["a"].origin, got["a"].url) == ("ris", None, None)
    with pytest.raises(InternalError, match="missing from its snapshot"):
        page_attributions(_Records({}), ["op:iclr:2024:AbCdEf123"])  # type: ignore[arg-type]
