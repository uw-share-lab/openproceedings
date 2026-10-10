"""`op ingest iclr|neurips|pmlr|dblp|ojs` (`dblp --venue AAAI` too), and the one offline replay of every crawler that
`op snapshot build` runs (spec 01 §CLI, §Pipeline).

`ingest_*` crawls each listing into `<cache>/<source>/pages/` through `common.Crawls.ingest` (one run at a
time per source: an exclusive lock on `<cache>/<source>/.lock`) and, when the whole listing is cached, writes
its crawl marker. A dry run reads only the index pages (through the cache) and reports what a crawl would
fetch; it writes no marker. `--offline` crawls from the cache alone. `replay_all` re-runs every marked crawl
of every source (OpenReview API v2, then v1, then ICLR, NeurIPS, PMLR, dblp (ICML), OJS and dblp (AAAI); `common.Crawls`) with no
transport at all, so a snapshot never fetches.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from openproceedings.ingest import acm_table, dblp_aaai_table
from openproceedings.ingest.dblp_table import TABLE as DBLP_TABLE
from openproceedings.ingest.dblp_table import Table as DblpTable
from openproceedings.ingest.ojs_table import TABLE as OJS_TABLE
from openproceedings.ingest.ojs_table import Table as OjsTable
from openproceedings.ingest.record import PaperRecord
from openproceedings.ingest.sources import (
    crossref,
    dblp,
    dblp_aaai,
    facct_site,
    iclr,
    icml_sites,
    neurips,
    ojs,
    openreview_v1,
    openreview_v2,
    pmlr,
)
from openproceedings.ingest.sources.common import (
    Crawls,
    ListingReport,
    MinerError,
    Report,
    sources_manifest,
)
from openproceedings.ingest.sources.http import (
    Fetcher,
    PageCache,
    StreamTransport,
    Transport,
    urllib_stream,
    urllib_transport,
)
from openproceedings.ingest.sources.openreview_client import repo_dotenv
from openproceedings.ingest.volumes import ingested_volume

log = logging.getLogger(__name__)

DEFAULT_INTERVAL = 1.0  # seconds between requests to a host (the openreview-api skill's pace)


def fetcher(
    cache: Path, source_dir: str, hosts: frozenset[str], *, offline: bool, transport: Transport | None = None,
    min_interval: float = DEFAULT_INTERVAL,
) -> Fetcher:  # fmt: skip
    live = None if offline else (transport or urllib_transport)
    return Fetcher(PageCache(cache / source_dir), live, hosts=hosts, min_interval=min_interval)


def crawls_dir(cache: Path, source_dir: str) -> Path:
    return cache / source_dir / "crawls"


def _output(reports: Iterable[ListingReport], f: Fetcher, dry_run: bool) -> dict[str, Any]:
    return {
        "dry_run": dry_run,
        "listings": [r.to_manifest() for r in reports],
        "requests": f.stats.network,
        "cached": f.stats.cached,
    }


def ingest_neurips(
    years: Iterable[int], cache: Path, *, offline: bool = False, dry_run: bool = False, refresh: bool = False,
    transport: Transport | None = None, min_interval: float = DEFAULT_INTERVAL,
) -> dict[str, Any]:  # fmt: skip
    """Crawl NeurIPS years (each year's listings, then every paper page) into the cache."""
    f = fetcher(cache, neurips.CACHE_DIR, neurips.HOSTS, offline=offline, transport=transport,
                min_interval=min_interval)  # fmt: skip
    mined = NEURIPS.ingest(
        cache, sorted(set(years)),
        lambda year: neurips.mine_year(year, f, refresh_index=refresh, plan_only=dry_run),
        lambda year, _: None if dry_run else (str(year), {"source": neurips.SOURCE, "year": year}),
    )  # fmt: skip
    reports = [r for m in mined for r in m.reports]
    log.info(
        "neurips_ingested", extra={"years": len(reports), "requests": f.stats.network, "dry_run": dry_run}
    )
    return _output(reports, f, dry_run)


def ingest_iclr(
    years: Iterable[int], cache: Path, *, offline: bool = False, dry_run: bool = False, refresh: bool = False,
    transport: Transport | None = None, min_interval: float = DEFAULT_INTERVAL,
) -> dict[str, Any]:  # fmt: skip
    """Crawl the official ICLR accepted-paper archive for the 2014-2016 conference tracks."""
    f = fetcher(cache, iclr.CACHE_DIR, iclr.HOSTS, offline=offline, transport=transport,
                min_interval=min_interval)  # fmt: skip
    mined = ICLR.ingest(
        cache, sorted(set(years)),
        lambda year: iclr.mine_year(year, f, refresh_index=refresh, plan_only=dry_run),
        lambda year, _: None if dry_run else (str(year), {"source": iclr.SOURCE, "year": year}),
    )  # fmt: skip
    reports = [report for result in mined for report in result.reports]
    log.info("iclr_archive_ingested", extra={"years": len(reports), "requests": f.stats.network,
                                             "dry_run": dry_run})  # fmt: skip
    return _output(reports, f, dry_run)


def ingest_pmlr(
    years: Iterable[int], cache: Path, *, offline: bool = False, dry_run: bool = False, refresh: bool = False,
    transport: Transport | None = None, min_interval: float = DEFAULT_INTERVAL, venue: str = "ICML",
) -> dict[str, Any]:  # fmt: skip
    """Crawl the `venue` (ICML, or FAccT 2018) volume of each year (from the volume table) into the cache."""
    volumes = []
    for year in sorted(set(years)):
        volume = ingested_volume(venue, year)
        if volume is None:
            raise MinerError(
                f"{venue} {year}: no verified PMLR volume in the volume table (add its row once its index is live)",
                reason="no_volume",
            )
        volumes.append(volume.number)
    f = fetcher(
        cache, pmlr.CACHE_DIR, pmlr.HOSTS, offline=offline, transport=transport, min_interval=min_interval
    )
    mined = PMLR.ingest(
        cache, volumes, lambda number: pmlr.mine_volume(number, f, refresh_index=refresh, plan_only=dry_run),
        lambda number, _: None if dry_run else (f"v{number}", {"source": pmlr.SOURCE, "volume": number}),
    )  # fmt: skip
    reports = [m.report for m in mined]
    log.info(
        "pmlr_ingested", extra={"volumes": len(reports), "requests": f.stats.network, "dry_run": dry_run}
    )
    return _output(reports, f, dry_run)


def ingest_dblp(
    years: Iterable[int], cache: Path, *, offline: bool = False, dry_run: bool = False, refresh: bool = False,
    transport: Transport | None = None, stream: StreamTransport | None = None,
    min_interval: float = DEFAULT_INTERVAL, table: DblpTable = DBLP_TABLE,
    pages: Mapping[int, tuple[icml_sites.SitePage, ...]] | None = None,
) -> dict[str, Any]:  # fmt: skip
    """ICML years from the pinned dblp release (downloaded and read once into its extract), each with the
    abstracts its official ICML pages give (`icml_sites`), into the cache (decision-047, TASK-205/206). A dry run
    fetches nothing at all: it says whether the release and its extract are on disk, and which pages a crawl would
    fetch. `table` and `pages` are the shipped tables unless a test passes its own."""
    wanted = sorted(set(years))
    if missing := [y for y in wanted if y not in table.years]:
        raise MinerError(f"ICML {missing[0]}: dblp_icml.toml covers ICML {min(table.years)}-"
                         f"{max(table.years)} (PMLR from 2013)", reason="no_year")  # fmt: skip
    hosts = icml_sites.HOSTS if pages is None else icml_sites.hosts_of(pages)
    # the Internet Archive asks for a slower pace than the proceedings hosts: never under its interval
    f = fetcher(cache, icml_sites.CACHE_DIR, hosts, offline=offline or dry_run, transport=transport,
                min_interval=max(min_interval, icml_sites.MIN_INTERVAL))  # fmt: skip
    if dry_run:
        plans = [icml_sites.plan_year(y, f, pages) for y in wanted]
        return {"dry_run": True, "release_on_disk": dblp.release_on_disk(cache, table),
                "extract_on_disk": dblp.extract_path(cache, table).exists(), "years": plans,
                "requests": f.stats.network, "cached": f.stats.cached}  # fmt: skip
    extract = dblp.prepare(cache, None if offline else (stream or urllib_stream), table)
    mined = DBLP.ingest(
        cache, wanted,
        lambda year: dblp.mine_year(
            year, extract, site=icml_sites.read_year(year, f, refresh=refresh, pages=pages), table=table),
        lambda year, _: (str(year), {"source": dblp.SOURCE, "year": year, "release": table.release.doi}),
    )  # fmt: skip
    reports = [r for m in mined for r in m.reports]
    log.info(
        "dblp_ingested", extra={"years": len(reports), "requests": f.stats.network, "cached": f.stats.cached}
    )
    return _output(reports, f, False)


def ingest_dblp_aaai(
    years: Iterable[int], cache: Path, *, offline: bool = False, dry_run: bool = False,
    stream: StreamTransport | None = None, table: DblpTable = DBLP_TABLE, aaai: dblp_aaai_table.Table | None = None,
) -> dict[str, Any]:  # fmt: skip
    """AAAI years from the pinned dblp release (decision-049, milestone B): not-held years are skipped and named; a
    dry run fetches nothing and says whether the release and AAAI's extract are on disk."""
    aaai = aaai or dblp_aaai_table.TABLE
    asked = sorted(set(years))
    not_held = [y for y in asked if y in aaai.not_held]
    wanted = [y for y in asked if y not in aaai.not_held]
    if missing := [y for y in wanted if y not in aaai.years]:
        span = f"{min(aaai.years)}-{max(aaai.years)}" if aaai.years else "no years yet"
        raise MinerError(
            f"AAAI {missing[0]}: dblp_aaai.toml covers AAAI {span} (OJS from 2010)", reason="no_year"
        )
    if dry_run:
        return {"dry_run": True, "release_on_disk": dblp.release_on_disk(cache, table),
                "extract_on_disk": dblp.AAAI_SLICE.path(cache, table).exists(), "years": wanted, "not_held": not_held}  # fmt: skip
    extract = dblp.prepare_slices(
        cache, None if offline else (stream or urllib_stream), table, (dblp.AAAI_SLICE,)
    )["AAAI"]
    dblp_aaai.check_extract(extract, aaai)
    mined = DBLP_AAAI.ingest(
        cache, wanted, lambda year: dblp_aaai.mine_year(year, extract, table=aaai),
        lambda year, _: (str(year), {"source": dblp.SOURCE, "venue": "AAAI", "year": year, "release": table.release.doi}),
    )  # fmt: skip
    reports = [r for m in mined for r in m.reports]
    log.info("dblp_aaai_ingested", extra={"years": len(reports), "not_held": len(not_held)})
    return {"dry_run": False, "listings": [r.to_manifest() for r in reports], "not_held": not_held}


# --- the one replay ----------------------------------------------------------------------------------------

ICLR: Crawls[iclr.YearResult] = Crawls(
    lambda cache: crawls_dir(cache, iclr.CACHE_DIR), lambda m: (int(m["year"]),),
    lambda k: f"ICLR archive {k[0]}", "op ingest iclr",
    lambda cache, k: iclr.mine_year(k[0], fetcher(cache, iclr.CACHE_DIR, iclr.HOSTS, offline=True)),
)  # fmt: skip
NEURIPS: Crawls[neurips.YearResult] = Crawls(
    lambda cache: crawls_dir(cache, neurips.CACHE_DIR), lambda m: (int(m["year"]),),
    lambda k: f"NeurIPS {k[0]}", "op ingest neurips",
    lambda cache, k: neurips.mine_year(k[0], fetcher(cache, neurips.CACHE_DIR, neurips.HOSTS, offline=True)),
)  # fmt: skip
PMLR: Crawls[pmlr.VolumeResult] = Crawls(
    lambda cache: crawls_dir(cache, pmlr.CACHE_DIR), lambda m: (int(m["volume"]),),
    lambda k: f"PMLR v{k[0]}", "op ingest pmlr",
    lambda cache, k: pmlr.mine_volume(k[0], fetcher(cache, pmlr.CACHE_DIR, pmlr.HOSTS, offline=True)),
)  # fmt: skip


def _replay_dblp(
    cache: Path, key: tuple[Any, ...], table: DblpTable = DBLP_TABLE,
    pages: Mapping[int, tuple[icml_sites.SitePage, ...]] | None = None,
) -> dblp.YearResult:  # fmt: skip
    """One marked ICML year, from the extract and the ICML pages in the cache. A year marked under another
    release than the table pins is refused: it was crawled from other bytes (guarantee 4)."""
    year, release = key
    if release != table.release.doi:
        raise MinerError(f"ICML {year} was ingested from dblp release {release}, not the pinned "
                         f"{table.release.doi}; re-run op ingest dblp", reason="release_changed")  # fmt: skip
    hosts = icml_sites.HOSTS if pages is None else icml_sites.hosts_of(pages)
    site = icml_sites.read_year(year, fetcher(cache, icml_sites.CACHE_DIR, hosts, offline=True), pages=pages)
    return dblp.mine_year(year, dblp.load_extract(cache, table), site=site, table=table)


DBLP: Crawls[dblp.YearResult] = Crawls(
    lambda cache: crawls_dir(cache, dblp.CACHE_DIR), lambda m: (int(m["year"]), str(m["release"])),
    lambda k: f"ICML {k[0]} (dblp)", "op ingest dblp", _replay_dblp,
)  # fmt: skip


def ojs_fetcher(cache: Path, *, offline: bool, transport: Transport | None = None,
                min_interval: float = DEFAULT_INTERVAL) -> Fetcher:  # fmt: skip
    live = None if offline else (transport or urllib_transport)
    return Fetcher(PageCache(cache / ojs.CACHE_DIR), live, hosts=ojs.HOSTS,
                   min_interval=max(min_interval, ojs.MIN_INTERVAL), accept="application/xml, text/xml",
                   expect="xml", keep_query=True)  # fmt: skip


def ingest_ojs(
    journals: Iterable[str], cache: Path, *, offline: bool = False, dry_run: bool = False, refresh: bool = False,
    transport: Transport | None = None, min_interval: float = DEFAULT_INTERVAL, table: OjsTable = OJS_TABLE,
) -> dict[str, Any]:  # fmt: skip
    """Harvest each ojs.aaai.org journal (AAAI, AIES, IASEAI; `ojs_table`) into the cache through OAI-PMH, set by
    set. A dry run fetches at most each journal's first ListSets page and writes no marker."""
    wanted = sorted(set(journals)) or sorted(table.journals)
    for j in wanted:
        if j not in table.journals:
            raise MinerError(f"OJS journal {j} is not in ojs_sections.toml", reason="unlisted_journal")
    f = ojs_fetcher(cache, offline=offline, transport=transport, min_interval=min_interval)
    if dry_run:
        plans = []
        for j in wanted:
            url = ojs.sets_url(j)
            cached = f.is_cached(url)  # before the get, which caches the page
            first = f.get(url)
            if not first.ok:
                raise MinerError(f"{url} answered HTTP {first.status}", reason="no_listing")
            sets, token = ojs.parse_sets(first.text)
            plans.append(
                {
                    "journal": j,
                    "first_page_cached": cached,
                    "sets_on_first_page": sum(1 for s in sets if s.startswith(f"{j}:")),
                    "more_pages": token is not None,
                }
            )
        return {"dry_run": True, "journals": plans, "requests": f.stats.network, "cached": f.stats.cached}
    mined = OJS.ingest(
        cache, wanted, lambda j: ojs.mine_journal(j, f, refresh=refresh, table=table),
        lambda j, _: (j, {"source": ojs.SOURCE, "journal": j}),
    )  # fmt: skip
    reports = [r for m in mined for r in m.reports]
    log.info("ojs_ingested", extra={"journals": len(wanted), "listings": len(reports), "requests": f.stats.network,
                                    "cached": f.stats.cached,
                                    "deleted": sum(m.deleted for m in mined),
                                    "front_matter": sum(m.front_matter for m in mined),
                                    "unavailable": sum(m.unavailable for m in mined),
                                    "duplicates": sum(m.duplicates for m in mined),
                                    "recovered": sum(m.recovered for m in mined)})  # fmt: skip
    out = _output(reports, f, False)
    out["journals"] = [{"journal": j, "pages": m.pages, "deleted": m.deleted, "front_matter": m.front_matter,
                        "unavailable": m.unavailable, "duplicates": m.duplicates, "recovered": m.recovered,
                        "fallback_sets": m.fallback_sets}
                       for j, m in zip(wanted, mined, strict=True)]  # fmt: skip
    return out


OJS: Crawls[ojs.JournalResult] = Crawls(
    lambda cache: crawls_dir(cache, ojs.CACHE_DIR), lambda m: (str(m["journal"]),),
    lambda k: f"OJS {k[0]}", "op ingest ojs",
    lambda cache, k: ojs.mine_journal(k[0], ojs_fetcher(cache, offline=True)),
)  # fmt: skip


def _aaai_key(m: Mapping[str, Any]) -> tuple[Any, ...]:
    if m["venue"] != "AAAI":
        raise ValueError("not an AAAI marker")
    return (int(m["year"]), str(m["release"]))


def _replay_dblp_aaai(cache: Path, key: tuple[Any, ...]) -> dblp.YearResult:
    """One marked AAAI year, from AAAI's extract alone; the pinned release (`DBLP_TABLE`, read at call time) must
    be the marked one (guarantee 4). The year's count is checked again by `mine_year`."""
    year, release = key
    if release != DBLP_TABLE.release.doi:
        raise MinerError(f"AAAI {year} was ingested from dblp release {release}, not the pinned "
                         f"{DBLP_TABLE.release.doi}; re-run op ingest dblp --venue AAAI", reason="release_changed")  # fmt: skip
    return dblp_aaai.mine_year(year, dblp.load_extract(cache, DBLP_TABLE, dblp.AAAI_SLICE))


DBLP_AAAI: Crawls[dblp.YearResult] = Crawls(
    lambda cache: cache / dblp.CACHE_DIR / "aaai-crawls", _aaai_key,
    lambda k: f"AAAI {k[0]} (dblp)", "op ingest dblp --venue AAAI", _replay_dblp_aaai,
)  # fmt: skip


def crossref_fetcher(cache: Path, *, offline: bool, transport: Transport | None = None,
                     min_interval: float = DEFAULT_INTERVAL, mailto: str | None = None) -> Fetcher:  # fmt: skip
    """Crossref's fetcher, one request at a time. Live, the User-Agent names the contact (`mailto`, else
    `CROSSREF_MAILTO` from the environment or `.env`) when there is one; with none the plain User-Agent goes (the
    public pool). Offline, no contact is read at all."""
    live = None if offline else (transport or urllib_transport)
    agent = None if offline else crossref.user_agent(mailto or crossref.contact(os.environ, repo_dotenv()))
    return Fetcher(PageCache(cache / crossref.CACHE_DIR), live, hosts=crossref.HOSTS,
                   min_interval=max(min_interval, crossref.MIN_INTERVAL), accept="application/json", expect="json",
                   keep_query=True, user_agent=agent)  # fmt: skip


def facct_site_fetcher(cache: Path, *, offline: bool, transport: Transport | None = None,
                       min_interval: float = DEFAULT_INTERVAL) -> Fetcher:  # fmt: skip
    """facctconference.org's fetcher. Its CSVs are served as `application/octet-stream`, so the Accept header ends
    in `*/*` and the body is read as text whatever its type; a CSV has no closing tag, so `expect="text"` judges it
    whole unless it states a length it doesn't have (the table's row count is the guard)."""
    live = None if offline else (transport or urllib_transport)
    return Fetcher(PageCache(cache / facct_site.CACHE_DIR), live, hosts=facct_site.HOSTS,
                   min_interval=max(min_interval, facct_site.MIN_INTERVAL),
                   accept="text/csv, text/html, */*;q=0.1", expect="text")  # fmt: skip


def _facct_site(venue: str, year: int, f: Fetcher, *, refresh: bool = False) -> facct_site.SiteYear | None:
    """A FAccT year's official page (`facct_site.TABLE`), or None (AIES; a FAccT year with no page)."""
    return facct_site.read_year(year, f, refresh=refresh) if venue == "FAccT" else None


def ingest_crossref(
    keys: Iterable[tuple[str, int]], cache: Path, *, offline: bool = False, dry_run: bool = False,
    refresh: bool = False, transport: Transport | None = None, min_interval: float = DEFAULT_INTERVAL,
    table: acm_table.Table | None = None, mailto: str | None = None,
) -> dict[str, Any]:  # fmt: skip
    """Crawl each (venue, year) ACM proceedings of `acm_proceedings.toml` from Crossref into the cache. A dry run
    reads nothing live (no network, no contact) and says what is cached; it writes no marker. A FAccT year with an
    official page (`facct_site.toml`) reads that page too, for its abstracts."""
    table = table or acm_table.TABLE
    wanted = sorted(set(keys)) or sorted(table.proceedings)
    for v, y in wanted:
        if (v, y) not in table.proceedings:
            raise MinerError(f"{v} {y}: no acm_proceedings.toml row", reason="unlisted_proceedings")
    if dry_run:
        f = crossref_fetcher(cache, offline=True)
        return {"dry_run": True, "requests": 0, "cached": 0,
                "proceedings": [{"venue": v, "year": y,
                                 "record_cached": f.is_cached(crossref.proceedings_url(table.proceedings[v, y].doi)),
                                 "first_page_cached": f.is_cached(crossref.works_url(table.proceedings[v, y]))}
                                for v, y in wanted]}  # fmt: skip
    f = crossref_fetcher(
        cache, offline=offline, transport=transport, min_interval=min_interval, mailto=mailto
    )
    sf = facct_site_fetcher(cache, offline=offline, transport=transport, min_interval=min_interval)
    mined = CROSSREF.ingest(
        cache, wanted, lambda k: crossref.mine_proceedings(*k, f, refresh=refresh, table=table,
                                                            site=_facct_site(*k, sf, refresh=refresh)),
        lambda k, _: (f"{k[0]}-{k[1]}", {"source": crossref.SOURCE, "venue": k[0], "year": k[1]}),
    )  # fmt: skip
    reports = [r for m in mined for r in m.reports]
    log.info("crossref_ingested", extra={"proceedings": len(wanted), "listings": len(reports),
                                         "requests": f.stats.network, "site_requests": sf.stats.network})  # fmt: skip
    return _output(reports, f, False)


CROSSREF: Crawls[crossref.ProceedingsResult] = Crawls(
    lambda cache: crawls_dir(cache, crossref.CACHE_DIR), lambda m: (str(m["venue"]), int(m["year"])),
    lambda k: f"Crossref {k[0]} {k[1]}", "op ingest crossref",
    lambda cache, k: crossref.mine_proceedings(k[0], k[1], crossref_fetcher(cache, offline=True),
                                               site=_facct_site(k[0], k[1], facct_site_fetcher(cache, offline=True))),
)  # fmt: skip
SOURCES: tuple[Crawls[Any], ...] = (
    openreview_v2.CRAWLS,
    openreview_v1.CRAWLS,
    ICLR,
    NEURIPS,
    PMLR,
    DBLP,
    OJS,
    DBLP_AAAI,
    CROSSREF,
)


def replay_all(cache: Path) -> tuple[list[PaperRecord], list[Report]]:
    """Every finished crawl of every source, re-run from the cache alone (no transport, no credentials):
    their records and reports, source by source in `SOURCES` order. A marked crawl whose responses are no
    longer cached is a `CrawlError`, never a silently smaller snapshot."""
    records: list[PaperRecord] = []
    reports: list[Report] = []
    for source in SOURCES:
        for mined in source.replay(cache):
            records += mined.records
            reports += mined.reports
    return records, reports


def load_crawls(cache: Path) -> tuple[list[PaperRecord], dict[str, Any]]:
    """`replay_all`'s records, and each source's manifest entry (`common.sources_manifest`)."""
    records, reports = replay_all(cache)
    return records, sources_manifest(reports)
