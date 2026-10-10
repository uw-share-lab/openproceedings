"""Privacy regressions for the manual HTTP-capture scrubber."""

from __future__ import annotations

import json
import re

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


def test_an_oai_page_binding_dublin_core_to_another_prefix_is_refused() -> None:
    other = OAI_PAGE.replace(
        'xmlns:dc="http://purl.org/dc/elements/1.1/"', 'xmlns:d="http://purl.org/dc/elements/1.1/"'
    )
    assert other != OAI_PAGE
    with pytest.raises(ValueError, match=r"prefix\(es\) \['d'\]"):
        scrub.scrub_oai(other)


def test_an_oai_page_binding_dublin_core_as_the_default_namespace_is_refused() -> None:
    page = '<dc:title xmlns="http://purl.org/dc/elements/1.1/">Real title</dc:title>'
    with pytest.raises(ValueError, match=r"prefix\(es\) \[''\]"):
        scrub.scrub_oai(page)


def test_a_self_closing_oai_element_is_left_alone_and_the_next_one_scrubbed() -> None:
    page = "<dc:title/><dc:subject>x</dc:subject><dc:title>Real title</dc:title>"
    out = scrub.scrub_oai(page)
    assert out.startswith("<dc:title/>") and "Real title" not in out and out.count("</dc:title>") == 1


def test_a_crossref_work_list_loses_titles_and_names_and_is_trimmed_to_its_toc() -> None:
    item = {"DOI": "10.1145/1.2", "title": ["Real Title"], "subtitle": ["Real sub"], "type": "proceedings-article",
            "page": "1-9", "author": [{"given": "Real", "family": "Person", "ORCID": "x", "sequence": "first"}]}  # fmt: skip
    foreign = [{**item, "DOI": f"10.1145/9.{n}"} for n in range(5)]
    body = {"status": "ok", "message-type": "work-list",
            "message": {"items": [foreign[0], item, *foreign[1:]], "total-results": 6, "next-cursor": "AoJ"}}  # fmt: skip
    out, trimmed = scrub.scrub_crossref("https://api.crossref.org/works?x", body, "10.1145/1")
    items = out["message"]["items"]
    assert [i["DOI"] for i in items] == ["10.1145/9.0", "10.1145/1.2", "10.1145/9.1", "10.1145/9.2"]
    assert (out["message"]["total-results"], out["message"]["next-cursor"]) == (6, "AoJ")
    assert (
        "Real" not in json.dumps(out)
        and items[1]["page"] == "1-9"
        and items[1]["author"][0]["sequence"] == "first"
    )
    assert trimmed is not None and "from 6 to 4" in trimmed


def test_a_crossref_proceedings_record_keeps_its_title_and_loses_its_editors() -> None:
    body = {"status": "ok", "message-type": "work",
            "message": {"type": "proceedings", "DOI": "10.1145/1", "title": ["Proceedings of X"], "ISBN": ["9"],
                        "editor": [{"given": "Real", "family": "Editor"}]}}  # fmt: skip
    out, _ = scrub.scrub_crossref("https://api.crossref.org/works/10.1145/1", body)
    assert out["message"]["title"] == ["Proceedings of X"] and out["message"]["ISBN"] == ["9"]
    assert "Real" not in json.dumps(out)


def test_a_csv_keeps_ids_types_and_urls_and_its_line_shape() -> None:
    text = '﻿TYPE,ID,TITLE,AUTHOR,ABSTRACT,URL\r\narchival,8,Real title,"A, B and C, D",Real abstract,https://doi.org/10.1145/1.2\r\nnonarchival,9,T,E; F; G,Abs,\r\n'
    out, note = scrub.scrub_csv(text, per_type={"archival": 1, "nonarchival": 1})
    assert out.startswith("﻿TYPE,ID,TITLE,AUTHOR,ABSTRACT,URL\r\n") and note is None
    assert (
        "archival,8,Synthetic title 1,Synthetic Author 2 and Synthetic Author 3,Synthetic abstract text 4.,https://doi.org/10.1145/1.2"
        in out
    )
    assert "Synthetic Author 6; Synthetic Author 7; Synthetic Author 8" in out and "Real" not in out
    assert scrub.scrub_csv(text, keep=1)[1] == "1 of 2 rows kept (order kept)"


FACCT_2022_URL = "https://facctconference.org/2022/acceptedpapers.html"


def _facct_entry(n: int, id_attr: str = "") -> str:
    return (
        f"\n    <h4 {id_attr or f'id={chr(34)}{n}{chr(34)}'}><b>Real Title {n}</b></h4>\n"
        f"    <p><i>Real Person{n}, Real Other{n} and Real Last{n}</i></p><br>\n"
        f"    <p>Real abstract {n}.</p>\n"
        f'    <p><span class="label label-primary"><a href="https://doi.org/10.1145/3531146.{n}">Paper</a></span>\n'
        "      </p>\n"
    )


def _facct_page(*entries: str) -> str:
    return (
        '<html><body><div class="container"><div class="row"><div class="col-lg-12">'
        + "".join(entries)
        + "</div></div></div><footer>site footer</footer></body></html>"
    )


def test_the_facct_2022_page_keeps_its_structure_and_loses_titles_authors_and_abstracts() -> None:
    page = _facct_page(*(_facct_entry(n) for n in range(1, 6)))
    out, note = scrub.scrub_html(FACCT_2022_URL, page, keep=5)
    assert "Real" not in out and note == "5 of 5 entries kept (order kept; the page's HTML otherwise whole)"
    assert out.count('<h4 id="') == 5 and "<footer>site footer</footer>" in out
    assert "https://doi.org/10.1145/3531146.3" in out and '<div class="col-lg-12">' in out
    # the author list keeps its shape: commas, then "and" before the last name
    assert re.search(
        r"<p><i>Synthetic Author \d+, Synthetic Author \d+ and Synthetic Author \d+</i></p>", out
    )
    assert re.search(r"<h4 id=\"1\"><b>Synthetic title \d+</b></h4>", out)


def test_facct_2022_keep_ids_are_kept_past_the_first_entries_and_a_spaced_id_is_read() -> None:
    page = _facct_page(*(_facct_entry(n) for n in range(1, 6)), _facct_entry(17, 'id = "17"'))
    out, note = scrub.scrub_html(FACCT_2022_URL, page, keep_ids=["17"], keep=2)
    assert note == "2 of 6 entries kept (order kept; the page's HTML otherwise whole)"
    assert '<h4 id = "17">' in out and '<h4 id="1">' in out and '<h4 id="2">' not in out
    assert "3531146.17" in out and "Real" not in out


def test_facct_2022_keep_ids_not_on_the_page_are_refused() -> None:
    with pytest.raises(ValueError, match="keep_ids not on the page: 99"):
        scrub.scrub_html(FACCT_2022_URL, _facct_page(_facct_entry(1)), keep_ids=["99"])


def test_a_pmlr_volume_index_keeps_as_many_entries_as_the_capture_asks() -> None:
    block = '<div class="paper">\n  <p class="title">Real Title {n}</p>\n  <span class="authors">Real Person{n}</span>\n</div>'
    page = (
        "<html><body><h1>Volume 81: X</h1>\n"
        + "\n".join(block.format(n=n) for n in range(8))
        + "\n</body></html>"
    )
    url = "https://proceedings.mlr.press/v81/"
    assert scrub.scrub_html(url, page)[1] == "3 of 8 entries kept (3 per kind)"
    out, note = scrub.scrub_html(url, page, keep=5)
    assert note == "5 of 8 entries kept (5 per kind)" and out.count('<div class="paper">') == 5
    assert "Real" not in out


def test_a_capture_may_state_its_own_scrubbed_line() -> None:
    capture = {
        "url": "https://facctconference.org/robots.txt",
        "auth": False,
        "status": 200,
        "headers": {"content-type": "text/plain"},
        "body": "User-agent: *\nDisallow:\n",
    }
    assert scrub.fixture(capture)["_recorded"]["scrubbed"].startswith("decision-004: free text synthetic")
    own = scrub.fixture({**capture, "scrubbed": "nothing to scrub (robots.txt)"})
    assert own["_recorded"]["scrubbed"] == "nothing to scrub (robots.txt)"
    assert own["response"]["text"] == capture["body"]
