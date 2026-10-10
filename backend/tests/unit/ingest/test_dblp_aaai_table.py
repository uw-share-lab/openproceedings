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
    assert dblp_aaai_table.TABLE.not_held == frozenset({1981, 1985, 1989, 2001, 2003, 2009})


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
