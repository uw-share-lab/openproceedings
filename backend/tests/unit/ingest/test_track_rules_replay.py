"""The TASK-224/225/226 track rules replayed over the pinned data: every AAAI 1980-2008 main-conference entry of the
pinned dblp release (key, crossref, pages) and every AIES 2018-2023 work of the cached Crossref harvest (DOI, page),
written to `fixtures/pinned/` from the real cache. The shipped tables must move exactly the entries counted here, per
venue, year and track, and drop exactly the not-paper rows named here. Before these rules every one was `main`. No
network: the fixtures are committed."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from openproceedings.ingest import acm_table, dblp_aaai_table

PINNED = Path(__file__).parents[2] / "fixtures" / "pinned"

AAAI_MOVED = {
    1993: {"demo": 7},
    1994: {"demo": 6, "student_abstract": 77},
    1996: {"consortium": 15, "iaai": 18, "other": 9, "student_abstract": 43},
    1997: {"consortium": 13, "iaai": 32, "other": 16, "student_abstract": 30},
    1998: {"consortium": 16, "iaai": 22, "student_abstract": 24},
    1999: {"consortium": 16, "demo": 17, "iaai": 17, "other": 4, "student_abstract": 29},
    2000: {"consortium": 12, "demo": 12, "iaai": 18, "other": 2, "student_abstract": 38},
    2002: {"consortium": 13, "demo": 10, "iaai": 18, "student_abstract": 17},
    2004: {"consortium": 12, "demo": 21, "iaai": 24, "student_abstract": 17},
    2005: {"consortium": 16, "demo": 22, "iaai": 18, "other": 15, "student_abstract": 22},
    2006: {"consortium": 13, "demo": 13, "iaai": 21, "other": 77, "student_abstract": 25},
    2007: {"consortium": 17, "demo": 9, "iaai": 22, "other": 26, "student_abstract": 42},
    2008: {"consortium": 15, "demo": 10, "iaai": 22, "other": 24, "student_abstract": 35},
}
# milestone B's not-paper rows (1986's invited talks and panels, 1990's panel chair)
AAAI_NOT_PAPER_BEFORE = {
    "Darden86", "Hendrix86", "McDermottH86", "SolowayBMRS86", "Winston86", "FriedlandMS86", "HartGRW86",
    "AikinsHMSS86", "FehlingAAGLM86", "KaczmarekNBHMWWW86", "NechesFKMP86", "Dumais90",
}  # fmt: skip
AAAI_REMOVED = {
    # TASK-225: the 1990 panelists and the 1996 panel statements
    "Balzer90", "Fikes90", "Fox90", "McDermott90", "Soloway90", "Hollan90", "McKeown90", "Jones90", "SelmanBDHMN96",
    # TASK-226: the official contents' invited talks of two pages or fewer (TASK-225's five abstracts among them)
    "Feigenbaum93", "Simon93", "Abarbanel96", "BonassoD96", "Freeman96", "Halpern96a", "ArkinF97", "Etherington97",
    "Wellman97", "Koller98", "Cassell00", "Schaeffer00",
}  # fmt: skip
AIES_MOVED = {2018: 19, 2019: 20, 2020: 0, 2021: 7, 2022: 31, 2023: 31}  # all to student_abstract
AIES_REMOVED = {2018: 2, 2019: 2, 2020: 4, 2021: 1, 2022: 6, 2023: 3}  # the keynotes


def _aaai() -> dict:
    return json.loads((PINNED / "aaai-main-pages.json").read_text(encoding="utf-8"))


def test_the_aaai_fixture_is_the_pinned_release_and_the_tables_census() -> None:
    raw, t = _aaai(), dblp_aaai_table.TABLE
    assert (raw["release_doi"], raw["release_sha256"]) == (t.release.doi, t.release.file.sha256)
    per_year = Counter(year for year, _key, _crossref, _pages in raw["entries"])
    assert per_year == {y: row.papers for y, row in t.years.items()}
    assert all(f"conf/aaai/{c}" in t.years[y].proceedings for y, _k, c, _p in raw["entries"])


def test_the_aaai_rules_move_and_drop_exactly_the_counted_entries() -> None:
    t = dblp_aaai_table.TABLE
    moved: dict[int, Counter[str]] = {}
    removed: set[str] = set()
    kept = 0
    for year, key, _crossref, pages in _aaai()["entries"]:
        if f"conf/aaai/{key}" in t.not_papers:
            removed.add(key)
            continue
        track, rule = t.main_track(f"conf/aaai/{key}", year, pages)
        assert (track == "main") == (rule is None)
        if track == "main":
            kept += 1
        else:
            moved.setdefault(year, Counter())[track] += 1
    assert {y: dict(c) for y, c in moved.items()} == AAAI_MOVED
    assert removed == AAAI_NOT_PAPER_BEFORE | AAAI_REMOVED
    assert len(AAAI_REMOVED) == 21 and sum(sum(c.values()) for c in moved.values()) == 1089
    assert kept == 4689 - 33 - 1089  # the census less every not-paper row and every moved entry


def test_the_aaai_rows_the_rulings_name() -> None:
    t = dblp_aaai_table.TABLE

    def track(key: str, year: int, pages: str | None) -> str:
        return t.main_track(f"conf/aaai/{key}", year, pages)[0]

    entries = {k: (y, p) for y, k, _c, p in _aaai()["entries"]}
    # TASK-225's video, demo and robot abstracts of 1993-94; ChangN94 is a student abstract by the official
    # contents, which win over TASK-225's "keep main" (ruling 4)
    for key in ("HippS93", "HuffmanL93", "KortenkampHCRBCKW93", "PearsonJL93", "ReeceS93", "RisemanHT93",
                "SaffiottiHKLMMRW93", "MaesDBP94", "MostowHRKSCW94"):  # fmt: skip
        assert track(key, *entries[key]) == "demo", key
    assert track("ChangN94", *entries["ChangN94"]) == "student_abstract"
    # dblp page oddities: a typo the [[track]] row fixes, an open end page, a typo the IAAI range absorbs
    assert (
        entries["BlackH06"][1] == "855-1856" and track("BlackH06", *entries["BlackH06"]) == "student_abstract"
    )
    assert (
        entries["AhmadiS06a"][1] == "1853-"
        and track("AhmadiS06a", *entries["AhmadiS06a"]) == "student_abstract"
    )
    # round 2: the IAAI 1996-1999 ranges; 1997's DevA97 starts at p. 853 in dblp, p. 852 on the IAAI page
    assert track("DevA97", *entries["DevA97"]) == "iaai" and entries["DevA97"][1] == "853-860"
    assert entries["LimCKO00"][1] == "1020-1015" and track("LimCKO00", *entries["LimCKO00"]) == "iaai"
    # the full-length invited papers, the 2008 Short Papers and 2005's two unlisted entries stay main
    for key in (
        "Kambhampati96a",
        "Hinton00",
        "GaurJH97",
        "AllenPZ08",
        "Sultanik05",
        "Thornton05",
        "WangL05",
    ):
        assert track(key, *entries[key]) == "main", key


def test_the_aies_rules_move_and_drop_exactly_the_counted_works() -> None:
    t = acm_table.TABLE
    works = json.loads((PINNED / "aies-2018-2023-pages.json").read_text(encoding="utf-8"))["works"]
    moved: Counter[int] = Counter()
    removed: Counter[int] = Counter()
    for year, rows in works.items():
        row = t.proceedings[("AIES", int(year))]
        assert len(rows) == row.dois and all(row.paper(doi) for doi, _ in rows)
        for doi, page in rows:
            if doi in t.not_papers:
                removed[int(year)] += 1
            elif (section := t.section("AIES", int(year), page)) is not None:
                assert section.track == "student_abstract"
                moved[int(year)] += 1
    assert {y: moved[y] for y in AIES_MOVED} == AIES_MOVED
    assert {y: removed[y] for y in AIES_REMOVED} == AIES_REMOVED
    assert sum(AIES_MOVED.values()) == 108 and sum(AIES_REMOVED.values()) == 18
    # the two front-of-volume entries that look like papers stay main
    for doi in ("10.1145/3375627.3375839", "10.1145/3461702.3462443"):
        assert doi not in t.not_papers


def test_the_review_round_rows() -> None:
    """BarishKCMPS00 is on the IAAI-2000 page (printed without a page), 2006-2008's NECTAR and Senior Member sections
    are `other` as from 2010 (TASK-218), and 2006's 18 AAAI Member Abstracts, which dblp gives no pages, are `other`
    by key rows."""
    t = dblp_aaai_table.TABLE
    entries = {k: (y, p) for y, k, _c, p in _aaai()["entries"]}
    assert t.main_track("conf/aaai/BarishKCMPS00", *entries["BarishKCMPS00"])[0] == "iaai"
    members = [
        k for k, row in t.tracks.items() if row.reason.startswith("listed under AAAI Member Abstracts")
    ]
    assert len(members) == 18 and all(entries[k.removeprefix("conf/aaai/")][1] is None for k in members)
    assert all(t.main_track(k, 2006, None)[0] == "other" for k in members)
    nectar = [
        s for s in t.sections if "ectar" in s.label or "NECTAR" in s.label or "Senior Member" in s.label
    ]
    assert [(s.year, s.first, s.last, s.track) for s in nectar] == [
        (2006, 1508, 1556, "other"), (2006, 1557, 1699, "other"), (2007, 1597, 1605, "other"),
        (2007, 1606, 1683, "other"), (2008, 1509, 1588, "other"), (2008, 1590, 1614, "other")]  # fmt: skip


def test_every_range_starts_on_a_real_entry() -> None:
    """Each range's first page is the start page of an entry of its year, so an off-by-one edge can't pass unseen."""
    starts = {(y, dblp_aaai_table.start_page(p)) for y, _k, _c, p in _aaai()["entries"]}
    missing = [
        (s.year, s.first, s.label) for s in dblp_aaai_table.TABLE.sections if (s.year, s.first) not in starts
    ]
    assert missing == []
    works = json.loads((PINNED / "aies-2018-2023-pages.json").read_text(encoding="utf-8"))["works"]
    aies = {(int(y), acm_table.start_page(page)) for y, rows in works.items() for _doi, page in rows}
    assert [(s.year, s.first) for s in acm_table.TABLE.sections if (s.year, s.first) not in aies] == []
