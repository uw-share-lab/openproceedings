"""`GET /api/v1/export` (task-036; spec 04 §Exports): `op export`'s bytes for the same query and index, the
whole matched set in id order, `X-Total` (= `/search`'s `total`) and `X-Index-Version`, the media type and
filename, every format round-tripped to its ids by an independent parser (scholarmend for RIS, the pinned
refaudit for BibTeX), a pinned `index_version` served from that index (409 when this instance can't serve
it: absent, tampered with, or built by other code), a saved record's export (`record_id` alone; 409 for a
mismatch record), every refusal before the first byte, a body that really streams in bounded chunks, a
stream that finishes on its index across a hot swap, and a failure mid-stream logged as aborted with no
query text anywhere."""

from __future__ import annotations

import csv
import io
import json
import shutil
import threading
from collections.abc import Callable, Iterator
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
from openproceedings.query import QUERY_VERSION
from openproceedings.query.normalize import TOKENIZER_VERSION
from openproceedings.query.parser import parse
from refaudit.bibtex import parse_string
from scholarmend.parse import parse_ris

from tests.contract.conftest import SECRET, Store, build, make_app, point_current
from tests.contract.test_records import MISMATCHES, mismatched, save, tampered
from tests.fixtures.corpus.synthetic_5k import records

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
    line = f"openproceedings {store.big} · query {parse(q).canonical_hash} · exported {DATE}"
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
    assert r.headers["x-tokenizer-version"] == TOKENIZER_VERSION
    assert r.headers["x-query-version"] == QUERY_VERSION
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
    assert {"x-total", "x-index-version", "x-tokenizer-version", "x-query-version"} <= exposed


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
        {"format": "ris"},  # neither q nor record_id
        {"q": "trust", "format": "ris", "mode": "google"},
        {"record_id": "short", "format": "ris"},  # not a record id
        {"record_id": "abcdefghijk!", "format": "ris"},
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


class Failing(TantivyEngine):
    """Fails reading its 1,000th record (of 1,175): after the first body chunks have gone out."""

    reads = 0

    def _display(self, address: Any) -> dict[str, Any]:
        type(self).reads += 1
        if type(self).reads == 1_000:
            raise RuntimeError(f"disk gone while exporting {SECRET}")
        return super()._display(address)


@pytest.fixture(autouse=True)
def fresh_engines() -> Iterator[None]:
    """Held's events and Failing's count are class state: each test starts from none."""
    for event in (Held.armed, Held.entered, Held.release):
        event.clear()
    Failing.reads = 0
    yield
    Held.release.set()  # never leave a stream waiting


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


RECORD = {"id": "x:1", "title": "T", "abstract": None, "authors": [], "venue": "ICLR", "year": 2024,
          "track": "main", "status": "accepted", "urls": {}}  # fmt: skip


@pytest.mark.parametrize("n, total", [(1, 2), (3, 2), (0, 1)])  # short, over, and nothing at all
def test_a_stream_that_miscounts_fails_rather_than_pass_as_complete(n: int, total: int) -> None:
    provenance = exporter.Provenance("abc", "0" * 64, DATE)
    body = route._body("jsonl", iter([RECORD] * n), provenance, total=total)
    sent = next(body)  # what it has goes out; the miscount is found after the last record
    assert sent.count(b"\n") == n
    with pytest.raises(EngineInternalError):
        next(body)


def test_a_stream_that_counts_right_ends_cleanly() -> None:
    provenance = exporter.Provenance("abc", "0" * 64, DATE)
    assert b"".join(route._body("jsonl", iter([RECORD] * 3), provenance, total=3)).count(b"\n") == 3


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
    assert set(params) == {"q", "format", "mode", "index_version", "record_id"}
    assert params["format"]["required"]  # q or record_id: one of the two, checked by the route
    assert not any(params[p].get("required") for p in ("q", "mode", "index_version", "record_id"))
    assert params["mode"]["schema"]["default"] == "native"  # the default is in the contract (M3a review)
    assert set(op["responses"]["200"]["content"]) == {m.split(";")[0] for m, _ext in route.MEDIA.values()}
    headers = op["responses"]["200"]["headers"]
    assert set(headers) == {
        "X-Total", "X-Index-Version", "X-Tokenizer-Version", "X-Query-Version", "Content-Disposition",
    }  # fmt: skip
    assert headers["X-Total"]["schema"]["type"] == "integer"


def test_an_explicit_default_mode_is_a_q_export_like_none(client: TestClient) -> None:
    """`mode=native` sent explicitly with `q` is the same export as no `mode` (the default)."""
    a = client.get(EXPORT, params={"q": "trust", "format": "jsonl"})
    b = client.get(EXPORT, params={"q": "trust", "format": "jsonl", "mode": "native"})
    assert a.status_code == b.status_code == 200 and a.content == b.content


# --- the body really streams (S4) ---------------------------------------------------------------------------
def body_messages(client: TestClient, params: dict[str, str]) -> list[dict[str, Any]]:
    """Every ASGI message the app sends for one export, as the server would see them (TestClient joins the
    body, so the app is called directly on the client's own event loop)."""
    import urllib.parse

    sent: list[dict[str, Any]] = []
    scope = {
        "type": "http", "asgi": {"version": "3.0", "spec_version": "2.4"}, "http_version": "1.1",
        "method": "GET", "scheme": "http", "path": EXPORT, "raw_path": EXPORT.encode(),
        "query_string": urllib.parse.urlencode(params).encode(), "root_path": "",
        "headers": [(b"host", b"testserver")], "client": ("testclient", 1), "server": ("testserver", 80),
    }  # fmt: skip

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    async def run() -> None:
        await client.app(scope, receive, send)  # type: ignore[arg-type]

    assert client.portal is not None
    client.portal.call(run)
    return sent


@pytest.mark.parametrize("fmt", FORMATS)
def test_the_body_is_sent_in_bounded_chunks_as_it_is_written(client: TestClient, fmt: str) -> None:
    sent = body_messages(client, {"q": BROAD, "format": fmt})
    assert sent[0]["type"] == "http.response.start" and sent[0]["status"] == 200
    bodies = [m for m in sent if m["type"] == "http.response.body"]
    chunks = [m["body"] for m in bodies if m["body"]]
    assert len(chunks) > 2  # streamed, never buffered whole
    assert [m.get("more_body", False) for m in bodies][-1] is False
    text = b"".join(chunks).decode("utf-8")
    longest = max(
        len(e) for e in exporter.entries(fmt, _documents(client, BROAD), _provenance(client, BROAD))
    )
    assert all(len(c.decode("utf-8")) <= route.CHUNK + longest for c in chunks)
    assert text.encode("utf-8") == ok(client, BROAD, fmt).content  # the same bytes, however cut


def _documents(client: TestClient, q: str) -> Iterator[dict[str, Any]]:
    engine = client.app.state.index.engine  # type: ignore[attr-defined]
    return engine.documents(parse(q).effective_ast)[1]  # type: ignore[no-any-return]


def _provenance(client: TestClient, q: str) -> exporter.Provenance:
    engine = client.app.state.index.engine  # type: ignore[attr-defined]
    return exporter.Provenance(engine.index_version, parse(q).canonical_hash or "", DATE)


# --- a pinned index this instance can't serve (S1, S2) --------------------------------------------------------
def test_a_copied_index_directory_is_refused_as_tampered_409(
    data_dir: Path, store: Store, logs: Logs
) -> None:
    """A copy of an index under another version's name: its manifest names the original, so it doesn't
    verify. 409 (not available here), one ERROR line, and /meta doesn't offer it."""
    shutil.copytree(data_dir / "indexes" / store.small, data_dir / "indexes" / "abcdef012345")
    with TestClient(make_app(data_dir)) as c:
        for _ in range(2):
            error(
                c.get(EXPORT, params={"q": "trust", "format": "ris", "index_version": "abcdef012345"}),
                409,
                "API_INDEX_VERSION_UNAVAILABLE",
            )
        versions = c.get("/api/v1/meta").json()["index_versions"]
    refusals = [x for x in logs() if x["event"] == "pinned_index_unavailable"]
    assert [(x["level"], x["reason"]) for x in refusals] == [("ERROR", "tampered")]  # once, then remembered
    assert "abcdef012345" not in versions


@pytest.fixture
def stale(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """An index built by an older tokenizer, in the instance's data directory: its version."""
    import openproceedings.engine.index as index_module

    with monkeypatch.context() as m:
        m.setattr(index_module, "TOKENIZER_VERSION", "0-old")
        return build(list(records())[:50], data_dir / "snapshots", "old", data_dir / "indexes")


def test_an_index_this_code_cant_serve_is_409_logged_once_and_not_listed(
    data_dir: Path, stale: str, logs: Logs
) -> None:
    opened: list[str] = []

    def opener(path: Path) -> TantivyEngine:
        opened.append(path.name)
        return TantivyEngine(path)

    with TestClient(make_app(data_dir, opener=opener)) as c:
        assert stale not in c.get("/api/v1/meta").json()["index_versions"]  # from its manifest, unopened
        for _ in range(3):
            error(
                c.get(EXPORT, params={"q": "trust", "format": "ris", "index_version": stale}),
                409,
                "API_INDEX_VERSION_UNAVAILABLE",
            )
    assert opened.count(stale) == 1  # the refusal is remembered, not re-verified per request
    refusals = [x for x in logs() if x["event"] == "pinned_index_unavailable"]
    # the reason names the input that differs (M3a review), never the message's paths
    assert [(x["level"], x["reason"], x["error"], x["cause_reason"]) for x in refusals] == [
        ("WARNING", "unloadable", "IndexUnservable", "tokenizer_version_mismatch")
    ]


# --- record_id (AC3) ---------------------------------------------------------------------------------------
@pytest.fixture
def recorded(data_dir: Path) -> Iterator[TestClient]:
    """The app over a private data directory, so its records.sqlite is this test's own."""
    with TestClient(make_app(data_dir)) as c:
        yield c


def test_a_record_exports_its_own_query_on_its_own_index(
    recorded: TestClient, data_dir: Path, store: Store, tmp_path: Path
) -> None:
    record_id = save(recorded, "trust OR calibrat*")
    stored = recorded.get(f"/api/v1/records/{record_id}", params={"include": "ids"}).json()["record"]
    r = recorded.get(EXPORT, params={"record_id": record_id, "format": "jsonl"})
    assert r.status_code == 200, r.text
    assert r.headers["x-index-version"] == store.big and int(r.headers["x-total"]) == stored["total"]
    assert ids_of("jsonl", r.content) == stored["ids"]  # the record's membership, exactly
    # `op export` of the canonical gives the same records; the pinned export also names the record
    pinned = {"record_id": record_id, "searched_at": stored["searched_at"]}
    cli_rows = [json.loads(x) for x in op_export(store, stored["canonical"], "jsonl", tmp_path).splitlines()]
    assert [json.loads(x) for x in r.content.splitlines()] == [{**x, **pinned} for x in cli_rows]
    line = (f"openproceedings {store.big} · query {stored['canonical_hash']} · exported {DATE} · record "
            f"{record_id} · searched {stored['searched_at'][:10]}")  # fmt: skip
    ris = parse_ris(recorded.get(EXPORT, params={"record_id": record_id, "format": "ris"}).text, "r.ris")
    assert ris and all(x.fields["N1"][-1] == line for x in ris)
    bib = parse_string(recorded.get(EXPORT, params={"record_id": record_id, "format": "bibtex"}).text)
    assert bib and all(e.fields["note"].endswith(line.replace("_", "\\_")) for e in bib)
    # after a swap the record still exports from the index it names
    point_current(data_dir, store.small)
    assert recorded.app.state.index.load()  # type: ignore[attr-defined]
    after = recorded.get(EXPORT, params={"record_id": record_id, "format": "jsonl"})
    assert after.headers["x-index-version"] == store.big and after.content == r.content


def pinned(fmt: str, body: bytes, record_id: str, searched_at: str) -> bytes:
    """`op export`'s bytes as a record-pinned export writes them: the provenance names the record."""
    tail = f" · record {record_id} · searched {searched_at[:10]}"
    text = body.decode("utf-8")
    if fmt == "ris":
        text = text.replace(f" · exported {DATE}\n", f" · exported {DATE}{tail}\n")
    elif fmt == "bibtex":
        text = text.replace(
            f" · exported {DATE}}}", f" · exported {DATE}{tail.replace('_', chr(92) + '_')}}}"
        )
    elif fmt == "csv":
        text = text.replace(f",{DATE},,\r\n", f",{DATE},{exporter._cell(record_id)},{searched_at}\r\n")
    else:
        text = text.replace('"record_id": null', f'"record_id": "{record_id}"')
        text = text.replace('"searched_at": null', f'"searched_at": "{searched_at}"')
    return text.encode("utf-8")


@pytest.mark.parametrize("fmt", get_args(route.ExportFormat))
def test_a_record_export_is_op_exports_bytes_with_the_record_named(
    recorded: TestClient, store: Store, tmp_path: Path, fmt: str
) -> None:
    record_id = save(recorded, "trust OR calibrat*")
    stored = recorded.get(f"/api/v1/records/{record_id}").json()["record"]
    r = recorded.get(EXPORT, params={"record_id": record_id, "format": fmt})
    assert r.status_code == 200, r.text
    cli_bytes = op_export(store, stored["canonical"], fmt, tmp_path)
    assert cli_bytes != r.content  # the record is named: the two differ exactly by that
    assert r.content == pinned(fmt, cli_bytes, record_id, stored["searched_at"])


@pytest.mark.parametrize("what", MISMATCHES)
def test_exporting_a_mismatch_record_is_409_and_streams_nothing(
    recorded: TestClient, data_dir: Path, what: str
) -> None:
    """Every kind of mismatch, most of which only the replay (`refuse_mismatch`) can see: an `excluded`
    or canonical mismatch has a stored list that hashes right, so the route's own check would pass it."""
    good = save(recorded, "trust")
    bad = mismatched(recorded, data_dir, good, what)
    e = error(recorded.get(EXPORT, params={"record_id": bad, "format": "ris"}), 409, "API_RECORD_MISMATCH")
    assert bad not in e["message"]


def test_a_drifted_record_whose_stored_list_is_not_its_hash_is_409(
    recorded: TestClient, data_dir: Path
) -> None:
    """A drifted record passes the replay's gate (only `mismatch` is refused there), so the route's own
    check that the stored list hashes to `ids_hash` is what stops it streaming a set it doesn't cite."""
    good = save(recorded, "trust")
    ids = recorded.get(f"/api/v1/records/{good}", params={"include": "ids"}).json()["record"]["ids"]
    bad = tampered(data_dir, good, ids=ids[1:], query_version="0")
    assert recorded.get(f"/api/v1/records/{bad}").json()["replay"]["status"] == "drifted"
    error(recorded.get(EXPORT, params={"record_id": bad, "format": "jsonl"}), 409, "API_RECORD_MISMATCH")


def test_a_record_export_past_the_first_chunk_has_every_id(
    recorded: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(route, "STORED_CHUNK", 2)
    record_id = save(recorded, "trust OR calibrat*")
    stored = recorded.get(f"/api/v1/records/{record_id}", params={"include": "ids"}).json()["record"]
    assert stored["total"] > 5  # several chunks of 2, and a last partial one when odd
    r = recorded.get(EXPORT, params={"record_id": record_id, "format": "jsonl"})
    assert r.status_code == 200, r.text
    assert int(r.headers["x-total"]) == stored["total"] and ids_of("jsonl", r.content) == stored["ids"]


def test_a_record_exports_its_stored_ids_even_after_the_query_version_changed(
    recorded: TestClient, data_dir: Path, store: Store
) -> None:
    """The stored set is what the record cites, so the export never re-runs the query: here the copy's
    query version drifted and its canonical now names another query, and the export is still the stored ids."""
    good = save(recorded, "trust OR calibrat*")
    stored = recorded.get(f"/api/v1/records/{good}", params={"include": "ids"}).json()["record"]
    other = parse("benchmark").canonical
    drifted = tampered(data_dir, good, query_version="0", canonical=other)
    assert recorded.get(f"/api/v1/records/{drifted}").json()["replay"]["status"] == "drifted"
    r = recorded.get(EXPORT, params={"record_id": drifted, "format": "jsonl"})
    assert r.status_code == 200, r.text
    assert ids_of("jsonl", r.content) == stored["ids"] and int(r.headers["x-total"]) == stored["total"]
    assert r.headers["x-index-version"] == store.big
    assert ids_of("jsonl", r.content) != match_ids(store, store.big, "benchmark")


def test_a_record_whose_index_is_gone_is_409_unavailable(recorded: TestClient, data_dir: Path) -> None:
    good = save(recorded, "trust")
    gone = tampered(data_dir, good, index_version="ffffffffffff")  # an index this instance doesn't hold
    e = error(
        recorded.get(EXPORT, params={"record_id": gone, "format": "ris"}),
        409,
        "API_INDEX_VERSION_UNAVAILABLE",
    )
    assert gone not in e["message"]


@pytest.mark.parametrize(
    "extra",
    [
        {"q": "trust"},
        {"mode": "native"},  # the default, sent explicitly: still refused (read from the query string)
        {"mode": "scholar"},
        {"index_version": "0123456789ab"},
        {"q": "trust", "mode": "native", "index_version": "0123456789ab"},
    ],
)
def test_a_record_id_with_a_query_mode_or_version_is_422(recorded: TestClient, extra: dict[str, str]) -> None:
    """Each of q, mode and index_version alone turns a record export into a 422 (qa mutant E5: a check of
    `q` alone must not pass); the same export without it is a 200, so the extra parameter is the cause."""
    record_id = save(recorded, "trust")
    assert recorded.get(EXPORT, params={"record_id": record_id, "format": "ris"}).status_code == 200
    e = error(
        recorded.get(EXPORT, params={"record_id": record_id, "format": "ris", **extra}), 422, "API_BAD_PARAM"
    )
    assert "record_id alone" in e["message"]


def test_an_unknown_record_is_404(recorded: TestClient) -> None:
    error(recorded.get(EXPORT, params={"record_id": "A" * 12, "format": "ris"}), 404, "API_RECORD_NOT_FOUND")
