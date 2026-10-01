"use client";

/**
 * `/record/[id]` (spec 05 §Pages; design R1–R6; copy RC-1–RC-16). The stored record is read first
 * (`?replay=false`), so every recorded value shows at once; then its replay runs and the status block says
 * what it found. Every value on the page is the **recorded** one, never the replay's, except the status block.
 *
 * The methods text and the exports wait for the replay to settle: a `mismatch` is the blocking "do not cite"
 * state with neither rendered (design R4). If the replay can't run just now (429, `API_BUSY`), the page says
 * "Replay: waiting" and shows the methods text and exports from the stored record (decision-014).
 */
import Link from "next/link";
import { useId, useSyncExternalStore, type ReactNode } from "react";
import type { Failure } from "@/api/outcome";
import { clausesOf, removedBuckets, type SearchRecord } from "@/lib/methods-text";
import { indexGone, replayView, type Replay, type ReplayView } from "@/lib/replay-status";
import { Coded } from "../coded";
import { CopyButton } from "../copy-button";
import { box, button, Countdown, warnBox } from "../export/export-notice";
import { RecordExports } from "../export/record-exports";
import { modeWords } from "../paper/paper-view";
import { reportHref } from "../search/search-states";
import { MethodsBlock } from "./methods-block";
import { RecordDiff } from "./record-diff";
import { useRecordParses, useReplay, useStoredRecord } from "./use-record";

const subscribe = () => () => {};
/** The site's origin in the browser ("" while rendering on the server, where nothing uses it). */
export function useOrigin(): string {
  return useSyncExternalStore(
    subscribe,
    () => window.location.origin,
    () => "",
  );
}

const num = (n: number) => n.toLocaleString("en-US");
const Code = ({ children }: { children: string }) => <code className="font-mono break-all">{children}</code>;

/** `2026-09-25T14:03:11Z` → `2026-09-25 14:03:11 UTC`. */
export function searchedText(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? iso
    : `${d.toISOString().slice(0, 10)} ${d.toISOString().slice(11, 19)} UTC`;
}

/** RC-9: the crawl window's label and value by `crawl_dates_kind["*"]`. */
export function windowRow(record: SearchRecord): { label: string; value: string } | null {
  const w = record.crawl_dates["*"];
  if (w === undefined) return null;
  const span = `${w.from.slice(0, 10)} to ${w.to.slice(0, 10)}`;
  switch (record.crawl_dates_kind?.["*"]) {
    case "crawl":
      return { label: "Crawl run", value: span };
    case "scholar_query_dates":
      return { label: "Scholar searches run", value: `${span} (local time)` };
    case "scholar_query_dates_utc":
      return { label: "Scholar searches run", value: `${span} (UTC)` };
    case "mixed":
      return { label: "Crawls and Scholar searches run", value: `${span} (Scholar dates in local time)` };
    case "mixed_utc":
      return { label: "Crawls and Scholar searches run", value: `${span} (UTC)` };
    default:
      return { label: "Collected", value: span };
  }
}

/** RC-10: each dedup count on its own, never summed; a null count (a v1 record) reads "not recorded". */
export function dedupText(d: SearchRecord["dedup"]): string {
  const n = (v: number | null) => (v === null ? "not recorded" : num(v));
  return (
    `${num(d.merged)} cross-source records merged at ingest; look-alike pairs kept apart: ` +
    `${n(d.track_not_merged)} by track, ${n(d.venue_year_not_merged)} by venue-year; ` +
    `${num(d.ambiguous_not_merged)} ambiguous, not merged`
  );
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid gap-x-4 gap-y-1 border-b py-2 sm:grid-cols-[11rem_minmax(0,1fr)]">
      <dt className="font-semibold">{label}</dt>
      <dd className="min-w-0 break-words">{children}</dd>
    </div>
  );
}

function Diagnostics({ items }: { items: SearchRecord["warnings"] }) {
  if (items.length === 0) return <>none</>;
  return (
    <ul className="space-y-1">
      {items.map((d, i) => (
        <li key={i}>
          <Code>{d.code}</Code>: <Coded text={d.message} />
        </li>
      ))}
    </ul>
  );
}

/** Every recorded field (design R1; copy RC-8). */
function RecordDetails({ record }: { record: SearchRecord }) {
  const parses = useRecordParses(record);
  const clauses = clausesOf(record, parses.canonical);
  const window = windowRow(record);
  const removed = removedBuckets(record);
  const expansions = Object.entries(record.expansions);
  return (
    <dl className="text-sm">
      <Row label="Query as typed">
        <Code>{record.input}</Code> <CopyButton text={record.input} label="Copy the query as typed" /> ·{" "}
        {modeWords(record.mode)}
      </Row>
      <Row label="Identification string">
        {record.identification_query === "" ? (
          "none (all indexed records)"
        ) : (
          <>
            <Code>{record.identification_query}</Code>{" "}
            <CopyButton text={record.identification_query} label="Copy the identification string" />
          </>
        )}
      </Row>
      <Row label="Default filters">
        {!parses.settled
          ? "…"
          : clauses === null
            ? "Not separated from the canonical query here (this instance reads queries under other rules): see the canonical query."
            : clauses.defaults.length === 0
              ? "none"
              : clauses.defaults.map((c, i) => (
                  <span key={c}>
                    {i > 0 && " "}
                    <Code>{c}</Code>
                  </span>
                ))}
      </Row>
      <Row label="Canonical query">
        <Code>{record.canonical}</Code>{" "}
        <CopyButton text={record.canonical} label="Copy the canonical query" />
      </Row>
      <Row label="Index version">
        <Code>{record.index_version}</Code>{" "}
        <CopyButton text={record.index_version} label="Copy the index version" />
        <br />
        <span className="text-muted-foreground">
          tokenizer <Code>{record.tokenizer_version}</Code> · query version{" "}
          <Code>{record.query_version}</Code> · snapshot <Code>{record.snapshot_hash}</Code> · schema{" "}
          <Code>{record.schema_version}</Code>
        </span>
      </Row>
      <Row label="Searched">{searchedText(record.searched_at)}</Row>
      {window !== null && <Row label={window.label}>{window.value}</Row>}
      <Row label="Records">
        {num(record.identified_total)} identified · {num(record.excluded.total)} removed before screening ·{" "}
        {num(record.total)} screened
      </Row>
      <Row label="Removed before screening">
        {removed.length === 0 ? "none" : removed.join(" · ")}
        <br />
        unclassified: {num(record.excluded.track["unknown"] ?? 0)} track unknown ·{" "}
        {num(record.excluded.status["unknown"] ?? 0)} status unknown
      </Row>
      <Row label="Expansions">
        {expansions.length === 0 ? (
          "none"
        ) : (
          <ul className="space-y-1">
            {expansions.map(([stem, words]) => (
              <li key={stem}>
                <Code>{stem}</Code> → {words.join(", ")}
              </li>
            ))}
          </ul>
        )}
      </Row>
      <Row label="Warnings">
        <Diagnostics items={record.warnings} />
      </Row>
      {record.mode === "scholar" && (
        <Row label="Translations">
          <Diagnostics items={record.translations} />
        </Row>
      )}
      <Row label="Deduplication">{dedupText(record.dedup)}</Row>
    </dl>
  );
}

/** The status block: what the replay found (design R1–R3), or why it hasn't run. */
function StatusBlock({
  id,
  view,
  replay,
  failure,
  onRetry,
  statusId,
}: {
  id: string;
  view: ReplayView | null;
  replay: Replay | null;
  failure: Failure | null;
  onRetry: () => void;
  statusId: string;
}) {
  let content: ReactNode;
  if (failure !== null) {
    const waiting =
      failure.kind === "refused" && (failure.status === 429 || failure.error.code === "API_BUSY");
    content = (
      <div className={warnBox}>
        <p>
          <span aria-hidden="true">⚠ </span>
          {waiting ? "Replay: waiting" : "Replay: not checked"} — re-running this record&apos;s search to
          check it
          {failure.kind === "refused" ? (
            <>
              {" "}
              was refused just now (<Code>{failure.error.code}</Code>): {failure.error.message}
            </>
          ) : failure.kind === "no_answer" ? (
            " got no answer from the server (busy or restarting)."
          ) : (
            " couldn't reach the server."
          )}{" "}
          The recorded values below stand as recorded.
        </p>
        {waiting && failure.kind === "refused" ? (
          <Countdown seconds={failure.retryAfter} onRetry={onRetry} />
        ) : (
          <button type="button" onClick={onRetry} className={button}>
            Retry
          </button>
        )}
      </div>
    );
  } else if (view === null || replay === null) {
    content = (
      <p className="text-sm text-muted-foreground">
        Checking the record: re-running its search on this instance…
      </p>
    );
  } else if (view.kind === "reproduced") {
    content = (
      <p className={`${box} break-words`}>
        <span aria-hidden="true">✔ </span>
        {view.text}
      </p>
    );
  } else if (view.kind === "mismatch") {
    content = null; // drawn by the page as the blocking alert
  } else if (view.kind === "refused" || view.kind === "withheld") {
    content = (
      <p className={`${warnBox} break-words`}>
        <span aria-hidden="true">⚠ </span>
        <Coded text={view.text} />
      </p>
    );
  } else {
    content = (
      <div className={warnBox}>
        <p className="break-words">
          <span aria-hidden="true">⚠ </span>
          <Coded text={view.text} />
        </p>
        {view.membershipIdentical !== null && <p>{view.membershipIdentical}</p>}
        {view.changes.length > 0 && (
          <div>
            <p className="font-semibold">What changed:</p>
            <ul className="space-y-1">
              {view.changes.map((c) => (
                <li key={c.input} className="break-words">
                  <Code>{c.input}</Code> <Code>{c.recorded}</Code> → <Code>{c.current}</Code>
                  {c.meaning !== "" && ` — ${c.meaning}`}
                </li>
              ))}
            </ul>
          </div>
        )}
        {view.added + view.removed > 0 && <RecordDiff id={id} added={view.added} removed={view.removed} />}
        <p className="break-words">{view.exclusions}</p>
        <p>{view.cite}</p>
      </div>
    );
  }
  return (
    <div
      id={statusId}
      role={failure === null ? "status" : "alert"}
      aria-live={failure === null ? "polite" : "assertive"}
      aria-atomic="true"
    >
      {content}
    </div>
  );
}

function Mismatch({ record }: { record: SearchRecord }) {
  const report = new URL(reportHref("API_REPLAY_MISMATCH", new Date()));
  report.searchParams.set(
    "body",
    `${report.searchParams.get("body") ?? ""}Search record: ${record.record_id}\n`,
  );
  return (
    <section role="alert" className={`${box} border-destructive`}>
      <h2 className="text-base font-semibold">
        <span aria-hidden="true">✖ </span>Do not cite — replay mismatch
      </h2>
      <p className="break-words">
        Re-run on the same index (<Code>{record.index_version}</Code>) and query version (
        <Code>{record.query_version}</Code>), this search gives different papers or exclusions than the record
        holds. That should never happen: it is a bug in openproceedings, not in your search. Don&apos;t cite
        this record or its counts, and don&apos;t export it.{" "}
        <a href={report.toString()} rel="noopener noreferrer" className="underline underline-offset-4">
          Report it <span aria-hidden="true">▸</span>
        </a>
      </p>
      <details>
        <summary className="cursor-pointer">Show the record&apos;s details anyway</summary>
        <p className="mt-2 text-muted-foreground">Every value below is as recorded, and none can be cited.</p>
        <RecordDetails record={record} />
      </details>
    </section>
  );
}

function CantLoad({ failure, onRetry }: { failure: Failure; onRetry: () => void }) {
  const waiting = failure.kind === "refused" && (failure.status === 429 || failure.error.code === "API_BUSY");
  return (
    <div role="alert" className={waiting ? warnBox : box}>
      <p className="break-words">
        The record couldn&apos;t be loaded just now
        {failure.kind === "refused" ? (
          <>
            : <Code>{failure.error.code}</Code>: {failure.error.message}
          </>
        ) : failure.kind === "no_answer" ? (
          ": the server is busy or restarting."
        ) : (
          ": couldn't reach the server. Check your connection."
        )}
      </p>
      {waiting && failure.kind === "refused" ? (
        <Countdown seconds={failure.retryAfter} onRetry={onRetry} />
      ) : (
        <button type="button" onClick={onRetry} className={button}>
          Retry
        </button>
      )}
    </div>
  );
}

/** Today's UTC date (RC-2's "Reproduced on <today>"). */
function today(): string {
  return new Date().toISOString().slice(0, 10);
}

export function RecordView({ id }: { id: string }) {
  const origin = useOrigin();
  const stored = useStoredRecord(id);
  const replayed = useReplay(id, stored.outcome?.kind === "ok");
  const statusId = useId();

  if (stored.outcome === null) {
    return (
      <p role="status" className="text-sm text-muted-foreground">
        Loading the search record…
      </p>
    );
  }
  if (stored.outcome.kind === "not_found") {
    return (
      <section className="mx-auto max-w-3xl space-y-2 text-sm">
        <h1 className="text-lg font-semibold">Search record not found</h1>
        <p>No search record with that id on this instance. Check the link; a record id is 12 characters.</p>
        <Link href="/search" className="underline underline-offset-4">
          Search
        </Link>
      </section>
    );
  }
  if (stored.outcome.kind !== "ok") {
    return (
      <section className="mx-auto max-w-3xl space-y-2">
        <h1 className="text-lg font-semibold">Search record {id}</h1>
        <CantLoad failure={stored.outcome} onRetry={stored.refetch} />
      </section>
    );
  }

  const record = stored.outcome.data.record;
  const answer = replayed.outcome;
  const replay = answer?.kind === "ok" ? answer.data.replay : null;
  const failure: Failure | null =
    answer !== null && answer.kind !== "ok" && answer.kind !== "not_found" ? answer : null;
  const view = replay === null ? null : replayView(record, replay, today());
  const settled = view !== null || failure !== null;
  const url = `${origin}/record/${record.record_id}`;

  if (view?.kind === "mismatch") {
    return (
      <article className="mx-auto max-w-4xl space-y-4">
        <h1 className="text-lg font-semibold">
          Search record <span className="font-mono">{record.record_id}</span>
        </h1>
        <Mismatch record={record} />
      </article>
    );
  }

  return (
    <article className="mx-auto max-w-4xl space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <h1 aria-describedby={statusId} className="text-lg font-semibold">
          Search record <span className="font-mono">{record.record_id}</span>
        </h1>
        <CopyButton text={url} label="Copy link" />
      </div>
      <StatusBlock
        id={record.record_id}
        view={view}
        replay={replay}
        failure={failure}
        onRetry={replayed.refetch}
        statusId={statusId}
      />
      <RecordDetails record={record} />
      {settled && <MethodsBlock record={record} url={url} />}
      {settled && (
        <RecordExports
          recordId={record.record_id}
          indexVersion={record.index_version}
          total={record.total}
          indexGone={indexGone(record, replay)}
        />
      )}
    </article>
  );
}
