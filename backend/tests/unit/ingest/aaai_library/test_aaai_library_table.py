"""The AAAI library table (TASK-232, decision-051): one archived aaai.org paper page per dblp AAAI record, pinned to
one Internet Archive capture by URL, timestamp and SHA-1 digest. The loader refuses what the fetcher must never be
pointed at."""

from datetime import date

import pytest
from openproceedings.ingest import aaai_library_table as t

ROW = (
    '{ key = "conf/aaai/Faugeras80", url = "http://www.aaai.org/Library/AAAI/1980/aaai80-016.php", '
    'timestamp = "20081121081132", digest = "OCVOJKYZI5FDDK5QVHLKBBDR2G2ASKQE", length = 1553 }'
)


def table(*rows: str, verified: str = "2026-10-10") -> str:
    return f'verified = {verified}\nsource = "test"\npages = [\n' + ",\n".join(rows) + "\n]\n"


def test_a_row_loads_with_its_capture_url_and_native_id() -> None:
    got = t.load(table(ROW))
    assert got.verified == date(2026, 10, 10)
    (page,) = got.pages.values()
    assert page.key == "conf/aaai/Faugeras80" and page.native == "dblp-Faugeras80"
    assert page.capture == (
        "https://web.archive.org/web/20081121081132id_/http://www.aaai.org/Library/AAAI/1980/aaai80-016.php"
    )
    assert got.pages["conf/aaai/Faugeras80"] is page
    assert page.length == 1553


def test_an_iaai_page_and_an_https_url_load() -> None:
    row = ROW.replace("Faugeras80", "DetermanB98").replace(
        "http://www.aaai.org/Library/AAAI/1980/aaai80-016.php",
        "https://www.aaai.org/Library/IAAI/1998/iaai98-014.php",
    )
    assert (
        t.load(table(row)).pages["conf/aaai/DetermanB98"].url.startswith("https://www.aaai.org/Library/IAAI/")
    )


def test_a_duplicate_key_is_refused() -> None:
    with pytest.raises(ValueError, match="listed twice"):
        t.load(table(ROW, ROW))


@pytest.mark.parametrize(
    "url",
    [
        "http://aaai.org/Library/AAAI/1980/aaai80-016.php",  # another host
        "http://www.aaai.org.evil.example/Library/AAAI/1980/aaai80-016.php",
        "http://web.archive.org/Library/AAAI/1980/aaai80-016.php",
        "http://www.aaai.org/Papers/AAAI/1980/AAAI80-016.pdf",  # not a library page
        "http://www.aaai.org/Library/Symposia/Spring/2004/ss04-01-001.php",
        "http://www.aaai.org/Library/AAAI/1980/aaai80-016.php?x=1",
        "http://www.aaai.org/Library/AAAI/1980/aaai80-016.php#a",
        "http://www.aaai.org/Library/AAAI/../../etc/passwd",
        "ftp://www.aaai.org/Library/AAAI/1980/aaai80-016.php",
        "http://www.aaai.org:8080/Library/AAAI/1980/aaai80-016.php",
        "http://www.aaai.org/Library/AAAI/1980/aaai80 016.php",
    ],
)
def test_a_url_off_the_aaai_library_is_refused(url: str) -> None:
    with pytest.raises(ValueError, match="url"):
        t.load(table(ROW.replace("http://www.aaai.org/Library/AAAI/1980/aaai80-016.php", url)))


@pytest.mark.parametrize(
    ("old", "new", "what"),
    [
        ('"20081121081132"', '"2008112108113"', "timestamp"),
        ('"20081121081132"', "20081121081132", "timestamp"),
        ('"OCVOJKYZI5FDDK5QVHLKBBDR2G2ASKQE"', '"ocvojkyzi5fddk5qvhlkbbdr2g2askqe"', "digest"),
        ('"OCVOJKYZI5FDDK5QVHLKBBDR2G2ASKQE"', '"OCVOJKYZI5FDDK5QVHLKBBDR2G2ASK"', "digest"),
        ("length = 1553", "length = 0", "length"),
        ("length = 1553", 'length = "1553"', "length"),
        ('"conf/aaai/Faugeras80"', '"conf/icml/Faugeras80"', "key"),
        ('"conf/aaai/Faugeras80"', '"conf/aaai/Fau geras80"', "key"),
    ],
)
def test_a_malformed_column_is_refused(old: str, new: str, what: str) -> None:
    with pytest.raises(ValueError, match=what):
        t.load(table(ROW.replace(old, new)))


def test_a_missing_or_extra_column_is_refused() -> None:
    with pytest.raises(ValueError, match="columns"):
        t.load(table(ROW.replace(", length = 1553", "")))
    with pytest.raises(ValueError, match="columns"):
        t.load(table(ROW.replace("length = 1553", 'length = 1553, note = "x"')))


def test_the_header_is_required() -> None:
    with pytest.raises(ValueError, match="verified"):
        t.load('source = "x"\npages = []\n')
    with pytest.raises(ValueError, match="keys"):
        t.load('verified = 2026-10-10\nsource = "x"\npages = []\nother = 1\n')


def test_the_shipped_table_loads_and_names_only_held_aaai_years() -> None:
    from openproceedings.ingest import dblp_aaai_table
    from openproceedings.ingest.record import DBLP_YEARS

    shipped = t.TABLE
    assert shipped.pages, "the census rows are shipped"
    for page in shipped.pages.values():
        year = int(page.url.split("/")[-2])
        # a page's directory year is a held AAAI year (dblp may date a paper otherwise; the record's id rules)
        assert year in DBLP_YEARS["AAAI"] and year not in dblp_aaai_table.TABLE.not_held
