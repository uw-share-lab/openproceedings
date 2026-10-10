import pytest
from openproceedings.ingest import acm_table

from tests.unit.ingest.crossref.api import TABLE_TEXT


def test_loads_and_derives_the_expected_records() -> None:
    t = acm_table.load(TABLE_TEXT)
    row = t.proceedings[("FAccT", 2023)]
    assert (row.toc, t.expected("FAccT", 2023)) == ("3593013", 2)  # 3 DOIs, one of them no paper
    assert (
        row.paper("10.1145/3593013.3594011")
        and not row.paper("10.1145/35930130.1")
        and not row.paper("10.1145/3593013")
    )
    assert t.by_toc("3593013") is row and t.not_papers["10.1145/3593013.3594100"].year == 2023


@pytest.mark.parametrize(
    ("edit", "message"),
    [(lambda s: s.replace('venue = "FAccT"', 'venue = "ICML"'), "FAccT or AIES"),
     (lambda s: s.replace("year = 2023", "year = 2018"), "doi ids"),
     (lambda s: s.replace('doi = "10.1145/3593013"', 'doi = "10.1145/3593013.1"'), "proceedings DOI"),
     (lambda s: s.replace("window_until = 2023-06-30", "window_until = 2023-05-01"), "window"),
     (lambda s: s.replace("dois = 3", "dois = 1"), "fewer not-paper rows"),
     (lambda s: s.replace('doi = "10.1145/3593013.3594100"', 'doi = "10.1145/9999999.1"'), "no proceedings row"),
     (lambda s: s.replace('kind = "tutorial"', 'kind = "poster"'), "kind"),
     (lambda s: s + s[s.index("[[not_paper]]"):], "listed twice")],
)  # fmt: skip
def test_bad_rows_are_refused(edit, message) -> None:
    with pytest.raises(ValueError, match=message):
        acm_table.load(edit(TABLE_TEXT))


@pytest.mark.parametrize(("doi", "parts"), [("10.1145/3593013.3594011", ("3593013", "3594011")),
    ("10.1145/3593013.3594011a", None), ("10.1145/3593013", None), ("10.1609/aaai.v34i01.1", None),
    ("10.1145/3593013.3594011\n", None), (" 10.1145/3593013.3594011", None)])  # fmt: skip
def test_paper_doi(doi: str, parts) -> None:
    assert acm_table.paper_doi(doi) == parts
