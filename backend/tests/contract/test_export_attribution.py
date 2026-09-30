"""`GET /api/v1/export` names each abstract's source in every format (TASK-138; decision-018; spec 04 §Exports):
RIS an `N1  - Abstract source: <site> <url>` line before the provenance line, BibTeX an `abstract_source`
field, CSV three source columns and `abstract_withheld` appended after the others, JSONL an `abstract_source`
object and `abstract_withheld`, all from the exported index's snapshot records (what `GET /search` sends as
`abstract_source`). Read back with scholarmend's RIS parser and refaudit's BibTeX parser; the served index, a
pinned `index_version` and a search record's own index alike. A pinned index whose snapshot can't be verified
is exported with every abstract withheld and each record saying so (decision-021), never an abstract without
attribution; its snapshot records are held in an LRU and a failure is remembered for `refusal_seconds`."""

from __future__ import annotations

import csv
import io
import json
import shutil
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from openproceedings import cli
from openproceedings import export as exporter
from openproceedings.api import export as route
from openproceedings.ingest.dedup import Attribution
from openproceedings.ingest.snapshot import RecordFile
from refaudit.bibtex import parse_string
from scholarmend.parse import parse_ris

from tests.contract.conftest import attributed, build, make_app, point_current
from tests.contract.test_records import save
from tests.fixtures.corpus.synthetic_5k import records

EXPORT = "/api/v1/export"
DATE = "2026-09-27"
EVERY = "status:(accepted OR rejected OR withdrawn OR desk_rejected OR unknown)"
Q = f"(trust OR agent*) {EVERY}"  # every venue, every status, abstracts missing and present
# written out here, not imported: the words the results list shows (`hit-item.tsx`)
SITE = {
    "openreview": "OpenReview",
    "neurips_proceedings": "NeurIPS Proceedings",
    "iclr_proceedings": "ICLR Proceedings",
    "pmlr": "PMLR",
}
type Built = tuple[Path, str, str, str]  # the data directory, and indexes `a` (served), `b` and `c`


@pytest.fixture(autouse=True)
def fixed_date(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(exporter, "utc_date", lambda: DATE)
    monkeypatch.setattr(route, "utc_date", lambda: DATE)


@pytest.fixture(scope="module")
def store(tmp_path_factory: pytest.TempPathFactory) -> Built:
    """Three indexes of `attributed` records (so abstracts carry claims): `a` (every 3rd fixture record,
    served), `b` (the next third) and `c` (the last)."""
    data = tmp_path_factory.mktemp("export-attributed") / "data"
    corpus = list(records())
    a = build(corpus[::3], data / "snapshots", "a", data / "indexes", attributed)
    b = build(corpus[1::3], data / "snapshots", "b", data / "indexes", attributed)
    c = build(corpus[2::3], data / "snapshots", "c", data / "indexes", attributed)
    (data / "indexes" / "current").symlink_to(a)
    return data, a, b, c


@pytest.fixture
def data_dir(store: Built, tmp_path: Path) -> Path:
    shutil.copytree(store[0], tmp_path / "data", symlinks=True)
    return tmp_path / "data"


@pytest.fixture
def client(data_dir: Path) -> Iterator[TestClient]:
    with TestClient(make_app(data_dir)) as c:
        yield c


def attributions(data_dir: Path, snapshot: str) -> dict[str, Attribution | None]:
    return RecordFile(data_dir / "snapshots" / snapshot).attributions


def body(client: TestClient, fmt: str, **params: Any) -> str:
    r = client.get(EXPORT, params={"format": fmt, **params})
    assert r.status_code == 200, r.text
    assert r.headers["x-abstract-source"] == "attributed"
    return r.content.decode("utf-8")


def words(a: Attribution) -> str:
    """The expected `<site> <url>`, built here from the attribution's parts (not by the exporter's `credit`)."""
    site = (
        SITE[a.origin] + (" (via RIS import)" if a.source == "ris" else "")
        if a.origin
        else "an imported RIS file"
    )
    return f"{site} {a.url}" if a.url else site


def credits(fmt: str, text: str) -> dict[str, Any]:
    """Each exported record's id → what the file says about its abstract's source, read back by a parser that
    isn't ours (scholarmend for RIS, refaudit for BibTeX)."""
    if fmt == "ris":
        out = {}
        for r in parse_ris(text, "export.ris"):
            notes = r.fields["N1"]
            assert notes[-1].startswith("openproceedings "), "the provenance line stays the last N1"
            said = [n.removeprefix("Abstract source: ") for n in notes if n.startswith("Abstract source: ")]
            assert len(said) <= 1
            out[r.first("ID")] = said[0] if said else None
        return out
    if fmt == "bibtex":
        return {e.fields["openproceedings_id"]: e.fields.get("abstract_source") for e in parse_string(text)}
    if fmt == "csv":
        rows = csv.DictReader(io.StringIO(text.removeprefix("﻿")))
        assert rows.fieldnames is not None and rows.fieldnames[-4:] == [
            "abstract_source",
            "abstract_origin",
            "abstract_url",
            "abstract_withheld",
        ]
        return {
            row["id"]: (row["abstract_source"], row["abstract_origin"], row["abstract_url"]) for row in rows
        }
    return {(obj := json.loads(line))["id"]: obj["abstract_source"] for line in text.splitlines()}


def expected(fmt: str, a: Attribution | None) -> Any:
    if fmt in ("ris", "bibtex"):
        return None if a is None else words(a)
    if fmt == "csv":
        return ("", "", "") if a is None else (a.source, a.origin or "", a.url or "")
    return None if a is None else {"source": a.source, "origin": a.origin, "url": a.url}


def check(fmt: str, text: str, want: dict[str, Attribution | None]) -> int:
    """Every record names exactly its snapshot's attribution; how many named one."""
    got = credits(fmt, text)
    assert got, "the export holds records"
    for rid, said in got.items():
        assert said == expected(fmt, want[rid]), (fmt, rid)
    return sum(want[rid] is not None for rid in got)


@pytest.mark.parametrize("fmt", exporter.FORMATS)
def test_every_format_names_each_abstracts_source_from_the_served_snapshot(
    client: TestClient, data_dir: Path, fmt: str
) -> None:
    text = body(client, fmt, q=Q)
    named = check(fmt, text, attributions(data_dir, "a"))
    assert 0 < named < len(credits(fmt, text)), "some abstracts named, and records without one name nothing"


def test_the_export_names_what_search_sends_as_abstract_source(client: TestClient) -> None:
    """One attribution, two surfaces: each JSONL record's `abstract_source` is its `/search` hit's."""
    exported = credits("jsonl", body(client, "jsonl", q=Q))
    for venue in ("ICLR", "ICML", "NeurIPS"):
        r = client.get("/api/v1/search", params={"q": f"{Q} venue:{venue}", "limit": 200})
        assert r.status_code == 200, r.text
        for hit in r.json()["hits"]:
            assert exported[hit["id"]] == hit["abstract_source"], hit["id"]


def test_ris_and_bibtex_read_back_whole_with_the_reference_parsers(client: TestClient) -> None:
    """The extra `N1` and field cost nothing else: every record parses, with its title, abstract and id."""
    ris, bib = body(client, "ris", q=Q), body(client, "bibtex", q=Q)
    jsonl = {(o := json.loads(x))["id"]: o for x in body(client, "jsonl", q=Q).splitlines()}
    parsed = parse_ris(ris, "export.ris")
    assert [r.first("ID") for r in parsed] == sorted(jsonl)
    for r in parsed:
        assert r.fields["TI"] == [" ".join(jsonl[r.first("ID")]["title"].split())]
        assert r.fields.get("AB", [None])[0] == (
            " ".join(jsonl[r.first("ID")]["abstract"].split()) if jsonl[r.first("ID")]["abstract"] else None
        )
    entries = parse_string(bib)
    assert sorted(e.fields["openproceedings_id"] for e in entries) == sorted(jsonl)
    assert all(e.fields["note"].startswith(("openproceedings ", "Submitted to ")) for e in entries)


def test_a_pmlr_abstract_names_pmlr_and_links_its_pmlr_page(client: TestClient, data_dir: Path) -> None:
    """PMLR's CC BY 4.0 terms: a citation (the record itself) and a hyperlink to the paper's PMLR page."""
    want = attributions(data_dir, "a")
    ris = credits("ris", body(client, "ris", q=f"{Q} venue:ICML"))
    pmlr = {rid: said for rid, said in ris.items() if (a := want[rid]) is not None and a.origin == "pmlr"}
    assert pmlr
    for said in pmlr.values():
        assert said.startswith(
            ("PMLR https://proceedings.mlr.press/", "PMLR (via RIS import) https://proceedings.mlr.press/")
        )


@pytest.mark.parametrize("fmt", exporter.FORMATS)
def test_op_export_writes_the_same_attributed_bytes(
    client: TestClient, data_dir: Path, tmp_path: Path, fmt: str
) -> None:
    out = tmp_path / f"cli.{fmt}"
    assert cli.main(["--data-dir", str(data_dir), "export", Q, "--format", fmt, "--out", str(out)]) == 0
    assert out.read_bytes().decode("utf-8") == body(client, fmt, q=Q)


def test_a_pinned_index_version_names_its_own_snapshots_sources(
    client: TestClient, data_dir: Path, store: Built
) -> None:
    _data, _a, b, _c = store
    for fmt in exporter.FORMATS:
        check(fmt, body(client, fmt, q=Q, index_version=b), attributions(data_dir, "b"))


def test_a_record_export_names_the_sources_of_the_index_it_names(
    client: TestClient, data_dir: Path, store: Built
) -> None:
    """A search record saved on `a`, exported after `b` is served: `a`'s snapshot attributes its abstracts."""
    _data, _a, b, _c = store
    record_id = save(client, Q)
    point_current(data_dir, b)
    assert client.app.state.index.load()  # type: ignore[attr-defined]
    for fmt in exporter.FORMATS:
        check(fmt, body(client, fmt, record_id=record_id), attributions(data_dir, "a"))


def test_a_pinned_snapshot_is_verified_once_and_kept(client: TestClient, store: Built) -> None:
    _data, _a, b, _c = store
    state = client.app.state.index  # type: ignore[attr-defined]
    first = state.pinned_records(b)
    assert first is not None and state.pinned_records(b) is first
    assert state.pinned_records(state.engine.index_version) is state.served.records  # the served one's own


def test_a_snapshot_that_wont_verify_is_remembered_not_rehashed_per_request(
    data_dir: Path, store: Built, monkeypatch: pytest.MonkeyPatch
) -> None:
    """As a refused pin is: one verifying attempt per `refusal_seconds` (or reload), not one per export."""
    from openproceedings.api import state as state_module

    _data, _a, b, _c = store
    shutil.rmtree(data_dir / "snapshots" / "b")
    real, calls = state_module.snapshot_records, []

    def counted(*args: Any) -> RecordFile:
        calls.append(args[2])
        return real(*args)

    monkeypatch.setattr(state_module, "snapshot_records", counted)
    with TestClient(make_app(data_dir)) as c:
        calls.clear()  # the served index's own load
        for _ in range(3):
            withheld_export(c, "csv", q=Q, index_version=b)
        assert calls == [b]
        assert c.app.state.index.load()  # type: ignore[attr-defined]  # a reload looks again
        withheld_export(c, "csv", q=Q, index_version=b)
        assert calls == [b, b]


class Clock:
    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now


def counted_state(
    data_dir: Path, monkeypatch: pytest.MonkeyPatch, clock: Clock, keep: int
) -> tuple[Any, list[str]]:
    """An unloaded `IndexState` (so no version is the served one) and the versions it verified, in order."""
    from openproceedings.api import state as state_module
    from openproceedings.engine.tantivy_engine import TantivyEngine

    real, calls = state_module.snapshot_records, []

    def counted(*args: Any) -> RecordFile:
        calls.append(args[2])
        return real(*args)

    monkeypatch.setattr(state_module, "snapshot_records", counted)
    s = state_module.IndexState(
        data_dir, "current", TantivyEngine, keep_pinned=keep, refusal_seconds=60.0, clock=clock
    )
    return s, calls


def test_pinned_snapshot_records_are_an_lru_of_the_configured_size(
    data_dir: Path, store: Built, monkeypatch: pytest.MonkeyPatch
) -> None:
    """As the pinned engines are (`test_pinned.py`): a hit is kept without re-verifying, and a third version
    drops the least recently used."""
    _data, a, b, c = store
    s, calls = counted_state(data_dir, monkeypatch, Clock(), keep=2)
    kept = s.pinned_records(a)
    assert kept is not None and s.pinned_records(b) is not None
    assert s.pinned_records(a) is kept  # used again: `b` is now the least recent
    assert s.pinned_records(c) is not None  # a third version: `b` goes
    assert calls == [a, b, c]
    assert s.pinned_records(a) is kept and calls == [a, b, c]  # still held
    assert s.pinned_records(b) is not None and calls == [a, b, c, b]  # dropped, so verified again


def test_a_remembered_unverifiable_snapshot_is_verified_again_after_refusal_seconds(
    data_dir: Path, store: Built, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _data, _a, b, _c = store
    kept = tmp_path / "b-snapshot"
    shutil.move(data_dir / "snapshots" / "b", kept)
    clock = Clock()
    s, calls = counted_state(data_dir, monkeypatch, clock, keep=2)
    assert s.pinned_records(b) is None and calls == [b]
    shutil.move(kept, data_dir / "snapshots" / "b")  # restored, but the refusal is remembered
    clock.now += 59.0
    assert s.pinned_records(b) is None and calls == [b]
    clock.now += 2.0  # past refusal_seconds: verified again, and now it verifies
    assert s.pinned_records(b) is not None and calls == [b, b]


# --- a pinned index whose snapshot can't be verified: abstracts withheld (decision-021) ---------------------
def withheld_export(client: TestClient, fmt: str, **params: Any) -> str:
    r = client.get(EXPORT, params={"format": fmt, **params})
    assert r.status_code == 200, r.text
    assert r.headers["x-abstract-source"] == "unavailable"
    return r.content.decode("utf-8")


def check_withheld(fmt: str, text: str, ids: list[str]) -> None:
    """The same records, no abstract and no source anywhere, and each record saying why."""
    if fmt == "ris":
        parsed = parse_ris(text, "export.ris")
        assert [r.first("ID") for r in parsed] == ids
        for r in parsed:
            assert "AB" not in r.fields and r.fields["TI"]
            assert exporter.WITHHELD in r.fields["N1"] and r.fields["N1"][-1].startswith("openproceedings ")
            assert not any(n.startswith("Abstract source:") for n in r.fields["N1"])
    elif fmt == "bibtex":
        entries = parse_string(text)
        assert [e.fields["openproceedings_id"] for e in entries] == ids
        for e in entries:
            assert "abstract" not in e.fields and "abstract_source" not in e.fields
            assert e.fields["abstract_withheld"] == exporter.WITHHELD
    elif fmt == "csv":
        rows = list(csv.DictReader(io.StringIO(text.removeprefix("\ufeff"))))
        assert [row["id"] for row in rows] == ids
        assert all(row["abstract"] == "" and row["abstract_withheld"] == "true" for row in rows)
        assert all(
            row["abstract_source"] == row["abstract_origin"] == row["abstract_url"] == "" for row in rows
        )
    else:
        objs = [json.loads(line) for line in text.splitlines()]
        assert [o["id"] for o in objs] == ids
        assert all(
            o["abstract"] is None and o["abstract_source"] is None and o["abstract_withheld"] for o in objs
        )


def attributed_ids(client: TestClient, **params: Any) -> list[str]:
    return [json.loads(x)["id"] for x in body(client, "jsonl", **params).splitlines()]


@pytest.mark.parametrize("fmt", exporter.FORMATS)
def test_a_pinned_index_version_whose_snapshot_is_gone_withholds_every_abstract(
    data_dir: Path, store: Built, fmt: str
) -> None:
    _data, _a, b, _c = store
    with TestClient(make_app(data_dir)) as c:
        ids = attributed_ids(c, q=Q, index_version=b)
    shutil.rmtree(data_dir / "snapshots" / "b")
    with TestClient(make_app(data_dir)) as c:
        check_withheld(fmt, withheld_export(c, fmt, q=Q, index_version=b), ids)
        assert c.get(EXPORT, params={"format": fmt, "q": Q}).headers["x-abstract-source"] == "attributed"


def test_the_access_line_says_whether_the_export_withheld_its_abstracts(
    data_dir: Path, store: Built, logs: Callable[[], list[dict[str, Any]]]
) -> None:
    """An operator can count degraded exports and match a report to a request, not only the client."""
    _data, _a, b, _c = store
    shutil.rmtree(data_dir / "snapshots" / "b")
    with TestClient(make_app(data_dir)) as c:
        withheld_export(c, "ris", q=Q, index_version=b)
        withheld_export(c, "ris", q=Q, index_version=b)  # the refusal remembered: still on the access line
        body(c, "ris", q=Q)
    lines = [line for line in logs() if line["event"] == "request" and line["route"] == EXPORT]
    assert [line["abstract_source"] for line in lines] == ["unavailable", "unavailable", "attributed"]


@pytest.mark.parametrize("fmt", exporter.FORMATS)
def test_a_record_whose_index_snapshot_is_gone_withholds_abstracts_and_still_replays(
    data_dir: Path, store: Built, fmt: str
) -> None:
    """A record saved on `a`, `b` served, `a`'s snapshot gone: the cited ids go out without abstracts, and
    the record still replays `reproduced` (a replay needs the index, not the snapshot)."""
    _data, _a, b, _c = store
    with TestClient(make_app(data_dir)) as c:
        record_id = save(c, Q)
        ids = attributed_ids(c, record_id=record_id)
    point_current(data_dir, b)
    shutil.rmtree(data_dir / "snapshots" / "a")
    with TestClient(make_app(data_dir)) as c:
        check_withheld(fmt, withheld_export(c, fmt, record_id=record_id), ids)
        replay = c.get(f"/api/v1/records/{record_id}")
        assert replay.status_code == 200 and replay.json()["replay"]["status"] == "reproduced"


def test_op_export_without_the_snapshot_withholds_abstracts_with_a_warning(
    data_dir: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with TestClient(make_app(data_dir)) as c:
        ids = attributed_ids(c, q=Q)
    shutil.rmtree(data_dir / "snapshots" / "a")
    out = tmp_path / "cli.ris"
    assert cli.main(["--data-dir", str(data_dir), "export", Q, "--format", "ris", "--out", str(out)]) == 0
    check_withheld("ris", out.read_text(encoding="utf-8"), ids)
    err = capsys.readouterr().err
    assert "op export: warning:" in err and "every abstract is withheld" in err
