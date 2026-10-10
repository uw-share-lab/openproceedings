"""The OpenAlex census (spec 01 §Sources 6; decision-049, milestone C): the facts the OpenAlex abstract fill rests
on, and the draft `[[listing]]` rows of `ingest/openalex_sources.toml`. A person runs it; no test runs it.

It reads OpenAlex only through `crawl.openalex_fetcher` (api.openalex.org only, the repo's generic User-Agent, one
request at a time, `openalex.MIN_INTERVAL` apart) and **keyless**: it never reads `OPENALEX_API_KEY` or `.env`, and
sends no contact address (no `mailto`, no custom User-Agent). Every page lands in `<cache>/openalex/pages`, where
`op ingest openalex` finds the same DOI batches and listings; it writes nothing else. It prints:

1. Auth and budget: whether a keyless request answers 200, and the rate-limit and cost headers it carries (the key,
   when there is one, goes as `Authorization: Bearer`, `crawl.openalex_fetcher`).
2. Licence: what the API itself states (its root answer), with the documented licence's URL.
3. The DOI route: the candidates per venue-year (`crawl.replay_all`, offline), the batches (`openalex.doi_batches`,
   fetched as `op ingest openalex` fetches them), and per batch the DOIs requested and returned, the DOIs returned
   twice, and the works whose DOI was not requested.
4. FAccT 2025/2026: the research note's 195/206 and 293/317 against those years' DOIs, and OpenAlex's own count
   under its FAccT source.
5. The listing route: OpenAlex's sources named like the AAAI conference (`/sources?search=…`), their works per year,
   and per held DOI-less AAAI year the works listed and how the fill's title rule would match them.
6. The simulated fill (`openalex.fill` over the fetched lookups, the draft table) and the draft `[[listing]]` rows.

    uv run python scripts/openalex_census.py --cache <data>/cache

A run stops before the keyless daily budget runs out (`--reserve`, credits left in `x-ratelimit-remaining`).
"""

from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

from openproceedings.ingest import dblp_aaai_table, openalex_table
from openproceedings.ingest.dedup import title_key
from openproceedings.ingest.record import DBLP_YEARS, OPENALEX_VENUES, PaperRecord
from openproceedings.ingest.sources import crawl, openalex
from openproceedings.ingest.sources.http import Request, Response, urllib_transport

API = f"https://{openalex.HOST}"
LICENCE_DOC = "https://openalex.org"  # not fetched: outside api.openalex.org
SOURCE_QUERIES = ("AAAI", "National Conference on Artificial Intelligence")
# OpenAlex source names that are the AAAI conference itself (not a symposium, workshop, journal or press imprint)
AAAI_NAMES = frozenset(
    {
        "national conference on artificial intelligence",
        "proceedings of the aaai conference on artificial intelligence",
    }
)
FACCT_QUERY = "Fairness, Accountability, and Transparency"
NOTE_COUNTS = {
    2025: (195, 206),
    2026: (293, 317),
}  # the research note's "abstracts of works" (unverified there)
NOTE = "docs/research/2026-10-09-aaai-aies-facct-iaseai-sources.md (scripts/openalex_census.py)"
RATE_HEADERS = ("x-ratelimit-", "retry-after")


class Budget:
    """The live transport, wrapped: keeps each live answer's rate-limit headers, and stops before the daily budget
    is spent (a 429 would otherwise be waited out for hours by the fetcher's retries)."""

    def __init__(self, reserve: int) -> None:
        self.reserve = reserve
        self.seen: list[tuple[str, int, dict[str, str]]] = []
        self.started = time.monotonic()

    def __call__(self, request: Request, timeout: float) -> Response:
        resp = urllib_transport(request, timeout)
        rate = {k: v for k, v in resp.headers.items() if k.startswith(RATE_HEADERS)}
        self.seen.append((request.url, resp.status, rate))
        left = rate.get("x-ratelimit-remaining")
        if left is not None and left.isdigit() and int(left) < self.reserve:
            raise SystemExit(
                f"stopping: {left} OpenAlex credits left today, under the reserve of {self.reserve}"
            )
        return resp


def _json(f: Any, url: str, *, refresh: bool = False) -> Any:
    page = f.get(url, refresh=refresh)
    if not page.ok:
        raise SystemExit(f"{url}: HTTP {page.status}")
    return json.loads(page.text)


def auth_and_licence(f: Any, budget: Budget) -> None:
    root = _json(f, f"{API}/", refresh=True)  # live every run: the headers are the point
    url, status, rate = budget.seen[-1]
    print("== Auth and budget")
    print(f"keyless GET {url}: HTTP {status} (no Authorization header, no mailto, the repo's User-Agent)")
    for k in sorted(rate):
        print(f"  {k}: {rate[k]}")
    print("a key, when set, goes as `Authorization: Bearer <key>` (crawl.openalex_fetcher), never in a URL")
    print("\n== Licence")
    print(
        f"the API's root answer states no licence (keys: {sorted(root) if isinstance(root, dict) else '?'})"
    )
    print(
        f"the licence OpenAlex documents for its data (CC0, {LICENCE_DOC}) is not readable from api.openalex.org: "
        "not verified by this census"
    )


def _vy(r: PaperRecord) -> tuple[str, int]:
    return (r.venue, r.year)


def doi_route(records: list[PaperRecord], f: Any) -> list[openalex.Lookup]:
    cands = openalex.candidates(records)
    with_doi = Counter(_vy(r) for r in cands if openalex.bare_doi(r.urls.doi))
    without = Counter(_vy(r) for r in cands if not openalex.bare_doi(r.urls.doi))
    print("\n== Candidates (replay_all: AAAI, AIES and FAccT records with no abstract)")
    print(f"total {len(cands)}: with a DOI {sum(with_doi.values())}, DOI-less {sum(without.values())}")
    for vy in sorted(set(with_doi) | set(without)):
        print(f"  {vy[0]} {vy[1]}: DOI {with_doi[vy]}, DOI-less {without[vy]}")
    batches, unqueryable = openalex.doi_batches(records)
    print(
        f"\n== The DOI route: {len(batches)} batches of <= {openalex.BATCH}; unqueryable DOIs {unqueryable}"
    )
    lookups: list[openalex.Lookup] = []
    for chunk in batches:
        lookups += openalex.doi_lookups(chunk, f, refresh=False)
    _print_batches(lookups)
    return lookups


def _print_batches(lookups: list[openalex.Lookup]) -> None:
    for i, lk in enumerate(lookups, 1):
        requested = set(lk.requested)
        got = Counter(w.doi for w in lk.works)
        twice = sorted(d for d, n in got.items() if d and n > 1)
        foreign = sorted(str(w.doi) for w in lk.works if w.doi not in requested)
        missing = sorted(requested - set(got))
        print(f"  batch {i}: requested {len(requested)}, works {len(lk.works)}, DOIs returned "
              f"{len(requested & set(got))}, returned twice {len(twice)}, not requested {len(foreign)}, "
              f"no work {len(missing)}")  # fmt: skip
        for d in twice:
            print(f"    twice: {d} ({', '.join(w.id for w in lk.works if w.doi == d)})")
        for d in foreign:
            near = [r for r in requested if r.startswith(d) or d.startswith(r)]
            print(f"    not requested: {d}" + (f" (a cut-off form of {near[0]})" if near else ""))
        for d in missing:
            print(f"    no work: {d}")


def facct_reconciliation(records: list[PaperRecord], f: Any) -> list[openalex.Lookup]:
    print("\n== FAccT 2025/2026: the research note's counts against the DOIs")
    out: list[openalex.Lookup] = []
    for year, (note_abs, note_works) in NOTE_COUNTS.items():
        dois = sorted(
            {d for r in records if _vy(r) == ("FAccT", year) and (d := openalex.bare_doi(r.urls.doi))}
        )
        lookups: list[openalex.Lookup] = []
        for i in range(0, len(dois), openalex.BATCH):
            lookups += openalex.doi_lookups(dois[i : i + openalex.BATCH], f, refresh=False)
        works = [w for lk in lookups for w in lk.works if w.doi in set(dois)]
        found = {w.doi for w in works}
        with_abstract = {w.doi for w in works if openalex.abstract_of(w)[0] is not None}
        print(f"FAccT {year}: our DOIs {len(dois)}; OpenAlex works for them {len(works)} ({len(found)} DOIs); "
              f"with a usable abstract {len(with_abstract)} DOIs; the note said {note_abs} of {note_works}")  # fmt: skip
        _print_batches(lookups)
        out += lookups
    hits = _json(f, f"{API}/sources?search={quote(FACCT_QUERY)}&per-page=50")
    facct = [s for s in hits.get("results", []) if "fairness" in str(s.get("display_name", "")).casefold()]
    for s in facct:
        print(
            f"  source {s.get('id')} {s.get('display_name')!r} type {s.get('type')} works {s.get('works_count')}"
        )
    if facct:
        sid = str(facct[0]["id"]).rsplit("/", 1)[-1]
        for extra in ("", ",has_abstract:true"):
            body = _json(f, f"{API}/works?filter=primary_location.source.id:{sid},publication_year:2025|2026"
                            f"{extra}&group_by=publication_year")  # fmt: skip
            counts = {g["key"]: g["count"] for g in body.get("group_by", [])}
            print(f"  {sid} works per year{' with an abstract' if extra else ''}: {counts}")
    return out


def _held_years() -> list[int]:
    return [y for y in DBLP_YEARS["AAAI"] if y not in dblp_aaai_table.TABLE.not_held]


def listing_route(records: list[PaperRecord], f: Any) -> tuple[str, list[openalex.Lookup]]:
    print("\n== The listing route: OpenAlex sources named like the AAAI conference")
    sources: dict[str, str] = {}
    for q in SOURCE_QUERIES:
        body = _json(f, f"{API}/sources?search={quote(q)}&per-page=50")
        print(f"/sources?search={q}: {body['meta']['count']} sources")
        for s in body.get("results", []):
            sid = str(s.get("id", "")).rsplit("/", 1)[-1]
            name = str(s.get("display_name", ""))
            mark = "AAAI conference" if name.casefold() in AAAI_NAMES else "other"
            print(f"  {sid} {name!r} type {s.get('type')} works {s.get('works_count')} [{mark}]")
            if mark != "other":
                sources[sid] = name
    per_year: dict[int, dict[str, int]] = {}
    for sid in sorted(sources):
        body = _json(f, f"{API}/works?filter=primary_location.source.id:{sid}&group_by=publication_year")
        counts = {int(g["key"]): int(g["count"]) for g in body.get("group_by", [])}
        early = {y: n for y, n in sorted(counts.items()) if y <= DBLP_YEARS["AAAI"][-1]}
        print(f"{sid} {sources[sid]!r}: works by year to 2008 {early or 'none'}")
        for y, n in early.items():
            per_year.setdefault(y, {})[sid] = n
    held = _held_years()
    stray = {y: v for y, v in per_year.items() if y not in held}
    print(f"held DOI-less years {held[0]}-{held[-1]}: {len(held)}; works in years with no AAAI record "
          f"(not held, or out of range): {stray or 'none'}")  # fmt: skip
    doi_less = [
        r for r in records if r.venue == "AAAI" and r.year in held and not openalex.bare_doi(r.urls.doi)
    ]
    corpus_dois = {d for r in records if (d := openalex.bare_doi(r.urls.doi))}
    rows: list[str] = []
    lookups: list[openalex.Lookup] = []
    today = date.today()
    for year in held:
        sids = sorted(per_year.get(year, {}))
        recs = [r for r in doi_less if r.year == year]
        if not sids:
            print(f"  AAAI {year}: no source; {len(recs)} records stay none")
            continue
        probe = openalex_table.Listing("AAAI", year, tuple(sids), 1, today, NOTE)
        first = openalex.parse_works(f.get(openalex.listing_url(probe)).text)
        row = openalex_table.Listing("AAAI", year, tuple(sids), first.total, today, NOTE)
        lk = openalex.listing_lookup(row, f, refresh=False)
        lookups.append(lk)
        rec_keys = Counter(title_key(r.title) for r in recs)
        work_keys = Counter(title_key(w.title) for w in lk.works if w.title and w.year == year)
        one_to_one = [k for k, n in work_keys.items() if k and n == 1 and rec_keys.get(k) == 1]
        abstracts = sum(1 for w in lk.works if openalex.abstract_of(w)[0] is not None)
        no_doi = sum(1 for w in lk.works if w.doi is None)
        corpus = sum(1 for w in lk.works if w.doi in corpus_dois)
        unmatched = [w for w in lk.works if title_key(w.title or "") not in rec_keys]
        print(f"  AAAI {year}: {', '.join(sids)} works {len(lk.works)} (meta.count {first.total}; with a usable "
              f"abstract {abstracts}; no DOI {no_doi}; a corpus DOI {corpus}); DOI-less records {len(recs)}; "
              f"one-to-one title keys {len(one_to_one)}; works matching no record {len(unmatched)}")  # fmt: skip
        for w in unmatched[:4]:
            print(f"    unmatched work {w.id}: {w.title!r}")
        rows.append(f'[[listing]]\nvenue = "AAAI"\nyear = {year}\nsource_ids = {json.dumps(list(sids))}\n'
                    f'works = {len(lk.works)}\nverified = {today.isoformat()}\nsource = "{NOTE}"\n')  # fmt: skip
    return "\n".join(rows), lookups


def simulate(records: list[PaperRecord], lookups: list[openalex.Lookup], rows: str) -> None:
    table = openalex_table.load(rows)
    extract = openalex.Extract("census", tuple(lookups))
    scoped = [r for r in records if r.venue in OPENALEX_VENUES]
    out, report = openalex.fill(scoped, extract, table)
    print("\n== The simulated fill (openalex.fill over these lookups and the draft table)")
    print(json.dumps(report.to_manifest(), sort_keys=True))
    before = {r.id: r.abstract for r in scoped}
    filled = Counter(_vy(r) for r in out if r.abstract is not None and before[r.id] is None)
    cands = Counter(_vy(r) for r in openalex.candidates(scoped))
    for vy in sorted(cands):
        print(f"  {vy[0]} {vy[1]}: candidates {cands[vy]}, filled {filled[vy]}")
    print(f"  total: candidates {sum(cands.values())}, filled {sum(filled.values())}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--cache", type=Path, required=True, help="the data directory's cache/")
    parser.add_argument("--reserve", type=int, default=50, help="stop when fewer daily credits are left")
    args = parser.parse_args()
    budget = Budget(args.reserve)
    f = crawl.openalex_fetcher(args.cache, offline=False, transport=budget, key=None)
    print(f"OpenAlex census, {datetime.now(UTC).isoformat(timespec='seconds')}")
    auth_and_licence(f, budget)
    records, _ = crawl.replay_all(args.cache)
    lookups = doi_route(records, f)
    facct_reconciliation(records, f)
    rows, listings = listing_route(records, f)
    simulate(records, lookups + listings, rows)
    print("\n== Draft openalex_sources.toml rows\n")
    print(rows)
    last = next((r for _, _, r in reversed(budget.seen) if "x-ratelimit-remaining" in r), {})
    print(f"\n== Requests: live {f.stats.network}, cached {f.stats.cached}, "
          f"{time.monotonic() - budget.started:.0f} s; credits left {last.get('x-ratelimit-remaining')}")  # fmt: skip


if __name__ == "__main__":
    main()
