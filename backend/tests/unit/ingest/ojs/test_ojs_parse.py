import pytest
from openproceedings.ingest.sources import ojs
from openproceedings.ingest.sources.common import CrawlError

from tests.unit.ingest.ojs import oai


def test_a_record_and_the_next_token() -> None:
    records, token = ojs.parse_page(oai.page(oai.record(28000), token="c83a", size=115))
    assert token == "c83a"
    (r,) = records
    assert (r.article, r.deleted, r.set_spec, r.volume) == (28000, False, "AAAI:AISI", 34)
    assert r.title == "A Paper" and r.creators == ("Doe, Jane",) and r.description == "An abstract."
    assert r.doi == "10.1609/aaai.v34i01.28000"
    assert r.article_url == "https://ojs.aaai.org/index.php/AAAI/article/view/28000"
    assert r.pdf_url == "https://ojs.aaai.org/index.php/AAAI/article/view/28000/35000"


def test_last_page_has_no_token_and_an_empty_token_is_the_end() -> None:
    assert ojs.parse_page(oai.page(oai.record(1)))[1] is None
    assert (
        ojs.parse_page(oai.page(oai.record(1), token=""))[1] is None
    )  # OAI-PMH: empty token = list complete


def test_deleted_header_has_no_metadata() -> None:
    (r,), _ = ojs.parse_page(oai.page(oai.deleted(42953)))
    assert r.deleted and r.title is None and r.volume is None


def test_english_title_wins_over_other_locales() -> None:
    french = '<dc:title xml:lang="fr-FR">Un article</dc:title>'
    rec = oai.record(5).replace("<dc:title", french + "<dc:title", 1)  # the French title comes first
    assert rec.index("Un article") < rec.index("A Paper")
    (r,), _ = ojs.parse_page(oai.page(rec))
    assert r.title == "A Paper"


def test_first_title_when_none_is_english() -> None:
    rec = oai.record(5).replace('xml:lang="en-US">A Paper', 'xml:lang="de-DE">Ein Papier')
    (r,), _ = ojs.parse_page(oai.page(rec))
    assert r.title == "Ein Papier"


def test_missing_description_is_none() -> None:
    (r,), _ = ojs.parse_page(oai.page(oai.record(5, description=None)))
    assert r.description is None


@pytest.mark.parametrize("code", ["badResumptionToken", "badArgument", "cannotDisseminateFormat"])
def test_oai_error_stops(code: str) -> None:
    with pytest.raises(CrawlError, match=code) as e:
        ojs.parse_page(oai.error(code))
    assert e.value.reason == "oai_error"


def test_no_records_match_is_an_empty_page() -> None:
    assert ojs.parse_page(oai.error("noRecordsMatch")) == ([], None)


@pytest.mark.parametrize("text", ["<html><body>Maintenance</body></html>", "not xml", ""])
def test_a_page_that_is_not_oai_pmh_stops(text: str) -> None:
    with pytest.raises(CrawlError) as e:
        ojs.parse_page(text)
    assert e.value.reason == "oai_unreadable"


@pytest.mark.parametrize("prolog", ["", "<!-- " + "x" * 5000 + " -->"])
def test_a_doctype_is_refused_wherever_it_sits(prolog: str) -> None:  # no entity expansion from a response
    text = f'<?xml version="1.0"?>{prolog}<!DOCTYPE x [<!ENTITY a "b">]><OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/"/>'
    with pytest.raises(CrawlError, match="DOCTYPE") as e:
        ojs.parse_page(text)
    assert e.value.reason == "oai_unreadable"


@pytest.mark.parametrize(
    ("raw", "shown"),
    [
        ("Doe, Jane", "Jane Doe"),
        ("van der Berg, Anna-Lena", "Anna-Lena van der Berg"),
        ("Smith, Jr., John", "Smith, Jr., John"),
        ("Aristotle", "Aristotle"),
        ("  Doe ,  Jane ", "Jane Doe"),
    ],
)
def test_display_name(raw: str, shown: str) -> None:
    assert ojs.display_name(raw) == shown


def test_english_description_wins_over_other_locales() -> None:
    french = '<dc:description xml:lang="fr-FR">Un resume.</dc:description>'
    rec = oai.record(5).replace("<dc:description", french + "<dc:description", 1)
    assert rec.index("Un resume") < rec.index("An abstract")
    (r,), _ = ojs.parse_page(oai.page(rec))
    assert r.description == "An abstract."


def _sets_page(sets: str, token: str | None = None) -> str:
    rt = (
        "" if token is None else f'<resumptionToken completeListSize="3" cursor="0">{token}</resumptionToken>'
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/"><responseDate>2026-10-09T22:01:20Z</responseDate>
<request verb="ListSets">https://ojs.aaai.org/index.php/AAAI/oai</request><ListSets>{sets}{rt}</ListSets></OAI-PMH>
"""


def test_list_sets_parses_names_and_the_next_token() -> None:
    page = _sets_page(
        "<set><setSpec>AAAI</setSpec><setName>Proceedings of the AAAI Conference</setName></set>"
        "<set><setSpec>AAAI:AISI</setSpec><setName>AAAI Special Track on\n  AI for Social Impact</setName></set>",
        token="t1",
    )
    sets, token = ojs.parse_sets(page)
    assert sets == {
        "AAAI": "Proceedings of the AAAI Conference",
        "AAAI:AISI": "AAAI Special Track on AI for Social Impact",
    }
    assert token == "t1"
    assert ojs.parse_sets(_sets_page("<set><setSpec>X</setSpec><setName>Y</setName></set>"))[1] is None


def test_list_sets_follows_tokens_through_the_fetcher() -> None:
    from datetime import UTC, datetime

    from openproceedings.ingest.sources.http import Page

    pages = {
        ojs.sets_url("AAAI"): _sets_page(
            "<set><setSpec>A</setSpec><setName>One</setName></set>", token="t/1"
        ),
        ojs.sets_url("AAAI", "t/1"): _sets_page("<set><setSpec>B</setSpec><setName>Two</setName></set>"),
    }
    assert ojs.sets_url("AAAI", "t/1").endswith("&resumptionToken=t%2F1")

    class Fake:
        def get(self, url: str, *, refresh: bool = False) -> Page:
            return Page(url, 200, pages[url], datetime(2026, 10, 9, tzinfo=UTC), "text/xml")

    assert ojs.list_sets("AAAI", Fake()) == {"A": "One", "B": "Two"}  # type: ignore[arg-type]


def test_list_sets_error_stops() -> None:
    with pytest.raises(CrawlError, match="badArgument"):
        ojs.parse_sets(oai.error("badArgument"))


def test_a_deleted_header_may_keep_the_pre_2020_identifier() -> None:
    old = oai.deleted(5828, "AAAI:ML").replace("oai:ojs.aaai.org:", "oai:ojs.pkp.sfu.ca:")
    (r,), _ = ojs.parse_page(oai.page(old))
    assert (r.article, r.deleted, r.set_spec) == (5828, True, "AAAI:ML")


def test_a_live_record_with_the_pre_2020_identifier_stops() -> None:
    old = oai.record(5828).replace("oai:ojs.aaai.org:", "oai:ojs.pkp.sfu.ca:", 1)
    with pytest.raises(CrawlError, match=r"no ojs\.aaai\.org article id") as e:
        ojs.parse_page(oai.page(old))
    assert e.value.reason == "oai_unreadable"
