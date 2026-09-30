"""`GET /api/v1/export` names each abstract's source in every format (TASK-138; decision-018; spec 04 §Exports):
RIS an `N1  - Abstract source: <site> <url>` line before the provenance line, BibTeX an `abstract_source`
field, CSV three columns appended after the others, JSONL an `abstract_source` object, all from the exported
index's snapshot records (what `GET /search` sends as `abstract_source`). Read back with scholarmend's RIS
parser and refaudit's BibTeX parser; the served index, a pinned `index_version` and a search record's own
index alike; a pinned index whose snapshot is gone is refused, never exported without attribution."""

from __future__ import annotations

import csv
import io
import json
import shutil
from collections.abc import Iterator
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


@pytest.fixture(autouse=True)
def fixed_date(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(exporter, "utc_date", lambda: DATE)
    monkeypatch.setattr(route, "utc_date", lambda: DATE)


@pytest.fixture(scope="module")
def store(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, str, str]:
    """Two indexes of `attributed` records (so abstracts carry claims): `a` (every 3rd fixture record, served)
    and `b` (the next third)."""
    data = tmp_path_factory.mktemp("export-attributed") / "data"
    corpus = list(records())
    a = build(corpus[::3], data / "snapshots", "a", data / "indexes", attributed)
    b = build(corpus[1::3], data / "snapshots", "b", data / "indexes", attributed)
    (data / "indexes" / "current").symlink_to(a)
    return data, a, b


@pytest.fixture
def data_dir(store: tuple[Path, str, str], tmp_path: Path) -> Path:
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
        assert rows.fieldnames is not None and rows.fieldnames[-3:] == [
            "abstract_source",
            "abstract_origin",
            "abstract_url",
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
    client: TestClient, data_dir: Path, store: tuple[Path, str, str]
) -> None:
    _data, _a, b = store
    for fmt in exporter.FORMATS:
        check(fmt, body(client, fmt, q=Q, index_version=b), attributions(data_dir, "b"))


def test_a_record_export_names_the_sources_of_the_index_it_names(
    client: TestClient, data_dir: Path, store: tuple[Path, str, str]
) -> None:
    """A search record saved on `a`, exported after `b` is served: `a`'s snapshot attributes its abstracts."""
    _data, _a, b = store
    record_id = save(client, Q)
    point_current(data_dir, b)
    assert client.app.state.index.load()  # type: ignore[attr-defined]
    for fmt in exporter.FORMATS:
        check(fmt, body(client, fmt, record_id=record_id), attributions(data_dir, "a"))


def test_a_pinned_index_whose_snapshot_is_gone_is_409_not_an_unattributed_export(
    data_dir: Path, store: tuple[Path, str, str]
) -> None:
    _data, _a, b = store
    shutil.rmtree(data_dir / "snapshots" / "b")
    with TestClient(make_app(data_dir)) as c:
        r = c.get(EXPORT, params={"format": "ris", "q": Q, "index_version": b})
        assert r.status_code == 409, r.text
        assert r.json()["error"]["code"] == "API_INDEX_VERSION_UNAVAILABLE"
        assert "x-total" not in r.headers  # refused before the stream
        assert (
            c.get(EXPORT, params={"format": "ris", "q": Q}).status_code == 200
        )  # the served one still exports


def test_a_pinned_snapshot_is_verified_once_and_kept(
    client: TestClient, store: tuple[Path, str, str]
) -> None:
    _data, _a, b = store
    state = client.app.state.index  # type: ignore[attr-defined]
    first = state.pinned_records(b)
    assert first is not None and state.pinned_records(b) is first
    assert state.pinned_records(state.engine.index_version) is state.served.records  # the served one's own


def test_op_export_without_the_snapshot_fails_and_writes_nothing(data_dir: Path, tmp_path: Path) -> None:
    shutil.rmtree(data_dir / "snapshots" / "a")
    out = tmp_path / "cli.ris"
    assert cli.main(["--data-dir", str(data_dir), "export", Q, "--format", "ris", "--out", str(out)]) != 0
    assert not out.exists()


def test_a_snapshot_that_wont_verify_is_remembered_not_rehashed_per_request(
    data_dir: Path, store: tuple[Path, str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """As a refused pin is: one verifying attempt per `refusal_seconds` (or reload), not one per export."""
    from openproceedings.api import state as state_module

    _data, _a, b = store
    shutil.rmtree(data_dir / "snapshots" / "b")
    real, calls = state_module.snapshot_records, []

    def counted(*args: Any) -> RecordFile:
        calls.append(args[2])
        return real(*args)

    monkeypatch.setattr(state_module, "snapshot_records", counted)
    with TestClient(make_app(data_dir)) as c:
        calls.clear()  # the served index's own load
        for _ in range(3):
            assert c.get(EXPORT, params={"format": "csv", "q": Q, "index_version": b}).status_code == 409
        assert calls == [b]
        assert c.app.state.index.load()  # type: ignore[attr-defined]  # a reload looks again
        assert c.get(EXPORT, params={"format": "csv", "q": Q, "index_version": b}).status_code == 409
        assert calls == [b, b]
