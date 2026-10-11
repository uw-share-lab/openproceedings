"""`abstract_kind` through the API (spec 04; decision-049). Uses the contract suite's app builder (`build`,
`point_current`, `make_app` from tests/contract/conftest.py) over the abstract-kinds corpus."""

import csv
import io
import json
from pathlib import Path

from fastapi.testclient import TestClient
from openproceedings.ingest.record import PaperRecord

from tests.contract.conftest import build, make_app, point_current
from tests.fixtures.corpus import abstract_kinds

CORPUS = abstract_kinds.records()
PLAIN = [r for r in CORPUS if r.abstract_kind != "openalex"]  # what a schema-3 index may hold


def _paper(r: PaperRecord) -> PaperRecord:
    return r  # `build`'s default converts a corpus `Rec`; these records are already snapshot records


def _app(tmp_path: Path, schema: str | None = None, corpus: list[PaperRecord] = CORPUS):
    data = tmp_path / "data"
    version = build(corpus, data / "snapshots", "snap", data / "indexes", paper=_paper, schema_version=schema)
    point_current(data, version)
    return make_app(data), version


def test_hits_facets_and_meta_carry_the_kind(tmp_path: Path) -> None:
    app, _ = _app(tmp_path)
    with TestClient(app) as client:
        body = client.get("/api/v1/search", params={"q": "abstract_kind:openalex"}).json()
        assert body["total"] > 0 and {h["abstract_kind"] for h in body["hits"]} == {"openalex"}
        assert set(body["facets"]["abstract_kind"]) == {"official", "openalex", "none"}  # disjunctive
        assert client.get("/api/v1/meta").json()["values"]["abstract_kind"] == [
            "official",
            "openalex",
            "none",
        ]
        rid = body["hits"][0]["id"]
        paper = client.get(f"/api/v1/papers/{rid}").json()
        assert paper["paper"]["abstract_kind"] == "openalex"


def test_search_naming_abstract_kind_on_a_schema_3_index_is_422(tmp_path: Path) -> None:
    app, version = _app(tmp_path, "3", PLAIN)
    with TestClient(app) as client:
        got = client.get("/api/v1/search", params={"q": "trust abstract_kind:official"})
    assert got.status_code == 422, got.text
    assert got.json()["error"]["code"] == "FIELD_NOT_INDEXED", got.text
    assert version in got.json()["error"]["message"]


def test_meta_advertises_only_the_filter_fields_the_served_index_holds(tmp_path: Path) -> None:
    """Gate C round 1: autocomplete reads `/meta`'s `filter_fields`, so a served schema-3 index never offers
    `abstract_kind:`, which every route would refuse; `values` stays the grammar's vocabulary."""
    for schema, fields in (("3", ["venue", "year", "track", "status"]), (None, ["venue", "year", "track", "status",
                                                                                "abstract_kind"])):  # fmt: skip
        app, _ = _app(tmp_path / (schema or "4"), schema, PLAIN)
        with TestClient(app) as client:
            meta = client.get("/api/v1/meta").json()
        assert meta["filter_fields"] == fields
        assert meta["values"]["abstract_kind"] == ["official", "openalex", "none"]


def test_schema_3_facets_say_abstract_kind_null(tmp_path: Path) -> None:
    app, _ = _app(tmp_path, "3", PLAIN)
    with TestClient(app) as client:
        body = client.get("/api/v1/search", params={"q": "trust"}).json()
    assert body["facets"]["abstract_kind"] is None
    assert body["hits"] and {h["abstract_kind"] for h in body["hits"]} <= {"official", "none"}


def test_a_pinned_schema_3_export_naming_abstract_kind_is_422(tmp_path: Path) -> None:
    data = tmp_path / "data"
    old = build(PLAIN, data / "snapshots", "snap", data / "indexes", paper=_paper, schema_version="3")
    new = build(CORPUS, data / "snapshots", "snap2", data / "indexes", paper=_paper)
    point_current(data, new)
    with TestClient(make_app(data)) as client:
        got = client.get(
            "/api/v1/export", params={"q": "abstract_kind:none", "format": "csv", "index_version": old}
        )
    assert got.status_code == 422, got.text
    assert got.json()["error"]["code"] == "FIELD_NOT_INDEXED", got.text


def test_csv_and_jsonl_carry_the_kind_last(tmp_path: Path) -> None:
    app, _ = _app(tmp_path)
    with TestClient(app) as client:
        params = {"q": "abstract_kind:openalex"}
        text = client.get("/api/v1/export", params={**params, "format": "csv"}).text
        lines = client.get("/api/v1/export", params={**params, "format": "jsonl"}).text
        ris = client.get("/api/v1/export", params={**params, "format": "ris"}).text
    rows = list(csv.reader(io.StringIO(text.removeprefix("﻿"))))
    assert rows[0][-1] == "abstract_kind" and {r[-1] for r in rows[1:]} == {"openalex"}
    assert {r[rows[0].index("abstract_source")] for r in rows[1:]} == {"openalex"}  # the claim source column
    assert {json.loads(x)["abstract_kind"] for x in lines.splitlines() if x} == {"openalex"}
    assert "N1  - Abstract source: OpenAlex" in ris


def test_a_takedown_on_an_openalex_record_makes_its_kind_none_everywhere(tmp_path: Path) -> None:
    """A withheld abstract is `none` in a hit, the paper and both exports (never the stored `openalex`)."""
    data = tmp_path / "data"
    version = build(CORPUS, data / "snapshots", "snap", data / "indexes", paper=_paper)
    point_current(data, version)
    target = next(r for r in CORPUS if r.abstract_kind == "openalex")
    (data / "takedowns").mkdir()
    (data / "takedowns" / "withheld.txt").write_text(f"{target.id}  # logged\n", encoding="utf-8")
    with TestClient(make_app(data)) as client:
        hits = client.get("/api/v1/search", params={"q": "abstract_kind:openalex"}).json()["hits"]
        hit = next(h for h in hits if h["id"] == target.id)
        assert hit["abstract_withheld"] is True and hit["abstract_kind"] == "none"
        assert client.get(f"/api/v1/papers/{target.id}").json()["paper"]["abstract_kind"] == "none"
        params = {"q": "abstract_kind:openalex"}
        text = client.get("/api/v1/export", params={**params, "format": "csv"}).text
        lines = client.get("/api/v1/export", params={**params, "format": "jsonl"}).text
    rows = list(csv.DictReader(io.StringIO(text.removeprefix("\ufeff"))))
    by_id = {r["id"]: r["abstract_kind"] for r in rows}
    assert by_id[target.id] == "none" and "openalex" in by_id.values()  # the others keep theirs
    objs = {o["id"]: o for o in map(json.loads, filter(None, lines.splitlines()))}
    assert objs[target.id]["abstract_kind"] == "none" and objs[target.id]["abstract"] is None


def test_a_record_names_how_many_of_its_own_ids_have_an_openalex_abstract(tmp_path: Path) -> None:
    """Gate C round 2 (ruling 2): `openalex_abstracts` is derived from the record's saved ids on its own index,
    never stored and never from a search response; the same with and without a replay."""
    app, _ = _app(tmp_path)
    with TestClient(app) as client:
        made = client.post("/api/v1/records", json={"q": "paper venue:(AAAI OR AIES)"})
        assert made.status_code == 201, made.text
        rid = made.json()["record_id"]
        replayed = client.get(f"/api/v1/records/{rid}", params={"include": "ids"}).json()
        stored = client.get(f"/api/v1/records/{rid}", params={"replay": "false"}).json()
    kinds = {r.id: r.abstract_kind for r in CORPUS}
    want = sum(kinds[i] == "openalex" for i in replayed["record"]["ids"])
    assert 0 < want < replayed["record"]["total"]  # some, not all: a count of the ids, not of the facet
    assert replayed["openalex_abstracts"] == want
    assert stored["openalex_abstracts"] == want


def test_a_record_on_a_schema_3_index_has_no_openalex_count(tmp_path: Path) -> None:
    app, _ = _app(tmp_path, "3", PLAIN)
    with TestClient(app) as client:
        rid = client.post("/api/v1/records", json={"q": "paper"}).json()["record_id"]
        for params in ({}, {"replay": "false"}):
            body = client.get(f"/api/v1/records/{rid}", params=params).json()
            assert body["openalex_abstracts"] is None, body
