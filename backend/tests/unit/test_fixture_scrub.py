"""Privacy regressions for the manual HTTP-capture scrubber."""

from __future__ import annotations

import json

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
