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


# The live census of 2026-10-10 (docs/research/2026-10-09-aaai-aies-facct-iaseai-sources.md §FAccT, §AIES)
CENSUS = {("FAccT", 2019): ("10.1145/3287560", 41), ("FAccT", 2020): ("10.1145/3351095", 95),
          ("FAccT", 2021): ("10.1145/3442188", 82), ("FAccT", 2022): ("10.1145/3531146", 181),
          ("FAccT", 2023): ("10.1145/3593013", 153), ("FAccT", 2024): ("10.1145/3630106", 167),
          ("FAccT", 2025): ("10.1145/3715275", 206), ("FAccT", 2026): ("10.1145/3805689", 314),
          ("AIES", 2018): ("10.1145/3278721", 78), ("AIES", 2019): ("10.1145/3306618", 91),
          ("AIES", 2020): ("10.1145/3375627", 76), ("AIES", 2021): ("10.1145/3461702", 114),
          ("AIES", 2022): ("10.1145/3514094", 115), ("AIES", 2023): ("10.1145/3600211", 101)}  # fmt: skip
CENSUS_2020_NOT_PAPERS = 26  # 12 tutorials + 14 CRAFT sessions


def test_the_shipped_table_has_every_acm_proceedings() -> None:
    t = acm_table.TABLE
    assert {k: (p.doi, p.dois) for k, p in t.proceedings.items()} == CENSUS
    assert sum(p.dois for p in t.proceedings.values()) == 1239 + 575
    assert all(
        p.window_from < p.window_until and p.verified.isoformat() == "2026-10-10"
        for p in t.proceedings.values()
    )
    by_year = {(n.venue, n.year) for n in t.not_papers.values()}
    assert by_year == {("FAccT", 2020)}
    kinds = [n.kind for n in t.not_papers.values()]
    assert (len(kinds), kinds.count("tutorial"), kinds.count("craft session")) == (
        CENSUS_2020_NOT_PAPERS,
        12,
        14,
    )
    assert t.expected("FAccT", 2020) == 95 - CENSUS_2020_NOT_PAPERS
