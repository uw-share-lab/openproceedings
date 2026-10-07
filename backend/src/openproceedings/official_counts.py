"""Official accepted counts per venue × year × track, each with its citation (spec 07 §C; coverage-reporting
skill), and the M4 gate on them: every main-track and D&B cell with an official count is within ±1%.

This is the machine-readable copy of `docs/results/coverage-sources.md` (the cited, human-edited table); a
row goes into both in one change, and `tests/unit/test_official_counts.py` fails when they differ.
`GET /coverage` joins it to the indexed counts (`coverage.breakdown`). A row is added only with a citation a
reader can check (the conference's statistics page, the proceedings index or the OpenReview accepted
group), what it counts, and the date it was read; never a number from memory. Until a row exists, a cell is
reported with no official count and is not gated. The table is empty until the counts are sourced.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from openproceedings.vocab import TRACKS, VENUES

GATED_TRACKS: tuple[str, ...] = ("main", "datasets_benchmarks")  # spec 07 §C: main-track and D&B cells
GATE_PERCENT = 1  # |delta| ≤ 1% of the official count


@dataclass(frozen=True, slots=True)
class OfficialCount:
    accepted: int  # > 0
    counts: str  # what the number counts (orals + spotlights + posters? before withdrawals?)
    citation: str  # a URL or a citation a reader can check
    accessed: date


# (venue, year, track) → its official accepted count
type OfficialTable = dict[tuple[str, int, str], OfficialCount]
OFFICIAL_ACCEPTED: OfficialTable = {
    ("ICLR", 2013, "main"): OfficialCount(
        24,
        "conference-track papers on the ICLR 2013 accepted list (workshop track excluded)",
        "https://iclr.cc/archive/2013/conference-proceedings.html",
        date(2026, 9, 27),
    ),
    ("ICLR", 2014, "main"): OfficialCount(
        35,
        "conference-track papers on the ICLR 2014 accepted list (workshop track excluded)",
        "https://iclr.cc/archive/2014/conference-proceedings",
        date(2026, 9, 27),
    ),
    ("ICLR", 2015, "main"): OfficialCount(
        31,
        "distinct conference-track papers on the accepted list (11 orals also listed as posters, counted once; workshop papers excluded)",
        "https://iclr.cc/archive/www/doku.php%3Fid=iclr2015:accepted-main.html",
        date(2026, 9, 27),
    ),
    ("ICLR", 2016, "main"): OfficialCount(
        80,
        "conference-track papers on the accepted list: 15 orals + 65 posters (workshop track excluded)",
        "https://iclr.cc/archive/www/doku.php%3Fid=iclr2016:accepted-main.html",
        date(2026, 9, 27),
    ),
    ("ICLR", 2017, "main"): OfficialCount(
        198,
        "conference-track papers in the conference poster sessions C1-C198 (orals included; workshop invitations excluded)",
        "https://iclr.cc/archive/www/doku.php%3Fid=iclr2017:conference_posters.html",
        date(2026, 9, 27),
    ),
    ("ICLR", 2018, "main"): OfficialCount(
        336,
        "conference papers on the ICLR 2018 virtual-site paper list (orals + posters)",
        "https://iclr.cc/virtual/2018/papers.html",
        date(2026, 9, 27),
    ),
    ("ICLR", 2019, "main"): OfficialCount(
        501,
        "conference papers on the ICLR 2019 virtual-site paper list (orals + posters)",
        "https://iclr.cc/virtual/2019/papers.html",
        date(2026, 9, 27),
    ),
    ("ICLR", 2020, "main"): OfficialCount(
        687,
        "conference papers on the ICLR 2020 virtual-site paper list (orals + spotlights + posters)",
        "https://iclr.cc/virtual/2020/papers.html",
        date(2026, 9, 27),
    ),
    ("ICLR", 2021, "main"): OfficialCount(
        860,
        "posters in the fact sheet, one per accepted paper (orals and spotlights included); the virtual-site list also has 860",
        "https://iclr.cc/media/Press/ICLR_2021_Fact_Sheet.pdf",
        date(2026, 9, 27),
    ),
    ("ICLR", 2022, "main"): OfficialCount(
        1095,
        "total accepted papers in the fact sheet (orals + spotlights + posters)",
        "https://iclr.cc/media/Press/ICLR_2022_Fact_Sheet.pdf",
        date(2026, 9, 27),
    ),
    ("ICLR", 2023, "main"): OfficialCount(
        1574,
        "accepted papers in the fact sheet: 91 top-5% + 280 top-25% + 1,203 posters",
        "https://media.iclr.cc/Conferences/ICLR2023/ICLR2023-Fact_Sheet.pdf",
        date(2026, 9, 27),
    ),
    ("ICLR", 2024, "main"): OfficialCount(
        2260,
        "papers in the ICLR 2024 proceedings index (equals the fact sheet's accepted count); Tiny Papers and blog posts excluded",
        "https://proceedings.iclr.cc/paper_files/paper/2024",
        date(2026, 9, 27),
    ),
    ("ICLR", 2025, "main"): OfficialCount(
        3703,
        "papers in the ICLR 2025 proceedings index (fact sheet announced 3,704); blog posts excluded",
        "https://proceedings.iclr.cc/paper_files/paper/2025",
        date(2026, 9, 27),
    ),
    ("ICLR", 2026, "main"): OfficialCount(
        5351,
        "papers in the ICLR 2026 proceedings index (5,351 distinct Conference entries; fact sheet announced 5,357, retrospective 5,355)",
        "https://proceedings.iclr.cc/paper_files/paper/2026",
        date(2026, 10, 5),
    ),
    ("ICML", 2013, "main"): OfficialCount(
        283,
        "papers in PMLR volume 28 (every accepted paper; ICML 2013 had no separate tracks)",
        "https://proceedings.mlr.press/v28/",
        date(2026, 9, 27),
    ),
    ("ICML", 2014, "main"): OfficialCount(
        310,
        "papers in PMLR volume 32 (every accepted paper)",
        "https://proceedings.mlr.press/v32/",
        date(2026, 9, 27),
    ),
    ("ICML", 2015, "main"): OfficialCount(
        270,
        "papers in PMLR volume 37 (every accepted paper)",
        "https://proceedings.mlr.press/v37/",
        date(2026, 9, 27),
    ),
    ("ICML", 2016, "main"): OfficialCount(
        322,
        "papers in PMLR volume 48 (every accepted paper)",
        "https://proceedings.mlr.press/v48/",
        date(2026, 9, 27),
    ),
    ("ICML", 2017, "main"): OfficialCount(
        434,
        "papers in PMLR volume 70 (every accepted paper)",
        "https://proceedings.mlr.press/v70/",
        date(2026, 9, 27),
    ),
    ("ICML", 2018, "main"): OfficialCount(
        621,
        "papers in PMLR volume 80 (every accepted paper)",
        "https://proceedings.mlr.press/v80/",
        date(2026, 9, 27),
    ),
    ("ICML", 2019, "main"): OfficialCount(
        773,
        "papers in PMLR volume 97 (every accepted paper)",
        "https://proceedings.mlr.press/v97/",
        date(2026, 9, 27),
    ),
    ("ICML", 2020, "main"): OfficialCount(
        1084,
        "papers in PMLR volume 119 (every accepted paper)",
        "https://proceedings.mlr.press/v119/",
        date(2026, 9, 27),
    ),
    ("ICML", 2021, "main"): OfficialCount(
        1183,
        "papers in PMLR volume 139 (every accepted paper)",
        "https://proceedings.mlr.press/v139/",
        date(2026, 9, 27),
    ),
    ("ICML", 2022, "main"): OfficialCount(
        1233,
        "papers in PMLR volume 162 (every accepted paper)",
        "https://proceedings.mlr.press/v162/",
        date(2026, 9, 27),
    ),
    ("ICML", 2023, "main"): OfficialCount(
        1828,
        "papers in PMLR volume 202 (every accepted paper)",
        "https://proceedings.mlr.press/v202/",
        date(2026, 9, 27),
    ),
    ("ICML", 2024, "main"): OfficialCount(
        2610,
        "papers in PMLR volume 235, including the 75 position papers (fact sheet), which ICML 2024 did not publish as a separate track",
        "https://proceedings.mlr.press/v235/",
        date(2026, 9, 27),
    ),
    ("ICML", 2025, "main"): OfficialCount(
        3260,
        "main-track accepted papers in the fact sheet; the 73 position papers are counted separately",
        "https://media.icml.cc/Conferences/ICML2025/ICML2025_Fact_Sheet.pdf",
        date(2026, 9, 27),
    ),
    ("ICML", 2026, "main"): OfficialCount(
        6341,
        "papers on the ICML 2026 virtual-site paper list that link an OpenReview forum (6,554 of its 6,628 posters; the 74 TMLR/JMLR journal-track posters excluded) and are not among the 213 on the site's position-papers listing; both lists counted entry by entry",
        "https://icml.cc/static/virtual/data/icml-2026-orals-posters.json and https://icml.cc/virtual/2026/events/2026-position-papers",
        date(2026, 10, 5),
    ),
    ("NeurIPS", 1987, "main"): OfficialCount(
        90,
        "papers in the NeurIPS 1987 proceedings index (every accepted paper; the page's own count)",
        "https://proceedings.neurips.cc/paper_files/paper/1987",
        date(2026, 10, 7),
    ),
    ("NeurIPS", 1988, "main"): OfficialCount(
        94,
        "papers in the NeurIPS 1988 proceedings index (every accepted paper; the page's own count)",
        "https://proceedings.neurips.cc/paper_files/paper/1988",
        date(2026, 10, 7),
    ),
    ("NeurIPS", 1989, "main"): OfficialCount(
        101,
        "papers in the NeurIPS 1989 proceedings index (every accepted paper; the page's own count)",
        "https://proceedings.neurips.cc/paper_files/paper/1989",
        date(2026, 10, 7),
    ),
    ("NeurIPS", 1990, "main"): OfficialCount(
        143,
        "papers in the NeurIPS 1990 proceedings index (every accepted paper; the page's own count)",
        "https://proceedings.neurips.cc/paper_files/paper/1990",
        date(2026, 10, 7),
    ),
    ("NeurIPS", 1991, "main"): OfficialCount(
        144,
        "papers in the NeurIPS 1991 proceedings index (every accepted paper; the page's own count)",
        "https://proceedings.neurips.cc/paper_files/paper/1991",
        date(2026, 10, 7),
    ),
    ("NeurIPS", 1992, "main"): OfficialCount(
        127,
        "papers in the NeurIPS 1992 proceedings index (every accepted paper; the page's own count)",
        "https://proceedings.neurips.cc/paper_files/paper/1992",
        date(2026, 10, 7),
    ),
    ("NeurIPS", 1993, "main"): OfficialCount(
        158,
        "papers in the NeurIPS 1993 proceedings index (every accepted paper; the page's own count)",
        "https://proceedings.neurips.cc/paper_files/paper/1993",
        date(2026, 10, 7),
    ),
    ("NeurIPS", 1994, "main"): OfficialCount(
        140,
        "papers in the NeurIPS 1994 proceedings index (every accepted paper; the page's own count)",
        "https://proceedings.neurips.cc/paper_files/paper/1994",
        date(2026, 10, 7),
    ),
    ("NeurIPS", 1995, "main"): OfficialCount(
        152,
        "papers in the NeurIPS 1995 proceedings index (every accepted paper; the page's own count)",
        "https://proceedings.neurips.cc/paper_files/paper/1995",
        date(2026, 10, 7),
    ),
    ("NeurIPS", 1996, "main"): OfficialCount(
        152,
        "papers in the NeurIPS 1996 proceedings index (every accepted paper; the page's own count)",
        "https://proceedings.neurips.cc/paper_files/paper/1996",
        date(2026, 10, 7),
    ),
    ("NeurIPS", 1997, "main"): OfficialCount(
        150,
        "papers in the NeurIPS 1997 proceedings index (every accepted paper; the page's own count)",
        "https://proceedings.neurips.cc/paper_files/paper/1997",
        date(2026, 10, 7),
    ),
    ("NeurIPS", 1998, "main"): OfficialCount(
        151,
        "papers in the NeurIPS 1998 proceedings index (every accepted paper; the page's own count)",
        "https://proceedings.neurips.cc/paper_files/paper/1998",
        date(2026, 10, 7),
    ),
    ("NeurIPS", 1999, "main"): OfficialCount(
        150,
        "papers in the NeurIPS 1999 proceedings index (every accepted paper; the page's own count)",
        "https://proceedings.neurips.cc/paper_files/paper/1999",
        date(2026, 10, 7),
    ),
    ("NeurIPS", 2000, "main"): OfficialCount(
        152,
        "papers in the NeurIPS 2000 proceedings index (every accepted paper; the page's own count)",
        "https://proceedings.neurips.cc/paper_files/paper/2000",
        date(2026, 10, 7),
    ),
    ("NeurIPS", 2001, "main"): OfficialCount(
        197,
        "papers in the NeurIPS 2001 proceedings index (every accepted paper; the page's own count)",
        "https://proceedings.neurips.cc/paper_files/paper/2001",
        date(2026, 10, 7),
    ),
    ("NeurIPS", 2002, "main"): OfficialCount(
        207,
        "papers in the NeurIPS 2002 proceedings index (every accepted paper; the page's own count)",
        "https://proceedings.neurips.cc/paper_files/paper/2002",
        date(2026, 10, 7),
    ),
    ("NeurIPS", 2003, "main"): OfficialCount(
        198,
        "papers in the NeurIPS 2003 proceedings index (every accepted paper; the page's own count)",
        "https://proceedings.neurips.cc/paper_files/paper/2003",
        date(2026, 10, 7),
    ),
    ("NeurIPS", 2004, "main"): OfficialCount(
        207,
        "papers in the NeurIPS 2004 proceedings index (every accepted paper; the page's own count)",
        "https://proceedings.neurips.cc/paper_files/paper/2004",
        date(2026, 10, 7),
    ),
    ("NeurIPS", 2005, "main"): OfficialCount(
        207,
        "papers in the NeurIPS 2005 proceedings index (every accepted paper; the page's own count)",
        "https://proceedings.neurips.cc/paper_files/paper/2005",
        date(2026, 10, 7),
    ),
    ("NeurIPS", 2006, "main"): OfficialCount(
        204,
        "papers in the NeurIPS 2006 proceedings index (every accepted paper; the page's own count)",
        "https://proceedings.neurips.cc/paper_files/paper/2006",
        date(2026, 10, 7),
    ),
    ("NeurIPS", 2007, "main"): OfficialCount(
        217,
        "papers in the NeurIPS 2007 proceedings index (every accepted paper; the page's own count)",
        "https://proceedings.neurips.cc/paper_files/paper/2007",
        date(2026, 10, 7),
    ),
    ("NeurIPS", 2008, "main"): OfficialCount(
        250,
        "papers in the NeurIPS 2008 proceedings index (every accepted paper; the page's own count)",
        "https://proceedings.neurips.cc/paper_files/paper/2008",
        date(2026, 10, 7),
    ),
    ("NeurIPS", 2009, "main"): OfficialCount(
        262,
        "papers in the NeurIPS 2009 proceedings index (every accepted paper; the page's own count)",
        "https://proceedings.neurips.cc/paper_files/paper/2009",
        date(2026, 10, 7),
    ),
    ("NeurIPS", 2010, "main"): OfficialCount(
        292,
        "papers in the NeurIPS 2010 proceedings index (every accepted paper; the page's own count)",
        "https://proceedings.neurips.cc/paper_files/paper/2010",
        date(2026, 10, 7),
    ),
    ("NeurIPS", 2011, "main"): OfficialCount(
        306,
        "papers in the NeurIPS 2011 proceedings index (every accepted paper; the page's own count)",
        "https://proceedings.neurips.cc/paper_files/paper/2011",
        date(2026, 10, 7),
    ),
    ("NeurIPS", 2012, "main"): OfficialCount(
        370,
        "papers in the NeurIPS 2012 proceedings index (every accepted paper; the page's own count)",
        "https://proceedings.neurips.cc/paper_files/paper/2012",
        date(2026, 10, 7),
    ),
    ("NeurIPS", 2013, "main"): OfficialCount(
        360,
        "papers in the NeurIPS 2013 proceedings index (every accepted paper; the page's own count)",
        "https://proceedings.neurips.cc/paper_files/paper/2013",
        date(2026, 9, 27),
    ),
    ("NeurIPS", 2014, "main"): OfficialCount(
        411,
        "papers in the NeurIPS 2014 proceedings index (every accepted paper; the page's own count)",
        "https://proceedings.neurips.cc/paper_files/paper/2014",
        date(2026, 9, 27),
    ),
    ("NeurIPS", 2015, "main"): OfficialCount(
        403,
        "papers in the NeurIPS 2015 proceedings index (every accepted paper; the page's own count)",
        "https://proceedings.neurips.cc/paper_files/paper/2015",
        date(2026, 9, 27),
    ),
    ("NeurIPS", 2016, "main"): OfficialCount(
        569,
        "papers in the NeurIPS 2016 proceedings index (every accepted paper; the page's own count)",
        "https://proceedings.neurips.cc/paper_files/paper/2016",
        date(2026, 9, 27),
    ),
    ("NeurIPS", 2017, "main"): OfficialCount(
        679,
        "papers in the NeurIPS 2017 proceedings index (every accepted paper; the page's own count)",
        "https://proceedings.neurips.cc/paper_files/paper/2017",
        date(2026, 9, 27),
    ),
    ("NeurIPS", 2018, "main"): OfficialCount(
        1009,
        "papers in the NeurIPS 2018 proceedings index (every accepted paper; the page's own count)",
        "https://proceedings.neurips.cc/paper_files/paper/2018",
        date(2026, 9, 27),
    ),
    ("NeurIPS", 2019, "main"): OfficialCount(
        1428,
        "papers in the NeurIPS 2019 proceedings index (every accepted paper; the page's own count)",
        "https://proceedings.neurips.cc/paper_files/paper/2019",
        date(2026, 9, 27),
    ),
    ("NeurIPS", 2020, "main"): OfficialCount(
        1898,
        "papers in the NeurIPS 2020 proceedings index (equals the 2020 fact sheet)",
        "https://proceedings.neurips.cc/paper_files/paper/2020",
        date(2026, 9, 27),
    ),
    ("NeurIPS", 2021, "main"): OfficialCount(
        2334,
        "main-track papers in the NeurIPS 2021 proceedings index (equals the fact sheet); D&B is on its own site",
        "https://proceedings.neurips.cc/paper_files/paper/2021",
        date(2026, 9, 27),
    ),
    ("NeurIPS", 2022, "main"): OfficialCount(
        2671,
        "main-track (Conference) papers in the NeurIPS 2022 proceedings index; D&B excluded",
        "https://proceedings.neurips.cc/paper_files/paper/2022",
        date(2026, 9, 27),
    ),
    ("NeurIPS", 2023, "main"): OfficialCount(
        3218,
        "main-track (Conference) papers in the NeurIPS 2023 proceedings index (equals the fact sheet); D&B excluded",
        "https://proceedings.neurips.cc/paper_files/paper/2023",
        date(2026, 9, 27),
    ),
    ("NeurIPS", 2024, "main"): OfficialCount(
        4034,
        "main-track (Conference) papers in the NeurIPS 2024 proceedings index (fact sheet announced 4,037); D&B excluded",
        "https://proceedings.neurips.cc/paper_files/paper/2024",
        date(2026, 9, 27),
    ),
    ("NeurIPS", 2025, "main"): OfficialCount(
        5286,
        "main-track (`conference`) papers in the published vol38 proceedings companion; D&B and position excluded",
        "https://proceedings.neurips.cc/paper_files/paper/2025/vol38-main-conference",
        date(2026, 9, 27),
    ),
    ("NeurIPS", 2021, "datasets_benchmarks"): OfficialCount(
        174,
        "D&B papers in the 2021 D&B proceedings, round 1 (66) + round 2 (108); equals the fact sheet",
        "https://datasets-benchmarks-proceedings.neurips.cc/paper/2021",
        date(2026, 9, 27),
    ),
    ("NeurIPS", 2022, "datasets_benchmarks"): OfficialCount(
        163,
        "D&B papers in the NeurIPS 2022 proceedings index (equals the fact sheet)",
        "https://proceedings.neurips.cc/paper_files/paper/2022",
        date(2026, 9, 27),
    ),
    ("NeurIPS", 2023, "datasets_benchmarks"): OfficialCount(
        322,
        "D&B papers in the NeurIPS 2023 proceedings index (equals the fact sheet)",
        "https://proceedings.neurips.cc/paper_files/paper/2023",
        date(2026, 9, 27),
    ),
    ("NeurIPS", 2024, "datasets_benchmarks"): OfficialCount(
        459,
        "D&B papers in the NeurIPS 2024 proceedings index (fact sheet announced 460)",
        "https://proceedings.neurips.cc/paper_files/paper/2024",
        date(2026, 9, 27),
    ),
    ("NeurIPS", 2025, "datasets_benchmarks"): OfficialCount(
        497,
        "D&B (`datasets_and_benchmarks_track`) papers in the published vol38 proceedings companion",
        "https://proceedings.neurips.cc/paper_files/paper/2025/vol38-main-conference",
        date(2026, 9, 27),
    ),
}


def check_table(table: OfficialTable) -> None:
    """Every row names a known venue and track, a positive count and a citation (ValueError otherwise)."""
    for (venue, _year, track), row in table.items():
        if venue not in VENUES.values() or track not in TRACKS or track == "unknown":
            raise ValueError(f"an official count names an unknown venue or track: {venue} {track}")
        if row.accepted <= 0 or not row.citation.strip() or not row.counts.strip():
            raise ValueError(f"the official count for {venue} {track} needs a positive count and a citation")


check_table(OFFICIAL_ACCEPTED)


def within_gate(indexed: int, official: int) -> bool:
    """|indexed − official| ≤ 1% of official, in exact integer arithmetic."""
    return 100 * abs(indexed - official) <= GATE_PERCENT * official
