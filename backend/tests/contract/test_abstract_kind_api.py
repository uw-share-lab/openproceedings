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
    return r


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
