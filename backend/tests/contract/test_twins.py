"""Twin records (decision-029): the API's and the exports' twin ids (TASK-162), and a takedown that follows a
twin link (TASK-163, owner decision 2026-10-02).

Two snapshots of the 5k fixture's first 300 records: `plain`, an older one without twin claims, and `twins`
(current), where three of them (one venue-year) are made twins as ICLR 2017's are: `conf` names `copy` and `copy2`, each copy names `conf` (a two-id claim and two one-id claims). A takedown
of any one withholds all three, everywhere the API serves them and in `op export`; `op takedown check` asks for
each twin to be listed (and so logged) too; and a snapshot build withholds them as it builds."""

from __future__ import annotations

import csv
import io
import json
import shutil
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from openproceedings import cli, takedown_check
from openproceedings import export as exporter
from openproceedings.api import export as route
from openproceedings.ingest.dedup import DedupResult
from openproceedings.ingest.record import Claim, PaperRecord
from openproceedings.ingest.snapshot import withhold
from refaudit.bibtex import parse_string
from scholarmend.parse import parse_ris

from tests.contract.conftest import attributed, make_app, point_current
from tests.contract.test_records import save
from tests.contract.test_takedowns import DATE, FORMATS, _build, exported, fetcher, listing
from tests.fixtures.corpus.synthetic_5k import records

type Twins = tuple[Path, PaperRecord, PaperRecord, PaperRecord, PaperRecord]  # data, conf, copy, copy2, other

FETCHED = datetime(2026, 10, 1, tzinfo=UTC)


def _twin(r: PaperRecord, *ids: str) -> PaperRecord:
    claim = Claim(field="twin", value=ids, source="openreview_v1", fetched_at=FETCHED, evidence="test twins")
    return r.model_copy(update={"provenance": (*r.provenance, claim)})


def _three(papers: list[PaperRecord]) -> list[PaperRecord]:
    """Three papers of one venue-year, each with an attributed abstract."""
    by_cell: dict[tuple[str, int], list[PaperRecord]] = {}
    for p in papers:
        if p.abstract is not None and p.claims("abstract"):
            by_cell.setdefault((p.venue, p.year), []).append(p)
    return next(ps[:3] for ps in by_cell.values() if len(ps) >= 3)


@pytest.fixture(scope="module")
def twins_store(tmp_path_factory: pytest.TempPathFactory) -> Twins:
    data = tmp_path_factory.mktemp("twins") / "data"
    papers = [attributed(r) for r in list(records())[:300]]
    conf, copy, copy2 = _three(papers)
    linked = {
        conf.id: _twin(conf, copy2.id, copy.id),
        copy.id: _twin(copy, conf.id),
        copy2.id: _twin(copy2, conf.id),
    }
    _build(papers, data, "plain", frozenset())  # an older snapshot: the same papers, built before the claims
    papers = [linked.get(p.id, p) for p in papers]
    version = _build(papers, data, "twins", frozenset())
    (data / "indexes" / "current").symlink_to(version)
    other = next(p for p in papers if p.id not in linked and p.abstract is not None)
    return data, linked[conf.id], linked[copy.id], linked[copy2.id], other


@pytest.fixture
def data(twins_store: Twins, tmp_path: Path) -> Path:
    shutil.copytree(twins_store[0], tmp_path / "data", symlinks=True)
    return tmp_path / "data"


@pytest.fixture(autouse=True)
def fixed_date(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(exporter, "utc_date", lambda: DATE)
    monkeypatch.setattr(route, "utc_date", lambda: DATE)


@pytest.fixture
def client(data: Path) -> Iterator[TestClient]:
    with TestClient(make_app(data)) as c:
        yield c


def _cell(p: PaperRecord) -> str:
    return takedown_check.cell_query(p.id)


def _versions(data: Path) -> tuple[str, str]:
    """(plain, twins): the older index without twin claims, and `current`'s."""
    current = (data / "indexes" / "current").resolve().name
    (plain,) = [
        d.name for d in (data / "indexes").iterdir() if d.is_dir() and not d.is_symlink() and d.name != current
        and not d.name.startswith(".")
    ]  # fmt: skip
    return plain, current


def _abstract_out(fmt: str, text: str, r: PaperRecord) -> bool:
    assert r.abstract is not None
    return r.abstract not in text.replace("\r\n", "\n") and r.id in text


# --- TASK-162: the twin ids the API sends ------------------------------------------------------------------
def test_a_paper_names_its_twins_sorted(client: TestClient, twins_store: Twins) -> None:
    _, conf, copy, copy2, other = twins_store
    page = lambda rid: client.get(f"/api/v1/papers/{rid}").json()  # noqa: E731
    assert page(conf.id)["twins"] == sorted([copy.id, copy2.id])  # a two-id claim
    assert page(copy.id)["twins"] == [conf.id] and page(copy2.id)["twins"] == [conf.id]
    assert page(other.id)["twins"] == []
    assert all(client.get(f"/api/v1/papers/{t}").status_code == 200 for t in page(conf.id)["twins"])


def test_each_hit_names_its_twins_and_every_twin_is_still_a_hit(
    client: TestClient, twins_store: Twins
) -> None:
    """Membership is unchanged (guarantee 5): each twin keeps matching on its own text."""
    _, conf, copy, copy2, other = twins_store
    body = client.get("/api/v1/search", params={"q": _cell(conf), "limit": 200}).json()
    hits = {h["id"]: h["twins"] for h in body["hits"]}
    assert hits[conf.id] == sorted([copy.id, copy2.id]) and hits[copy.id] == hits[copy2.id] == [conf.id]
    assert all(t == [] for rid, t in hits.items() if rid not in (conf.id, copy.id, copy2.id))
    assert other.id in hits or body["total"] > 0


# --- TASK-162: the twin ids every export carries -----------------------------------------------------------
def _twins_in(fmt: str, text: str) -> dict[str, list[str]]:
    """Each record's twin ids as the export says them, read back with the reference parsers."""
    if fmt == "ris":
        out = {}
        for r in parse_ris(text, "x.ris"):
            notes = r.fields["N1"]
            assert notes[-1].startswith("openproceedings "), "the provenance line stays the last N1"
            said = [n for n in notes if n.startswith("See also: ")]
            assert len(said) <= 1
            out[r.first("ID")] = said[0].removeprefix("See also: ").split(" (")[0].split("; ") if said else []
        return out
    if fmt == "bibtex":
        return {
            e.fields["openproceedings_id"]: (
                e.fields["openproceedings_twins"].split("; ") if "openproceedings_twins" in e.fields else []
            )
            for e in parse_string(text)
        }
    if fmt == "csv":
        rows = csv.DictReader(io.StringIO(text.removeprefix("﻿")))
        assert rows.fieldnames is not None and rows.fieldnames[-1] == "twins"
        return {row["id"]: row["twins"].split("; ") if row["twins"] else [] for row in rows}
    objs = [json.loads(line) for line in text.splitlines()]
    return {o["id"]: o.get("twins", []) for o in objs}


@pytest.mark.parametrize("fmt", FORMATS)
def test_every_format_carries_the_twin_ids(client: TestClient, twins_store: Twins, fmt: str) -> None:
    _, conf, copy, copy2, _ = twins_store
    said = _twins_in(fmt, exported(client, fmt, q=_cell(conf)))
    assert said[conf.id] == sorted([copy.id, copy2.id]) and said[copy.id] == said[copy2.id] == [conf.id]
    assert all(t == [] for rid, t in said.items() if rid not in (conf.id, copy.id, copy2.id))


def test_the_ris_see_also_line_sits_before_the_abstract_line(client: TestClient, twins_store: Twins) -> None:
    _, conf, copy, copy2, _ = twins_store
    [rec] = [
        r for r in parse_ris(exported(client, "ris", q=_cell(conf)), "x.ris") if r.first("ID") == conf.id
    ]
    notes = rec.fields["N1"]
    assert notes[-3:-1] == [exporter.see_also((copy.id, copy2.id)), notes[-2]]
    assert notes[-2].startswith("Abstract source: ")


def test_a_record_without_a_twin_exports_byte_for_byte_as_without_the_twin_map(
    client: TestClient, twins_store: Twins
) -> None:
    """AC #2: only CSV's last column is new; RIS, BibTeX and JSONL are what they were."""
    _, _, _, _, other = twins_store
    for fmt in FORMATS:
        doc = [
            {"id": other.id, **{k: v for k, v in other.model_dump(mode="json").items() if k != "provenance"}}
        ]
        prov = exporter.Provenance("v", "h", DATE)
        sources = {other.id: None}
        with_map = "".join(exporter.entries(fmt, doc, prov, sources=sources, twins={"x": ("y",)}))
        without = "".join(exporter.entries(fmt, doc, prov, sources=sources))
        assert with_map == without
        if fmt != "csv":
            assert "twins" not in with_map and "See also" not in with_map


def test_op_export_carries_the_twin_ids(
    data: Path, twins_store: Twins, capsys: pytest.CaptureFixture[str]
) -> None:
    _, conf, copy, copy2, _ = twins_store
    assert cli.main(["--data-dir", str(data), "export", _cell(conf), "--format", "jsonl"]) == 0
    said = _twins_in("jsonl", capsys.readouterr().out)
    assert said[conf.id] == sorted([copy.id, copy2.id]) and said[copy.id] == [conf.id]


# --- TASK-163: a takedown follows twin links -----------------------------------------------------------------
def _withheld(client: TestClient, rid: str) -> bool:
    body = client.get(f"/api/v1/papers/{rid}").json()
    return bool(body["abstract_withheld"]) and body["paper"]["abstract"] is None


@pytest.mark.parametrize("which", [1, 2, 3])
def test_a_takedown_of_any_twin_withholds_every_twin(data: Path, twins_store: Twins, which: int) -> None:
    _, conf, copy, copy2, other = twins_store
    listing(data, twins_store[which].id)
    with TestClient(make_app(data)) as c:
        assert all(_withheld(c, r.id) for r in (conf, copy, copy2))
        assert not _withheld(c, other.id)
        hits = {
            h["id"]: h
            for h in c.get("/api/v1/search", params={"q": _cell(conf), "limit": 200}).json()["hits"]
        }
        assert all(
            hits[r.id]["abstract_withheld"] and hits[r.id]["abstract"] is None for r in (conf, copy, copy2)
        )
        for fmt in FORMATS:
            text = exported(c, fmt, q=_cell(conf))
            for r in (conf, copy, copy2):
                assert r.abstract is not None and r.abstract not in text.replace("\r\n", "\n")


def test_op_export_withholds_every_twin(
    data: Path, twins_store: Twins, capsys: pytest.CaptureFixture[str]
) -> None:
    _, conf, copy, copy2, _ = twins_store
    listing(data, copy2.id)
    assert cli.main(["--data-dir", str(data), "export", _cell(conf), "--format", "jsonl"]) == 0
    objs = {o["id"]: o for o in map(json.loads, capsys.readouterr().out.splitlines())}
    assert all(objs[r.id]["abstract"] is None and objs[r.id]["abstract_withheld_reason"] == "takedown"
               for r in (conf, copy, copy2))  # fmt: skip


def test_the_check_asks_for_every_twin_to_be_listed_and_logged(data: Path, twins_store: Twins) -> None:
    _, conf, copy, copy2, _ = twins_store
    listing(data, conf.id)
    with TestClient(make_app(data)) as c:
        problems = takedown_check.check(fetcher(c), frozenset({conf.id})).problems
    assert sorted(p for p in problems if "twin" in p) == sorted(
        f"{t}: the twin of listed {conf.id} (decision-029, the same paper), withheld with it; list it too and "
        "log a `withheld` entry for it"
        for t in (copy.id, copy2.id)
    )
    listing(data, conf.id, copy.id, copy2.id)
    with TestClient(make_app(data)) as c:
        listed = frozenset({conf.id, copy.id, copy2.id})
        assert [p for p in takedown_check.check(fetcher(c), listed).problems if "twin" in p] == []


def test_a_snapshot_build_withholds_the_twins_of_a_listed_paper(twins_store: Twins) -> None:
    _, conf, copy, copy2, other = twins_store
    result = DedupResult(tuple(sorted((conf, copy, copy2, other), key=lambda p: p.id)), (), ())
    done = withhold(result, frozenset({copy.id}))
    assert done.withheld == {conf.id, copy.id, copy2.id}
    assert done.twins == {conf.id: copy.id, copy2.id: copy.id}  # copy2 reached through conf, from copy
    assert all(r.abstract is None for r in done.result.records if r.id != other.id)
    assert withhold(result, frozenset({other.id})).twins == {}


# --- TASK-163 across index versions: an older snapshot without twin claims -----------------------------
@pytest.mark.parametrize("fmt", FORMATS)
def test_a_pinned_older_version_withholds_the_twins_by_the_served_snapshots_claims(
    data: Path, twins_store: Twins, fmt: str
) -> None:
    """`plain` holds no twin claim; the served snapshot's (`Served.withheld_in`) still link its ids."""
    _, conf, copy, copy2, _ = twins_store
    plain, _ = _versions(data)
    listing(data, conf.id)
    with TestClient(make_app(data)) as c:
        text = exported(c, fmt, q=_cell(conf), index_version=plain)
    assert all(_abstract_out(fmt, text, r) for r in (conf, copy, copy2))
    assert "See also" not in text and "openproceedings_twins" not in text  # plain's own records name none


def test_a_record_export_pinned_to_the_older_version_withholds_the_twins(data: Path, twins_store: Twins) -> None:
    _, conf, copy, copy2, _ = twins_store
    plain, twins = _versions(data)
    point_current(data, plain)
    with TestClient(make_app(data)) as c:
        record_id = save(c, _cell(conf))
    point_current(data, twins)
    listing(data, copy.id)
    with TestClient(make_app(data)) as c:
        text = exported(c, "jsonl", record_id=record_id)
    objs = {o["id"]: o for o in map(json.loads, text.splitlines())}
    assert all(objs[r.id]["abstract"] is None and objs[r.id]["abstract_withheld_reason"] == "takedown"
               for r in (conf, copy, copy2))  # fmt: skip


def test_op_export_of_the_older_version_follows_the_current_indexs_twin_claims(
    data: Path, twins_store: Twins, capsys: pytest.CaptureFixture[str]
) -> None:
    _, conf, copy, copy2, _ = twins_store
    plain, _ = _versions(data)
    listing(data, copy2.id)
    argv = ["--data-dir", str(data), "export", _cell(conf), "--index", plain, "--format", "jsonl"]
    assert cli.main(argv) == 0
    out, err = capsys.readouterr()
    objs = {o["id"]: o for o in map(json.loads, out.splitlines())}
    assert all(objs[r.id]["abstract"] is None for r in (conf, copy, copy2))
    assert "twin links" not in err


def test_op_export_says_so_when_the_current_snapshot_cant_be_read(
    data: Path, twins_store: Twins, capsys: pytest.CaptureFixture[str]
) -> None:
    """The exported snapshot's own links still apply (here none): a warning on stderr and one ERROR line."""
    _, conf, copy, copy2, _ = twins_store
    plain, _ = _versions(data)
    records = data / "snapshots" / "twins" / "records.jsonl"
    records.chmod(0o644)
    records.write_bytes(records.read_bytes() + b"\n")  # no longer hashes to its manifest
    listing(data, copy2.id)
    argv = ["--data-dir", str(data), "--log-level", "debug", "export", _cell(conf), "--index", plain,
            "--format", "jsonl"]  # fmt: skip
    assert cli.main(argv) == 0
    out, err = capsys.readouterr()
    objs = {o["id"]: o for o in map(json.loads, out.splitlines())}
    assert objs[copy2.id]["abstract"] is None and objs[conf.id]["abstract"] is not None
    assert "the takedown list follows only the exported snapshot's twin links" in err
    lines = [json.loads(x) for x in err.splitlines() if x.startswith("{")]
    [line] = [x for x in lines if x["event"] == "takedown_twins_unavailable"]
    assert (line["level"], line["error"], line["reason"]) == ("ERROR", "SnapshotError", "snapshot_invalid")


# --- decision-021: an export whose snapshot can't be verified names no twins -------------------------------
@pytest.mark.parametrize("fmt", FORMATS)
def test_an_unverifiable_pinned_snapshot_names_no_twins(data: Path, twins_store: Twins, fmt: str) -> None:
    _, conf, _, _, _ = twins_store
    plain, twins = _versions(data)
    point_current(data, plain)
    records = data / "snapshots" / "twins" / "records.jsonl"
    records.chmod(0o644)
    records.write_bytes(records.read_bytes() + b"\n")
    with TestClient(make_app(data)) as c:
        text = exported(c, fmt, q=_cell(conf), index_version=twins)
    assert all(t == [] for t in _twins_in(fmt, text).values())
    assert "See also" not in text and "openproceedings_twins" not in text


def test_op_export_of_an_unverifiable_snapshot_names_no_twins(
    data: Path, twins_store: Twins, capsys: pytest.CaptureFixture[str]
) -> None:
    _, conf, _, _, _ = twins_store
    records = data / "snapshots" / "twins" / "records.jsonl"
    records.chmod(0o644)
    records.write_bytes(records.read_bytes() + b"\n")
    assert cli.main(["--data-dir", str(data), "export", _cell(conf), "--format", "jsonl"]) == 0
    assert all(t == [] for t in _twins_in("jsonl", capsys.readouterr().out).values())
