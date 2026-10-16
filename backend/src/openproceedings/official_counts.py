"""Official accepted counts per venue × year × track, each with its citation (spec 07 §C; coverage-reporting
skill), and the M4 gate on them: every main-track and D&B cell with an official count is within ±1%.

This is the machine-readable copy of `docs/results/coverage-sources.md` (the cited, human-edited table); a
row goes into both in one change, and `tests/unit/test_official_counts.py` fails when they differ.
`GET /coverage` joins it to the indexed counts (`coverage.breakdown`). A row is added only with a citation a
reader can check (the conference's statistics page, the proceedings index or the OpenReview accepted
group), what it counts, and the date it was read; never a number from memory. Until a row exists, a cell is
reported with no official count and is not gated. An ungated cell may carry a cited note saying why it has no
row (`UNGATED_NOTES`, TASK-222), served on `/coverage` and listed in the coverage report.
"""

from __future__ import annotations

from collections.abc import Mapping
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
    ("AAAI", 2012, "main"): OfficialCount(
        292,
        "papers counted on AAAI's own accepted-paper list (the AAAI-12 accepted-papers PDF on aaai.org): 220 main technical, poster-only full papers included, plus 26 AI and the Web, 11 Cognitive Systems, 21 Computational Sustainability and AI, and 14 Robotics; independent of the proceedings because it differs from them in count (+2 on snapshot 2026-10-10-9efa49481112)",
        "https://aaai.org/wp-content/uploads/2023/01/aaai12accepted-papers.pdf (linked from https://aaai.org/conference/aaai/aaai12/)",
        date(2026, 10, 10),
    ),
    ("AAAI", 2013, "main"): OfficialCount(
        203,
        "papers accepted for publication in the proceedings from the 690 technical-program submissions, the four special tracks included (AI and the Web, Cognitive Systems, Computational Sustainability, AI and Robotics); late-breaking papers and spotlights excluded",
        "https://ojs.aaai.org/index.php/AAAI/article/view/8512 (AAAI-13 preface)",
        date(2026, 10, 9),
    ),
    ("AAAI", 2015, "main"): OfficialCount(
        539,
        "papers selected from the 1,991 main technical and topical track submissions and presented (AI Magazine conference report); student abstracts, IAAI, demos and the doctoral consortium excluded",
        "https://ojs.aaai.org/index.php/aimagazine/article/view/2606/2500 (submissions: https://ojs.aaai.org/index.php/AAAI/issue/view/304)",
        date(2026, 10, 9),
    ),
    ("AAAI", 2017, "main"): OfficialCount(
        637,
        "papers counted on AAAI's own accepted-paper list (the AAAI-17 accepted-papers PDF on aaai.org): 599 main technical plus 38 in three special tracks (Cognitive Systems, Computational Sustainability, Integrated Systems); independent of the proceedings because it differs from them in count (+2 on snapshot 2026-10-10-9efa49481112)",
        "https://aaai.org/wp-content/uploads/2023/01/aaai17accepted-papers.pdf (linked from https://aaai.org/conference/aaai/aaai17/aaai-17-program-overview/)",
        date(2026, 10, 10),
    ),
    ("AAAI", 2018, "main"): OfficialCount(
        938,
        "original research publications in the proceedings, selected from 3,800 well-formed submissions (acceptance rate 24.7%); student abstracts, IAAI and EAAI excluded",
        "https://ojs.aaai.org/index.php/AAAI/issue/view/301",
        date(2026, 10, 9),
    ),
    ("AAAI", 2019, "main"): OfficialCount(
        1147,
        "original research publications in the proceedings, selected from 7,095 original full paper submissions (acceptance rate 16.2%); senior member, doctoral consortium, student abstracts and demos excluded",
        "https://ojs.aaai.org/index.php/AAAI/issue/view/246",
        date(2026, 10, 9),
    ),
    ("AAAI", 2020, "main"): OfficialCount(
        1614,
        "papers counted on AAAI's own accepted-paper lists (the AAAI-20 PDFs on aaai.org): 1,589 main technical plus 25 AI for Social Impact; sister conference track, student abstracts, IAAI and EAAI excluded; independent of the proceedings because the list says it was made before camera-ready",
        "https://aaai.org/wp-content/uploads/2023/01/AAAI-20-Accepted-Paper-List.pdf and https://aaai.org/wp-content/uploads/2023/01/AAAI-20-Accepted-AISI-Papers.pdf (linked from https://aaai.org/conference/aaai/aaai-20/)",
        date(2026, 10, 10),
    ),
    ("AAAI", 2021, "main"): OfficialCount(
        1697,
        "papers counted on AAAI's own accepted-paper list as it stood before the proceedings (the AAAI-21 PDF headed Main Technical Track, in the copy the Internet Archive captured on 2020-12-30, before the conference): 1,657 main technical plus 40 AI for Social Impact, the 40 from the PDF's last section, Special Track on AI for Social Impact (pp. 121–124); independent of the proceedings because it was made before them; the owner chose this copy on 2026-10-16, since official counts come from a list made before the proceedings; the later copy on aaai.org has 1,656 plus the same 40, dropping one paper absent from the proceedings",
        "https://web.archive.org/web/20201230042125id_/https://aaai.org/Conferences/AAAI-21/wp-content/uploads/2020/12/AAAI-21_Accepted-Paper-List.Main_.Technical.Track_.pdf (SHA-1 base32 DZJNTKYZTPBVFWBS5AXMQIUBXI457YSX); the later copy: https://aaai.org/wp-content/uploads/2023/01/AAAI-21_Accepted-Paper-List.Main_.Technical.Track_.pdf (linked from https://aaai.org/conference/aaai/aaai-21/; captured https://web.archive.org/web/20230929155523id_/https://aaai.org/wp-content/uploads/2023/01/AAAI-21_Accepted-Paper-List.Main_.Technical.Track_.pdf, SOFX7UV3F7DWXILKLOLHRV5OKIO76JPZ)",
        date(2026, 10, 16),
    ),
    ("AIES", 2024, "main"): OfficialCount(
        150,
        "full archival papers accepted, per the chairs' statement ('sent 468 papers out for review and accepted 150'); student abstracts excluded",
        "https://ojs.aaai.org/index.php/AIES/article/view/31763 (AIES 2024 front matter); same figure in the table of https://www.aies-conference.com/2025/wp-content/doc/AIES-2025-Program-10.20.pdf",
        date(2026, 10, 9),
    ),
    ("AIES", 2025, "main"): OfficialCount(
        238,
        "full archival papers accepted, per the chairs' welcome ('sent 748 papers out for review and accepted 238 of them'); student abstracts excluded",
        "https://www.aies-conference.com/2025/wp-content/doc/AIES-2025-Program-10.20.pdf",
        date(2026, 10, 9),
    ),
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


@dataclass(frozen=True, slots=True)
class UngatedNote:
    """Why a cell has no official count to gate on, with a citation a reader can check (TASK-222)."""

    note: str
    citation: str
    accessed: date


_NOT_FOUND = (
    "no official accepted count was found: the only figure, {}, comes from the chairs' notification email as "
    "quoted on other sites and from third-party paper trackers, and it appears to count the main technical track alone, while "
    "this main track also holds the special tracks"
)

# a list counts as independent of the proceedings when it either says it is pre-camera-ready, or visibly differs from
# them in content (a different count or membership): either shows it was not derived from them (the controller's
# rulings, gate C rounds 1 and 2). A list that matches them exactly and isn't shown to predate them is a note
_AFTER = (
    "AAAI's own {list} lists {n} papers, the same as the proceedings, and nothing on it says it was made before "
    "them (its only archived copy was captured on {captured}, after they were published); like AAAI 2016's list it "
    "may be derived from the proceedings, so a gate on it could check the proceedings against themselves"
)

# (venue, year, track) → why that ungated cell has no official count; `docs/results/coverage-sources.md`
# §Ungated cells with a note is the cited copy, and `tests/unit/test_official_counts.py` keeps the two equal
UNGATED_NOTES: dict[tuple[str, int, str], UngatedNote] = {
    ("AAAI", 2010, "main"): UngatedNote(
        _AFTER.format(list="AAAI-10 papers page", n="262", captured="2010-08-30"),
        "https://web.archive.org/web/20100830185521/http://www.aaai.org/Conferences/AAAI/2010/aaai10papers.php",
        date(2026, 10, 11),
    ),
    ("AAAI", 2011, "main"): UngatedNote(
        "AAAI's own accepted-paper list has 240 papers and leaves out the Robotics Program; the index's main track "
        "holds 248, those 240 plus the 8 Robotics Program papers, so the list counts a different set of papers",
        "https://web.archive.org/web/20120605015434/http://www.aaai.org/Conferences/AAAI/2011/aaai11accepts.php",
        date(2026, 10, 10),
    ),
    ("AAAI", 2014, "main"): UngatedNote(
        _AFTER.format(list="AAAI-14 accepted-papers page", n="398", captured="2015-09-06"),
        "https://web.archive.org/web/20150906033202/http://www.aaai.org/Conferences/AAAI/2014/aaai14accepts.php",
        date(2026, 10, 11),
    ),
    ("AAAI", 2016, "main"): UngatedNote(
        "AAAI's own accepted-paper list is the same as the proceedings, section by section, and nothing on it says it "
        "was made before them, so it may be derived from them; a gate on it would check the proceedings against "
        "themselves",
        "https://ojs.aaai.org/index.php/AAAI/issue/view/303 (the proceedings the list matches; docs/research/2026-10-09-aaai-aies-facct-iaseai-sources.md §Official counts)",
        date(2026, 10, 10),
    ),
    ("AAAI", 2022, "main"): UngatedNote(
        _NOT_FOUND.format("1,349"),
        "docs/research/2026-10-09-aaai-aies-facct-iaseai-sources.md §Official counts",
        date(2026, 10, 10),
    ),
    ("AAAI", 2023, "main"): UngatedNote(
        _NOT_FOUND.format("1,721"),
        "docs/research/2026-10-09-aaai-aies-facct-iaseai-sources.md §Official counts",
        date(2026, 10, 10),
    ),
    ("AAAI", 2024, "main"): UngatedNote(
        _NOT_FOUND.format("2,342"),
        "docs/research/2026-10-09-aaai-aies-facct-iaseai-sources.md §Official counts",
        date(2026, 10, 10),
    ),
    ("AAAI", 2025, "main"): UngatedNote(
        _NOT_FOUND.format("3,032"),
        "docs/research/2026-10-09-aaai-aies-facct-iaseai-sources.md §Official counts",
        date(2026, 10, 10),
    ),
    ("AAAI", 2026, "main"): UngatedNote(
        _NOT_FOUND.format("4,167"),
        "docs/research/2026-10-09-aaai-aies-facct-iaseai-sources.md §Official counts",
        date(2026, 10, 10),
    ),
    ("AIES", 2026, "main"): UngatedNote(
        "the program co-chairs state that 1,001 papers were reviewed and 249 accepted (44 presented as orals or "
        "discussions, 205 as posters), but the program's own sessions list 244 papers: the 243 main-track papers "
        "the OJS proceedings publish and one that is not in them; the other 5 are named nowhere found, so no "
        "official count of what the index can hold exists; ungated by the owner, 2026-10-16 (TASK-217)",
        "https://www.aies-conference.com/2026/wp-content/uploads/2026/10/AIES-26-Program_v7.pdf (the program co-chairs' welcome; SHA-1 519552b4439d3ddec45ccb9085e2d9660072ed6a)",
        date(2026, 10, 16),
    ),
    ("IASEAI", 2026, "main"): UngatedNote(
        "57 archival papers are published in the proceedings; the conference accepted 92, and the 35 non-archival "
        "ones have no findable listing, so no official count of what the index can hold exists",
        "https://ojs.aaai.org/index.php/IASEAI/issue/view/741 (docs/research/2026-10-09-aaai-aies-facct-iaseai-sources.md §IASEAI)",
        date(2026, 10, 9),
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


def check_notes(
    notes: Mapping[tuple[str, int, str], UngatedNote], table: OfficialTable = OFFICIAL_ACCEPTED
) -> None:
    """Every note names a known venue and track, an ungated cell, its note and a citation (ValueError otherwise)."""
    for key, n in notes.items():
        venue, _year, track = key
        if venue not in VENUES.values() or track not in TRACKS or track == "unknown":
            raise ValueError(f"an ungated note names an unknown venue or track: {venue} {track}")
        if key in table and track in GATED_TRACKS:
            raise ValueError(
                f"{key}: a gated cell takes its cause in coverage-causes.toml, not an ungated note"
            )
        if not n.note.strip() or not n.citation.strip():
            raise ValueError(f"{key}: an ungated note needs its note and a citation")


check_notes(UNGATED_NOTES)


def within_gate(indexed: int, official: int) -> bool:
    """|indexed − official| ≤ 1% of official, in exact integer arithmetic."""
    return 100 * abs(indexed - official) <= GATE_PERCENT * official
