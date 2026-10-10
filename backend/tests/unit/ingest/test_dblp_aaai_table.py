from datetime import date

import pytest
from openproceedings.ingest import dblp_aaai_table, dblp_table

GOOD = """
not_held = [1981, 1985, 1989, 2001, 2003, 2009]

[[year]]
year = 1986
proceedings = ["conf/aaai/1986-1", "conf/aaai/1986-2"]
papers = 4
title = "Synthetic AAAI 1986"
verified = 2026-10-10
source = "test"

[[year]]
year = 2006
proceedings = ["conf/aaai/2006"]
papers = 1
title = "Synthetic AAAI 2006"
verified = 2026-10-10
source = "test"

[[workshop]]
key = "conf/aaai/2006w"
year = 2006
papers = 1
title = "Synthetic AAAI 2006 workshop"
verified = 2026-10-10
source = "test"

[[not_paper]]
key = "conf/aaai/Invited86"
year = 1986
kind = "invited talk"
reason = "an invited talk's abstract in the proceedings"
"""


def test_loads_with_the_icml_tables_pin() -> None:
    t = dblp_aaai_table.load(GOOD)
    assert t.release == dblp_table.TABLE.release and t.dtd == dblp_table.TABLE.dtd  # one pin, never a second
    assert t.main_key("conf/aaai/1986-2").year == 1986 and t.main_key("conf/aaai/2006w") is None
    assert t.workshop("conf/aaai/2006w").papers == 1
    assert t.stated(2006) == 2 and t.stated(1986) == 4
    assert t.not_held == frozenset({1981, 1985, 1989, 2001, 2003, 2009})
    assert t.years[1986].verified == date(2026, 10, 10)
    assert (dblp_aaai_table.FIRST_YEAR, dblp_aaai_table.LAST_YEAR) == (1980, 2008)
    assert range(1980, 2010) == dblp_aaai_table.CHECKED


@pytest.mark.parametrize(
    ("edit", "message"),
    [
        (lambda s: s.replace("year = 2006\nproceedings", "year = 2010\nproceedings"), "1980 to 2008"),
        (lambda s: s.replace("year = 1986\nproceedings", "year = 1985\nproceedings"), "both held and not held"),
        (lambda s: s.replace('"conf/aaai/2006"]', '"conf/icml/2006"]'), "conf/aaai/"),
        (lambda s: s.replace("papers = 4", "papers = 0"), "positive"),
        (lambda s: s.replace('key = "conf/aaai/2006w"\nyear = 2006', 'key = "conf/aaai/2006w"\nyear = 2005'),
         "a year the table holds"),
        (lambda s: s.replace('kind = "invited talk"', 'kind = "keynote speech"'), "kind"),
        (lambda s: s.replace("not_held = [1981,", "not_held = [1979,"), "1980 to 2009"),
        (lambda s: s.replace('key = "conf/aaai/2006w"', 'key = "conf/aaai/2006"'), "listed twice"),
        (lambda s: s + "\n[release]\ndoi = \"x\"\n", "unknown tables"),
    ],
)  # fmt: skip
def test_bad_rows_are_refused(edit, message) -> None:
    with pytest.raises(ValueError, match=message):
        dblp_aaai_table.load(edit(GOOD))


def test_the_shipped_table_loads_and_records_the_years_aaai_was_not_held() -> None:
    # 1995 too: the 12th conference is 1994 and the 13th 1996 (the census, docs/research/2026-10-09-...-sources.md)
    assert dblp_aaai_table.TABLE.not_held == frozenset({1981, 1985, 1989, 1995, 2001, 2003, 2009})


@pytest.mark.parametrize(
    ("edit", "message"),
    [
        (lambda s: s.replace('proceedings = ["conf/aaai/1986-1", "conf/aaai/1986-2"]',
                             'proceedings = ["conf/aaai/1986-1", "conf/aaai/1986-1"]'), "listed twice"),
        (lambda s: s.replace('key = "conf/aaai/2006w"\nyear = 2006', 'key = "conf/aaai/2006w"\nyear = 2006.0'),
         "a year the table holds"),
        (lambda s: s.replace('key = "conf/aaai/Invited86"\nyear = 1986', 'key = "conf/aaai/Invited86"\nyear = 1986.0'),
         "a year the table holds"),
    ],
)  # fmt: skip
def test_a_repeated_proceedings_key_and_a_float_year_are_refused(edit, message) -> None:
    with pytest.raises(ValueError, match=message):
        dblp_aaai_table.load(edit(GOOD))


# the 2026-10-10 census of release 10.4230/dblp.xml.2026-10-03: inproceedings under the main keys, 1980-2008
CENSUS_MAIN = 4689


def test_the_shipped_table_covers_every_year_1980_to_2009() -> None:
    t = dblp_aaai_table.TABLE
    assert set(t.years) | t.not_held == set(range(1980, 2010)) and not set(t.years) & t.not_held
    assert sorted(t.years) == [1980, 1982, 1983, 1984, 1986, 1987, 1988, *range(1990, 1995), *range(1996, 2001),
                               2002, *range(2004, 2009)]  # fmt: skip
    assert all(len(t.years[y].proceedings) == 2 for y in (1986, 1991, 1994, 1996))
    assert sum(y.papers for y in t.years.values()) == CENSUS_MAIN  # the census total, written in as a literal


SECTIONS = """
[[section]]
year = 2006
pages = [1853, 1903]
track = "student_abstract"
label = "Student Abstracts"
verified = 2026-10-10
source = "test contents page"

[[section]]
year = 2006
pages = [1904, 1930]
track = "consortium"
label = "Doctoral Consortium"
verified = 2026-10-10
source = "test contents page"

[[track]]
key = "conf/aaai/Typo06"
year = 2006
track = "student_abstract"
reason = "listed under Student Abstracts, p. 1855; dblp's pages are a typo"
verified = 2026-10-10
source = "test contents page"
"""


@pytest.mark.parametrize(
    ("pages", "start"),
    [("1425-1426", 1425), ("856", 856), ("1853-", 1853), ("855-1856", 855), (None, None), ("", None),
     ("I-XV", None), ("12-13, 15", None), ("-5", None)],
)  # fmt: skip
def test_start_page_reads_dblps_page_field(pages, start) -> None:
    assert dblp_aaai_table.start_page(pages) == start


def test_a_main_entry_takes_its_track_row_then_its_section_then_main() -> None:
    t = dblp_aaai_table.load(GOOD + SECTIONS)
    assert [(s.year, s.first, s.last, s.track) for s in t.sections] == [
        (2006, 1853, 1903, "student_abstract"), (2006, 1904, 1930, "consortium")]  # fmt: skip
    assert t.main_track("conf/aaai/A06", 2006, "1853-1854") == ("student_abstract", t.sections[0])
    assert t.main_track("conf/aaai/A06", 2006, "1903") == ("student_abstract", t.sections[0])  # inclusive
    assert t.main_track("conf/aaai/A06", 2006, "1904-1905")[0] == "consortium"
    assert t.main_track("conf/aaai/A06", 2006, "1931-1932") == ("main", None)
    assert t.main_track("conf/aaai/A06", 2006, "1852-1853") == ("main", None)  # the start page decides
    assert t.main_track("conf/aaai/A06", 2006, None) == ("main", None)  # no pages: no section
    assert t.main_track("conf/aaai/A06", 1986, "1853-1854") == ("main", None)  # another year's range
    assert t.main_track("conf/aaai/Typo06", 2006, "855-1856") == (
        "student_abstract",
        t.tracks["conf/aaai/Typo06"],
    )
    assert dblp_aaai_table.load(GOOD).main_track("conf/aaai/A06", 2006, "1853") == ("main", None)


_TRACK_ROW = 'key = "conf/aaai/Typo06"\nyear = 2006\ntrack = "student_abstract"'


@pytest.mark.parametrize(
    ("edit", "message"),
    [
        (lambda s: s.replace("pages = [1904, 1930]", "pages = [1900, 1930]"), "overlaps"),
        (lambda s: s.replace("pages = [1904, 1930]", "pages = [1930, 1904]"), r"first <= last"),
        (lambda s: s.replace("pages = [1904, 1930]", "pages = [0, 1930]"), "positive"),
        (lambda s: s.replace("pages = [1904, 1930]", "pages = [1904]"), r"\[first, last\]"),
        (lambda s: s.replace("pages = [1904, 1930]", 'pages = ["1904", "1930"]'), r"\[first, last\]"),
        (lambda s: s.replace('track = "consortium"', 'track = "main"'), "track must be one of"),
        (lambda s: s.replace('track = "consortium"', 'track = "eaai"'), "track must be one of"),
        (lambda s: s.replace("year = 2006\npages = [1904", "year = 2005\npages = [1904"), "a year the table holds"),
        (lambda s: s.replace('label = "Doctoral Consortium"', 'label = ""'), "a label"),
        (lambda s: s.replace('label = "Doctoral Consortium"\nverified = 2026-10-10',
                             'label = "Doctoral Consortium"\nverified = "2026-10-10"'), "verified date"),
        (lambda s: s.replace('label = "Doctoral Consortium"\nverified = 2026-10-10\nsource = "test contents page"',
                             'label = "Doctoral Consortium"\nverified = 2026-10-10\nsource = ""'), "a source"),
        (lambda s: s.replace('label = "Doctoral Consortium"\n', ""), "missing columns"),
        (lambda s: s.replace(_TRACK_ROW, _TRACK_ROW.replace("student_abstract", "workshop")), "track must be one of"),
        (lambda s: s.replace(_TRACK_ROW, _TRACK_ROW.replace("2006", "1985")), "a year the table holds"),
        (lambda s: s.replace(_TRACK_ROW, _TRACK_ROW.replace("Typo06", "Invited86")), "listed twice"),
        (lambda s: s.replace(_TRACK_ROW, _TRACK_ROW.replace("conf/aaai/Typo06", "conf/icml/Typo06")), "conf/aaai/"),
        (lambda s: s.replace("reason = \"listed under", "reason = \"\"\nnote = \"listed under"), "unknown columns"),
        (lambda s: s + SECTIONS[SECTIONS.index("[[track]]"):], "listed twice"),
    ],
)  # fmt: skip
def test_bad_section_and_track_rows_are_refused(edit, message) -> None:
    with pytest.raises(ValueError, match=message):
        dblp_aaai_table.load(edit(GOOD + SECTIONS))


def test_the_shipped_sections_never_give_main_and_never_overlap() -> None:
    t = dblp_aaai_table.TABLE
    assert {s.track for s in t.sections} | {
        r.track for r in t.tracks.values()
    } <= dblp_aaai_table.SECTION_TRACKS
    for a, b in zip(t.sections, t.sections[1:], strict=False):
        assert a.year != b.year or a.last < b.first
    assert not set(t.tracks) & set(t.not_papers)
