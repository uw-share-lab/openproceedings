from datetime import date

import pytest
from openproceedings.ingest import openalex_table

GOOD = """
[[listing]]
venue = "AAAI"
year = 1990
source_ids = ["S4306420609"]
works = 3
verified = 2026-10-10
source = "docs/research/2026-10-09-aaai-aies-facct-iaseai-sources.md"
"""


def test_loads_a_listing() -> None:
    t = openalex_table.load(GOOD)
    row = t.listings[("AAAI", 1990)]
    assert row == openalex_table.Listing("AAAI", 1990, ("S4306420609",), 3, date(2026, 10, 10),
                                         "docs/research/2026-10-09-aaai-aies-facct-iaseai-sources.md")  # fmt: skip
    assert openalex_table.load("").listings == {}


@pytest.mark.parametrize(
    ("edit", "message"),
    [
        (lambda s: s.replace('venue = "AAAI"', 'venue = "ICML"'), "AAAI, AIES or FAccT"),
        (lambda s: s.replace("year = 1990", "year = 2010"), "only years whose records carry no DOI"),
        (lambda s: s.replace("year = 1990", "year = 1995"), "only years whose records carry no DOI"),
        (lambda s: s.replace('venue = "AAAI"', 'venue = "FAccT"'), "only years whose records carry no DOI"),
        (lambda s: s.replace("year = 1990", "year = true"), "year must be"),
        (lambda s: s.replace('["S4306420609"]', '["X1"]'), "source id"),
        (lambda s: s.replace('["S4306420609"]', '["S' + "1" * 20 + '"]'), "source id"),
        (lambda s: s.replace('["S4306420609"]', "[]"), "source id"),
        (lambda s: s.replace('["S4306420609"]', '"S4306420609"'), "source id"),
        (lambda s: s.replace('["S4306420609"]', '["S1", "S1"]'), "source id"),
        (lambda s: s.replace("works = 3", "works = 0"), "positive"),
        (lambda s: s.replace("works = 3", "works = true"), "positive"),
        (lambda s: s + s, "listed twice"),
        (lambda s: s.replace("verified = 2026-10-10", 'verified = "2026-10-10"'), "verified date"),
        (lambda s: s.replace('source = "docs', 'source = ""\n#'), "verified date"),
        (lambda s: s + "extra = 1\n", "unknown columns"),
        (lambda s: s.replace("works = 3\n", ""), "missing columns"),
    ],
)
def test_bad_rows_are_refused(edit, message) -> None:
    with pytest.raises(ValueError, match=message):
        openalex_table.load(edit(GOOD))


def test_the_shipped_table_loads() -> None:
    assert all(venue == "AAAI" for venue, _year in openalex_table.TABLE.listings)
