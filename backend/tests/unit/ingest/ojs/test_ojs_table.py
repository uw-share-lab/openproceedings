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
        (lambda s: s.replace('track = "main"', 'track = "mainn"'), "not a spec 01 track"),
        (lambda s: s.replace('venue = "AAAI"', 'venue = "AAAJ"'), "not one of"),
        (lambda s: s.replace('kind = "papers"', 'kind = "paper"'), "kind"),
        (lambda s: s.replace("papers = 70", "papers = 0"), "positive"),
        (lambda s: s.replace('kind = "front_matter"\nlabel', 'kind = "front_matter"\ntrack = "main"\nlabel'),
         "front matter has no track"),
        (lambda s: s + s[s.index("[[section]]"):s.index("[[section]]", s.index("[[section]]") + 1)],
         "listed twice"),
        (lambda s: s.replace("year_offset = 1986", "year_offset = 1900"), "not held under that name"),
        (lambda s: s.replace('track = "main"', 'track = "iaai"').replace('venue = "AAAI"', 'venue = "AIES"')
         .replace('code = "AAAI"', 'code = "AIES"').replace('journal = "AAAI"', 'journal = "AIES"')
         .replace("year_offset = 1986", "year_offset = 2017").replace("volume = 34", "volume = 7"),
         "only an AAAI track"),
        (lambda s: s.replace('journal = "AAAI"\nvolume = 34\nset_spec = "AAAI:AISI"',
                             'journal = "AIES"\nvolume = 34\nset_spec = "AAAI:AISI"'), "no journal row"),
    ],
)
def test_bad_rows_are_refused(edit, message) -> None:
    with pytest.raises(ValueError, match=message):
        ojs_table.load(edit(GOOD))


def test_the_shipped_table_loads() -> None:
    assert set(ojs_table.TABLE.journals) == {"AAAI", "AIES", "IASEAI"}
