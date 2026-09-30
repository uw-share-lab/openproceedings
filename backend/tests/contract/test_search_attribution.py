"""`GET /api/v1/search`'s `abstract_source` (TASK-134; decision-018): each hit names where its abstract came
from and links to that page, read from the served snapshot's provenance (spec 04 §SearchResponse)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from openproceedings.api.search import abstract_source, page_records
from openproceedings.diagnostics import InternalError
from openproceedings.ingest.record import Claim, PaperRecord, Urls

from tests.contract.conftest import Store, attributed, build, make_app
from tests.fixtures.corpus.synthetic_5k import records
from tests.unit.engine.test_exclusions import BUILT

SEARCH = "/api/v1/search"
QUERIES = ["trust", "trust AND calibrat*", "status:(accepted OR rejected OR withdrawn OR unknown)"]


@pytest.fixture(scope="module")
def client(tmp_path_factory: pytest.TempPathFactory) -> Iterator[TestClient]:
    """The app over every 5th fixture record as `attributed` makes it (all three venues, some abstracts
    missing, some abstracts also claimed by `ris`)."""
    data = tmp_path_factory.mktemp("attributed") / "data"
    version = build(list(records())[::5], data / "snapshots", "attributed", data / "indexes", attributed)
    (data / "indexes" / "current").symlink_to(version)
    with TestClient(make_app(data)) as c:
        yield c


def hits(client: TestClient, q: str) -> list[dict[str, Any]]:
    r = client.get(SEARCH, params={"q": q, "limit": 200})
    assert r.status_code == 200, r.text
    found: list[dict[str, Any]] = r.json()["hits"]
    return found


@pytest.mark.parametrize("q", QUERIES)
def test_every_abstract_is_attributed_to_its_source_page(client: TestClient, q: str) -> None:
    page = hits(client, q)
    assert {h["venue"] for h in page} == {"ICLR", "ICML", "NeurIPS"}, "the page covers every source"
    for h in page:
        if h["abstract"] is None:
            assert h["abstract_source"] is None
            continue
        expected = {
            "ICML": {"source": "pmlr", "url": h["urls"]["proceedings"]},
            # the forum, never the API listing the claim was read from
            "ICLR": {"source": "openreview_v2", "url": h["urls"]["forum"]},
            "NeurIPS": {"source": "neurips_proceedings", "url": h["urls"]["proceedings"]},
        }[h["venue"]]
        assert h["abstract_source"] == expected, h["id"]
        assert expected["url"] is not None


def test_a_pmlr_abstract_links_to_its_pmlr_page(client: TestClient) -> None:
    """PMLR's CC BY 4.0 terms: a citation (the hit's title, authors, venue and year) and a link to PMLR."""
    pmlr = [
        h
        for h in hits(client, QUERIES[2])
        if h["abstract_source"] and h["abstract_source"]["source"] == "pmlr"
    ]
    assert pmlr
    for h in pmlr:
        assert h["abstract_source"]["url"].startswith("https://proceedings.mlr.press/")
        assert h["authors"] and h["title"] and h["venue"] == "ICML" and h["year"]


def test_a_hit_without_a_claim_for_its_abstract_names_no_source(store_client: TestClient) -> None:
    """The 5k contract corpus has no abstract claims: `abstract_source` is sent, and null, never guessed."""
    page = hits(store_client, "trust")
    assert page and any(h["abstract"] is not None for h in page)
    assert all("abstract_source" in h and h["abstract_source"] is None for h in page)


@pytest.fixture
def store_client(store: Store) -> Iterator[TestClient]:
    with TestClient(make_app(store.indexes.parent)) as c:
        yield c


def _record(*claims: Claim, forum: str | None = None, abstract: str | None = "An abstract.") -> PaperRecord:
    return PaperRecord.build(
        id="op:iclr:2024:AbCdEf123", title="Trust in AI", abstract=abstract, authors=("Ada Okafor",),
        venue="ICLR", year=2024, track="main", status="accepted", urls=Urls(forum=forum), provenance=claims,
    )  # fmt: skip


def test_abstract_source_rules() -> None:
    api = "https://api2.openreview.net/notes?offset=0"
    forum = "https://openreview.net/forum?id=AbCdEf123"
    orv = Claim(field="abstract", value="An abstract.", source="openreview_v1", url=api, fetched_at=BUILT)
    ris = Claim(field="abstract", value="An abstract.", source="ris", fetched_at=BUILT)
    got = abstract_source(_record(orv, ris, forum=forum))
    assert got is not None and (got.source, got.url) == ("openreview_v1", forum)
    got = abstract_source(_record(ris, forum=forum))
    assert got is not None and (got.source, got.url) == ("ris", None)  # RIS has no page to link
    got = abstract_source(_record(orv, forum=None))  # a record without a forum: nothing to link
    assert got is not None and (got.source, got.url) == ("openreview_v1", None)
    assert abstract_source(_record(orv, abstract=None)) is None


def test_a_page_record_the_snapshot_lacks_is_an_internal_error() -> None:
    class Records:
        def get_many(self, ids: list[str]) -> dict[str, PaperRecord]:
            return {}

    with pytest.raises(InternalError, match="missing from its snapshot"):
        page_records(Records(), ["op:iclr:2024:AbCdEf123"])  # type: ignore[arg-type]

    class Gone:
        def get_many(self, ids: list[str]) -> dict[str, PaperRecord]:
            raise FileNotFoundError(Path("records.jsonl"))

    with pytest.raises(InternalError, match="unreadable"):
        page_records(Gone(), ["op:iclr:2024:AbCdEf123"])  # type: ignore[arg-type]
