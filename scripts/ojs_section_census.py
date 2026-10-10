"""The ojs.aaai.org section census: per journal, volume and OAI set, how many records the live list holds (spec 01
§Sources, OJS row; decision-049). A person runs it to build or re-check `ingest/ojs_sections.toml`; no test runs it.

It harvests each journal set by set with the miner's own `ojs.journal_sets` and `ojs.harvest_set` (the per-set
`ListRecords` chains and their ListIdentifiers + GetRecord fallback) through `crawl.ojs_fetcher`, the same fetcher
and URLs `op ingest ojs` reads, so the pages it caches are the ones the miner replays. It needs no table, so it
never stops at an unlisted section. Section names come from `ListSets` (`ojs.list_sets`). A set whose token the
server no longer knows (`badResumptionToken`, after 24 h) is harvested again from a refreshed first page. The
journal-wide first page (cached once) gives `completeListSize`, which the per-set totals must add up to.

    OP_DATA_DIR=<data> uv run python scripts/ojs_section_census.py IASEAI AIES AAAI [--offline] [--budget 540]
    OP_DATA_DIR=<data> uv run python scripts/ojs_section_census.py AAAI --offline --toml   # draft [[section]] rows
    OP_DATA_DIR=<data> uv run python scripts/ojs_section_census.py AAAI --offline --json out.json

Per (volume, setSpec) it prints the live record count, a sample title and the ListSets label; deleted headers carry
no volume (OAI-PMH sends only their header), so they are counted per set; articles the server can't serve at all
(`unavailable`) are listed with their set, for a person to name in `[[unavailable]]`. `--budget` stops starting new
sets after that many seconds (the cache keeps every page; run it again to go on). `--toml` drafts rows with `track = "?"`:
the track is a person's mapping (spec §Data model), never the script's guess.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from openproceedings.ingest.sources import ojs
from openproceedings.ingest.sources.common import CrawlError
from openproceedings.ingest.sources.crawl import ojs_fetcher
from openproceedings.ingest.sources.http import CacheMiss
from openproceedings.logs import configure_logging

_SIZE = re.compile(r'completeListSize="([0-9]+)"')


@dataclass
class Census:
    journal: str
    complete_list_size: int | None = None
    pages: int = 0
    complete: bool = False
    live: Counter[tuple[int, str]] = field(default_factory=Counter)
    deleted: Counter[str] = field(default_factory=Counter)
    no_volume: Counter[str] = field(default_factory=Counter)  # live records whose dc:source names no volume
    duplicates: int = 0  # live records listed twice
    fallback: list[str] = field(default_factory=list)  # sets harvested through the fallback
    unavailable: list[tuple[str, int]] = field(default_factory=list)  # (set, article)
    live_ids: set[int] = field(default_factory=set)
    sample: dict[tuple[int, str], str] = field(default_factory=dict)
    labels: dict[str, str] = field(default_factory=dict)


def walk(journal: str, cache: Path, *, offline: bool, budget: float | None) -> Census:
    f = ojs_fetcher(cache, offline=offline)
    started = time.monotonic()
    c = Census(journal)
    c.labels = ojs.list_sets(journal, f)
    whole = ojs.oai_url(journal)  # the journal-wide first page: only its completeListSize is read
    if not offline or f.is_cached(whole):
        page = f.get(whole)
        if page.ok and (m := _SIZE.search(page.text)):
            c.complete_list_size = int(m.group(1))
    for n, spec in enumerate(ojs.journal_sets(journal, f)):
        first = ojs.oai_url(journal, set_spec=spec)
        spent = budget is not None and time.monotonic() - started > budget
        if (offline or spent) and not f.is_cached(first):
            why = "page not cached" if offline else "budget spent"
            print(f"# {journal}: {why} at set {spec} ({n} sets done); stopped", file=sys.stderr)
            return c
        try:
            h = ojs.harvest_set(journal, spec, f)
        except CacheMiss as miss:
            print(f"# {journal}: {miss}; stopped", file=sys.stderr)
            return c
        except CrawlError as e:
            if "badResumptionToken" not in str(e) or offline:
                raise
            print(f"# {journal}: set {spec}: token expired; harvesting it again", file=sys.stderr)
            h = ojs.harvest_set(journal, spec, f, refresh=True)
        c.pages += h.pages
        c.deleted[spec] += h.deleted
        if h.fallback:
            c.fallback.append(spec)
        c.unavailable += [(spec, a) for a, _p in h.unavailable]
        for _page, rec in h.live:
            if rec.article in c.live_ids:
                c.duplicates += 1
                continue
            c.live_ids.add(rec.article)
            if rec.volume is None:
                c.no_volume[rec.set_spec] += 1
            else:
                c.live[(rec.volume, rec.set_spec)] += 1
                c.sample.setdefault((rec.volume, rec.set_spec), rec.title or "")
        if (n + 1) % 25 == 0:
            print(f"# {journal}: {n + 1} sets, {c.pages} pages, {len(c.live_ids)} live", file=sys.stderr)
    c.complete = True
    return c


def report(c: Census) -> None:
    live, deleted = sum(c.live.values()), sum(c.deleted.values())
    print(f"## {c.journal}: {'complete' if c.complete else 'INCOMPLETE'}; {c.pages} pages; "
          f"completeListSize {c.complete_list_size}; live {live}; deleted headers {deleted} "
          f"unavailable {len(c.unavailable)} {c.unavailable}; fallback sets {c.fallback}; "
          f"no volume {sum(c.no_volume.values())}; duplicates {c.duplicates}; "
          f"live+unavailable+deleted {live + len(c.unavailable) + deleted + sum(c.no_volume.values())}")  # fmt: skip
    for volume in sorted({v for v, _ in c.live}):
        rows = sorted((s, n) for (v, s), n in c.live.items() if v == volume)
        print(f"### v{volume}: {sum(n for _, n in rows)} live in {len(rows)} sets")
        for s, n in rows:
            print(f"  {s}\t{n}\t{c.labels.get(s, '?')}\t{c.sample[(volume, s)][:70]}")
    print(f"### deleted headers by set ({deleted})")
    for s, n in sorted(c.deleted.items()):
        vols = sorted(v for v, s2 in c.live if s2 == s)
        print(f"  {s}\t{n}\t{c.labels.get(s, '?')}\tlive in v{vols}")
    for s, n in sorted(c.no_volume.items()):
        print(f"  NO VOLUME {s}\t{n}")
    unused = sorted(set(c.labels) - {s for _, s in c.live} - set(c.deleted) - {c.journal})
    print(f"### ListSets sets with no record ({len(unused)}): {unused}")


def toml_rows(c: Census, verified: str) -> str:
    out = []
    for (volume, s), n in sorted(c.live.items()):
        out.append(
            f'[[section]]\njournal = "{c.journal}"\nvolume = {volume}\nset_spec = "{s}"\nkind = "papers"\n'
            f'track = "?"\nlabel = {json.dumps(c.labels.get(s, "?"), ensure_ascii=False)}\npapers = {n}\n'
            f'verified = {verified}\nsource = "docs/research/2026-10-09-aaai-aies-facct-iaseai-sources.md"\n'
        )
    return "\n".join(out)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("journals", nargs="+", help="OJS journal codes (AAAI, AIES, IASEAI)")
    p.add_argument("--offline", action="store_true", help="the cache only (no network)")
    p.add_argument("--budget", type=float, help="stop fetching new pages after this many seconds")
    p.add_argument("--toml", action="store_true", help="print draft [[section]] rows instead of the census")
    p.add_argument("--json", type=Path, help="also write the census as JSON here")
    p.add_argument("-v", "--verbose", action="store_true", help="log every retry and wait")
    p.add_argument("--verified", default=time.strftime("%Y-%m-%d"), help="the rows' verified date")
    ns = p.parse_args()
    configure_logging("INFO" if ns.verbose else "WARNING", stream=sys.stderr)
    data = Path(os.environ.get("OP_DATA_DIR") or Path(__file__).resolve().parents[1] / "data")
    dump = {}
    for j in ns.journals:
        c = walk(j, data / "cache", offline=ns.offline, budget=ns.budget)
        print(toml_rows(c, ns.verified)) if ns.toml else report(c)
        dump[j] = {
            "complete": c.complete, "pages": c.pages, "complete_list_size": c.complete_list_size,
            "duplicates": c.duplicates, "labels": c.labels,
            "live": [{"volume": v, "set_spec": s, "records": n, "sample": c.sample[(v, s)]}
                     for (v, s), n in sorted(c.live.items())],
            "deleted": dict(sorted(c.deleted.items())), "no_volume": dict(c.no_volume),
            "unavailable": c.unavailable, "fallback": c.fallback,
        }  # fmt: skip
    if ns.json:
        ns.json.write_text(json.dumps(dump, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
