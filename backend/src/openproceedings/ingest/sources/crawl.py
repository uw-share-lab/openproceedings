"""`op ingest iclr|neurips|pmlr`, and the one offline replay of every crawler that `op snapshot build` runs (spec 01
§CLI, §Pipeline).

`ingest_*` crawls each listing into `<cache>/<source>/pages/` through `common.Crawls.ingest` (one run at a
time per source: an exclusive lock on `<cache>/<source>/.lock`) and, when the whole listing is cached, writes
its crawl marker. A dry run reads only the index pages (through the cache) and reports what a crawl would
fetch; it writes no marker. `--offline` crawls from the cache alone. `replay_all` re-runs every marked crawl of every source
(OpenReview API v2, then v1, then ICLR, NeurIPS and PMLR; `common.Crawls`) with no transport at all, so a snapshot
never fetches.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from openproceedings.ingest.record import PaperRecord
from openproceedings.ingest.sources import iclr, neurips, openreview_v1, openreview_v2, pmlr
from openproceedings.ingest.sources.common import (
    Crawls,
    ListingReport,
    MinerError,
    Report,
    sources_manifest,
)
from openproceedings.ingest.sources.http import Fetcher, PageCache, Transport, urllib_transport
from openproceedings.ingest.volumes import icml_volume

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
    mined = PMLR.ingest(
        cache, volumes, lambda number: pmlr.mine_volume(number, f, refresh_index=refresh, plan_only=dry_run),
        lambda number, _: None if dry_run else (f"v{number}", {"source": pmlr.SOURCE, "volume": number}),
    )  # fmt: skip
    reports = [m.report for m in mined]
    log.info(
        "pmlr_ingested", extra={"volumes": len(reports), "requests": f.stats.network, "dry_run": dry_run}
    )
    return _output(reports, f, dry_run)


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
SOURCES: tuple[Crawls[Any], ...] = (openreview_v2.CRAWLS, openreview_v1.CRAWLS, ICLR, NEURIPS, PMLR)


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
