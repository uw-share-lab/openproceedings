import json
from datetime import date

import pytest
from openproceedings.ingest.openalex_table import Listing
from openproceedings.ingest.sources import openalex
from openproceedings.ingest.sources.common import CrawlError

from tests.unit.ingest.openalex import api


def test_rebuild_orders_by_position() -> None:
    assert openalex.rebuild({"world": [1], "hello": [0], "again": [2]}) == openalex.Rebuilt(
        "hello world again", None
    )


def test_rebuild_refuses_a_gap() -> None:
    assert openalex.rebuild({"hello": [0], "again": [2]}) == openalex.Rebuilt(None, "inverted_gap")
    assert openalex.rebuild({"hello": [1]}) == openalex.Rebuilt(None, "inverted_gap")  # not from 0


def test_rebuild_refuses_two_words_at_one_position() -> None:
    assert openalex.rebuild({"a": [0], "b": [0, 1]}) == openalex.Rebuilt(None, "inverted_conflict")


def test_rebuild_keeps_a_word_listed_twice_at_its_position_once() -> None:
    assert openalex.rebuild({"the": [0, 2, 2], "cat": [1]}) == openalex.Rebuilt("the cat the", None)


@pytest.mark.parametrize("raw", [[], "x", {"": [0]}, {"a": []}, {"a": [-1]}, {"a": [True]}, {"a": [0.0]},
                                 {"a": "0"}, {1: [0]}, {"a": [10**7]}])  # fmt: skip
def test_rebuild_refuses_unreadable_shapes(raw) -> None:
    got = openalex.rebuild(raw)
    assert got.text is None and got.refused in ("inverted_unreadable", "inverted_gap")


def test_rebuild_refuses_more_entries_than_any_abstract_has_words() -> None:
    """A hostile index repeating one position millions of times is refused before it is walked whole."""
    assert openalex.rebuild({"a": [0] * (openalex.MAX_POSITIONS + 1)}) == openalex.Rebuilt(
        None, "inverted_unreadable"
    )
    assert openalex.rebuild({"a": [openalex.MAX_POSITIONS]}) == openalex.Rebuilt(None, "inverted_unreadable")
    assert openalex.rebuild({"a": [openalex.MAX_POSITIONS - 1]}) == openalex.Rebuilt(None, "inverted_gap")


def test_no_inverted_index_is_no_abstract_not_a_refusal() -> None:
    assert openalex.rebuild(None) == openalex.Rebuilt(None, None)


@pytest.mark.parametrize(("text", "kept"), [
    ("An abstract \x02with a control.", "An abstract with a control."),
    ("… a snippet that starts with an ellipsis", None),
    ("ends with an ellipsis …", None),
])  # fmt: skip
def test_hygiene_is_every_abstracts(text: str, kept: str | None) -> None:
    w = openalex.parse_works(api.page(api.work("W1", "10.1/x", text=text))).works[0]
    cleaned, refused = openalex.abstract_of(w)
    assert (cleaned.text if cleaned else None) == kept
    assert refused == (None if kept else "abstract_unusable")


def test_abstract_of_passes_rebuild_refusals_and_absence_through() -> None:
    gap = openalex.parse_works(api.page(api.work("W1", None, raw={"a": [1]}))).works[0]
    none = openalex.parse_works(api.page(api.work("W2", None, text=None))).works[0]
    assert openalex.abstract_of(gap) == (None, "inverted_gap")
    assert openalex.abstract_of(none) == (None, None)


def test_parse_works_reads_ids_dois_sources_and_the_cursor() -> None:
    page = openalex.parse_works(api.page(api.work("W1", "10.1145/3593013.3594011", sources=("S9",)), count=7,
                                         cursor="IlsxNjk"))  # fmt: skip
    (w,) = page.works
    assert (w.id, w.doi, w.sources, page.total, page.next_cursor) == (
        "W1",
        "10.1145/3593013.3594011",
        ("S9",),
        7,
        "IlsxNjk",
    )


def test_parse_works_keeps_odd_optional_fields_as_none() -> None:
    raw = api.work("W1", None, sources=())
    raw.update(title=["not a string"], publication_year=True)
    (w,) = openalex.parse_works(api.page(raw, cursor="")).works
    assert (w.doi, w.title, w.year, w.sources) == (None, None, None, ())
    assert openalex.parse_works(api.page(raw, cursor="")).next_cursor is None
    raw.update(primary_location={"source": {"id": "https://openalex.org/X1"}}, publication_year=10**6)
    (w,) = openalex.parse_works(api.page(raw)).works
    assert (w.sources, w.year) == ((), None)


@pytest.mark.parametrize("text", ["not json", "[]", '{"results": []}', '{"meta": {}, "results": {}}',
                                  '{"meta": {"count": 1}, "results": [{"doi": null}]}'])  # fmt: skip
def test_an_answer_that_is_not_a_work_list_stops(text: str) -> None:
    with pytest.raises(CrawlError) as e:
        openalex.parse_works(text)
    assert e.value.reason == "openalex_unreadable"


HOSTILE = [
    "[" * 100_000 + "]" * 100_000,  # nesting past the recursion limit
    '{"meta": {"count": ' + "9" * 5000 + '}, "results": []}',  # an integer past int's digit limit
    '{"meta": {"count": true}, "results": []}',
    '{"meta": {"count": -1}, "results": []}',
    '{"meta": {"count": 1, "next_cursor": 7}, "results": []}',
    '{"meta": {"count": 1, "next_cursor": "a\\nb"}, "results": []}',
    json.dumps({"meta": {"count": 1, "next_cursor": "c" * 5000}, "results": []}),
    json.dumps({"meta": {"count": 1}, "results": [{"id": "https://openalex.org/W" + "1" * 40}]}),
    json.dumps({"meta": {"count": 1}, "results": [{"id": "https://openalex.org/W1 "}]}),
    json.dumps({"meta": {"count": 1}, "results": [{"id": "W1"}] * (openalex.PER_PAGE + 1)}),
]


@pytest.mark.parametrize("text", HOSTILE, ids=range(len(HOSTILE)))
def test_a_hostile_answer_stops_typed_never_raw(text: str) -> None:
    with pytest.raises(CrawlError) as e:
        openalex.parse_works(text)
    assert e.value.reason == "openalex_unreadable"


def test_an_oversized_answer_stops_unread() -> None:
    with pytest.raises(CrawlError) as e:
        openalex.parse_works(" " * (openalex.MAX_ANSWER + 1))
    assert e.value.reason == "openalex_unreadable"


def test_an_error_never_quotes_the_body() -> None:
    with pytest.raises(CrawlError) as e:
        openalex.parse_works('{"meta": {"count": 1}, "results": [{"id": "SECRET-BODY-TEXT"}]}')
    assert "SECRET-BODY-TEXT" not in str(e.value)


@pytest.mark.parametrize(("value", "doi"), [("https://doi.org/10.1145/ABC.1", "10.1145/abc.1"),
    ("10.1609/aaai.v34i01.5000", "10.1609/aaai.v34i01.5000"), ("https://doi.org/", None), (None, None),
    ("doi:10.1/x", None), ("https://doi.org/10.1/x y", None)])  # fmt: skip
def test_bare_doi(value, doi) -> None:
    assert openalex.bare_doi(value) == doi


def test_bare_doi_bounds_its_parts() -> None:
    assert openalex.bare_doi("10." + "1" * 40 + "/x") is None
    assert openalex.bare_doi("10.1/" + "x" * 2000) is None


def test_the_doi_url_is_sorted_and_capped() -> None:
    assert openalex.doi_url(["10.1/b", "10.1/a"]) == (
        f"https://api.openalex.org/works?filter=doi:10.1/a|10.1/b&per-page=50&select={openalex.SELECT}"
    )
    with pytest.raises(ValueError):
        openalex.doi_url([f"10.1/{i}" for i in range(51)])
    with pytest.raises(ValueError):
        openalex.doi_url([])


def test_the_listing_and_work_urls() -> None:
    row = Listing("AAAI", 1990, ("S1", "S2"), 3, date(2026, 10, 10), "x")
    assert openalex.listing_url(row, "a/b=") == (
        "https://api.openalex.org/works?filter=primary_location.source.id:S1|S2,publication_year:1990"
        f"&per-page=200&select={openalex.SELECT}&cursor=a%2Fb%3D"
    )
    assert openalex.listing_url(row).endswith("&cursor=%2A")
    assert openalex.work_url("W7") == "https://api.openalex.org/works/W7"
    assert openalex.work_page("W7") == "https://openalex.org/W7"


def test_no_url_carries_a_key_or_a_contact() -> None:
    urls = [
        openalex.doi_url(["10.1/a"]),
        openalex.listing_url(Listing("AAAI", 1990, ("S1",), 1, date(2026, 1, 1), "x")),
    ]
    for url in urls:
        assert "api_key" not in url and "mailto" not in url and "@" not in url


def test_the_key_is_optional_and_read_from_the_environment_first(tmp_path) -> None:
    env = tmp_path / ".env"
    env.write_text("OPENALEX_API_KEY=from-dotenv\n")
    assert openalex.api_key({}, None) is None
    assert openalex.api_key({}, env) == "from-dotenv"
    assert openalex.api_key({"OPENALEX_API_KEY": "from-env"}, env) == "from-env"
    assert openalex.api_key({"OPENALEX_API_KEY": "  "}, None) is None


def test_the_key_never_raises(tmp_path) -> None:
    assert openalex.api_key({}, tmp_path) is None  # a directory, not a file
    bad = tmp_path / "bad.env"
    bad.write_bytes(b"\xff\xfe OPENALEX_API_KEY=x\n")
    assert openalex.api_key({}, bad) is None
    assert openalex.api_key({}, tmp_path / "missing.env") is None
    # a value a header would split on, or not printable ASCII, is no key (never sent, never quoted)
    assert openalex.api_key({"OPENALEX_API_KEY": "a\r\nX-Evil: 1"}, None) is None
    assert openalex.api_key({"OPENALEX_API_KEY": "ké"}, None) is None
    assert openalex.api_key({"OPENALEX_API_KEY": "k" * 1000}, None) is None
