"""The dblp AAAI census: per `conf/aaai/` proceedings key dated 1980-2009, the inproceedings the pinned release
lists under it (spec 01 §Sources, dblp row; decision-049, milestone B). A person runs it to build or re-check
`ingest/dblp_aaai.toml`; no test runs it.

It reads the release already on disk (`dblp_table.TABLE`'s pin) through `dblp.prepare_slices` with AAAI's slice
alone, so it fetches nothing: with no release on disk it stops. It writes nothing but AAAI's extract
(`<cache>/dblp/extract/aaai/<sha256>.json`); ICML's extract is read back or left alone, never rewritten.

    uv run python scripts/dblp_aaai_census.py --cache <data>/cache

It prints every proceedings key dated 1980-2009 with dblp's year and title and the inproceedings crossref'ing it,
the years with no key, the not-paper candidates under each key (a title that starts like front matter, or no
author), the counts of homonym-numbered authors, keys outside `dblp.NATIVE`, `publtype` entries and DOI `ee`s, and
draft TOML rows. Which key is the main conference, a workshop or excluded, and which candidate is no paper, is a
person's call: the draft rows mark every key with more than one per year for review.
"""

from __future__ import annotations

import argparse
import re
from collections import Counter, defaultdict
from pathlib import Path

from openproceedings.ingest.sources import dblp
from openproceedings.ingest.sources.dblp_xml import DblpEntry

FIRST, LAST = 1980, 2009
_CANDIDATE = re.compile(
    r"(?i)^(invited talk|keynote|panel|preface|front matter|index|proceedings|program committee)"
)
_HOMONYM = re.compile(r"\s[0-9]{4}\Z")


def _year(e: DblpEntry) -> int | None:
    raw = e.fields.get("year", "")
    return int(raw) if raw.isdigit() else None


def _toml(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--cache", type=Path, required=True, help="the data directory's cache/ (offline)")
    args = parser.parse_args()
    extract = dblp.prepare_slices(args.cache, None, slices=(dblp.AAAI_SLICE,))["AAAI"]
    print(f"release {extract.doi} sha256 {extract.sha256}; {len(extract.entries)} conf/aaai/ entries")

    proceedings = {e.key: e for e in extract.entries if e.type == "proceedings"}
    under: dict[str, list[DblpEntry]] = defaultdict(list)
    for e in extract.entries:
        if e.type == "inproceedings":
            under[e.fields.get("crossref", "")].append(e)
    in_range = {k: e for k, e in proceedings.items() if (y := _year(e)) is not None and FIRST <= y <= LAST}
    undated = sorted(k for k, e in proceedings.items() if _year(e) is None)

    print(f"\n== proceedings keys dated {FIRST}-{LAST} (key, year, inproceedings, title)")
    by_year: dict[int, list[str]] = defaultdict(list)
    for key, e in sorted(in_range.items(), key=lambda kv: (_year(kv[1]), kv[0])):
        y = _year(e)
        assert y is not None
        by_year[y].append(key)
        print(f"{key}\t{y}\t{len(under[key])}\t{e.fields.get('title', '')}")
    if undated:
        print(f"proceedings with no readable year: {undated}")
    print(
        f"\n== years {FIRST}-{LAST} with no proceedings key: {[y for y in range(FIRST, LAST + 1) if y not in by_year]}"
    )

    print("\n== not-paper candidates under keys dated in range (key, crossref, authors, title)")
    for key in sorted(in_range):
        for e in under[key]:
            title = e.fields.get("title", "")
            if _CANDIDATE.match(title) or not e.lists.get("author"):
                print(f"{e.key}\t{key}\t{len(e.lists.get('author', []))}\t{title}")

    papers = [e for k in in_range for e in under[k]]
    homonyms = Counter(a for e in papers for a in e.lists.get("author", []) if _HOMONYM.search(a))
    bad_native = sorted(e.key for e in papers if not dblp.NATIVE.fullmatch(e.key[len("conf/aaai/") :]))
    publtype = Counter((e.publtype, e.fields.get("crossref")) for e in papers if e.publtype is not None)
    doi = sum(1 for e in papers if any(dblp._DOI_URL.match(x) for x in e.lists.get("ee", [])))
    orphans = Counter(e.fields.get("crossref") for e in extract.entries
                      if e.type == "inproceedings" and e.fields.get("crossref") not in proceedings
                      and (y := _year(e)) is not None and FIRST <= y <= LAST)  # fmt: skip
    other_types = Counter(e.type for e in extract.entries if e.type not in {"proceedings", "inproceedings"})
    print(f"\n== over the {len(papers)} inproceedings under keys dated {FIRST}-{LAST}")
    print(f"authors with a homonym number: {sum(homonyms.values())} occurrences, {len(homonyms)} distinct")
    print(f"keys failing dblp.NATIVE: {len(bad_native)} {bad_native[:20]}")
    print(f"publtype entries: {sum(publtype.values())} {dict(publtype)}")
    print(f"with a DOI ee: {doi}")
    print(
        f"inproceedings dated {FIRST}-{LAST} whose crossref is no conf/aaai/ proceedings key: {dict(orphans)}"
    )
    print(f"other entry types in the slice: {dict(other_types)}")

    print(
        "\n== draft TOML rows (every key of a year is drafted under [[year]]: a person moves workshops out)"
    )
    for y in sorted(by_year):
        if y > LAST - 1:
            continue
        keys = by_year[y]
        title = in_range[keys[0]].fields.get("title", "")
        print("\n[[year]]")
        print(f"year = {y}")
        print(f"proceedings = [{', '.join(_toml(k) for k in keys)}]")
        print(f"papers = {sum(len(under[k]) for k in keys)}")
        print(f"title = {_toml(title)}")
        print("verified = 2026-10-10")
        print('source = "docs/research/2026-10-09-aaai-aies-facct-iaseai-sources.md"')


if __name__ == "__main__":
    main()
