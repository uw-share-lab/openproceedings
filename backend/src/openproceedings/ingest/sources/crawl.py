"""`op ingest neurips|pmlr` and the offline re-mine `op snapshot build` runs (spec 01 §CLI, §Pipeline).

`ingest_*` crawls each listing into `<cache>/<source>/pages/` (one run at a time per source: an exclusive
lock on `<cache>/<source>/.lock`) and, when the whole listing is cached, writes its crawl marker. A dry
run reads only the index pages (through the cache) and reports what a crawl would fetch; it writes no
marker. `--offline` crawls from the cache alone. `load_crawls` re-mines every marked listing from the cache
with no transport at all, so a snapshot never fetches.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from openproceedings import storage
from openproceedings.ingest.record import PaperRecord
from openproceedings.ingest.sources import neurips, pmlr
from openproceedings.ingest.sources.common import (
    ListingReport,
    MinerError,
    markers,
    source_manifest,
    write_marker,
)
from openproceedings.ingest.sources.http import Fetcher, FetchError, PageCache, Transport, urllib_transport
from openproceedings.ingest.volumes import icml_volume

log = logging.getLogger(__name__)

DEFAULT_INTERVAL = 1.0  # seconds between requests to a host (the openreview-api skill's pace)


def fetcher(
    cache: Path, source_dir: str, hosts: frozenset[str], *, offline: bool, transport: Transport | None = None,
    min_interval: float = DEFAULT_INTERVAL,
) -> Fetcher:  # fmt: skip
    live = None if offline else (transport or urllib_transport)
    return Fetcher(PageCache(cache / source_dir), live, hosts=hosts, min_interval=min_interval)


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
    f = fetcher(
        cache,
        neurips.CACHE_DIR,
        neurips.HOSTS,
        offline=offline,
        transport=transport,
        min_interval=min_interval,
    )
    reports: list[ListingReport] = []
    with storage.exclusive(cache / neurips.CACHE_DIR):
        for year in sorted(set(years)):
            result = neurips.mine_year(year, f, refresh_index=refresh, plan_only=dry_run)
            reports += result.reports
            if not dry_run:
                write_marker(cache, neurips.CACHE_DIR, str(year), {"source": neurips.SOURCE, "year": year})
    log.info(
        "neurips_ingested", extra={"years": len(reports), "requests": f.stats.network, "dry_run": dry_run}
    )
    return _output(reports, f, dry_run)


def ingest_pmlr(
    years: Iterable[int], cache: Path, *, offline: bool = False, dry_run: bool = False, refresh: bool = False,
    transport: Transport | None = None, min_interval: float = DEFAULT_INTERVAL,
) -> dict[str, Any]:  # fmt: skip
    """Crawl the ICML volume of each year (from the volume table) into the cache."""
    volumes = []
    for year in sorted(set(years)):
        volume = icml_volume(year)
        if volume is None:
            raise MinerError(
                f"ICML {year}: no verified PMLR volume in the volume table (add its row once its index is live)",
                reason="no_volume",
            )
        volumes.append(volume.number)
    f = fetcher(
        cache, pmlr.CACHE_DIR, pmlr.HOSTS, offline=offline, transport=transport, min_interval=min_interval
    )
    reports: list[ListingReport] = []
    with storage.exclusive(cache / pmlr.CACHE_DIR):
        for number in volumes:
            result = pmlr.mine_volume(number, f, refresh_index=refresh, plan_only=dry_run)
            reports.append(result.report)
            if not dry_run:
                write_marker(cache, pmlr.CACHE_DIR, f"v{number}", {"source": pmlr.SOURCE, "volume": number})
    log.info(
        "pmlr_ingested", extra={"volumes": len(reports), "requests": f.stats.network, "dry_run": dry_run}
    )
    return _output(reports, f, dry_run)


def load_crawls(cache: Path) -> tuple[list[PaperRecord], dict[str, Any]]:
    """Every finished crawl, re-mined from the cache alone (no transport), and each source's manifest entry.
    A marked listing whose pages are no longer cached is an error, never a silently smaller snapshot."""
    records: list[PaperRecord] = []
    sources: dict[str, Any] = {}
    nf = fetcher(cache, neurips.CACHE_DIR, neurips.HOSTS, offline=True)
    years = sorted({int(m["year"]) for m in markers(cache, neurips.CACHE_DIR)})
    reports: list[ListingReport] = []
    for year in years:
        try:
            result = neurips.mine_year(year, nf)
        except FetchError as e:
            raise MinerError(
                f"NeurIPS {year} is marked crawled but {e}; re-run op ingest neurips", reason=e.reason
            ) from e
        records += result.records
        reports += result.reports
    if reports:
        sources[neurips.SOURCE] = source_manifest(reports)
    pf = fetcher(cache, pmlr.CACHE_DIR, pmlr.HOSTS, offline=True)
    numbers = sorted({int(m["volume"]) for m in markers(cache, pmlr.CACHE_DIR)})
    reports = []
    for number in numbers:
        try:
            got = pmlr.mine_volume(number, pf)
        except FetchError as e:
            raise MinerError(
                f"PMLR v{number} is marked crawled but {e}; re-run op ingest pmlr", reason=e.reason
            ) from e
        records += got.records
        reports.append(got.report)
    if reports:
        sources[pmlr.SOURCE] = source_manifest(reports)
    return records, sources
