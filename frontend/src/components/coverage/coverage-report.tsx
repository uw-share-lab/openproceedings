"use client";

import { Fragment, useState } from "react";
import type { Schemas } from "@/api/client";
import { CopyButton } from "./copy-button";
import { ALL_SOURCES, corpusWindow, kindWindowText, count, minuteUtc, percent, signed } from "./format";

type Coverage = Schemas["CoverageResponse"];
type VenueYear = Schemas["VenueYearCoverage"];
type Track = Schemas["TrackCoverage"];

/** "–" for a track × status pair with no cell: none indexed, never a made-up 0 (copy deck CV-4). */
function None() {
  return (
    <>
      <span aria-hidden="true">–</span>
      <span className="sr-only">none</span>
    </>
  );
}

type Span = { venue: string; from: number; to: number; missing: number[] };

/** Each venue's first and last indexed year, and the years between with no records, in venue order (copy deck
 * CV-7). */
export function yearSpans(venueYears: readonly VenueYear[]): Span[] {
  const years = new Map<string, Set<number>>();
  for (const vy of venueYears) years.set(vy.venue, (years.get(vy.venue) ?? new Set<number>()).add(vy.year));
  return [...years.entries()]
    .map(([venue, held]) => {
      const from = Math.min(...held);
      const to = Math.max(...held);
      const missing = Array.from({ length: to - from + 1 }, (_, i) => from + i).filter((y) => !held.has(y));
      return { venue, from, to, missing };
    })
    .sort((a, b) => (a.venue < b.venue ? -1 : a.venue > b.venue ? 1 : 0));
}

/** A venue and its years as both coverage surfaces write them: `AAAI 2010–2026`, one year alone (`IASEAI 2026`). */
export function spanRange(s: Span): string {
  return s.from === s.to ? `${s.venue} ${s.from}` : `${s.venue} ${s.from}–${s.to}`;
}

function spanText(s: Span): string {
  const range = s.from === s.to ? `${s.from}` : `${s.from}–${s.to}`;
  return s.missing.length === 0
    ? `${s.venue} ${range}`
    : `${s.venue} ${range} (none in ${s.missing.join(", ")})`;
}

/** A `year:` clause for a span: one year alone, else `from..to`. */
function yearClause(from: number, to: number): string {
  return from === to ? `year:${from}` : `year:${from}..${to}`;
}

/** "Years indexed: …", and when the venues cover different years, why that matters and what compares them: the
 * `year:` clause of the years every venue holds, or, when no year is held by all, a per-venue clause (copy deck
 * CV-7; decision-047 and decision-049: NeurIPS from 1987, ICML from 1988, ICLR from 2013, AAAI from 2010, AIES
 * 2024–2025, IASEAI 2026). Display only: the clause is a suggestion the reader may add to their query. */
function YearSpans({ venueYears }: { venueYears: readonly VenueYear[] }) {
  const spans = yearSpans(venueYears);
  if (spans.length === 0) return null;
  const differ = new Set(spans.map((s) => s.from)).size > 1 || new Set(spans.map((s) => s.to)).size > 1;
  const common = { from: Math.max(...spans.map((s) => s.from)), to: Math.min(...spans.map((s) => s.to)) };
  // the venue that starts last, as the example of a venue with its own years
  const latest = spans.reduce((a, b) => (b.from > a.from ? b : a));
  return (
    <p className="tabular-nums">
      Years indexed: {spans.map(spanText).join(" · ")}
      {differ ? (
        <>
          . The venues cover different years, so a search without a <code className="font-mono">year:</code>{" "}
          filter compares them over different years
          {common.from <= common.to ? (
            <>
              . Add <code className="font-mono">{yearClause(common.from, common.to)}</code> to compare them
              over the same years
            </>
          ) : (
            <>
              . No year is held by every venue: give each venue its own years, one clause per venue joined
              with OR, as in{" "}
              <code className="font-mono">{`(venue:${latest.venue} ${yearClause(latest.from, latest.to)})`}</code>
            </>
          )}
          .
        </>
      ) : null}
    </p>
  );
}

/** The snapshot facts and totals above the table (design C1; copy deck CV-1 to CV-3, CV-7). */
function Header({ coverage }: { coverage: Coverage }) {
  const { snapshot, totals } = coverage;
  const corpus = corpusWindow(snapshot);
  const perSource = Object.entries(snapshot.crawl_dates).filter(([key]) => key !== ALL_SOURCES);
  return (
    <div className="space-y-1 text-sm">
      <p>
        Index <code className="font-mono">{coverage.index_version}</code>{" "}
        <CopyButton value={coverage.index_version} label="index version" /> · tokenizer{" "}
        <code className="font-mono">{coverage.tokenizer_version}</code> · query version{" "}
        <code className="font-mono">{coverage.query_version}</code>
      </p>
      <p className="break-all">
        Snapshot <code className="font-mono">{snapshot.name}</code> ·{" "}
        <code className="font-mono">{snapshot.snapshot_hash}</code>{" "}
        <CopyButton value={snapshot.snapshot_hash} label="snapshot hash" />
      </p>
      <p>
        Built {minuteUtc(snapshot.built_at)}
        {corpus === null ? null : ` · ${corpus}`}
      </p>
      <p>
        Sources: {snapshot.sources.join(", ")}
        {perSource.map(([source, window]) => (
          <Fragment key={source}>
            {" · "}
            <code className="font-mono">{source}</code>:{" "}
            {kindWindowText(snapshot.crawl_dates_kind[source], window)}
          </Fragment>
        ))}
      </p>
      {snapshot.identification_citable ? null : (
        <p className="rounded-md border border-warn-border bg-warn-bg px-2 py-1 text-warn-fg">
          Every source of this snapshot is an earlier search&apos;s output, not a database: its counts are not
          PRISMA identification numbers.
        </p>
      )}
      <p className="pt-2 tabular-nums">
        {count(totals.records)} records · {count(totals.abstract_missing)} without an abstract ·{" "}
        {count(totals.unknown_track)} of unknown track · {count(totals.unknown_status)} of unknown status
        {totals.abstract_withheld > 0 && (
          <>
            {" "}
            · {count(totals.abstract_withheld)} with the abstract removed at a rights holder&apos;s request
          </>
        )}
      </p>
      <YearSpans venueYears={coverage.venue_years} />
      <p className="text-muted-foreground">
        Only titles and abstracts are indexed. A record without an abstract can be found by its title only.
      </p>
    </div>
  );
}

/** Under a "No abstract" count: the abstracts removed at a rights holder's request (decision-022; copy CV-6),
 * which that count leaves out. Nothing when there are none. */
function Withheld({ n }: { n: number }) {
  if (n === 0) return null;
  return <span className="block text-xs text-muted-foreground">and {count(n)} removed on request</span>;
}

function Gate({ track }: { track: Track }) {
  if (!track.gated || track.within_gate === null) return <>not gated</>;
  return track.within_gate ? <>✓ within the gate</> : <>✗ outside the gate</>;
}

function Official({ track }: { track: Track }) {
  if (track.official_accepted === null) return <>no official count</>;
  return (
    <>
      {count(track.official_accepted)}
      {track.official_citation ? (
        <span className="block text-xs text-muted-foreground">
          {track.official_counts}
          {track.official_counts ? "; " : ""}
          {/^https?:\/\//.test(track.official_citation) ? (
            <a className="underline underline-offset-4" href={track.official_citation}>
              {track.official_citation}
            </a>
          ) : (
            track.official_citation
          )}
          {track.official_accessed ? `, read ${track.official_accessed}` : ""}
        </span>
      ) : null}
    </>
  );
}

/** One venue-year's detail: records by track and status (from `cells`), then each track against its official
 * accepted count (from `tracks`). Columns are the venue-year's statuses indexed, which hold every status it has. */
function Detail({ vy, id }: { vy: VenueYear; id: string }) {
  const name = `${vy.venue} ${vy.year}`;
  const cell = (track: string, status: string) =>
    vy.cells.find((c) => c.track === track && c.status === status);
  return (
    <div id={id} className="space-y-3 py-2">
      <table className="text-sm tabular-nums">
        <caption className="text-left font-medium">{name}: records by track and status</caption>
        <thead>
          <tr>
            <th scope="col" className="px-2 text-left">
              Track
            </th>
            {vy.statuses_indexed.map((status) => (
              <th key={status} scope="col" className="px-2 text-right">
                {status}
              </th>
            ))}
            <th scope="col" className="px-2 text-right">
              Records
            </th>
            <th scope="col" className="px-2 text-right">
              No abstract
            </th>
            <th scope="col" className="px-2 text-left">
              Sources
            </th>
          </tr>
        </thead>
        <tbody>
          {vy.tracks.map((track) => (
            <tr key={track.track}>
              <th scope="row" className="px-2 text-left font-normal">
                {track.track}
              </th>
              {vy.statuses_indexed.map((status) => {
                const found = cell(track.track, status);
                return (
                  <td key={status} className="px-2 text-right">
                    {found ? count(found.count) : <None />}
                  </td>
                );
              })}
              <td className="px-2 text-right">{count(track.records)}</td>
              <td className="px-2 text-right">
                {count(track.abstract_missing)}
                <Withheld n={track.abstract_withheld} />
              </td>
              <td className="px-2 text-left">{track.sources.join(", ")}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <table className="text-sm tabular-nums">
        <caption className="text-left font-medium">
          {name}: accepted records against the official count
        </caption>
        <thead>
          <tr>
            <th scope="col" className="px-2 text-left">
              Track
            </th>
            <th scope="col" className="px-2 text-right">
              Indexed accepted
            </th>
            <th scope="col" className="px-2 text-left">
              Official accepted
            </th>
            <th scope="col" className="px-2 text-right">
              Difference
            </th>
            <th scope="col" className="px-2 text-left">
              Coverage gate
            </th>
          </tr>
        </thead>
        <tbody>
          {vy.tracks.map((track) => (
            <tr key={track.track}>
              <th scope="row" className="px-2 text-left font-normal">
                {track.track}
              </th>
              <td className="px-2 text-right">{count(track.indexed_accepted)}</td>
              <td className="px-2 text-left">
                <Official track={track} />
              </td>
              <td className="px-2 text-right">
                {track.delta === null || track.delta_pct === null ? (
                  <None />
                ) : (
                  <>
                    {signed(track.delta)} ({percent(track.delta_pct)})
                  </>
                )}
              </td>
              <td className="px-2 text-left">
                <Gate track={track} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const COLUMNS = ["Records", "No abstract", "Unknown track", "Unknown status"] as const;

/** The whole `/coverage` report for one `GET /coverage` answer. Every number is an API field (design C1). */
export function CoverageReport({ coverage }: { coverage: Coverage }) {
  const [open, setOpen] = useState<ReadonlySet<string>>(new Set());
  // venue A–Z, then newest year first (design C1); the API orders by venue, then year ascending
  const rows = [...coverage.venue_years].sort((a, b) =>
    a.venue === b.venue ? b.year - a.year : a.venue < b.venue ? -1 : 1,
  );
  const toggle = (key: string) =>
    setOpen((before) => {
      const next = new Set(before);
      if (!next.delete(key)) next.add(key);
      return next;
    });
  return (
    <div className="min-w-0 space-y-4">
      <Header coverage={coverage} />
      {/* 1.4.10 allows two-dimensional scrolling for a data table: it scrolls in its own region, not the page */}
      <div
        role="region"
        aria-label="Coverage table"
        tabIndex={0}
        className="max-w-full overflow-x-auto contain-layout"
      >
        <table className="min-w-full text-sm tabular-nums">
          <caption className="pb-2 text-left text-muted-foreground">
            Records per venue and year in snapshot <code className="font-mono">{coverage.snapshot.name}</code>
          </caption>
          <thead>
            <tr className="border-b">
              <th scope="col" className="sticky left-0 bg-background px-2 text-left">
                Venue
              </th>
              <th scope="col" className="px-2 text-left">
                Year
              </th>
              {COLUMNS.map((c) => (
                <th key={c} scope="col" className="px-2 text-right">
                  {c}
                </th>
              ))}
              <th scope="col" className="px-2 text-left">
                Statuses indexed
              </th>
              <th scope="col" className="px-2 text-left">
                <span className="sr-only">Details</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((vy) => {
              const key = `${vy.venue}-${vy.year}`;
              const id = `coverage-detail-${key}`;
              const expanded = open.has(key);
              // no record shows an abstract: missing ones and removed ones together
              const noAbstracts = vy.records > 0 && vy.abstract_missing + vy.abstract_withheld === vy.records;
              return (
                <Fragment key={key}>
                  <tr className="border-b">
                    <th scope="row" className="sticky left-0 bg-background px-2 text-left font-normal">
                      {vy.venue}
                    </th>
                    <td className="px-2">{vy.year}</td>
                    <td className="px-2 text-right">{count(vy.records)}</td>
                    <td className="px-2 text-right">
                      {noAbstracts ? (
                        <span className="text-warn-fg">
                          <span aria-hidden="true">⚠ </span>
                          {count(vy.abstract_missing)}
                          <Withheld n={vy.abstract_withheld} />
                          <span className="block text-xs">
                            {/* removed abstracts may still be matched on an older index (decision-022) */}
                            {vy.abstract_withheld > 0
                              ? "no abstracts shown"
                              : "no abstracts: only titles are searchable"}
                          </span>
                        </span>
                      ) : (
                        <>
                          {count(vy.abstract_missing)}
                          <Withheld n={vy.abstract_withheld} />
                        </>
                      )}
                    </td>
                    <td className="px-2 text-right">{count(vy.unknown_track)}</td>
                    <td className="px-2 text-right">{count(vy.unknown_status)}</td>
                    <td className="px-2">{vy.statuses_indexed.join(", ")}</td>
                    <td className="px-2">
                      <button
                        type="button"
                        aria-expanded={expanded}
                        aria-controls={id}
                        aria-label={`Details: track and status for ${vy.venue} ${vy.year}`}
                        onClick={() => toggle(key)}
                        className="inline-flex min-h-6 items-center whitespace-nowrap underline-offset-4 hover:underline"
                      >
                        Details {expanded ? "▾" : "▸"}
                      </button>
                    </td>
                  </tr>
                  {expanded ? (
                    <tr className="border-b">
                      <td colSpan={COLUMNS.length + 4} className="px-2">
                        <Detail vy={vy} id={id} />
                      </td>
                    </tr>
                  ) : null}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
