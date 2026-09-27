"use client";

import { Fragment, useState } from "react";
import type { Schemas } from "@/api/client";
import { CopyButton } from "./copy-button";
import { count, day, minuteUtc, percent, signed, windowVerb } from "./format";

type Coverage = Schemas["CoverageResponse"];
type VenueYear = Schemas["VenueYearCoverage"];
type Track = Schemas["TrackCoverage"];

const ALL_SOURCES = "*"; // `crawl_dates`' corpus-wide window (spec 04 §Conventions)

/** "–" for a track × status pair with no cell: none indexed, never a made-up 0 (copy deck CV-4). */
function None() {
  return (
    <>
      <span aria-hidden="true">–</span>
      <span className="sr-only">none</span>
    </>
  );
}

function Window({ label, window }: { label: string; window: Schemas["CrawlWindow"] }) {
  return (
    <>
      {label} {day(window.from)} to {day(window.to)}
    </>
  );
}

/** The snapshot facts and totals above the table (design C1; copy deck CV-1 to CV-3). */
function Header({ coverage }: { coverage: Coverage }) {
  const { snapshot, totals } = coverage;
  const corpus = snapshot.crawl_dates[ALL_SOURCES];
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
        {corpus ? (
          <>
            {" · "}
            <Window label={windowVerb(snapshot.crawl_dates_kind[ALL_SOURCES])} window={corpus} />
          </>
        ) : null}
      </p>
      <p>
        Sources: {snapshot.sources.join(", ")}
        {perSource.map(([source, window]) => (
          <Fragment key={source}>
            {" · "}
            <code className="font-mono">{source}</code>:{" "}
            <Window label={windowVerb(snapshot.crawl_dates_kind[source]).toLowerCase()} window={window} />
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
      </p>
      <p className="text-muted-foreground">
        Only titles and abstracts are indexed. A record without an abstract can be found by its title only.
      </p>
    </div>
  );
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
              <td className="px-2 text-right">{count(track.abstract_missing)}</td>
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
    <div className="space-y-4">
      <Header coverage={coverage} />
      {/* 1.4.10 allows two-dimensional scrolling for a data table: it scrolls in its own region, not the page */}
      <div role="region" aria-label="Coverage table" tabIndex={0} className="max-w-full overflow-x-auto">
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
              const noAbstracts = vy.records > 0 && vy.abstract_missing === vy.records;
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
                          <span className="block text-xs">no abstracts: only titles are searchable</span>
                        </span>
                      ) : (
                        count(vy.abstract_missing)
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
                        className="whitespace-nowrap underline-offset-4 hover:underline"
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
