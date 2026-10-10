from datetime import UTC, datetime

import pytest
from openproceedings.ingest import acm_table
from openproceedings.ingest.dedup import dedup
from openproceedings.ingest.record import Claim
from openproceedings.ingest.sources import crossref
from openproceedings.ingest.sources.common import CrawlError, record_from_claims
from openproceedings.ingest.sources.http import USER_AGENT

from tests.unit.ingest.crossref import api

T = datetime(2026, 10, 10, tzinfo=UTC)
ROW = acm_table.load(api.TABLE_TEXT).proceedings[("FAccT", 2023)]


def test_a_works_page_and_its_cursor() -> None:
    page = crossref.parse_works(api.works_page(api.work("10.1145/3593013.3594011", title="<i>Fair</i> &amp; Square",
                                                        subtitle="A Study"), cursor="AoJ+/x=", total=1))  # fmt: skip
    (w,) = page.works
    assert (w.doi, w.type, w.title, w.authors, page.next_cursor, page.total) == (
        "10.1145/3593013.3594011",
        "proceedings-article",
        "Fair & Square: A Study",
        ("Jane Doe",),
        "AoJ+/x=",
        1,
    )


def test_the_proceedings_record() -> None:
    assert crossref.parse_proceedings(api.proceedings()) == (
        "10.1145/3593013",
        "Proceedings of the 2023 ACM Conference on Fairness, Accountability, and Transparency",
        ("9798400701924",),
    )
    with pytest.raises(CrawlError):
        crossref.parse_proceedings(api.works_page())


@pytest.mark.parametrize(
    ("item", "title"),
    [({"title": ["Fair: A Study"], "subtitle": ["A Study"]}, "Fair: A Study"),  # subtitle already in the title
     ({"title": ["X<sub>1</sub> and <mml:math><mml:mi>k</mml:mi></mml:math>"]}, "X1 and k"),
     ({"title": []}, None), ({}, None), ({"title": ["   "]}, None)],
)  # fmt: skip
def test_title_of(item, title) -> None:
    assert crossref.title_of(item) == title


@pytest.mark.parametrize(
    ("author", "name"),
    [({"given": "Jane", "family": "Doe"}, "Jane Doe"), ({"family": "Doe"}, "Doe"), ({"name": "The Lab"}, "The Lab"),
     ({"given": " Jane ", "family": " van  Doe "}, "Jane van Doe"), ({}, None)],
)  # fmt: skip
def test_author_name(author, name) -> None:
    assert crossref.author_name(author) == name


@pytest.mark.parametrize("text", ["not json", '{"status": "failed", "message": []}', '{"status": "ok"}', ""])
def test_a_page_that_is_not_a_work_list_stops(text: str) -> None:
    with pytest.raises(CrawlError) as e:
        crossref.parse_works(text)
    assert e.value.reason in ("crossref_unreadable", "crossref_error")


def test_the_works_url_is_stable_and_quotes_the_cursor() -> None:
    assert crossref.works_url(ROW) == (
        "https://api.crossref.org/works?filter=prefix:10.1145,from-pub-date:2023-06-01,until-pub-date:2023-06-30"
        f"&rows=1000&select={crossref.SELECT}&cursor=%2A"
    )
    assert crossref.works_url(ROW, "AoJ+/x=").endswith("&cursor=AoJ%2B%2Fx%3D")


def test_the_contact_comes_from_the_environment_or_dotenv(tmp_path) -> None:
    env = tmp_path / ".env"
    env.write_text("CROSSREF_MAILTO=reviewer@example.org\n")
    assert crossref.contact({}, env) == "reviewer@example.org"
    assert crossref.contact({"CROSSREF_MAILTO": "other@example.org"}, env) == "other@example.org"
    assert crossref.user_agent("reviewer@example.org").endswith("; mailto:reviewer@example.org)")


@pytest.mark.parametrize("environ", [{}, {"CROSSREF_MAILTO": ""}, {"CROSSREF_MAILTO": "   "}])
def test_an_unset_contact_is_none_and_the_user_agent_is_the_plain_one(environ, tmp_path) -> None:
    assert crossref.contact(environ, None) is None
    assert crossref.contact(environ, tmp_path / "missing.env") is None
    assert crossref.user_agent(None) == USER_AGENT and "mailto" not in USER_AGENT


def test_a_malformed_contact_stops_without_echoing_it() -> None:
    with pytest.raises(CrawlError) as e:
        crossref.contact({"CROSSREF_MAILTO": "not an address"}, None)
    assert e.value.reason == "bad_contact" and "not an address" not in str(e.value)


def test_a_doi_link_names_the_record_and_passes_dedups_self_naming_check(monkeypatch) -> None:
    monkeypatch.setattr(acm_table, "TABLE", acm_table.load(api.TABLE_TEXT))
    url, where = "https://api.crossref.org/works/10.1145/3593013.3594011", "test"
    claims = [
        Claim(field=f, value=v, source="crossref", url=url, fetched_at=T, evidence=where)
        for f, v in (
            ("venue", "FAccT"),
            ("year", 2023),
            ("track", "main"),
            ("status", "accepted"),
            ("title", "A Paper"),
            ("urls.doi", "10.1145/3593013.3594011"),
            ("urls.proceedings", "https://doi.org/10.1145/3593013.3594011"),
        )
    ]
    record = record_from_claims("op:facct:2023:doi-3593013.3594011", claims)
    assert dedup([record]).records == (record,)
