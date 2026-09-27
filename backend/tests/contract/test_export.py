"""`GET /api/v1/export` (task-036; spec 04 §Exports): `op export`'s bytes for the same query and index, the
whole matched set in id order, `X-Total` (= `/search`'s `total`) and `X-Index-Version`, the media type and
filename, every format round-tripped to its ids by an independent parser (scholarmend for RIS, the pinned
refaudit for BibTeX), a pinned `index_version` served from that index (409 when this instance lacks it),
every refusal before the first byte, a stream that finishes on its index across a hot swap, and a failure
mid-stream logged as aborted with no query text anywhere."""

from __future__ import annotations

import csv
import io
import json
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, get_args

import pytest
from fastapi.testclient import TestClient
from openproceedings import cli
from openproceedings import export as exporter
from openproceedings.api import export as route
from openproceedings.api.state import IndexState
from openproceedings.engine.protocol import EngineInternalError
from openproceedings.engine.tantivy_engine import TantivyEngine
from openproceedings.query.parser import parse
from refaudit.bibtex import parse_string
from scholarmend.parse import parse_ris

from tests.contract.conftest import SECRET, Store, make_app, point_current

EXPORT = "/api/v1/export"
DATE = "2026-09-27"
QUERIES = [
    "trust",
    "trust AND calibrat*",
    '"language model" OR benchmark* NOT venue:ICLR',
    "agents track:workshop",
]
FORMATS = get_args(route.ExportFormat)
EVERY_STATUS = "status:(accepted OR rejected OR withdrawn OR desk_rejected OR unknown)"
BROAD = f"agent {EVERY_STATUS}"  # 1,175 of the 5k: well past one body chunk in every format
Logs = Callable[[], list[dict[str, Any]]]


@pytest.fixture(autouse=True)
def fixed_date(monkeypatch: pytest.MonkeyPatch) -> None:
    """One provenance date for the API and `op export` alike (both read `export.utc_date`)."""
    monkeypatch.setattr(exporter, "utc_date", lambda: DATE)
    monkeypatch.setattr(route, "utc_date", lambda: DATE)


def ok(client: TestClient, q: str, fmt: str, **params: Any) -> Any:
    r = client.get(EXPORT, params={"q": q, "format": fmt, **params})
    assert r.status_code == 200, r.text
    return r


def op_export(store: Store, q: str, fmt: str, tmp_path: Path, *extra: str) -> bytes:
    out = tmp_path / f"cli.{fmt}"
    data = str(store.indexes.parent)
    assert cli.main(["--data-dir", data, "export", q, "--format", fmt, "--out", str(out), *extra]) == 0
    return out.read_bytes()


def match_ids(store: Store, version: str, q: str) -> list[str]:
    ast = parse(q).effective_ast
    assert ast is not None
    return sorted(TantivyEngine(store.indexes / version).match_ids(ast))


def ids_of(fmt: str, body: bytes) -> list[str]:
    """The ids an export holds, in file order, read back by a parser that isn't ours where one exists."""
    text = body.decode("utf-8")
    if fmt == "ris":
        return [r.first("ID") for r in parse_ris(text, "export.ris")]
    if fmt == "bibtex":
        return [e.fields["openproceedings_id"] for e in parse_string(text)]
    if fmt == "csv":
        assert text.startswith("﻿")
        return [row["id"] for row in csv.DictReader(io.StringIO(text[1:]))]
    return [json.loads(line)["id"] for line in text.splitlines()]


def error(r: Any, status: int, code: str) -> dict[str, Any]:
    assert r.status_code == status, r.text
    assert r.headers["content-type"] == "application/json"
    assert "x-total" not in r.headers  # refused before the stream: no export headers, no export bytes
    body = r.json()
    assert set(body) == {"error"} and body["error"]["code"] == code
    return body["error"]  # type: ignore[no-any-return]


# --- the API adds transport, not behaviour ----------------------------------------------------------------
@pytest.mark.parametrize("fmt", FORMATS)
@pytest.mark.parametrize("q", QUERIES)
def test_the_body_is_op_exports_bytes(
    client: TestClient, store: Store, tmp_path: Path, q: str, fmt: str
) -> None:
    assert ok(client, q, fmt).content == op_export(store, q, fmt, tmp_path)


def test_the_formats_are_the_exporters() -> None:
    assert set(FORMATS) == set(exporter.FORMATS) == set(route.MEDIA) == set(cli.FORMATS)


# --- AC1/AC2: every format round-trips to its ids, the whole set in id order ------------------------------
@pytest.mark.parametrize("fmt", FORMATS)
def test_every_format_round_trips_to_the_matched_ids_in_id_order(
    client: TestClient, store: Store, fmt: str
) -> None:
    q = BROAD
    r = ok(client, q, fmt)
    expected = match_ids(store, store.big, q)
    assert len(expected) > 1_000 and len(r.content) > 2 * route.CHUNK
    assert ids_of(fmt, r.content) == expected  # every id once, ordered by id, nothing truncated
    assert int(r.headers["x-total"]) == len(expected)


def test_the_bibtex_note_and_ris_n1_carry_the_provenance(client: TestClient, store: Store) -> None:
    q = "trust AND calibrat*"
    line = f"openproceedings {store.big} · query {parse(q).canonical_hash} · {DATE}"
    entries = parse_string(ok(client, q, "bibtex").text)
    assert entries and all(e.entry_type == "inproceedings" and e.fields["note"] == line for e in entries)
    records = parse_ris(ok(client, q, "ris").text, "export.ris")
    assert records and all(r.first("N1") == line for r in records)
    rows = [json.loads(x) for x in ok(client, q, "jsonl").text.splitlines()]
    assert {(x["index_version"], x["canonical_hash"], x["exported_at"]) for x in rows} == {
        (store.big, parse(q).canonical_hash, DATE)
    }


def test_an_empty_match_set_is_an_empty_export(client: TestClient) -> None:
    r = ok(client, "zzznomatchword", "csv")
    assert r.headers["x-total"] == "0"
    assert r.content.decode("utf-8") == exporter.header("csv")  # the BOM and column row, no records
    assert ok(client, "zzznomatchword", "ris").content == b""


# --- AC3: headers, and the pinned index ---------------------------------------------------------------
@pytest.mark.parametrize("fmt", FORMATS)
def test_headers_name_the_set_its_type_and_a_filename(client: TestClient, store: Store, fmt: str) -> None:
    q = "trust AND calibrat*"
    r = ok(client, q, fmt)
    total = client.get("/api/v1/search", params={"q": q, "limit": 0}).json()["total"]
    assert r.headers["x-total"] == str(total) and r.headers["x-index-version"] == store.big
    assert r.headers["content-type"] == route.MEDIA[fmt][0]
    digest = parse(q).canonical_hash
    assert digest is not None
    ext = route.MEDIA[fmt][1]
    assert r.headers["content-disposition"] == (
        f'attachment; filename="openproceedings-{store.big}-{digest[:12]}.{ext}"'
    )


def test_cors_exposes_the_export_headers(store: Store) -> None:
    origin = "https://app.example.org"
    with TestClient(make_app(store.indexes.parent, cors_origins=(origin,))) as c:
        r = c.get(EXPORT, params={"q": "trust", "format": "ris"}, headers={"Origin": origin})
    exposed = {h.strip().lower() for h in r.headers["access-control-expose-headers"].split(",")}
    assert {"x-total", "x-index-version"} <= exposed


def test_a_pinned_index_version_is_served_from_that_index(
    client: TestClient, store: Store, tmp_path: Path
) -> None:
    q = "trust OR model"
    r = ok(client, q, "jsonl", index_version=store.small)  # the service serves the 5k index
    assert r.headers["x-index-version"] == store.small
    assert ids_of("jsonl", r.content) == match_ids(store, store.small, q)
    assert int(r.headers["x-total"]) < int(ok(client, q, "jsonl").headers["x-total"])
    assert r.content == op_export(store, q, "jsonl", tmp_path, "--index", store.small)
    served = ok(client, q, "ris", index_version=store.big)  # pinning the served version is the served index
    assert served.headers["x-index-version"] == store.big


def test_pinned_engines_are_opened_once_and_few_are_kept(data_dir: Path, store: Store) -> None:
    opened: list[str] = []

    def opener(path: Path) -> TantivyEngine:
        opened.append(path.name)
        return TantivyEngine(path)

    with TestClient(make_app(data_dir, opener=opener)) as c:
        for _ in range(3):
            ok(c, "trust", "ris", index_version=store.small)
    assert opened == [store.big, store.small]  # the startup load, then the pinned one, once


def test_an_index_version_not_on_this_instance_is_a_409(
    client: TestClient, data_dir: Path, store: Store
) -> None:
    e = error(
        client.get(EXPORT, params={"q": "trust", "format": "ris", "index_version": "0123456789ab"}),
        409,
        "API_INDEX_VERSION_UNAVAILABLE",
    )
    assert "0123456789ab" not in e["message"]
    # a name that resolves to another version (an alias symlink) is not that version
    (data_dir / "indexes" / "abcdef").symlink_to(store.small)
    with TestClient(make_app(data_dir)) as c:
        error(
            c.get(EXPORT, params={"q": "trust", "format": "ris", "index_version": "abcdef"}),
            409,
            "API_INDEX_VERSION_UNAVAILABLE",
        )


@pytest.mark.parametrize("version", ["current", "../indexes/x", "ABC", "", "a" * 65, "-abc"])
def test_a_malformed_index_version_is_a_422(client: TestClient, version: str) -> None:
    error(
        client.get(EXPORT, params={"q": "trust", "format": "ris", "index_version": version}),
        422,
        "API_BAD_PARAM",
    )


# --- refusals, all before the first byte ------------------------------------------------------------------
def test_a_query_that_does_not_parse_is_a_422_with_its_diagnostics(client: TestClient) -> None:
    e = error(client.get(EXPORT, params={"q": "𝔸I (trust", "format": "ris"}), 422, "PARSE_UNBALANCED_PAREN")
    assert e["diagnostics"] and e["diagnostics"][0]["span"] is not None


def test_an_over_cap_wildcard_is_a_located_422(store: Store, monkeypatch: pytest.MonkeyPatch) -> None:
    import openproceedings.engine.tantivy_engine as te

    monkeypatch.setattr(te, "MAX_EXPANSIONS", 1)
    with TestClient(make_app(store.indexes.parent)) as c:
        e = error(
            c.get(EXPORT, params={"q": "𝔸I trust calibrat*", "format": "csv"}),
            422,
            "WILDCARD_TOO_MANY_EXPANSIONS",
        )
    assert [(d["code"], d["span"]) for d in e["diagnostics"]] == [("WILDCARD_TOO_MANY_EXPANSIONS", [9, 18])]


@pytest.mark.parametrize(
    "params",
    [
        {"q": "trust"},  # no format
        {"q": "trust", "format": "xml"},
        {"q": "trust", "format": "RIS"},
        {"format": "ris"},  # no q
        {"q": "trust", "format": "ris", "mode": "google"},
    ],
)
def test_bad_parameters_are_422_api_bad_param(client: TestClient, params: dict[str, Any]) -> None:
    error(client.get(EXPORT, params=params), 422, "API_BAD_PARAM")


def test_an_over_long_query_is_refused_before_parsing(client: TestClient) -> None:
    error(client.get(EXPORT, params={"q": "a " * 1_001, "format": "ris"}), 422, "PARSE_TOO_LONG")


# --- the stream: one index across a swap, and a failure mid-way ----------------------------------------------
class Held(TantivyEngine):
    """Blocks on its first record read once `armed`: an export in flight while the index is swapped."""

    armed = threading.Event()
    entered = threading.Event()
    release = threading.Event()

    def _display(self, address: Any) -> dict[str, Any]:
        if self.armed.is_set() and not self.entered.is_set():
            self.entered.set()
            self.release.wait(10)
        return super()._display(address)


def test_an_export_started_before_a_swap_finishes_on_its_index(data_dir: Path, store: Store) -> None:
    q = "trust OR model"
    app = make_app(data_dir, opener=Held)
    state: IndexState = app.state.index
    with TestClient(app) as c, ThreadPoolExecutor(1) as pool:
        Held.armed.set()
        try:
            streaming = pool.submit(c.get, EXPORT, params={"q": q, "format": "jsonl"})
            assert Held.entered.wait(10)  # headers are fixed and the stream has begun on the 5k index
            point_current(data_dir, store.small)
            assert state.load()
            assert state.engine is not None and state.engine.index_version == store.small
        finally:
            Held.release.set()
        r = streaming.result(20)
        after = ok(c, q, "jsonl")
    assert r.headers["x-index-version"] == store.big
    assert ids_of("jsonl", r.content) == match_ids(store, store.big, q)  # every record from the old index
    assert after.headers["x-index-version"] == store.small  # a new export gets the new one


class Failing(TantivyEngine):
    """Fails reading its 1,000th record (of 1,175): after the first body chunks have gone out."""

    reads = 0

    def _display(self, address: Any) -> dict[str, Any]:
        type(self).reads += 1
        if type(self).reads == 1_000:
            raise RuntimeError(f"disk gone while exporting {SECRET}")
        return super()._display(address)


def test_a_failure_mid_stream_is_logged_as_aborted_without_query_text(store: Store, logs: Logs) -> None:
    with TestClient(make_app(store.indexes.parent, opener=Failing)) as c:
        r = c.get(EXPORT, params={"q": f"(agent OR {SECRET}) {EVERY_STATUS}", "format": "ris"})
    # the 200 and its first chunks were out (TestClient hands back no body for a response never completed)
    assert r.status_code == 200 and Failing.reads == 1_000
    (line,) = [x for x in logs() if x["event"] == "request"]
    assert line["route"] == EXPORT and line["status"] == 200 and line["aborted"] is True
    failed = [x for x in logs() if x["event"] == "request_failed"]
    assert len(failed) == 1 and failed[0]["level"] == "ERROR" and failed[0]["error"] == "RuntimeError"
    assert SECRET not in logs.raw.getvalue()  # type: ignore[attr-defined]


def test_a_stream_that_miscounts_fails_rather_than_pass_as_complete() -> None:
    provenance = exporter.Provenance("abc", "0" * 64, DATE)
    record = {"id": "x:1", "title": "T", "abstract": None, "authors": [], "venue": "ICLR", "year": 2024,
              "track": "main", "status": "accepted", "urls": {}}  # fmt: skip
    body = route._body("jsonl", iter([record]), provenance, total=2)
    assert next(body)  # the record goes out; the shortfall is found after it
    with pytest.raises(EngineInternalError):
        next(body)


def test_the_access_line_has_the_hash_and_total_and_no_query_text(
    client: TestClient, store: Store, logs: Logs
) -> None:
    q = f"trust OR {SECRET}"
    r = ok(client, q, "bibtex")
    (line,) = [x for x in logs() if x["event"] == "request"]
    assert line["route"] == EXPORT and line["canonical_hash"] == parse(q).canonical_hash
    assert line["total"] == int(r.headers["x-total"]) and line["index_version"] == store.big
    ok(client, q, "ris", index_version=store.small)
    pinned = [x for x in logs() if x["event"] == "request"][-1]
    assert pinned["index_version"] == store.small  # the pinned index, not the served one
    assert SECRET not in logs.raw.getvalue()  # type: ignore[attr-defined]


def test_the_openapi_document_describes_the_export(client: TestClient) -> None:
    op = client.get("/api/v1/openapi.json").json()["paths"][EXPORT]["get"]
    params = {p["name"]: p for p in op["parameters"]}
    assert set(params) == {"q", "format", "mode", "index_version"}  # record_id arrives with task-037
    assert params["q"]["required"] and params["format"]["required"]
    assert not params["index_version"]["required"]
    assert set(op["responses"]["200"]["content"]) == {m.split(";")[0] for m, _ext in route.MEDIA.values()}
