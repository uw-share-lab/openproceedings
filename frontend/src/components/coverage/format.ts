/**
 * How `/coverage` and the home page's coverage line write the API's values (copy deck §8). Formatting only:
 * every number shown is an API field, written with `toLocaleString("en-US")`; nothing here counts, sums or
 * compares records.
 */
import type { Schemas } from "@/api/client";

/** `crawl_dates`' corpus-wide key: the window over every source (spec 04 §Conventions). */
export const ALL_SOURCES = "*";

/** `1,805`: exact, never abbreviated. */
export function count(n: number): string {
  return n.toLocaleString("en-US");
}

/** The calendar date of an API timestamp (`2026-09-20T08:14:03Z` → `2026-09-20`), as the API wrote it. */
export function day(timestamp: string): string {
  return timestamp.slice(0, 10);
}

/** `2026-09-20 08:14 UTC` from an API timestamp, which is always UTC with a `Z` (spec 04 §Conventions). */
export function minuteUtc(timestamp: string): string {
  return `${timestamp.slice(0, 10)} ${timestamp.slice(11, 16)} UTC`;
}

/**
 * What a window's ends are, in words (`snapshot.crawl_dates_kind`): a crawl's fetch times, or the dates a
 * bootstrap source's Google Scholar searches were run, which the page must never call a crawl
 * (prisma-reporting). A kind this page doesn't know, `mixed` included, reads as the neutral "Collected".
 */
export function windowVerb(kind: string | undefined): string {
  switch (kind) {
    case "crawl":
      return "Crawled";
    case "scholar_query_dates":
      return "Google Scholar searches run";
    default:
      return "Collected";
  }
}

/**
 * `Crawled 2026-09-20 to 2026-09-26`: a window's ends as calendar days, after its label; a window within one
 * day reads `Crawled on 2026-09-26`.
 */
export function windowText(label: string, window: Schemas["CrawlWindow"]): string {
  const from = day(window.from);
  const to = day(window.to);
  return from === to ? `${label} on ${from}` : `${label} ${from} to ${to}`;
}

/**
 * The corpus-wide window in words (`Google Scholar searches run on 2026-09-26`), the one sentence
 * `/coverage` and the home line both show; `null` when the snapshot has no `*` window, which is left out.
 */
export function corpusWindow(snapshot: Schemas["SnapshotInfo"]): string | null {
  const window = snapshot.crawl_dates[ALL_SOURCES];
  return window ? windowText(windowVerb(snapshot.crawl_dates_kind[ALL_SOURCES]), window) : null;
}

/** `+1.3%`, `−0.4%`, `0.0%`: the API's unrounded `delta_pct` to one decimal (coverage-reporting §Report shape). */
export function percent(pct: number): string {
  const fixed = Math.abs(pct).toFixed(1);
  if (fixed === "0.0") return "0.0%";
  return `${pct < 0 ? "−" : "+"}${fixed}%`;
}

/** `+12`, `−3`, `0`. */
export function signed(n: number): string {
  if (n === 0) return "0";
  return `${n < 0 ? "−" : "+"}${count(Math.abs(n))}`;
}
