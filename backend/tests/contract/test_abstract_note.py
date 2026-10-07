"""A submission-time abstract says so (TASK-210): `GET /search` hits and `GET /papers/{id}` carry `abstract_note`,
and every export format the same sentence (`SUBMISSION_NOTE`), read from the served snapshot's attributions.

The 5k fixture's first 300 records as `attributed` makes them; of one venue-year's three papers with an
attributed abstract, `submitted` takes it from an ICML submission page (an `icml_site` claim whose evidence says
it is as submitted, as TASK-207's 1997 and 1998 claims do), `published` from an ICML page as published (2001-2007's
evidence), and `other` keeps its own source. Nothing about the record changes but a claim, so this is what the
served corpus's 1997 and 1998 records look like to the API."""

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
from openproceedings.ingest.dedup import AS_SUBMITTED, SUBMISSION_NOTE
from openproceedings.ingest.record import Claim, PaperRecord
from refaudit.bibtex import parse_string
from scholarmend.parse import parse_ris

from tests.contract.conftest import BUILT, attributed, make_app
from tests.contract.test_takedowns import DATE, FORMATS, _build, exported, listing
from tests.contract.test_twins import _three
from tests.fixtures.corpus.synthetic_5k import records

type Papers = tuple[Path, PaperRecord, PaperRecord, PaperRecord]  # data, submitted, published, other

PAGE_98 = "http://www.cs.wisc.edu:80/icml98/papers/paper2.html"
CAPTURE_98 = f"https://web.archive.org/web/19991009084141id_/{PAGE_98}"
PAGE_03 = "http://www.hpl.hp.com:80/conferences/icml2003/allAbstracts.html"
CAPTURE_03 = f"https://web.archive.org/web/20030628150843id_/{PAGE_03}"


def _from_site(r: PaperRecord, capture: str, evidence: str) -> PaperRecord:
    """`r` with its abstract credited to an official ICML page: an `icml_site` claim, every abstract claim
    precedence would rank above it dropped (its `ris` one, ranked below, is kept)."""
    kept = tuple(c for c in r.provenance if c.field != "abstract" or c.source == "ris")
    claim = Claim(
        field="abstract",
        value=r.abstract,
        source="icml_site",
        url=capture,
        fetched_at=BUILT,
        evidence=evidence,
    )
    return r.model_copy(update={"provenance": (*kept, claim)})


@pytest.fixture(scope="module")
def papers(tmp_path_factory: pytest.TempPathFactory) -> Papers:
    data = tmp_path_factory.mktemp("note") / "data"
    every = [attributed(r) for r in list(records())[:300]]
    first, second, other = _three(every)
    changed = {
        first.id: _from_site(
            first, CAPTURE_98, f"official ICML 1998 page {PAGE_98}, Internet Archive capture {CAPTURE_98}: "
            f"{AS_SUBMITTED}; the page's contact details are not kept",
        ),
        second.id: _from_site(
            second, CAPTURE_03, f"official ICML 2003 page {PAGE_03}, Internet Archive capture {CAPTURE_03}"
        ),
    }  # fmt: skip
    version = _build([changed.get(p.id, p) for p in every], data, "note", frozenset())
    (data / "indexes" / "current").symlink_to(version)
    return data, changed[first.id], changed[second.id], other


@pytest.fixture
def data(papers: Papers, tmp_path: Path) -> Path:
    shutil.copytree(papers[0], tmp_path / "data", symlinks=True)
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


def _hits(client: TestClient, p: PaperRecord) -> dict[str, dict[str, object]]:
    body = client.get("/api/v1/search", params={"q": _cell(p), "limit": 200}).json()
    return {h["id"]: h for h in body["hits"]}


# --- the API ---------------------------------------------------------------------------------------------------
def test_a_submission_time_abstract_has_the_note_on_its_hit_and_its_paper(
    client: TestClient, papers: Papers
) -> None:
    _, submitted, published, other = papers
    hits = _hits(client, submitted)
    assert hits[submitted.id]["abstract_note"] == SUBMISSION_NOTE
    assert hits[submitted.id]["abstract_source"] == {
        "source": "icml_site",
        "origin": "icml_site",
        "url": CAPTURE_98,
    }
    assert hits[published.id]["abstract_source"] == {
        "source": "icml_site",
        "origin": "icml_site",
        "url": CAPTURE_03,
    }
    assert all(h["abstract_note"] is None for rid, h in hits.items() if rid != submitted.id)
    page = lambda rid: client.get(f"/api/v1/papers/{rid}").json()  # noqa: E731
    assert page(submitted.id)["abstract_note"] == SUBMISSION_NOTE
    assert page(published.id)["abstract_note"] is None and page(other.id)["abstract_note"] is None
    with_q = client.get(f"/api/v1/papers/{submitted.id}", params={"q": _cell(submitted)}).json()
    assert with_q["matched"] is True and with_q["abstract_note"] == SUBMISSION_NOTE


def test_a_withheld_submission_time_abstract_has_no_note(data: Path, papers: Papers) -> None:
    """A takedown (decision-022): no abstract is shown, so nothing is said of it."""
    _, submitted, _, _ = papers
    listing(data, submitted.id)
    with TestClient(make_app(data)) as c:
        hit = _hits(c, submitted)[submitted.id]
        assert hit["abstract_withheld"] is True and hit["abstract_note"] is None
        body = c.get(f"/api/v1/papers/{submitted.id}").json()
        assert body["abstract_withheld"] is True and body["abstract_note"] is None
        for fmt in FORMATS:
            assert SUBMISSION_NOTE not in exported(c, fmt, q=_cell(submitted))


# --- every export ----------------------------------------------------------------------------------------------
def _notes_in(fmt: str, text: str) -> dict[str, str | None]:
    """Each record's note as the export says it, read back with the reference parsers."""
    if fmt == "ris":
        out: dict[str, str | None] = {}
        for r in parse_ris(text, "x.ris"):
            notes = r.fields["N1"]
            said = [n for n in notes if n == SUBMISSION_NOTE]
            assert len(said) <= 1 and notes[-1].startswith("openproceedings ")  # provenance stays last
            if said:  # right after the source it qualifies
                assert notes[notes.index(SUBMISSION_NOTE) - 1].startswith(
                    "Abstract source: ICML conference site "
                )
            out[r.first("ID")] = said[0] if said else None
        return out
    if fmt == "bibtex":
        return {e.fields["openproceedings_id"]: e.fields.get("abstract_note") for e in parse_string(text)}
    if fmt == "csv":
        rows = csv.DictReader(io.StringIO(text.removeprefix("﻿")))
        assert rows.fieldnames is not None and rows.fieldnames[-1] == "abstract_note"
        return {row["id"]: row["abstract_note"] or None for row in rows}
    return {(o := json.loads(line))["id"]: o.get("abstract_note") for line in text.splitlines()}


@pytest.mark.parametrize("fmt", FORMATS)
def test_every_format_carries_the_note_on_the_submission_time_abstract_only(
    client: TestClient, papers: Papers, fmt: str
) -> None:
    _, submitted, published, other = papers
    said = _notes_in(fmt, exported(client, fmt, q=_cell(submitted)))
    assert said[submitted.id] == SUBMISSION_NOTE
    assert {published.id, other.id} <= set(said)
    assert all(note is None for rid, note in said.items() if rid != submitted.id)


def test_op_export_carries_the_note(data: Path, papers: Papers, capsys: pytest.CaptureFixture[str]) -> None:
    _, submitted, _, _ = papers
    assert cli.main(["--data-dir", str(data), "export", _cell(submitted), "--format", "jsonl"]) == 0
    assert _notes_in("jsonl", capsys.readouterr().out)[submitted.id] == SUBMISSION_NOTE
