"""A record whose author or keyword list the ingest caps cut (decision-054, TASK-280) says so in every export: BibTeX
writes `and others` after the last kept author, RIS one `N1` (no `AU` line that isn't a person), CSV the last column
`lists_cut` and JSONL a `lists_cut` object, from the snapshot's `RecordFile.lists_cut`; `GET /export` and `op export`
alike. A record with no cut list exports byte for byte as without the map (CSV aside: its last column is empty)."""

from __future__ import annotations

import csv
import io
import json
import shutil
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
from tests.contract.test_compare import COMPARE, NO_COOLDOWN, RIS, by_title
from tests.contract.test_records import save
from tests.contract.test_takedowns import DATE, EXPORT, FORMATS, _build, exported
from tests.fixtures.corpus.synthetic_5k import records

# data, many authors, many keywords, the other cases by name (`_cases`), and a record with no cut list
type Store = tuple[Path, PaperRecord, PaperRecord, dict[str, PaperRecord], PaperRecord]

AUTHORS = tuple(f"Author, A{i}" for i in range(MAX_AUTHORS + 112))  # 612: the first 500 are kept
KEYWORDS = tuple(f"keyword {i}" for i in range(MAX_KEYWORDS + 50))  # 250: the first 200 are kept
SEVEN_HUNDRED = tuple(f"Author, B{i}" for i in range(700))


def _many(r: PaperRecord, field: str, values: tuple[str, ...]) -> PaperRecord:
    """`r` with a source's over-long `field` list, record and claim, capped as the snapshot build caps it."""
    claim = Claim(field=field, value=values, source="ris", fetched_at=BUILT, evidence=f"mended.ris:{field}")  # type: ignore[arg-type]
    kept = tuple(c for c in r.provenance if c.field != field)
    return cap_record(r.model_copy(update={field: values, "provenance": (*kept, claim)}))


def _authors_claim(values: tuple[str, ...], source: str, evidence: str) -> Claim:
    return Claim(field="authors", value=values, source=source, fetched_at=BUILT, evidence=evidence)  # type: ignore[arg-type]


# a source of each venue's own records beside `ris` (one claim per field and source)
_OWN = {"ICML": "pmlr", "ICLR": "openreview_v2", "NeurIPS": "neurips_proceedings"}


def _cases(papers: list[PaperRecord]) -> dict[str, PaperRecord]:
    """- `rejected`: a paper not accepted, its author list cut (its RIS note comes after the status sentence).
    - `losing`: a record of a few authors with a losing claim cut from 612 to 500: its own list wasn't cut.
    - `two_totals`, `two_totals_reversed`: two claims of the record's own list, cut from 700 and from 600, in both
      orders: the list's source listed the most, 700."""
    accepted = [p for p in papers if p.status == "accepted"]
    rejected = next(p for p in papers if p.status != "accepted")
    losing = accepted[3]
    out = {
        "rejected": _many(rejected, "authors", AUTHORS),
        "losing": cap_record(
            losing.model_copy(
                update={
                    "provenance": (*losing.provenance, _authors_claim(AUTHORS, _OWN[losing.venue], "losing"))
                }
            )
        ),
    }
    for name, r, order in (
        ("two_totals", accepted[4], (700, 600)),
        ("two_totals_reversed", accepted[5], (600, 700)),
    ):
        kept = tuple(c for c in r.provenance if c.field != "authors")
        sources = ("ris", _OWN[r.venue])
        claims = tuple(
            _authors_claim(SEVEN_HUNDRED[:n], src, f"listed {n}")
            for n, src in zip(order, sources, strict=True)
        )
        out[name] = cap_record(
            r.model_copy(update={"authors": SEVEN_HUNDRED, "provenance": (*kept, *claims)})
        )
    return out


def _papers() -> tuple[list[PaperRecord], PaperRecord, PaperRecord, dict[str, PaperRecord], PaperRecord]:
    """The corpus with every case of this module in it, and the cases."""
    papers = [attributed(r) for r in list(records())[:300]]
    accepted = [p for p in papers if p.status == "accepted"]
    many_authors, many_keywords, other = _many(accepted[0], "authors", AUTHORS), _many(accepted[1], "keywords", KEYWORDS), accepted[2]  # fmt: skip
    cases = _cases(papers)
    swap = {r.id: r for r in (many_authors, many_keywords, *cases.values())}
    return [swap.get(p.id, p) for p in papers], many_authors, many_keywords, cases, other


@pytest.fixture(scope="module")
def store(tmp_path_factory: pytest.TempPathFactory) -> Store:
    data = tmp_path_factory.mktemp("lists-cut") / "data"
    papers, many_authors, many_keywords, cases, other = _papers()
    version = _build(papers, data, "cut", frozenset())
    (data / "indexes" / "current").symlink_to(version)
    return data, many_authors, many_keywords, cases, other


@pytest.fixture(scope="module")
def pinned_store(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, str]:
    """A data directory serving the corpus with no cut list (`plain`), beside an index of it with the cut lists
    (`cut`, the version returned), which an export can pin."""
    data = tmp_path_factory.mktemp("lists-cut-pinned") / "data"
    papers, *_ = _papers()
    plain = _build([attributed(r) for r in list(records())[:300]], data, "plain", frozenset())
    cut = _build(papers, data, "cut", frozenset())
    assert plain != cut
    (data / "indexes" / "current").symlink_to(plain)
    return data, cut


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
    data, many_authors, many_keywords, cases, _ = store
    index = (data / "indexes" / "current").resolve()
    found = snapshot_records(data, index, index.name).lists_cut
    assert found == {
        many_authors.id: {"authors": len(AUTHORS)},
        many_keywords.id: {"keywords": len(KEYWORDS)},
        cases["rejected"].id: {"authors": len(AUTHORS)},
        # the most its source listed, whichever claim comes first
        cases["two_totals"].id: {"authors": 700},
        cases["two_totals_reversed"].id: {"authors": 700},
    }  # never `losing`: only a losing claim was cut, not the record's own list
    assert len(cases["losing"].authors) < MAX_AUTHORS
    assert len(many_authors.authors) == MAX_AUTHORS and len(many_keywords.keywords) == MAX_KEYWORDS


def test_bibtex_writes_and_others_after_the_last_kept_author(client: TestClient, store: Store) -> None:
    _, many_authors, many_keywords, _, _ = store
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
    _, many_authors, many_keywords, _, _ = store
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
        == "Author list cut: only the first 500 of the 612 authors listed by its source are given (decision-054)."
    )
    assert not any(n.startswith("Author list cut") for n in by_id[many_keywords.id].fields["N1"])


def test_csv_and_jsonl_name_each_cut_list(client: TestClient, store: Store) -> None:
    _, many_authors, many_keywords, _, other = store
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
    data, many_authors, _, cases, _ = store
    assert cli.main(["--data-dir", str(data), "export", _q(many_authors), "--format", "bibtex"]) == 0
    entries = {e.fields["openproceedings_id"]: e for e in parse_string(capsys.readouterr().out)}
    cut = {many_authors.id, *(cases[k].id for k in ("rejected", "two_totals", "two_totals_reversed"))}
    assert entries[many_authors.id].fields["author"].endswith(" and others")
    assert {i for i, e in entries.items() if e.fields.get("author", "").endswith(" and others")} <= cut


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


def test_a_rejected_papers_cut_note_comes_right_after_its_status_sentence(
    client: TestClient, store: Store
) -> None:
    _, _, _, cases, _ = store
    rejected = cases["rejected"]
    [rec] = [
        r for r in parse_ris(exported(client, "ris", q=_q(rejected)), "x.ris") if r.first("ID") == rejected.id
    ]
    notes = rec.fields["N1"]
    assert notes[0].startswith("Submitted to ") and notes[1] == exporter.authors_cut(
        MAX_AUTHORS, len(AUTHORS)
    )
    assert notes[-1].startswith("openproceedings ")  # the provenance line stays last


def test_a_record_whose_losing_claim_was_cut_says_nothing_of_it(client: TestClient, store: Store) -> None:
    _, _, _, cases, _ = store
    losing = cases["losing"]
    [entry] = [
        e
        for e in parse_string(exported(client, "bibtex", q=_q(losing)))
        if e.fields["openproceedings_id"] == losing.id
    ]
    assert not entry.fields["author"].endswith(" and others")


def test_a_saved_records_export_says_so_too(client: TestClient, store: Store) -> None:
    _, many_authors, _, _, _ = store
    record_id = save(client, _q(many_authors))
    objs = {o["id"]: o for o in map(json.loads, exported(client, "jsonl", record_id=record_id).splitlines())}
    assert objs[many_authors.id]["lists_cut"] == {"authors": len(AUTHORS)}


def test_the_compare_panels_added_ris_says_so_too(store: Store) -> None:
    data, many_authors, _, _, other = store
    with TestClient(make_app(data, compare_enabled=True, rate_limit=NO_COOLDOWN)) as c:
        r = c.post(
            COMPARE, params={"q": _q(many_authors)}, content=by_title(other).encode("utf-8"), headers=RIS
        )
    assert r.status_code == 200, r.text
    added = {rec.first("ID"): rec for rec in parse_ris(r.json()["added_ris"], "added.ris")}
    assert exporter.authors_cut(MAX_AUTHORS, len(AUTHORS)) in added[many_authors.id].fields["N1"]


def test_an_export_pinned_to_another_index_reads_that_snapshots_cut_lists(
    pinned_store: tuple[Path, str],
) -> None:
    data, cut = pinned_store
    _, many_authors, *_ = _papers()
    with TestClient(make_app(data)) as c:
        served = exported(c, "csv", q=_q(many_authors))
        pinned = exported(c, "csv", q=_q(many_authors), index_version=cut)
    assert f"authors {len(AUTHORS)}" in pinned and f"authors {len(AUTHORS)}" not in served


def test_an_export_whose_snapshot_cant_be_verified_names_no_cut_list(
    pinned_store: tuple[Path, str], tmp_path: Path
) -> None:
    source, cut = pinned_store
    data = tmp_path / "data"
    shutil.copytree(source, data, symlinks=True)
    records_file = data / "snapshots" / "cut" / "records.jsonl"
    records_file.chmod(0o644)
    records_file.write_bytes(records_file.read_bytes() + b"\n")  # no longer hashes to its manifest
    _, many_authors, *_ = _papers()
    with TestClient(make_app(data)) as c:
        # what spec 04 tells a reviewer to check: the export says its snapshot couldn't be verified
        r = c.get(EXPORT, params={"format": "csv", "q": _q(many_authors), "index_version": cut})
        assert r.headers["X-Abstract-Source"] == "unavailable"
        for fmt in FORMATS:
            text = exported(c, fmt, q=_q(many_authors), index_version=cut)
            assert (
                " and others" not in text
                and "Author list cut" not in text
                and f"authors {len(AUTHORS)}" not in text
            )
