"""A record whose author or keyword list the ingest caps cut (decision-054, TASK-280) says so in every export: BibTeX
writes `and others` after the last kept author, RIS one `N1` (no `AU` line that isn't a person), CSV the last column
`lists_cut` and JSONL a `lists_cut` object, from the snapshot's `RecordFile.lists_cut`; `GET /export` and `op export`
alike. A record with no cut list exports byte for byte as without the map (CSV aside: its last column is empty)."""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from openproceedings import cli, takedown_check
from openproceedings import export as exporter
from openproceedings.api import export as route
from openproceedings.api.state import snapshot_records
from openproceedings.ingest.caps import MAX_AUTHORS, MAX_KEYWORDS, cap_record
from openproceedings.ingest.record import Claim, PaperRecord
from refaudit.bibtex import parse_string
from scholarmend.parse import parse_ris

from tests.contract.conftest import BUILT, attributed, make_app
from tests.contract.test_takedowns import DATE, FORMATS, _build, exported
from tests.fixtures.corpus.synthetic_5k import records

type Store = tuple[Path, PaperRecord, PaperRecord, PaperRecord]  # data, many authors, many keywords, another

AUTHORS = tuple(f"Author, A{i}" for i in range(MAX_AUTHORS + 112))  # 612: the first 500 are kept
KEYWORDS = tuple(f"keyword {i}" for i in range(MAX_KEYWORDS + 50))  # 250: the first 200 are kept


def _many(r: PaperRecord, field: str, values: tuple[str, ...]) -> PaperRecord:
    """`r` with a source's over-long `field` list, record and claim, capped as the snapshot build caps it."""
    claim = Claim(field=field, value=values, source="ris", fetched_at=BUILT, evidence=f"mended.ris:{field}")  # type: ignore[arg-type]
    kept = tuple(c for c in r.provenance if c.field != field)
    return cap_record(r.model_copy(update={field: values, "provenance": (*kept, claim)}))


@pytest.fixture(scope="module")
def store(tmp_path_factory: pytest.TempPathFactory) -> Store:
    data = tmp_path_factory.mktemp("lists-cut") / "data"
    papers = [attributed(r) for r in list(records())[:300]]
    accepted = [p for p in papers if p.status == "accepted"]
    many_authors, many_keywords, other = _many(accepted[0], "authors", AUTHORS), _many(accepted[1], "keywords", KEYWORDS), accepted[2]  # fmt: skip
    papers = [{many_authors.id: many_authors, many_keywords.id: many_keywords}.get(p.id, p) for p in papers]
    version = _build(papers, data, "cut", frozenset())
    (data / "indexes" / "current").symlink_to(version)
    return data, many_authors, many_keywords, other


@pytest.fixture(autouse=True)
def fixed_date(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(exporter, "utc_date", lambda: DATE)
    monkeypatch.setattr(route, "utc_date", lambda: DATE)


@pytest.fixture
def client(store: Store) -> Iterator[TestClient]:
    with TestClient(make_app(store[0])) as c:
        yield c


def _q(*papers: PaperRecord) -> str:
    """A query for each paper's venue-year cell (and so for other records too)."""
    return " OR ".join(f"({takedown_check.cell_query(p.id)})" for p in papers)


def test_the_snapshot_reader_names_each_cut_list_and_how_long_it_was(store: Store) -> None:
    data, many_authors, many_keywords, _ = store
    index = (data / "indexes" / "current").resolve()
    found = snapshot_records(data, index, index.name).lists_cut
    assert found == {
        many_authors.id: {"authors": len(AUTHORS)},
        many_keywords.id: {"keywords": len(KEYWORDS)},
    }
    assert len(many_authors.authors) == MAX_AUTHORS and len(many_keywords.keywords) == MAX_KEYWORDS


def test_bibtex_writes_and_others_after_the_last_kept_author(client: TestClient, store: Store) -> None:
    _, many_authors, many_keywords, _ = store
    entries = {
        e.fields["openproceedings_id"]: e
        for e in parse_string(exported(client, "bibtex", q=_q(many_authors, many_keywords)))
    }
    names = entries[many_authors.id].fields["author"].split(" and ")
    assert names[-1] == "others" and names[:-1] == list(AUTHORS[:MAX_AUTHORS])
    assert "others" not in entries[many_keywords.id].fields.get("author", "")  # its authors weren't cut


def test_ris_says_the_author_list_was_cut_in_one_note_and_lists_only_people(
    client: TestClient, store: Store
) -> None:
    _, many_authors, many_keywords, _ = store
    by_id = {
        r.first("ID"): r
        for r in parse_ris(exported(client, "ris", q=_q(many_authors, many_keywords)), "x.ris")
    }
    rec = by_id[many_authors.id]
    assert rec.fields["AU"] == list(AUTHORS[:MAX_AUTHORS])  # no "et al." line
    notes = rec.fields["N1"]
    assert notes[0] == exporter.authors_cut(MAX_AUTHORS, len(AUTHORS)) and notes[-1].startswith(
        "openproceedings "
    )
    assert (
        notes[0]
        == "Author list cut: the first 500 of the 612 authors its source lists are given (decision-054)."
    )
    assert not any(n.startswith("Author list cut") for n in by_id[many_keywords.id].fields["N1"])


def test_csv_and_jsonl_name_each_cut_list(client: TestClient, store: Store) -> None:
    _, many_authors, many_keywords, other = store
    q = _q(many_authors, many_keywords, other)
    rows = {
        row["id"]: row for row in csv.DictReader(io.StringIO(exported(client, "csv", q=q).removeprefix("﻿")))
    }
    assert exporter.CSV_COLUMNS[-1] == "lists_cut"
    assert (rows[many_authors.id]["lists_cut"], rows[many_keywords.id]["lists_cut"], rows[other.id]["lists_cut"]) == (
        f"authors {len(AUTHORS)}", f"keywords {len(KEYWORDS)}", ""
    )  # fmt: skip
    objs = {o["id"]: o for o in map(json.loads, exported(client, "jsonl", q=q).splitlines())}
    assert objs[many_authors.id]["lists_cut"] == {"authors": len(AUTHORS)}
    assert objs[many_keywords.id]["lists_cut"] == {"keywords": len(KEYWORDS)}
    assert "lists_cut" not in objs[other.id]  # only on a record with a cut list


def test_op_export_says_so_too(store: Store, capsys: pytest.CaptureFixture[str]) -> None:
    data, many_authors, _, _ = store
    assert cli.main(["--data-dir", str(data), "export", _q(many_authors), "--format", "bibtex"]) == 0
    entries = {e.fields["openproceedings_id"]: e for e in parse_string(capsys.readouterr().out)}
    assert entries[many_authors.id].fields["author"].endswith(" and others")
    assert not any(
        e.fields.get("author", "").endswith(" and others") for i, e in entries.items() if i != many_authors.id
    )


def test_a_record_with_no_cut_list_exports_byte_for_byte_as_without_the_map(store: Store) -> None:
    *_, other = store
    doc = [{"id": other.id, **{k: v for k, v in other.model_dump(mode="json").items() if k != "provenance"}}]
    prov = exporter.Provenance("v", "h", DATE)
    for fmt in FORMATS:
        with_map = "".join(
            exporter.entries(fmt, doc, prov, sources={other.id: None}, lists_cut={"x": {"authors": 9}})
        )
        without = "".join(exporter.entries(fmt, doc, prov, sources={other.id: None}))
        assert with_map == without
        if fmt != "csv":
            assert (
                "lists_cut" not in with_map
                and "Author list cut" not in with_map
                and " and others" not in with_map
            )


def test_an_author_named_others_is_still_one_person_beside_the_cut(store: Store) -> None:
    *_, other = store
    doc = [{**other.model_dump(mode="json"), "authors": ["others", "Doe, Jane"]}]
    text = "".join(exporter.entries("bibtex", doc, exporter.Provenance("v", "h", DATE), sources={other.id: None},
                                    lists_cut={other.id: {"authors": 900}}))  # fmt: skip
    assert "author = {{others} and Doe, Jane and others}" in text
