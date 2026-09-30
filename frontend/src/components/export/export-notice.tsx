"use client";

/**
 * Why an export (or a save) didn't happen, and what to do (design E3, S3; copy EX-E3b, EX-E4, SV-6; spec 05
 * §Error handling): the index moved, the count differs on the same index (a bug), or the server refused or
 * didn't answer. Each says that nothing was downloaded. A wait (429, 503 `API_BUSY`) counts down to Retry.
 */
import { useEffect, useState } from "react";
import type { Failure } from "@/api/outcome";
import { plural } from "@/editor/diagnostics";
import type { ExportResult } from "@/lib/export";
import { reportHref } from "../search/search-states";

export const box = "space-y-2 rounded-md border p-3 text-sm";
export const warnBox = `${box} border-warn-border bg-warn-bg text-warn-fg`;
export const button = "min-h-8 rounded-md border px-3 hover:bg-muted";

/** `seconds` counted down to 0, then "You can retry now" and Retry (announced at the start and at 0 only). */
export function Countdown({ seconds, onRetry }: { seconds: number | null; onRetry: () => void }) {
  const [left, setLeft] = useState(seconds ?? 0);
  useEffect(() => {
    if (left <= 0) return;
    const t = setTimeout(() => setLeft(left - 1), 1000);
    return () => clearTimeout(t);
  }, [left]);
  const waiting = left > 0;
  return (
    <div className="flex flex-wrap items-center gap-3">
      <p role="status" aria-live="polite">
        {waiting ? `Retry in ${seconds ?? 0} s` : "You can retry now"}
      </p>
      <button
        type="button"
        aria-disabled={waiting ? true : undefined}
        onClick={() => {
          if (!waiting) onRetry();
        }}
        className={`${button} ${waiting ? "opacity-60" : ""}`}
      >
        Retry
      </button>
      {waiting && (
        <span aria-hidden="true" className="tabular-nums">
          {left} s
        </span>
      )}
    </div>
  );
}

function Report({ code }: { code: string }) {
  return (
    <a href={reportHref(code, new Date())} rel="noopener noreferrer" className="underline underline-offset-4">
      Report it <span aria-hidden="true">▸</span>
    </a>
  );
}

/** A refusal or no answer, worded from the envelope (never a raw status), with Retry. */
export function FailureNotice({ failure, onRetry }: { failure: Failure; onRetry: () => void }) {
  if (failure.kind === "unreachable") {
    return (
      <div role="alert" className={box}>
        <p>Couldn&apos;t reach the server. Check your connection.</p>
        <button type="button" onClick={onRetry} className={button}>
          Retry
        </button>
      </div>
    );
  }
  if (failure.kind === "no_answer") {
    return (
      <div role="alert" className={box}>
        <p>
          The server is busy or restarting
          {failure.status === null ? " (" : ` (HTTP ${failure.status}, `}not from the search service).
        </p>
        <button type="button" onClick={onRetry} className={button}>
          Retry
        </button>
      </div>
    );
  }
  const { error } = failure;
  if (failure.status === 429 || error.code === "API_BUSY") {
    return (
      <div role="alert" className={warnBox}>
        <p className="break-words">{error.message}</p>
        <Countdown
          key={`${error.code}:${failure.retryAfter ?? ""}`}
          seconds={failure.retryAfter}
          onRetry={onRetry}
        />
      </div>
    );
  }
  return (
    <div role="alert" className={box}>
      <p className="break-words">
        <code className="font-mono">{error.code}</code>: {error.message}
      </p>
      <div className="flex flex-wrap items-center gap-3">
        <button type="button" onClick={onRetry} className={button}>
          Retry
        </button>
        {error.code === "API_INTERNAL" && <Report code={error.code} />}
      </div>
    </div>
  );
}

const code = (text: string) => <code className="font-mono break-all">{text}</code>;

/** EX-E8: the downloaded file has no abstracts (`X-Abstract-Source: unavailable`, decision-021). */
export const WITHHELD_TEXT =
  "This file has no abstracts: their source couldn't be attributed on this instance (the index's snapshot is " +
  "unavailable), so each record says its abstract was withheld. Titles, authors and venues are complete.";
const WITHHELD_COVIDENCE =
  "Covidence doesn't show that note to screeners, so they would screen these papers on titles alone. To " +
  "screen on abstracts, ask whoever runs this instance to restore the snapshot of this index.";

/** EX-E9: `n` records of the downloaded file have no abstract, removed at a rights holder's request (decision-022). */
export function removedText(n: number): string {
  const which =
    n === 1
      ? "1 paper in this file has no abstract: it was"
      : `${n.toLocaleString("en")} papers in this file have no abstract: each was`;
  return `${which} removed from this site at a rights holder's request, and each such record says so.`;
}
const REMOVED_COVIDENCE =
  "Covidence doesn't show that note to screeners, so they would screen those papers on titles alone. Each " +
  "paper's page here links to where it was published, which may still show its abstract.";

/** A saved export with abstracts removed at a rights holder's request (EX-E9). Announced by the export's live
 * region. */
export function RemovedNotice({ n }: { n: number }) {
  return (
    <div className={warnBox}>
      <p className="break-words">
        <span aria-hidden="true">⚠ </span>
        {removedText(n)} {REMOVED_COVIDENCE}
      </p>
    </div>
  );
}

/** A saved export whose abstracts were withheld (EX-E8). Announced by the export's own live region. */
export function WithheldNotice() {
  return (
    <div className={warnBox}>
      <p className="break-words">
        <span aria-hidden="true">⚠ </span>
        {WITHHELD_TEXT} {WITHHELD_COVIDENCE}
      </p>
    </div>
  );
}

/** Why an export didn't download (every case but `ok`). */
export function ExportNotice({
  result,
  onRetry,
  onSearchAgain,
}: {
  result: Exclude<ExportResult, { kind: "ok" }>;
  onRetry: () => void;
  /** From a search: re-run it to see the current results. `null` on the record page (the record doesn't move). */
  onSearchAgain: (() => void) | null;
}) {
  switch (result.kind) {
    case "index_changed":
      return (
        <div role="alert" className={box}>
          <p className="break-words">
            <span aria-hidden="true">✖ </span>The index changed after this search: the export would come from
            index {code(result.got)}, not {code(result.shown)}, so it could hold different papers. Nothing was
            downloaded.{onSearchAgain !== null && " Search again to see the current results, then export."}
          </p>
          {onSearchAgain !== null && (
            <button type="button" onClick={onSearchAgain} className={button}>
              Search again
            </button>
          )}
        </div>
      );
    case "index_unavailable":
      return (
        <div role="alert" className={box}>
          <p className="break-words">
            <span aria-hidden="true">✖ </span>Index {code(result.shown)} is no longer served here. Nothing was
            downloaded.{onSearchAgain !== null && " Search again to see the current results, then export."}
          </p>
          {onSearchAgain !== null && (
            <button type="button" onClick={onSearchAgain} className={button}>
              Search again
            </button>
          )}
        </div>
      );
    case "total_differs":
      return (
        <div role="alert" className={`${box} border-destructive`}>
          <p className="break-words">
            <span aria-hidden="true">✖ </span>The export would hold{" "}
            {result.got === null ? "an unstated number of papers" : plural(result.got, "paper")}, not the{" "}
            {result.shown.toLocaleString("en-US")} shown, from the same index. That shouldn&apos;t happen: it
            is a bug in openproceedings. Nothing was downloaded.
          </p>
          <Report code="EXPORT_TOTAL_MISMATCH" />
        </div>
      );
    default:
      return <FailureNotice failure={result} onRetry={onRetry} />;
  }
}
