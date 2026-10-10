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
# TASK-224: AIES 2018-2023's front-of-volume keynotes, per year
AIES_KEYNOTES = {2018: 2, 2019: 2, 2020: 4, 2021: 1, 2022: 6, 2023: 3}


def test_the_shipped_table_has_every_acm_proceedings() -> None:
    t = acm_table.TABLE
    assert {k: (p.doi, p.dois) for k, p in t.proceedings.items()} == CENSUS
    assert sum(p.dois for p in t.proceedings.values()) == 1239 + 575
    assert all(
        p.window_from < p.window_until and p.verified.isoformat() == "2026-10-10"
        for p in t.proceedings.values()
    )
    by_year = {(n.venue, n.year) for n in t.not_papers.values()}
    assert by_year == {("FAccT", 2020)} | {("AIES", y) for y in AIES_KEYNOTES}
    kinds = [n.kind for n in t.not_papers.values() if n.venue == "FAccT"]
    assert (len(kinds), kinds.count("tutorial"), kinds.count("craft session")) == (
        CENSUS_2020_NOT_PAPERS,
        12,
        14,
    )
    assert t.expected("FAccT", 2020) == 95 - CENSUS_2020_NOT_PAPERS
    aies = [n for n in t.not_papers.values() if n.venue == "AIES"]
    assert {n.kind for n in aies} == {"keynote"}
    assert {y: sum(n.year == y for n in aies) for y in AIES_KEYNOTES} == AIES_KEYNOTES
    assert sum(t.expected("AIES", y) for y in AIES_KEYNOTES) == 575 - 18
    assert [(s.year, s.first, s.last, s.track) for s in t.sections] == [
        (2018, 354, 391, "student_abstract"), (2019, 521, 560, "student_abstract"),
        (2021, 267, 280, "student_abstract"), (2022, 890, 920, "student_abstract"),
        (2023, 939, 1012, "student_abstract")]  # fmt: skip
    assert {s.venue for s in t.sections} == {"AIES"}


SECTION = """
[[section]]
venue = "FAccT"
year = 2023
pages = [900, 950]
track = "student_abstract"
label = "Student abstracts"
verified = 2026-10-10
source = "test"
"""


@pytest.mark.parametrize(("page", "start"), [("354-355", 354), ("7", 7), ("1-1", 1), (None, None), ("", None),
                                             ("e1-e5", None), ("12-", 12),
                                             ("1" * 5000, None)])  # fmt: skip
def test_start_page_reads_crossrefs_page_field(page, start) -> None:
    assert acm_table.start_page(page) == start


def test_a_section_row_places_works_by_their_start_page() -> None:
    t = acm_table.load(TABLE_TEXT + SECTION)
    (sec,) = t.sections
    assert (sec.venue, sec.year, sec.first, sec.last, sec.track) == (
        "FAccT",
        2023,
        900,
        950,
        "student_abstract",
    )
    assert t.section("FAccT", 2023, "900-901") is sec and t.section("FAccT", 2023, "950") is sec
    assert t.section("FAccT", 2023, "899-901") is None and t.section("FAccT", 2023, "951-952") is None
    assert t.section("FAccT", 2023, None) is None and t.section("AIES", 2023, "900") is None
    assert acm_table.load(TABLE_TEXT).section("FAccT", 2023, "900") is None


@pytest.mark.parametrize(
    ("edit", "message"),
    [(lambda s: s.replace("year = 2023\npages", "year = 2024\npages"), "no proceedings row"),
     (lambda s: s.replace("pages = [900, 950]", "pages = [950, 900]"), r"first <= last"),
     (lambda s: s.replace("pages = [900, 950]", "pages = [0, 950]"), "positive"),
     (lambda s: s.replace("pages = [900, 950]", "pages = [900]"), r"\[first, last\]"),
     (lambda s: s.replace('track = "student_abstract"', 'track = "main"'), "track must be one of"),
     (lambda s: s.replace('track = "student_abstract"', 'track = "iaai"'), "track must be one of"),
     (lambda s: s.replace('label = "Student abstracts"', 'label = ""'), "label"),
     (lambda s: s.replace('label = "Student abstracts"\nverified = 2026-10-10',
                          'label = "Student abstracts"\nverified = "2026-10-10"'), "section .* verified must be a date"),
     (lambda s: s.replace('label = "Student abstracts"\n', ""), "missing columns"),
     (lambda s: s + SECTION.replace("[900, 950]", "[950, 960]"), "overlaps")],
)  # fmt: skip
def test_bad_section_rows_are_refused(edit, message) -> None:
    with pytest.raises(ValueError, match=message):
        acm_table.load(edit(TABLE_TEXT + SECTION))
