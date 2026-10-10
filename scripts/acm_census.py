"""The ACM census: per FAccT and AIES proceedings DOI, every Crossref work whose DOI extends it (spec 01 §Sources,
Crossref row; decision-049, milestone B). A person runs it to build or re-check `ingest/acm_proceedings.toml`; no
test runs it.

It reads Crossref through `crawl.crossref_fetcher` (one request at a time, a second apart; the contact, when
`CROSSREF_MAILTO` is set, goes in the User-Agent only), so every page it reads lands in `<cache>/crossref` where
`op ingest crossref` finds it. It writes nothing else. Per proceedings it:

1. reads the proceedings record (title, ISBNs, `published`);
2. walks a wide window (`published` +/- 120 days) of `prefix:10.1145` through `crossref.harvest`, and keeps every
   DOI extending the proceedings DOI with its `published` date-parts, type, `page` and title;
3. reads `works?filter=prefix:10.1145,isbn:<isbn>&rows=0` per ISBN (the independent count; the proceedings record
   itself carries the ISBN too);
4. proposes `window_from = min(published) - 7 days`, `window_until = max(published) + 7 days`;
5. prints the not-paper candidates (a `page` spanning one page, a title starting Tutorial, CRAFT, Keynote or Panel,
   a type other than `proceedings-article`) and, for AIES, every entry of two pages or fewer;
6. prints draft TOML rows.

    uv run python scripts/acm_census.py --cache <data>/cache [--only FAccT-2019] [--json out.json]

Which candidate is no paper is a person's call; the draft rows hold no `[[not_paper]]` rows.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from openproceedings.ingest.acm_table import Proceedings
from openproceedings.ingest.sources import crawl, crossref

PROCEEDINGS: tuple[tuple[str, int, str], ...] = (
    ("FAccT", 2019, "10.1145/3287560"),
    ("FAccT", 2020, "10.1145/3351095"),
    ("FAccT", 2021, "10.1145/3442188"),
    ("FAccT", 2022, "10.1145/3531146"),
    ("FAccT", 2023, "10.1145/3593013"),
    ("FAccT", 2024, "10.1145/3630106"),
    ("FAccT", 2025, "10.1145/3715275"),
    ("FAccT", 2026, "10.1145/3805689"),
    ("AIES", 2018, "10.1145/3278721"),
    ("AIES", 2019, "10.1145/3306618"),
    ("AIES", 2020, "10.1145/3375627"),
    ("AIES", 2021, "10.1145/3461702"),
    ("AIES", 2022, "10.1145/3514094"),
    ("AIES", 2023, "10.1145/3600211"),
)
WIDE = timedelta(days=120)
MARGIN = timedelta(days=7)
_CANDIDATE = re.compile(r"(?i)^\s*(tutorial|craft|keynote|panel)")
_PAGES = re.compile(r"^\s*([0-9]+)\s*(?:[-–]\s*([0-9]+))?\s*$")


def _date(parts: Any) -> date | None:
    """A Crossref `date-parts` value as a date (a missing month or day is the first)."""
    try:
        p = [int(x) for x in parts["date-parts"][0]]
    except (KeyError, IndexError, TypeError, ValueError):
        return None
    return date(p[0], p[1] if len(p) > 1 else 1, p[2] if len(p) > 2 else 1) if p else None


def span(page: str | None) -> int | None:
    """How many pages a Crossref `page` value spans (`690` and `690-690` are 1), or None when unreadable."""
    m = _PAGES.match(page or "")
    if not m:
        return None
    first, last = int(m.group(1)), int(m.group(2) or m.group(1))
    return last - first + 1 if last >= first else None


def _toml(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def census(venue: str, year: int, doi: str, f: Any) -> dict[str, Any]:
    head = f.get(crossref.proceedings_url(doi))
    msg = json.loads(head.text)["message"]
    title = crossref.title_of(msg) or ""
    isbns = [str(i) for i in msg.get("ISBN") or []]
    published = _date(msg.get("published")) or _date(msg.get("issued"))
    assert published is not None, f"{doi}: no published date"
    wide = Proceedings(venue, year, doi, title, published - WIDE, published + WIDE, 1, date.today(), "census")
    chain = crossref.harvest(wide, f)
    works: dict[str, dict[str, Any]] = {}
    window_works = 0
    for page, _parsed in chain:
        for item in json.loads(page.text)["message"].get("items") or []:
            window_works += 1
            d = str(item.get("DOI", "")).strip().lower()
            if not wide.paper(d):
                continue
            pub = _date(item.get("published"))
            works[d] = {"doi": d, "type": item.get("type"), "page": item.get("page"),
                        "published": pub.isoformat() if pub else None, "title": crossref.title_of(item),
                        "authors": len(item.get("author") or [])}  # fmt: skip
    isbn_totals = {}
    for isbn in isbns:
        page = f.get(f"https://{crossref.HOST}/works?filter=prefix:10.1145,isbn:{isbn}&rows=0")
        isbn_totals[isbn] = int(json.loads(page.text)["message"]["total-results"])
    dates = sorted(date.fromisoformat(w["published"]) for w in works.values() if w["published"])
    return {"venue": venue, "year": year, "doi": doi, "title": title, "isbn": isbn_totals,
            "published": published.isoformat(), "wide": [wide.window_from.isoformat(), wide.window_until.isoformat()],
            "pages": len(chain), "window_works": window_works, "works": sorted(works.values(), key=lambda w: w["doi"]),
            "window_from": (dates[0] - MARGIN).isoformat() if dates else None,
            "window_until": (dates[-1] + MARGIN).isoformat() if dates else None,
            "no_date": sum(1 for w in works.values() if not w["published"])}  # fmt: skip


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--cache", type=Path, required=True, help="the data directory's cache/")
    parser.add_argument("--only", action="append", default=[], help="VENUE-YEAR (repeatable); default all 14")
    parser.add_argument("--json", type=Path, help="also write every proceedings' works here")
    args = parser.parse_args()
    f = crawl.crossref_fetcher(args.cache, offline=False)
    out = []
    for venue, year, doi in PROCEEDINGS:
        if args.only and f"{venue}-{year}" not in args.only:
            continue
        c = census(venue, year, doi, f)
        out.append(c)
        types: dict[str, int] = {}
        for w in c["works"]:
            types[w["type"]] = types.get(w["type"], 0) + 1
        print(f"\n== {venue} {year} {doi} {c['title']!r}")
        print(f"published {c['published']}; wide window {c['wide'][0]}..{c['wide'][1]}: {c['pages']} pages, "
              f"{c['window_works']} works")  # fmt: skip
        print(f"toc DOIs: {len(c['works'])} (types {types}; no published date {c['no_date']})")
        print(f"ISBN totals (the proceedings record included): {c['isbn']}")
        print(f"proposed window {c['window_from']}..{c['window_until']}")
        print("not-paper candidates (doi, type, page, published, authors, title):")
        for w in c["works"]:
            s = span(w["page"])
            if s == 1 or _CANDIDATE.match(w["title"] or "") or w["type"] != "proceedings-article":
                print(
                    f"  {w['doi']}\t{w['type']}\t{w['page']}\t{w['published']}\t{w['authors']}\t{w['title']}"
                )
        if venue == "AIES":
            print("two pages or fewer (owner review):")
            for w in c["works"]:
                if (s := span(w["page"])) is not None and s <= 2:
                    print(f"  {w['doi']}\t{w['page']}\t{w['authors']}\t{w['title']}")
        print(f"no page value: {sum(1 for w in c['works'] if span(w['page']) is None)}")
    print("\n== draft TOML rows")
    for c in out:
        print("\n[[proceedings]]")
        print(f'venue = "{c["venue"]}"\nyear = {c["year"]}\ndoi = "{c["doi"]}"\ntitle = {_toml(c["title"])}')
        print(
            f"window_from = {c['window_from']}\nwindow_until = {c['window_until']}\ndois = {len(c['works'])}"
        )
        print(f"verified = {date.today().isoformat()}")
        print('source = "docs/research/2026-10-09-aaai-aies-facct-iaseai-sources.md (scripts/acm_census.py)"')
    if args.json:
        args.json.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
