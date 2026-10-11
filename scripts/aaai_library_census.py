"""The AAAI library census (spec 01 §Sources, aaai_library row; decision-051, TASK-232): writes the rows of
`ingest/aaai_library.toml`, one Internet Archive capture of each dblp AAAI 1980-2008 record's aaai.org paper page. A
person runs it; no test runs it.

It reads, offline: the snapshot's AAAI 1980-2008 dblp records (`--snapshot`, read-only), and each one's dblp `ee`
links from the pinned release's AAAI extract (`<cache>/dblp/extract/aaai/`, read-only). It then sends exactly two
requests, both to the Internet Archive's CDX index (`web.archive.org/cdx/search/cdx`, never aaai.org): every
status-200 capture under `www.aaai.org/Library/AAAI/` and under `www.aaai.org/Library/IAAI/` (prefix queries,
`output=json`). The requests go through the shared HTTP layer (`http.HttpClient.send`: web.archive.org only, the repo's
generic User-Agent, no contact string, `aaai_library.MIN_INTERVAL` apart, one at a time) and are not cached.

For each record whose `ee` is a `www.aaai.org/Library/{AAAI,IAAI}/` page it picks one capture of that page (the same
URL once scheme, host case and a `:80` port are set aside; the path compared case-blind, as the archive's own URL key
does): the latest `text/html` 200 capture before 2023-01-01 (aaai.org moved to a new site in 2023), else the earliest.
It prints the counts and writes the table (`--out`), and nothing else.

    uv run python scripts/aaai_library_census.py --data-dir <data> --snapshot <data>/snapshots/<name>
"""

from __future__ import annotations

import argparse
import functools
import json
import textwrap
from collections import Counter
from dataclasses import replace
from datetime import date
from pathlib import Path
from urllib.parse import urlencode, urlparse

from openproceedings.ingest import aaai_library_table
from openproceedings.ingest.dblp_table import TABLE as DBLP_TABLE
from openproceedings.ingest.record import DBLP_YEARS
from openproceedings.ingest.sources import aaai_library, dblp
from openproceedings.ingest.sources.http import (
    PROCEEDINGS,
    USER_AGENT,
    HttpClient,
    Page,
    PageCache,
    Request,
    urllib_transport,
)

CDX = f"https://{aaai_library.HOST}/cdx/search/cdx"
PREFIXES = ("www.aaai.org/Library/AAAI/", "www.aaai.org/Library/IAAI/")
CUTOFF = "20230101000000"  # aaai.org's new site (2023) dropped the Library pages
MAX_BODY = 128 * 1024 * 1024
OUT = Path("backend/src/openproceedings/ingest/aaai_library.toml")
SOURCE = "docs/research/2026-10-09-aaai-aies-facct-iaseai-sources.md §AAAI 1980–2008 abstracts (scripts/aaai_library_census.py)"
HEADER = """\
# The AAAI library table (spec 01 §Sources, aaai_library row; decision-051, TASK-232). Data, not code:
# `ingest/aaai_library_table.py` loads and checks it, and `ingest/sources/aaai_library.py` reads AAAI's own abstracts
# for AAAI 1980-2008 from the Internet Archive's captures of the old aaai.org paper pages it names. aaai.org itself is
# never fetched (its robots.txt asks for a 43,200-second crawl delay; decision-051).
#
# Written by scripts/aaai_library_census.py (two CDX requests to web.archive.org; never edit a row by hand). One row
# per dblp AAAI 1980-2008 record whose dblp `ee` is a www.aaai.org/Library/{{AAAI,IAAI}}/ page with a 200 capture:
#   key        the dblp key (conf/aaai/<tail>; the record is op:aaai:<year>:dblp-<tail>)
#   url        the dblp `ee`, the aaai.org paper page (the attribution links it, never the archive)
#   timestamp  the capture fetched, https://web.archive.org/web/<timestamp>id_/<url>: the latest text/html 200
#              capture before 2023-01-01, else the earliest
#   digest     the archive's SHA-1 of the captured bytes (base32): other bytes are refused, never read
#   length     the CDX record length, for the record
#
{census}
"""


def snapshot_keys(snapshot: Path) -> dict[str, int]:
    """The snapshot's AAAI 1980-2008 dblp records: dblp key → year."""
    out: dict[str, int] = {}
    with (snapshot / "records.jsonl").open(encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            native = r["id"].split(":", 3)[3]
            if r["venue"] == "AAAI" and r["year"] in DBLP_YEARS["AAAI"] and native.startswith("dblp-"):
                out[f"conf/aaai/{native.removeprefix('dblp-')}"] = r["year"]
    return out


def norm(url: str) -> tuple[str, str] | None:
    """A page URL as the archive's URL key compares it: (host without a :80 port, lower-cased path); None for one
    with a query or another port."""
    p = urlparse(url)
    host = (p.hostname or "").lower()
    if p.query or p.fragment or p.port not in (None, 80, 443):
        return None
    return host, p.path.lower()


def library_ee(ees: list[str]) -> str | None:
    """The record's first `ee` that is an aaai.org Library page (`aaai_library_table.is_library_url`), or None."""
    return next((u for u in ees if aaai_library_table.is_library_url(u)), None)


def cdx_rows(f: HttpClient[Page], prefix: str) -> list[list[str]]:
    query = urlencode(
        {
            "url": prefix,
            "matchType": "prefix",
            "output": "json",
            "filter": "statuscode:200",
            "fl": "timestamp,original,digest,length,mimetype",
        }
    )
    resp = f.send(Request("GET", f"{CDX}?{query}", {"User-Agent": USER_AGENT, "Accept": "application/json"}))
    if resp.status != 200:
        raise SystemExit(f"CDX {prefix}: HTTP {resp.status}")
    body = json.loads(resp.body.decode("utf-8"))
    if not body:
        return []
    if body[0] != ["timestamp", "original", "digest", "length", "mimetype"]:
        raise SystemExit(f"CDX {prefix}: unexpected header row")
    return [list(map(str, row)) for row in body[1:]]


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()
    cache = args.data_dir / "cache"
    held = snapshot_keys(args.snapshot)
    extract = dblp.load_extract(cache, DBLP_TABLE, dblp.AAAI_SLICE)
    ees = {e.key: e.lists.get("ee", []) for e in extract.entries}
    print(f"snapshot {args.snapshot.name}: AAAI 1980-2008 dblp records {len(held)}")
    no_entry = [k for k in held if k not in ees]
    no_ee = [k for k in held if k in ees and not ees[k]]
    pages = {k: u for k in held if (u := library_ee(ees.get(k, [])))}
    other = [k for k in held if k in ees and ees[k] and k not in pages]
    print(f"  no release entry {len(no_entry)}; no ee {len(no_ee)} (by year "
          f"{dict(sorted(Counter(held[k] for k in no_ee).items()))}); ee not an aaai.org Library page "
          f"{len(other)}; a Library page {len(pages)}")  # fmt: skip

    # the shared client, uncached (`send` only): web.archive.org only, paced, retried; a CDX answer is a few MB
    policy = replace(PROCEEDINGS, hosts=aaai_library.HOSTS, min_interval=aaai_library.MIN_INTERVAL,
                     accept="application/json", expect="json", keep_query=True, max_body=MAX_BODY, timeout=300.0)  # fmt: skip
    f: HttpClient[Page] = HttpClient(PageCache(cache / aaai_library.CACHE_DIR),
                                     functools.partial(urllib_transport, max_body=MAX_BODY), policy)  # fmt: skip
    captures: dict[tuple[str, str], list[tuple[str, str, str, int]]] = {}
    skipped: Counter[str] = Counter()
    for prefix in PREFIXES:
        rows = cdx_rows(f, prefix)
        print(f"CDX {prefix}: {len(rows)} status-200 captures")
        for ts, original, digest, length, mime in rows:
            key = norm(original)
            if key is None:
                skipped["query_or_port"] += 1
            elif not mime.startswith("text/html"):
                skipped["not_html"] += 1
            elif not length.isdigit() or not aaai_library_table.DIGEST.fullmatch(digest):
                skipped["no_length_or_digest"] += 1
            else:
                captures.setdefault(key, []).append((ts, original, digest, int(length)))
    print(f"  captures set aside: {dict(sorted(skipped.items()))}; distinct pages captured {len(captures)}")

    chosen: dict[str, tuple[str, str, int]] = {}
    kinds: Counter[str] = Counter()
    url_differs = 0
    missing: list[str] = []
    for k, url in sorted(pages.items()):
        nk = norm(url)
        caps = captures.get(nk) if nk else None
        if not caps:
            missing.append(k)
            continue
        before = [c for c in caps if c[0] < CUTOFF]
        ts, original, digest, length = max(before) if before else min(caps)
        kinds["latest_before_2023" if before else "earliest"] += 1
        url_differs += original.split("://", 1)[-1].replace(":80/", "/") != url.split("://", 1)[-1]
        chosen[k] = (ts, digest, length)
    print(f"records with a capture {len(chosen)} of {len(pages)} with a Library page; no capture {len(missing)} "
          f"{missing[:10]}")  # fmt: skip
    print(f"captures chosen: {dict(sorted(kinds.items()))}; the capture's original URL differs from the ee "
          f"(beyond scheme and :80) {url_differs}")  # fmt: skip
    by_year = Counter(held[k] for k in chosen)
    print(f"rows by year: {dict(sorted(by_year.items()))}")

    verified = date.today()
    summary = (f"{len(held)} records in snapshot {args.snapshot.name}; {len(pages)} with a Library page `ee`; "
               f"{len(chosen)} rows ({kinds['latest_before_2023']} the latest capture before 2023, "
               f"{kinds['earliest']} the earliest); {len(no_ee)} records have no ee, {len(other)} another ee")  # fmt: skip
    census = textwrap.fill(f"Census {verified.isoformat()}: {summary}.", width=118, initial_indent="# ",
                           subsequent_indent="# ")  # fmt: skip
    lines = [HEADER.format(census=census), f"verified = {verified.isoformat()}",
             f"source = {json.dumps(SOURCE, ensure_ascii=False)}", "pages = ["]  # fmt: skip
    for k, (ts, digest, length) in sorted(chosen.items()):
        lines.append(f"  {{ key = {json.dumps(k)}, url = {json.dumps(pages[k])}, timestamp = \"{ts}\", "
                     f"digest = \"{digest}\", length = {length} }},")  # fmt: skip
    lines.append("]")
    text = "\n".join(lines) + "\n"
    aaai_library_table.load(text)  # the loader's rules, before anything is written
    args.out.write_text(text, encoding="utf-8")
    print(f"wrote {args.out} ({len(chosen)} rows); requests {f.stats.network}")


if __name__ == "__main__":
    main()
