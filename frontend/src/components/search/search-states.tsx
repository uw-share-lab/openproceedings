"use client";

/**
 * The states a search can end in besides results (design W6, W9, W10, W12; copy ER-1–8; spec 05 §Error
 * handling): each says what happened from the envelope's `code` and `message` (never a raw status), keeps the
 * query, and offers Retry. Nothing retries on its own. A block's heading takes focus only after a search the
 * reader started (`focus`), never on load.
 */
import { useEffect, useRef, useState } from "react";
import type { Failure } from "@/api/outcome";
import { plural } from "@/editor/diagnostics";

/** Where "Report it" goes: the issue form, with the code and the time, never the query (W10). */
export const ISSUES_URL = "https://github.com/uw-share-lab/openproceedings/issues/new";

export function reportHref(code: string, at: Date): string {
  const params = new URLSearchParams({
    title: `${code} from the search page`,
    body: `Error code: ${code}\nTime (UTC): ${at.toISOString()}\n`,
  });
  return `${ISSUES_URL}?${params.toString()}`;
}

const block = "space-y-2 rounded-md border p-3 text-sm";
const button = "min-h-8 rounded-md border px-3 hover:bg-muted";

function Heading({ text, focus }: { text: string; focus: boolean }) {
  const ref = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    if (focus) ref.current?.focus();
  }, [focus]);
  return (
    <h2 ref={ref} tabIndex={-1} className="font-semibold">
      {text}
    </h2>
  );
}

/** 429 `API_RATE_LIMITED` / 503 `API_BUSY` (W9): the server's message, a countdown, Retry enabled at 0. */
function Wait({
  message,
  seconds,
  onRetry,
  focus,
}: {
  message: string;
  seconds: number | null;
  onRetry: () => void;
  focus: boolean;
}) {
  const [left, setLeft] = useState(seconds ?? 0);
  useEffect(() => {
    if (left <= 0) return;
    const t = setTimeout(() => setLeft(left - 1), 1000);
    return () => clearTimeout(t);
  }, [left]);
  const waiting = left > 0;
  return (
    <section className={`${block} border-warn-border bg-warn-bg text-warn-fg`}>
      <Heading text="The search didn't run" focus={focus} />
      <p className="break-words">{message}</p>
      {/* announced at the start and when it reaches 0, not every second */}
      <p role="status" aria-live="polite">
        {seconds !== null && seconds > 0 && waiting ? `Retry in ${seconds} s` : "You can retry now"}
      </p>
      <div className="flex items-center gap-3">
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
    </section>
  );
}

export function FailureBlock({
  failure,
  onRetry,
  focus,
}: {
  failure: Failure;
  onRetry: () => void;
  focus: boolean;
}) {
  const retry = (
    <button type="button" onClick={onRetry} className={button}>
      Retry
    </button>
  );
  if (failure.kind === "unreachable") {
    return (
      <section role="alert" className={block}>
        <Heading text="The server didn't answer" focus={focus} />
        <p>Couldn&apos;t reach the server. Check your connection; your query is kept.</p>
        {retry}
      </section>
    );
  }
  if (failure.kind === "no_answer") {
    return (
      <section role="alert" className={block}>
        <Heading text="The server didn't answer" focus={focus} />
        <p>
          The server is busy or restarting
          {failure.status === null ? " (" : ` (HTTP ${failure.status}, `}not from the search service). Your
          query is kept.
        </p>
        {retry}
      </section>
    );
  }
  const { error, status } = failure;
  if (status === 429 || error.code === "API_BUSY") {
    return (
      <Wait
        key={`${error.code}:${failure.retryAfter ?? ""}`}
        message={error.message}
        seconds={failure.retryAfter}
        onRetry={onRetry}
        focus={focus}
      />
    );
  }
  if (error.code === "API_INDEX_NOT_LOADED") {
    return (
      <section role="alert" className={block}>
        <Heading text="Search index loading" focus={focus} />
        <p className="break-words">{error.message}</p>
        {retry}
      </section>
    );
  }
  if (error.code === "API_INTERNAL") {
    return (
      <section role="alert" className={`${block} border-destructive`}>
        <Heading text="Something went wrong on the server" focus={focus} />
        <p className="break-words">
          <code className="font-mono">API_INTERNAL</code>: {error.message}. This is a bug in openproceedings,
          not in your query.
        </p>
        <div className="flex items-center gap-3">
          {retry}
          <a
            href={reportHref(error.code, new Date())}
            rel="noopener noreferrer"
            className="underline underline-offset-4"
          >
            Report it <span aria-hidden="true">▸</span>
          </a>
        </div>
      </section>
    );
  }
  return (
    <section role="alert" className={block}>
      <Heading text="The search didn't run" focus={focus} />
      <p className="break-words">
        <code className="font-mono">{error.code}</code>: {error.message}
      </p>
      {retry}
    </section>
  );
}

/** W6: the shown results belong to another query; Restore it searches that one again. */
export function StaleNotice({
  q,
  total,
  onRestore,
}: {
  q: string;
  total: number;
  onRestore: (() => void) | null;
}) {
  return (
    <section className={`${block} border-warn-border bg-warn-bg text-warn-fg`}>
      <h2 className="font-semibold">Showing the last search that ran, not the query above</h2>
      <p className="break-words">
        <code className="font-mono break-all">{q}</code> · {plural(total, "paper")}
        {onRestore !== null && (
          <>
            {" · "}
            <button type="button" onClick={onRestore} className="underline underline-offset-4">
              Restore it
            </button>
          </>
        )}
      </p>
    </section>
  );
}

/** W12: a response for the same `(q, mode)` came from another index. */
export function IndexSwapNotice({
  from,
  to,
  onDismiss,
}: {
  from: string;
  to: string;
  onDismiss: () => void;
}) {
  return (
    <div role="status" className={`${block} flex flex-wrap items-start gap-2`}>
      <p className="min-w-0 flex-1 break-words">
        <span aria-hidden="true">ⓘ </span>The index changed while you were working: results are now from index{" "}
        <code className="font-mono break-all">{to}</code> (they were from{" "}
        <code className="font-mono break-all">{from}</code>). Counts may differ from what you noted.
      </p>
      <button type="button" onClick={onDismiss} className={button}>
        Dismiss
      </button>
    </div>
  );
}
