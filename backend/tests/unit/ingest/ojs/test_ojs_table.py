from datetime import date

import pytest
from openproceedings.ingest import ojs_table

GOOD = """
[[journal]]
code = "AAAI"
venue = "AAAI"
year_offset = 1986
verified = 2026-10-09
source = "docs/research/2026-10-09-aaai-aies-facct-iaseai-sources.md"

[[section]]
journal = "AAAI"
volume = 34
set_spec = "AAAI:AISI"
kind = "papers"
track = "main"
label = "Special Track on AI for Social Impact"
papers = 70
verified = 2026-10-09
source = "backend/tests/fixtures/http/ojs/aaai-v34-aisi.json"

[[section]]
journal = "AAAI"
volume = 34
set_spec = "AAAI:FMT"
kind = "front_matter"
label = "Front Matter"
papers = 1
verified = 2026-10-09
source = "x"
"""


def test_loads_and_derives_year_and_expected_count() -> None:
    t = ojs_table.load(GOOD)
    assert t.year("AAAI", 34) == 2020
    assert t.volumes("AAAI") == (34,)
    assert t.expected("AAAI", 34) == 70  # front matter is counted, never a paper
    assert t.sections[("AAAI", 34, "AAAI:AISI")].track == "main"
    assert t.journals["AAAI"].verified == date(2026, 10, 9)


@pytest.mark.parametrize(
    ("edit", "message"),
    [
        (lambda s: s.replace("verified = 2026-10-09", "verified = 2026-10-09T10:00:00", 1), "verified date"),
        (lambda s: s.replace('code = "AAAI"', 'code = ""'), "code must be"),
        (lambda s: s.replace('set_spec = "AAAI:AISI"', 'set_spec = ""'), "set_spec must be"),
        (lambda s: s.replace('set_spec = "AAAI:AISI"', "set_spec = 7"), "set_spec must be"),
        (
            lambda s: s.replace('label = "Special Track on AI for Social Impact"', 'label = ""'),
            "label must be",
        ),
        (lambda s: s.replace('journal = "AAAI"\nvolume', "journal = [1]\nvolume"), "journal must be"),
        (lambda s: s.replace('track = "main"', "track = [1]"), "not a spec 01 track"),
    ],
)
def test_loader_type_checks(edit, message) -> None:
    with pytest.raises(ValueError, match=message):
        ojs_table.load(edit(GOOD))


@pytest.mark.parametrize(
    ("edit", "message"),
    [
        (lambda s: s.replace('track = "main"', 'track = "mainn"'), "not a spec 01 track"),
        (lambda s: s.replace('venue = "AAAI"', 'venue = "AAAJ"'), "not one of"),
        (lambda s: s.replace('kind = "papers"', 'kind = "paper"'), "kind"),
        (lambda s: s.replace("papers = 70", "papers = 0"), "positive"),
        (
            lambda s: s.replace(
                'kind = "front_matter"\nlabel', 'kind = "front_matter"\ntrack = "main"\nlabel'
            ),
            "front matter has no track",
        ),
        (
            lambda s: s + s[s.index("[[section]]") : s.index("[[section]]", s.index("[[section]]") + 1)],
            "listed twice",
        ),
        (lambda s: s.replace("year_offset = 1986", "year_offset = 1900"), "not held under that name"),
        (
            lambda s: (
                s.replace('track = "main"', 'track = "iaai"')
                .replace('venue = "AAAI"', 'venue = "AIES"')
                .replace('code = "AAAI"', 'code = "AIES"')
                .replace('journal = "AAAI"', 'journal = "AIES"')
                .replace("year_offset = 1986", "year_offset = 2017")
                .replace("volume = 34", "volume = 7")
            ),
            "only an AAAI track",
        ),
        (
            lambda s: s.replace(
                'journal = "AAAI"\nvolume = 34\nset_spec = "AAAI:AISI"',
                'journal = "AIES"\nvolume = 34\nset_spec = "AAAI:AISI"',
            ),
            "no journal row",
        ),
    ],
)
def test_bad_rows_are_refused(edit, message) -> None:
    with pytest.raises(ValueError, match=message):
        ojs_table.load(edit(GOOD))


def test_the_shipped_table_loads() -> None:
    assert set(ojs_table.TABLE.journals) == {"AAAI", "AIES", "IASEAI"}


UNAVAILABLE = """
[[unavailable]]
journal = "AAAI"
article = 39173
set_spec = "AAAI:AISI"
volume = 34
reason = "HTTP 500 in every form"
verified = 2026-10-09
source = "x"
"""


def test_an_unavailable_row_loads() -> None:
    u = ojs_table.load(GOOD + UNAVAILABLE).unavailable[("AAAI", 39173)]
    assert (u.set_spec, u.volume, u.reason) == ("AAAI:AISI", 34, "HTTP 500 in every form")
    assert ojs_table.load(GOOD).unavailable == {}


@pytest.mark.parametrize(
    ("edit", "message"),
    [
        (lambda s: s.replace('set_spec = "AAAI:AISI"\nvolume = 34\nreason', 'set_spec = "AAAI:NEW"\nvolume = 34\nreason'),
         "no papers section row"),
        (lambda s: s.replace('source = "x"', 'source = "x"\nextra = 1'), "unknown columns"),
        (lambda s: s.replace("article = 39173", "article = 0"), "article must be a positive integer"),
        (lambda s: s.replace('reason = "HTTP 500 in every form"', 'reason = ""'), "reason must be"),
        (lambda s: s + s, "listed twice"),
    ],
)  # fmt: skip
def test_bad_unavailable_rows_are_refused(edit, message) -> None:
    with pytest.raises(ValueError, match=message):
        ojs_table.load(GOOD + edit(UNAVAILABLE))


def test_an_unavailable_row_must_point_at_a_papers_section() -> None:
    fm = UNAVAILABLE.replace('set_spec = "AAAI:AISI"', 'set_spec = "AAAI:FMT"')
    with pytest.raises(ValueError, match="no papers section row"):
        ojs_table.load(GOOD + fm)
