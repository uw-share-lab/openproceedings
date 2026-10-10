"""Privacy regressions for the manual HTTP-capture scrubber."""

from __future__ import annotations

import json

import pytest

from tests.fixtures.http import scrub


def test_nested_details_are_scrubbed_recursively() -> None:
    body = {
        "notes": [
            {
                "id": "PublicNote1",
                "content": {},
                "details": {"metadata": {"contact": "real.person@example.edu", "profiles": ["~Real_User1"]}},
            }
        ]
    }
    got, _ = scrub.scrub_json("https://api2.openreview.net/notes", body)
    text = json.dumps(got)
    assert "real.person@example.edu" not in text and "~Real_User1" not in text
    assert "synthetic.person" in text and "~Synthetic_Person" in text


def test_paper_meta_authors_are_found_structurally_regardless_of_attribute_order_or_quotes() -> None:
    page = """<!doctype html><html><head>
    <meta content='A Reordered Title' data-source='publisher' name='citation_title'>
    <meta content='Real Person' data-source='publisher' name='citation_author'>
    <meta content='Real description' data-source='publisher' property='og:description'>
    </head><body><h1>A Reordered Title</h1><p>Real Person</p>
    <div class='abstract extra' id='abstract'>Real abstract text</div></body></html>"""
    got, _ = scrub.scrub_html("https://proceedings.mlr.press/v1/paper.html", page)
    for private in ("A Reordered Title", "Real Person", "Real description", "Real abstract text"):
        assert private not in got
    assert all(
        synthetic in got for synthetic in ("Synthetic title", "Synthetic Author", "Synthetic abstract")
    )


def test_nested_sensitive_containers_remain_suppressed_until_the_outer_close() -> None:
    page = """<html><head><meta name="citation_title" content="Public shell"></head><body>
    <div id="abstract">private before<div>private nested</div>private after</div>
    <span class="authors">Private One<span>Private Two</span>Private Three</span>
    </body></html>"""
    got, _ = scrub.scrub_html("https://proceedings.mlr.press/v1/paper.html", page)
    for private in (
        "private before",
        "private nested",
        "private after",
        "Private One",
        "Private Two",
        "Private Three",
    ):
        assert private not in got
    assert "Synthetic abstract" in got and "Synthetic authors" in got


def test_only_allow_listed_venue_labels_keep_an_at_sign_and_dotless_addresses_are_still_scrubbed() -> None:
    values = {
        "N0": ("venue", "BT@ICLR2024"),  # allow-listed label: kept
        "N1": ("venue", "Tiny Papers @ ICLR 2024 Archive"),  # a bare "@": kept
        "N2": ("venue", "user@localhost"),  # dotless address: scrubbed
        "N3": ("venue", "a.b@mail.example.edu"),
        "N4": ("title", "BT@ICLR2024"),  # the allow-list is for venue labels only
        "N5": ("contact", "user@localhost"),
    }
    body = {"notes": [{"id": i, "content": {k: {"value": v}}} for i, (k, v) in values.items()]}
    got, _ = scrub.scrub_json("https://api2.openreview.net/notes", body)
    out = {n["id"]: next(iter(n["content"].values()))["value"] for n in got["notes"]}
    assert (out["N0"], out["N1"]) == ("BT@ICLR2024", "Tiny Papers @ ICLR 2024 Archive")
    assert all(out[i].startswith("synthetic.person") for i in ("N2", "N3", "N4", "N5"))
    assert scrub.PERSON.search("user@localhost")


def test_a_capture_states_its_own_fetch_date_and_one_without_it_takes_the_default() -> None:
    capture = {
        "url": "https://api2.openreview.net/notes?content.venueid=ICML.cc/2026/Conference",
        "auth": True,
        "status": 200,
        "headers": {"content-type": "application/json"},
        "body": json.dumps({"notes": [], "count": 0}),
    }
    assert scrub.fixture(capture)["_recorded"]["date"] == scrub.RECORDED
    assert scrub.fixture({**capture, "date": "2026-10-05"})["_recorded"]["date"] == "2026-10-05"
    with pytest.raises(ValueError):
        scrub.fixture({**capture, "date": "5 October 2026"})


OAI_PAGE = """<?xml version="1.0" encoding="UTF-8"?>
<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/"><ListRecords>
<record><header><identifier>oai:ojs.aaai.org:article/43116</identifier><datestamp>2026-07-15T06:11:29Z</datestamp>
<setSpec>IASEAI:IASEAI</setSpec></header><metadata>
<oai_dc:dc xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/" xmlns:dc="http://purl.org/dc/elements/1.1/">
<dc:title xml:lang="en-US">A Real Title &amp; More</dc:title>
<dc:creator>Person, Real</dc:creator><dc:creator>Other, Real</dc:creator>
<dc:subject xml:lang="en-US">real keyword</dc:subject>
<dc:description xml:lang="en-US">A real abstract
over two lines.</dc:description>
<dc:publisher xml:lang="en-US">AAAI Press</dc:publisher>
<dc:identifier>https://ojs.aaai.org/index.php/IASEAI/article/view/43116</dc:identifier>
<dc:identifier>10.1609/iaseai.v2i1.43116</dc:identifier>
<dc:source xml:lang="en-US">Proceedings of IASEAI Conference; Vol. 2 No. 1: IASEAI '26; 1-12</dc:source>
</oai_dc:dc></metadata></record>
<record><header status="deleted"><identifier>oai:ojs.aaai.org:article/42953</identifier>
<datestamp>2026-07-15T06:11:29Z</datestamp><setSpec>IASEAI:IASEAI</setSpec></header></record>
<resumptionToken expirationDate="2026-10-10T22:01:20Z" completeListSize="115" cursor="0">abc123</resumptionToken>
</ListRecords></OAI-PMH>
"""


def test_an_oai_page_keeps_its_structure_and_loses_its_free_text() -> None:
    capture = {
        "url": "https://ojs.aaai.org/index.php/IASEAI/oai?verb=ListRecords&metadataPrefix=oai_dc",
        "auth": False,
        "status": 200,
        "headers": {"Content-Type": "text/xml;charset=utf-8", "Set-Cookie": "OJSSID=secret"},
        "body": OAI_PAGE,
        "date": "2026-10-09",
        "run": "manual op ingest ojs",
    }
    got = scrub.fixture(capture)
    text = got["response"]["text"]
    for private in ("A Real Title", "Person, Real", "Other, Real", "real keyword", "A real abstract"):
        assert private not in text
    for kept in (
        "oai:ojs.aaai.org:article/43116",
        "<setSpec>IASEAI:IASEAI</setSpec>",
        'status="deleted"',
        "AAAI Press",
        "10.1609/iaseai.v2i1.43116",
        "Vol. 2 No. 1: IASEAI '26; 1-12",
        'completeListSize="115"',
        ">abc123</resumptionToken>",
        '<dc:title xml:lang="en-US">Synthetic title 1</dc:title>',
        "<dc:creator>Author2, Synthetic</dc:creator><dc:creator>Author3, Synthetic</dc:creator>",
    ):
        assert kept in text
    assert got["response"]["headers"] == {"content-type": "text/xml;charset=utf-8"}  # no cookie
    assert got["_recorded"]["date"] == "2026-10-09"
    from openproceedings.ingest.sources import ojs

    records, token = ojs.parse_page(text)  # still a page the miner reads
    assert [(r.article, r.deleted, r.volume) for r in records] == [(43116, False, 2), (42953, True, None)]
    assert token == "abc123" and records[0].creators == ("Author2, Synthetic", "Author3, Synthetic")
