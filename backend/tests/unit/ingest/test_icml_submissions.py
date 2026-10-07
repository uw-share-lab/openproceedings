"""ICML 1997 and 1998 abstracts from the official submission pages (TASK-207, owner decision of 2026-10-07).

Those pages are the call for papers' form as each author filled it in: title, authors with postal addresses,
abstract, keywords, the contact author's e-mail address and phone and fax numbers. Only the abstract may be kept,
and no contact detail may reach a record, the snapshot, the index, an export or a log line.

The pages below are synthetic, in the real pages' markup and layouts (decision-004: structure real, text and
contact details invented; `example.org` addresses, `555-01xx` numbers). No network: pages are seeded or scripted.
"""

from __future__ import annotations

import io
import json
import logging
import time
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from openproceedings import export
from openproceedings.engine.index import build_index
from openproceedings.engine.tantivy_engine import TantivyEngine
from openproceedings.ingest.dedup import DedupResult
from openproceedings.ingest.snapshot import RecordFile, render
from openproceedings.ingest.sources import crawl, icml_sites
from openproceedings.ingest.sources.http import Response
from openproceedings.ingest.sources.icml_sites import Entry, SitePage
from openproceedings.query.parser import parse

from tests.unit.ingest.proceedings_helpers import FakeTransport
from tests.unit.ingest.test_dblp import TABLE, stream

T = datetime(2026, 10, 7, 12, tzinfo=UTC)
PROGRAM = "http://cswww.vuse.vanderbilt.edu:80/~icml97/program.html"
PROGRAM_CAPTURE = f"https://web.archive.org/web/19970619200718id_/{PROGRAM}"
PAPER = "http://www.cs.wisc.edu:80/icml98/papers/paper{n}.html"
PAPER_CAPTURE = "https://web.archive.org/web/19991009084141id_/" + PAPER

# Every contact detail the pages below hold. None may leave the parser.
CONTACT = ("example.org", "Example Road", "Springfield", "NJ 08544", "Middletown", "NJ 07748", "555-010", "010-0199",
           "624 9418", "Contact Author", "Synthetic Institute")  # fmt: skip

P1997 = """<body bgcolor="#ffffff">
<p><hr><hr><p>
<h3>Papers to be presented at ICML-97</h3>
<li><a href="#2"> Synthetic title with markup 1</a><br>
<li><a href="#11"> Synthetic Title Two</a><br>
<li><a href="#14"> Synthetic Title Three</a><br>
<p><hr><hr><p>
<a name="2"></a>
<pre>
TITLE: Synthetic title with markup 1

AUTHORS:
\tSynthetic Contact Author
\t 1 Example Road
\t Springfield, NJ 08544-2087
\t author.one@example.org

ABSTRACT:

Synthetic submission abstract one,
on two lines.

KEYWORDS:

  synthetic, keywords

EMAIL: author.one@example.org
VOICE: 555-010-0199
FAX:   555-010-0198
</pre>
<p><hr><p>
<a name="11"></a>   (62-63)
<pre>
Title:
   Synthetic Title Two

Author(s) with address(es):

   Synthetic Contact Author, Synthetic Institute

Abstract (200 word maximum):
--------
Synthetic abstract two: state t+1 of a + b, in 1993-1997.

Keywords:
   synthetic

Email address of contact author:
   two@example.org

Phone number of contact author:
   +(34-1) 624 9418

</pre>
<p><hr><p>
<a name="14"></a>
<pre>
\tSynthetic Title Three

        Synthetic Contact Author, Synthetic Institute, Springfield

Synthetic text with no abstract heading.

Phone number: (555) 010-0100
</pre>
"""

P1998_PRE = """<HTML>
<HEAD>
<TITLE>ICML98 - Submission #101</TITLE>
</HEAD>

<BODY>

<H1>ICML-98 Submission #101</H1>

<PRE WIDTH=80>
Synthetic title with
markup 1

\t* Synthetic Contact Author
\t\tSynthetic Institute,
\t\t1 Example Road, Springfield, Spain,
\t\temail: author@example.org

Abstract:

  Synthetic abstract from the
  submission, Informática.

Keywords: synthetic

Email address of contact author: author@example.org

Phone number of contact author: +(34-1) 624 9418
</PRE>
</BODY>
</HTML>
"""

P1998_HTML = """<HTML>
<HEAD>
<TITLE>ICML98 - PAPER 2</TITLE>
</HEAD>
<H1>ICML-98 Submission #2</H1>


<BODY>

Title:     Synthetic Title Two
<P>
Authors: <OL>
           Synthetic Contact Author <BR>
           480 Example Road     <BR>
           Middletown, NJ 07748     <BR>
</OL>
Abstract:
   <OL>    Synthetic abstract two
           on two lines.
<P>
</OL>
Keywords: synthetic
<P>
Email: two@example.org
<P>
Phone: (555) 010-0199
</BODY>
</HTML>
"""


def test_the_1997_program_page_gives_each_listed_title_and_only_its_abstract() -> None:
    assert icml_sites.icml1997(P1997, PROGRAM_CAPTURE) == [
        Entry("2", "Synthetic title with markup 1", "Synthetic submission abstract one, on two lines."),
        Entry("11", "Synthetic Title Two", "Synthetic abstract two: state t+1 of a + b, in 1993-1997."),
        Entry("14", "Synthetic Title Three", ""),  # no `Abstract` heading: no abstract, never a guess
    ]


@pytest.mark.parametrize(
    ("page", "n", "expected"),
    [
        (P1998_PRE, 101, Entry("101", "Synthetic title with markup 1",
                               "Synthetic abstract from the submission, Informática.")),
        (P1998_HTML, 2, Entry("2", "Synthetic Title Two", "Synthetic abstract two on two lines.")),
    ],
)  # fmt: skip
def test_a_1998_submission_page_gives_its_title_and_only_its_abstract(
    page: str, n: int, expected: Entry
) -> None:
    assert icml_sites.icml1998_paper(page, PAPER_CAPTURE.format(n=n)) == [expected]


def test_a_1998_page_whose_heading_is_not_its_urls_paper_gives_nothing() -> None:
    assert icml_sites.icml1998_paper(P1998_PRE, PAPER_CAPTURE.format(n=102)) == []
    assert icml_sites.icml1998_paper(P1998_PRE, "https://icml.cc/x.html") == []


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("write to a.b@example.org", "email"), ("{x,y}@example.org", "email"), ("x at example dot edu", "email"),
        ("call (609) 258-4455", "phone"), ("609-258-4455", "phone"), ("+(34-1) 624 9418", "phone"),
        ("+1 503 737 5552", "phone"), ("972-3-640-8829", "phone"), ("0231 755 4708", "phone"),
        ("5550199", "phone"), ("6095550199", "phone"), ("609 5550199", "phone"), ("123456789012", "phone"),
        ("name at cs.example.edu", "email"), ("name at cs dot example dot ac dot uk", "email"),
        ("Fax: none", "label"), ("Address: 1 Example Road", "label"),
        ("Exampleton EX1 2ZZ", "postal"), ("Ottawa, Ontario K1A 0R6", "postal"), ("D-53754 Sankt Augustin", "postal"),
        ("6500 HB Nijmegen", "postal"), ("12 Example Road", "postal"), ("someone {at} example {dot} edu", "email"), ("tel. none", "label"), ("Princeton, NJ 08544", "postal"), ("NJ 08544-2087", "phone"), ("624 9418", "phone"),
        # an abstract's own text is no contact detail
        ("the state at t+1", None), ("a + b log T", None), ("from 1993-1997", None), ("C++ classes", None),
        ("up to 29% over 10 000 documents", None), ("in 1987 1988 1989", None), ("telephone speech and voice", None), ("O(n^2) time", None), ("Areas under the ROC curve", None),
        ("the problems we address.", None),
        ("at least 30 examples", None),
    ],
)  # fmt: skip
def test_contact_details_are_recognised_and_an_abstracts_own_text_is_not(text: str, kind: str | None) -> None:
    assert icml_sites.contact_detail(text) == kind


@pytest.mark.parametrize(
    "inside",
    ["Mail the authors at author@example.org for the data.", "Call 555-010-0199 for the code.",
     "Write to us in Princeton, NJ 08544."],
)  # fmt: skip
def test_an_abstract_that_still_holds_a_contact_detail_is_withheld_whole(inside: str) -> None:
    page = P1998_PRE.replace("submission, Informática.", f"submission. {inside}")
    [entry] = icml_sites.icml1998_paper(page, PAPER_CAPTURE.format(n=101))
    assert entry == Entry("101", "Synthetic title with markup 1", "", withheld=True)


def test_an_abstract_line_that_reads_like_a_field_stays_and_one_no_field_ends_is_withheld() -> None:
    page = P1998_PRE.replace(
        "  submission, Informática.", "  submission.\nAreas under the ROC curve: a study."
    )
    [entry] = icml_sites.icml1998_paper(page, PAPER_CAPTURE.format(n=101))
    assert entry.abstract == "Synthetic abstract from the submission. Areas under the ROC curve: a study."
    # no field after the abstract: an address in a layout no rule knows could follow it, so it is withheld
    cut = P1998_PRE.split("Keywords:", 1)[0] + "Synthetic Institute\nVeldweg 1, 6500 HB Nijmegen\n</PRE>"
    [entry] = icml_sites.icml1998_paper(cut, PAPER_CAPTURE.format(n=101))
    assert entry.withheld and entry.abstract == ""


@pytest.mark.parametrize(
    "block",
    ["AUTHORS:\nSynthetic Person\nSynthetic Institute\nVeldweg 1, Exampleton",
     "Address: Veldweg 1, Exampleton", "Mailing address\nVeldweg 1, Exampleton",
     "Contact author Synthetic Person, Veldweg 1, Exampleton", "Affiliation: Synthetic Institute, Exampleton"],
)  # fmt: skip
def test_an_author_or_address_block_after_the_abstract_ends_it(block: str) -> None:
    """An address in a form no postal pattern knows (`Veldweg 1, Exampleton`) never joins the abstract: the block's
    own label ends it, whatever comes before the keywords."""
    page = P1998_PRE.replace("Keywords: synthetic", f"{block}\n\nKeywords: synthetic")
    [entry] = icml_sites.icml1998_paper(page, PAPER_CAPTURE.format(n=101))
    assert entry == Entry(
        "101", "Synthetic title with markup 1", "Synthetic abstract from the submission, Informática."
    )


def test_a_hostile_1998_page_is_parsed_in_linear_time() -> None:
    page = "<h1>ICML-98 Submission #1</h1>" + "Abstract:\n" * 20_000 + "12 34 " * 20_000 + "<" + "a" * 100_000
    started = time.monotonic()
    icml_sites.icml1998_paper(page, PAPER_CAPTURE.format(n=1))
    assert time.monotonic() - started < 2.0


# --- end to end: no contact detail reaches records, the snapshot, the index, an export or a log line ------------


V = date(2026, 10, 7)
WITHHELD_1998 = P1998_HTML.replace("on two lines.", "on two lines; ask two@example.org.")
# The synthetic dblp release's year (1990, one paper: "Synthetic title with markup 1"), read through the 1997 program
# page, or through a 1998 submission page and a 1998 page whose abstract is withheld, as the shipped rows are read.
CASES = {
    "1997": ({PROGRAM_CAPTURE: P1997},
             (SitePage(1990, PROGRAM_CAPTURE, PROGRAM, "icml1997", "cp1252", 3, V, "t"),),
             # attached, withheld, entries kept, dropped (#14 has no heading), the abstract, its capture
             (1, 0, 2, 1, "Synthetic submission abstract one, on two lines.", "19970619200718")),
    "1998": ({PAPER_CAPTURE.format(n=101): P1998_PRE, PAPER_CAPTURE.format(n=2): WITHHELD_1998},
             (SitePage(1990, PAPER_CAPTURE.format(n=101), PAPER.format(n=101), "icml1998_paper", "cp1252", 1, V, "t"),
              SitePage(1990, PAPER_CAPTURE.format(n=2), PAPER.format(n=2), "icml1998_paper", "cp1252", 1, V, "t")),
             (1, 1, 1, 0, "Synthetic abstract from the submission, Informática.", "19991009084141")),
}  # fmt: skip


@pytest.mark.parametrize("case", sorted(CASES))
def test_no_contact_detail_reaches_a_record_the_snapshot_the_index_an_export_or_a_log(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, case: str
) -> None:
    served, rows, (attached, withheld, kept, dropped, abstract, capture) = CASES[case]
    pages = {1990: rows}
    transport = FakeTransport({  # bare `text/html`, cp1252 bytes and their length, as the archive serves them
        url: Response(200, {"content-type": "text/html", "content-length": str(len(text.encode("cp1252")))},
                      text.encode("cp1252")) for url, text in served.items()
    })  # fmt: skip
    with caplog.at_level(logging.DEBUG):
        out = crawl.ingest_dblp([1990], tmp_path / "cache", stream=stream(), transport=transport, table=TABLE,
                                pages=pages)  # fmt: skip
        [listing] = out["listings"]
        assert (listing["abstract_attached"], listing["site_withheld"], listing["site_entries"],
                listing["site_dropped"], listing["abstracts_as_submitted"]) == (attached, withheld, kept, dropped, True)  # fmt: skip
        replayed = crawl._replay_dblp(tmp_path / "cache", (1990, TABLE.release.doi), TABLE, pages)
        records = replayed.records
        [record] = records
        assert record.abstract == abstract
        [claim] = record.claims("abstract")
        assert claim.url == rows[0].url
        assert f"Internet Archive capture {capture}" in (claim.evidence or "")
        assert "submission-time abstract" in (claim.evidence or "")

        snapshot = tmp_path / "snapshots" / "2026-10-07-test"
        snapshot.mkdir(parents=True)
        files = render(DedupResult(tuple(records), (), ()), [], T, crawls=replayed.reports)
        for name, data in files.items():
            (snapshot / name).write_bytes(data)
        built = build_index(snapshot, tmp_path / "indexes", T)
        engine = TantivyEngine(tmp_path / "indexes" / built.index_version)

        stored = [json.loads(line) for line in (snapshot / "records.jsonl").read_text("utf-8").splitlines()]
        exports = {}
        for fmt in export.FORMATS:
            buf = io.StringIO()
            export.write(fmt, stored, export.Provenance(built.index_version, "0" * 64, "2026-10-07"), buf,
                         sources=RecordFile(snapshot).attributions)  # fmt: skip
            exports[fmt] = buf.getvalue()

    indexed = parse("submission").effective_ast
    assert indexed is not None and engine.match_ids(indexed) == frozenset(
        {record.id}
    )  # the abstract is indexed
    for word in ("springfield", "example", "middletown", "institute", "keywords", "phone", "voice", "fax"):
        ast = parse(word).effective_ast
        assert ast is not None and engine.match_ids(ast) == frozenset(), word
    surfaces = {"ingest output": json.dumps(out), "records": "".join(r.model_dump_json() for r in records),
                "logs": "\n".join(repr(r.__dict__) for r in caplog.records),  # every field, before any scrub
                **{f"snapshot {k}": v.decode("utf-8") for k, v in files.items()},
                **{f"export {k}": v for k, v in exports.items()}}  # fmt: skip
    assert {"snapshot records.jsonl", "snapshot manifest.json", "export ris", "export jsonl"} <= set(surfaces)
    for where, text in surfaces.items():
        for detail in CONTACT:
            assert detail not in text, (where, detail)
