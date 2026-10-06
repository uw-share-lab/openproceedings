"use client";

/**
 * "Compare with your records" (spec 05 §Components 9; design docs/design/2026-10-05-ris-comparison.md, C1–C8;
 * copy CM-1–CM-22; TASK-177). A reviewer chooses a RIS file they already hold (a Google Scholar export) and
 * sees what the searched query does to it: the papers it keeps, drops (and why, and what to do), and adds, and
 * the papers the index doesn't hold. Counts first, each list on demand, each list downloadable, and the whole
 * in one sentence to copy.
 *
 * Offered only when this instance does comparisons (`GET /meta` `limits.compare`; null draws nothing). The
 * comparison is for the search shown, `(q, mode)` on the shown index: it is off while the draft or the results
 * are stale, and an answer for another query or index is never drawn as the current one. Every number is the
 * server's (`*_total`, `reason_totals`, `next_comparison_seconds`), and each download is the response's own
 * text, saved as sent.
 *
 * The file goes to the server for this one request and is not kept there (spec 04). Its name never leaves the
 * browser, and its sha256, for the citable sentence, is computed here (TASK-195). The comparison is kept
 * nowhere but this component, so a row's title opens its paper in a new tab (Back would otherwise lose it).
 */
import Link from "next/link";
import { useCallback, useEffect, useId, useRef, useState } from "react";
import { useMeta } from "@/api/hooks";
import type { Failure } from "@/api/outcome";
import { useApi } from "@/components/providers";
import { plural } from "@/editor/diagnostics";
import {
  detailText,
  doneText,
  downloadName,
  fileProblem,
  fileSha256,
  limitsLine,
  listCount,
  LIST_LABELS,
  LIST_MEANINGS,
  LISTS,
  matchedByText,
  megabytes,
  notComparedText,
  postCompare,
  reasonLines,
  reasonText,
  summaryText,
  undecidedText,
  type CompareRow,
  type Comparison,
  type ListName,
} from "@/lib/compare";
import { saveBlob } from "@/lib/export";
import type { Mode } from "@/lib/search-state";
import { CopyButton } from "../copy-button";
import { autoRetryText, box, button, FailureNotice, Report, warnBox } from "../export/export-notice";
import { paperHref } from "../search/hit-item";

export interface CompareRecordsProps {
  /** The search shown: the comparison is of exactly this query on this index. */
  readonly q: string;
  readonly mode: Mode;
  readonly indexVersion: string;
  readonly total: number;
  /** Why comparing is off (a dirty draft, stale results), or `null`. */
  readonly disabledReason: string | null;
  /** Re-run the search shown, to see the current index's results (an answer from another index). */
  readonly onSearchAgain?: () => void;
}

/** Rows drawn at once in an open list; "Show more" adds as many again (C6). */
export const ROWS_SHOWN = 100;
/** A wait the server answers with `API_BUSY` is retried by itself this many times in a row, then by Retry. */
export const AUTO_RETRIES = 3;
/** A refusal a retry by itself follows: `API_BUSY` with a `Retry-After`, while retries are left (`tries`). */
function retriedByItself(failure: Failure, tries: number): failure is Extract<Failure, { kind: "refused" }> {
  return (
    failure.kind === "refused" &&
    failure.status === 503 &&
    failure.error.code === "API_BUSY" &&
    failure.retryAfter !== null &&
    tries < AUTO_RETRIES
  );
}
/** Refusals of the file itself: the same file would be refused again, so the notice offers another file. */
const FILE_CODES = new Set([
  "API_BODY_TOO_LARGE",
  "API_RIS_TOO_LARGE",
  "API_RIS_INVALID",
  "API_UNSUPPORTED_MEDIA_TYPE",
]);

const n = (x: number) => x.toLocaleString("en-US");

/** " · " between facts, read as "; " (a middle dot means nothing to a screen reader). */
function Sep() {
  return (
    <>
      <span aria-hidden="true"> · </span>
      <span className="sr-only">; </span>
    </>
  );
}

function joined(parts: readonly string[]) {
  return parts.map((part, i) => (
    <span key={i}>
      {i > 0 && <Sep />}
      {part}
    </span>
  ));
}

/** The clock (ms since the epoch), read again once a second while `active`. */
function useNow(active: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    const first = setTimeout(() => setNow(Date.now()), 0);
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => {
      clearTimeout(first);
      clearInterval(t);
    };
  }, [active]);
  return now;
}

interface Done {
  readonly key: string;
  readonly fileName: string;
  /** The file's sha256, computed in this browser from the bytes sent (`fileSha256`; null where it can't be). */
  readonly sha256: string | null;
  readonly comparison: Comparison;
  /** The UTC day the answer came, for the summary sentence. */
  readonly date: string;
}

type Run =
  | { readonly kind: "idle" }
  | { readonly kind: "running"; readonly fileName: string; readonly size: number; readonly since: number }
  | {
      readonly kind: "failed";
      readonly key: string;
      readonly failure: Failure;
      /** Which request failed (one per start): each failure draws its own notice and countdown. */
      readonly attempt: number;
    };

export function CompareRecords({
  q,
  mode,
  indexVersion,
  total,
  disabledReason,
  onSearchAgain,
}: CompareRecordsProps) {
  const limits = useMeta()?.limits.compare ?? null;
  const api = useApi();
  const [open, setOpen] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [run, setRun] = useState<Run>({ kind: "idle" });
  const [done, setDone] = useState<Done | null>(null);
  const [announcement, setAnnouncement] = useState("");
  // when this network may start the next comparison (ms since the epoch) and the wait the last answer gave
  const [nextAt, setNextAt] = useState<{ readonly at: number; readonly seconds: number } | null>(null);
  const aborter = useRef<AbortController | null>(null);
  const attempts = useRef(0);
  const heading = useRef<HTMLHeadingElement>(null);
  const compareButton = useRef<HTMLButtonElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLElement>(null);
  const notice = useRef<HTMLDivElement>(null);
  const focusResult = useRef(false);
  const [autoTries, setAutoTries] = useState(0);
  const panelId = useId();
  const fileId = useId();
  const noteId = useId();
  const reasonId = useId();
  const key = `${q}\u0000${mode}\u0000${indexVersion}`;
  const now = useNow(run.kind === "running" || nextAt !== null);
  const elapsed = run.kind === "running" ? Math.max(0, Math.floor((now - run.since) / 1000)) : 0;
  // never more than the server said: `now` can be up to a tick older than the answer
  const pause =
    nextAt === null ? 0 : Math.min(nextAt.seconds, Math.max(0, Math.ceil((nextAt.at - now) / 1000)));

  useEffect(() => () => aborter.current?.abort(), []);
  useEffect(() => {
    if (focusResult.current && done !== null) {
      focusResult.current = false;
      if (open) heading.current?.focus(); // never a heading the closed panel hides
    }
  }, [done, open]);

  /** Focus to Compare when the control that had it is about to go (a Retry's notice, Cancel), never from
   * elsewhere on the page. A retry by itself moves it only off the notice it replaces, never off another of
   * the panel's controls (A11Y-R2-1). */
  const keepFocus = (byItself: boolean) => {
    const active = document.activeElement;
    const going = byItself ? notice.current : panel.current;
    if (active === null || active === document.body || going?.contains(active))
      compareButton.current?.focus();
  };

  /** `byItself`: the countdown's own retry, which uses up one of `AUTO_RETRIES` and is not announced again.
   * `keepCount`: a press of Retry on a busy notice, which neither uses up a retry nor starts the count over. */
  const start = useCallback(
    ({ byItself = false, keepCount = false }: { byItself?: boolean; keepCount?: boolean } = {}) => {
      const problem = file === null || limits === null ? null : fileProblem(file, limits);
      if (disabledReason !== null || file === null || problem !== null || run.kind === "running") return;
      if (pause > 0) return; // Compare is aria-disabled, not disabled: a click still lands (USAB-R2-2)
      const tries = byItself ? autoTries + 1 : keepCount ? autoTries : 0;
      setAutoTries(tries);
      aborter.current?.abort();
      const controller = new AbortController();
      aborter.current = controller;
      const asked = key;
      const attempt = (attempts.current += 1);
      keepFocus(byItself);
      setRun({ kind: "running", fileName: file.name, size: file.size, since: Date.now() });
      // a retry by itself was announced with its wait; "Comparing…" again would only repeat it (A11Y-R2-2)
      if (!byItself) setAnnouncement(`Comparing ${file.name} with this search.`);
      // the digest is of the File sent, read here alongside the upload (the server is never asked for it)
      void Promise.all([postCompare(api, { q, mode }, file, controller.signal), fileSha256(file)]).then(
        ([outcome, sha256]) => {
          if (controller.signal.aborted) return;
          if (outcome.kind === "ok") {
            // an answer that came by itself takes focus only from Compare or from nowhere, never from
            // wherever the reader went while it waited (A11Y-R2-1)
            const active = document.activeElement;
            focusResult.current =
              !byItself || active === null || active === document.body || active === compareButton.current;
            setAutoTries(0);
            const wait = outcome.data.next_comparison_seconds;
            setNextAt(wait > 0 ? { at: Date.now() + wait * 1000, seconds: wait } : null);
            if (wait > 0) setTimeout(() => setNextAt(null), wait * 1000);
            setDone({
              key: asked,
              fileName: file.name,
              sha256,
              comparison: outcome.data,
              date: new Date().toISOString().slice(0, 10),
            });
            setRun({ kind: "idle" });
            setAnnouncement(doneText(outcome.data));
          } else {
            setRun({ kind: "failed", key: asked, failure: outcome, attempt });
            setAnnouncement(
              retriedByItself(outcome, tries)
                ? `${autoRetryText(outcome.retryAfter ?? 0)}.`
                : "The comparison didn't run.",
            );
          }
        },
        () => {
          if (controller.signal.aborted) return;
          setRun({ kind: "failed", key: asked, failure: { kind: "unreachable" }, attempt });
          setAnnouncement("The comparison didn't run.");
        },
      );
    },
    [api, autoTries, disabledReason, file, key, limits, mode, pause, q, run.kind],
  );

  if (limits === null) return null; // this instance doesn't offer comparisons (C8)

  const problem = file === null ? null : fileProblem(file, limits);
  const running = run.kind === "running";
  const waiting = pause > 0;
  // why Compare is off, said beside it (WCAG 4.1.2: an aria-disabled button says why)
  const why =
    disabledReason ??
    (file === null
      ? "Choose a RIS file first."
      : problem !== null
        ? "Choose a smaller file."
        : waiting
          ? `Next comparison in ${n(pause)} s: this instance pauses between one network's comparisons.`
          : null);
  const off = why !== null || running;
  const refusedFile =
    run.kind === "failed" &&
    run.key === key &&
    run.failure.kind === "refused" &&
    (FILE_CODES.has(run.failure.error.code) || run.failure.error.code === "API_COMPARE_TOO_COSTLY");
  const busy =
    run.kind === "failed" &&
    run.failure.kind === "refused" &&
    run.failure.status === 503 &&
    run.failure.error.code === "API_BUSY";
  // the wait ends in a retry by itself: not "didn't run" while it is still to come (A11Y-R2-2)
  const retrying = run.kind === "failed" && retriedByItself(run.failure, autoTries);

  const cancel = () => {
    aborter.current?.abort();
    keepFocus(false); // Cancel is gone once the run is
    setRun({ kind: "idle" });
    setAnnouncement("Comparison cancelled.");
  };

  const current = done !== null && done.key === key ? done : null;
  const stale = done !== null && done.key !== key;

  return (
    <>
      <button
        ref={trigger}
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        data-compare-trigger=""
        onClick={() => setOpen(!open)}
        className={button}
      >
        Compare with your records <span aria-hidden="true">{open ? "▾" : "▸"}</span>
      </button>
      {/* outside the panel, so an answer that lands while it is closed is still announced */}
      <p role="status" aria-live="polite" className="sr-only">
        {announcement}
      </p>
      <section
        ref={panel}
        id={panelId}
        hidden={!open}
        aria-label="Compare with your records"
        className="w-full basis-full space-y-3 rounded-md border p-3 text-sm"
      >
        <h2 className="font-semibold">Compare with your records</h2>
        <p className="break-words">
          Choose a RIS file of papers you already hold, for example a Google Scholar export. You will see
          which of them this search keeps, which it drops and why, and which papers it adds.
        </p>
        <div className="flex flex-wrap items-end gap-3">
          <div className="min-w-0 space-y-1">
            <label htmlFor={fileId} className="block font-medium">
              RIS file
            </label>
            <input
              id={fileId}
              type="file"
              accept=".ris,application/x-research-info-systems,text/plain"
              aria-describedby={noteId}
              aria-invalid={problem !== null || refusedFile ? true : undefined}
              onChange={(e) => {
                setFile(e.target.files?.[0] ?? null);
                if (run.kind === "failed") setRun({ kind: "idle" });
              }}
              className="block w-full max-w-full min-w-0 text-sm file:mr-3 file:min-h-8 file:rounded-md file:border file:border-solid file:bg-background file:px-3"
            />
          </div>
          <button
            ref={compareButton}
            type="button"
            aria-disabled={off ? true : undefined}
            aria-describedby={why !== null ? reasonId : undefined}
            onClick={() => start()}
            className={`${button} ${off ? "opacity-60" : ""}`}
          >
            Compare
          </button>
          {running && (
            <button type="button" onClick={cancel} className={button}>
              Cancel
            </button>
          )}
        </div>
        {why !== null && (
          <p id={reasonId} className="text-xs break-words text-muted-foreground">
            {why}
          </p>
        )}
        <p id={noteId} className="text-xs break-words text-muted-foreground">
          The file is sent to this instance for this one comparison. It is not stored, not logged and not
          added to the index. {limitsLine(limits)}
        </p>
        {problem !== null && (
          <p role="alert" className="break-words">
            {problem}
          </p>
        )}
        {run.kind === "running" && (
          <p className="break-words">
            Comparing <span className="break-all">{run.fileName}</span> ({megabytes(run.size)}) with this
            search… Each paper is checked against the query, so a large file can take up to{" "}
            {n(limits.max_seconds)} s.{" "}
            <span aria-hidden="true" className="tabular-nums">
              {n(elapsed)} s so far.
            </span>
          </p>
        )}
        {run.kind === "failed" && run.key === key && (
          <div ref={notice} className="space-y-2">
            {current === null ? (
              <p className="font-medium">
                {retrying
                  ? "The comparison hasn't run yet: this instance is busy; this page will try again by itself."
                  : "The comparison didn't run. Nothing was compared."}
              </p>
            ) : (
              <p className="font-medium break-words">
                {retrying
                  ? "The new comparison hasn't run yet: this instance is busy; this page will try again by itself."
                  : "The new comparison didn't run."}{" "}
                The results below are from the earlier comparison with{" "}
                <span className="break-all">{current.fileName}</span>.
              </p>
            )}
            <FailureNotice
              // a new notice per failed request: two busy answers in a row can land without the "running"
              // state between them ever being drawn, and the one countdown kept would not retry again (it
              // had retried; a test failed 1 run in 6 on it)
              key={run.attempt}
              failure={run.failure}
              onRetry={refusedFile ? null : (byItself) => start({ byItself, keepCount: busy })}
              autoRetry={retrying}
            />
            {refusedFile && (
              <p className="break-words">
                {FILE_CODES.has(run.failure.kind === "refused" ? run.failure.error.code : "")
                  ? "Choose another file, then Compare."
                  : "Compare a smaller file, or narrow the query and search again."}
              </p>
            )}
          </div>
        )}
        {stale && run.kind !== "running" && (
          <p className={warnBox}>
            <span aria-hidden="true">⚠ </span>The search changed since the last comparison, so its numbers are
            no longer shown. Compare again to see what the current query keeps, drops and adds.
          </p>
        )}
        {current !== null && (
          <Result
            done={current}
            shownIndex={indexVersion}
            shownTotal={total}
            q={q}
            mode={mode}
            heading={heading}
            onSearchAgain={onSearchAgain}
          />
        )}
      </section>
    </>
  );
}

function Result({
  done,
  shownIndex,
  shownTotal,
  q,
  mode,
  heading,
  onSearchAgain,
}: {
  done: Done;
  shownIndex: string;
  shownTotal: number;
  q: string;
  mode: Mode;
  heading: React.RefObject<HTMLHeadingElement | null>;
  onSearchAgain: (() => void) | undefined;
}) {
  const c = done.comparison;
  const title = (
    <h3 ref={heading} tabIndex={-1} className="font-semibold break-words">
      Comparison with <span className="break-all">{done.fileName}</span>
    </h3>
  );
  if (c.index_version !== shownIndex) {
    return (
      <div className="space-y-2">
        {title}
        <div role="alert" className={box}>
          <p className="break-words">
            <span aria-hidden="true">✖ </span>The index changed after this search: the comparison ran on index{" "}
            <code className="font-mono break-all">{c.index_version}</code>, and the results shown are from{" "}
            <code className="font-mono break-all">{shownIndex}</code>, so its numbers are not shown. Search
            again, then compare again.
          </p>
          {onSearchAgain !== undefined && (
            <button type="button" onClick={onSearchAgain} className={button}>
              Search again
            </button>
          )}
        </div>
      </div>
    );
  }
  if (c.total !== shownTotal) {
    return (
      <div className="space-y-2">
        {title}
        <div role="alert" className={`${box} border-destructive`}>
          <p className="break-words">
            <span aria-hidden="true">✖ </span>The comparison counted {plural(c.total, "paper")} for this
            search, not the {n(shownTotal)} shown, on the same index. That shouldn&apos;t happen: it is a bug
            in openproceedings. Its numbers are not shown.
          </p>
          <Report code="COMPARE_TOTAL_MISMATCH" />
        </div>
      </div>
    );
  }
  const totals: Record<ListName, number> = {
    kept: c.kept_total,
    dropped: c.dropped_total,
    not_in_index: c.not_in_index_total,
    added: c.added_total,
  };
  return (
    <div className="space-y-3">
      {title}
      <p className="break-words">
        {plural(c.records_total, "record")} read, {plural(c.papers_total, "paper")} compared with the{" "}
        {plural(c.total, "paper")} of this search
        <Sep />
        index <code className="font-mono break-all">{c.index_version}</code>
      </p>
      <table className="w-full border-collapse text-left">
        <caption className="sr-only">What this search does to the papers in your file</caption>
        <thead>
          <tr className="border-b">
            <th scope="col" className="py-1 pr-3 font-medium">
              Papers
            </th>
            <th scope="col" className="py-1 text-right font-medium">
              Count
            </th>
          </tr>
        </thead>
        <tbody>
          {LISTS.map((name) => (
            <tr key={name} className="border-b align-top">
              <th scope="row" className="py-1 pr-3 font-normal">
                <span className="font-semibold">{LIST_LABELS[name]}</span>
                <span className="block text-xs break-words text-muted-foreground">{LIST_MEANINGS[name]}</span>
              </th>
              <td className="py-1 text-right tabular-nums">{n(totals[name])}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="break-words">
        Kept and added papers together are the {plural(c.total, "paper")} of this search. Left out of the
        comparison: {plural(c.not_compared_total, "record")} whose venue is not recognised or is outside the
        indexed venues and years
        {c.duplicates_total > 0 &&
          `, and ${plural(c.duplicates_total, "record")} that ${c.duplicates_total === 1 ? "repeats" : "repeat"} a paper already counted`}
        .
      </p>
      <Citable done={done} />
      <p className={`${box} break-words`}>
        <span className="font-semibold">What &ldquo;dropped&rdquo; means.</span> The index holds the paper,
        and this search doesn&apos;t return it: the query&apos;s words are not in its title or abstract as
        written (other word forms only where the query asks for them, with $ or *), or a default filter
        excludes it. Google Scholar also matches full text and other word forms. A dropped paper is not judged
        irrelevant: check the reasons before leaving it out of a review.
      </p>
      {c.kept_ris_only_total + c.dropped_ris_only_total > 0 && (
        <p className={`${warnBox} break-words`}>
          <span aria-hidden="true">⚠ </span>
          {n(c.kept_ris_only_total)} of the {n(c.kept_total)} kept and {n(c.dropped_ris_only_total)} of the{" "}
          {n(c.dropped_total)} dropped papers are in this index only because a RIS file was imported into it
          (marked &ldquo;import only&rdquo;). Matching such a paper shows that the import holds it, not that
          the index covers it from its own sources.
        </p>
      )}
      {LISTS.map((name) => (
        <ListSection key={name} name={name} c={c} q={q} mode={mode} />
      ))}
      <NotCompared c={c} />
    </div>
  );
}

/**
 * The rows drawn so far, and "Show more", which hands focus to the first row it drew: the last Show more
 * removes itself, and focus must not fall to the page (WCAG 2.4.3).
 */
function useRowsShown() {
  const [shown, setShown] = useState(ROWS_SHOWN);
  const drawn = useRef<HTMLLIElement>(null);
  const moved = useRef(false);
  useEffect(() => {
    if (moved.current) {
      moved.current = false;
      drawn.current?.focus();
    }
  }, [shown]);
  return {
    shown,
    more: () => {
      moved.current = true;
      setShown(shown + ROWS_SHOWN);
    },
    /** The ref and tab stop of row `i`: the first one the last Show more drew takes focus. */
    row: (i: number) =>
      shown > ROWS_SHOWN && i === shown - ROWS_SHOWN ? { ref: drawn, tabIndex: -1 } : { tabIndex: undefined },
  };
}

function save(text: string, type: string, name: string) {
  saveBlob(new Blob([text], { type }), name);
}

/** A list's heading: its name and count ("Dropped · 1,756", read "Dropped: 1,756"). */
function CountHeading({ label, count }: { label: string; count: number }) {
  return (
    <h4 className="font-semibold">
      {label}
      <span aria-hidden="true"> · </span>
      <span className="sr-only">: </span>
      <span className="tabular-nums">{n(count)}</span>
    </h4>
  );
}

/** A list's Show/Hide: one name whatever its state, which `aria-expanded` and the arrow carry (A11Y-N10). */
function ListToggle({
  open,
  controls,
  name,
  onToggle,
}: {
  open: boolean;
  controls: string;
  name: string;
  onToggle: () => void;
}) {
  return (
    <button type="button" aria-expanded={open} aria-controls={controls} onClick={onToggle} className={button}>
      List the {name} <span aria-hidden="true">{open ? "▾" : "▸"}</span>
    </button>
  );
}

/**
 * The comparison as one sentence to cite (copy CM-21; TASK-195, decision-043): in a read-only text box sized to
 * its text, which the keyboard reaches, so it can be selected where the clipboard can't be written (WCAG 2.1.1);
 * the Copy button then focuses and selects it. A search record never notes a comparison; this sentence, with
 * the file's own sha256, is what a methods section cites.
 */
function Citable({ done }: { done: Done }) {
  const captionId = useId();
  const box = useRef<HTMLTextAreaElement>(null);
  const text = summaryText(done.comparison, { name: done.fileName, sha256: done.sha256 }, done.date);
  return (
    <figure className="space-y-1">
      <figcaption id={captionId} className="text-xs text-muted-foreground">
        This comparison in one sentence, to cite beside your file (nothing of it is kept here, and a saved
        search record doesn&apos;t note it):
      </figcaption>
      <textarea
        ref={box}
        readOnly
        value={text}
        aria-labelledby={captionId}
        // `field-sizing: content` fits the box to the sentence where supported; elsewhere (Firefox) rows are
        // counted at a 320px width's 32 characters, up to 12, past which the box scrolls
        rows={Math.min(Math.ceil(text.length / 32), 12)}
        className="block field-sizing-content w-full resize-none rounded-md border bg-muted/40 p-2 text-sm break-words"
      />
      <CopyButton
        text={text}
        label="Copy this comparison as one sentence"
        onFailed={() => {
          box.current?.focus();
          box.current?.select();
        }}
      />
    </figure>
  );
}

function ListSection({ name, c, q, mode }: { name: ListName; c: Comparison; q: string; mode: Mode }) {
  const rows = c[name];
  const totals = {
    kept: c.kept_total,
    dropped: c.dropped_total,
    not_in_index: c.not_in_index_total,
    added: c.added_total,
  };
  const total = totals[name];
  const [open, setOpen] = useState(false);
  const { shown, more, row: rowProps } = useRowsShown();
  const listId = useId();
  const reasons = reasonLines(name, c.reason_totals[name], mode);
  return (
    <section aria-label={listCount(name, total)} className="space-y-1 border-t pt-2">
      <CountHeading label={LIST_LABELS[name]} count={total} />
      {reasons.map((line) => (
        <p key={line} className="break-words">
          {line}
        </p>
      ))}
      {total > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          <ListToggle
            open={open}
            controls={listId}
            name={listCount(name, total)}
            onToggle={() => setOpen(!open)}
          />
          {name === "added" && (
            <button
              type="button"
              aria-label={`Download RIS of the ${listCount(name, total)}`}
              onClick={() =>
                save(c.added_ris, "application/x-research-info-systems", downloadName(c, name, "ris"))
              }
              className={button}
            >
              Download RIS
            </button>
          )}
          <button
            type="button"
            aria-label={`Download CSV of the ${listCount(name, total)}`}
            onClick={() => save(c.csv[name], "text/csv;charset=utf-8", downloadName(c, name, "csv"))}
            className={button}
          >
            Download CSV
          </button>
        </div>
      )}
      {open && (
        <div id={listId} className="space-y-2">
          <ol className="space-y-2">
            {rows.slice(0, shown).map((row, i) => (
              <li key={`${row.id ?? ""}:${row.ris_record ?? i}`} {...rowProps(i)} className="break-words">
                <RowLine name={name} row={row} q={q} mode={mode} />
              </li>
            ))}
          </ol>
          {rows.length > shown && (
            <button type="button" onClick={more} className={button}>
              Show more ({n(Math.min(shown, rows.length))} of {n(rows.length)} shown)
            </button>
          )}
        </div>
      )}
    </section>
  );
}

function RowLine({ name, row, q, mode }: { name: ListName; row: CompareRow; q: string; mode: Mode }) {
  const where = [row.venue, row.year === null ? null : String(row.year)].filter(Boolean).join(" ");
  const facts = [
    where,
    row.ris_record === null ? "" : `record ${n(row.ris_record)} of your file`,
    row.copies > 1 ? `${n(row.copies)} times in your file` : "",
    name === "kept" || name === "not_in_index" ? matchedByText(row.matched_by) : "",
  ].filter((x) => x !== "");
  // a missing paper's reason is its list's name, and its match line already says why: neither is repeated
  const why = name === "not_in_index" ? "" : reasonText(name, row.reason);
  const detail = detailText(name, row);
  const flags = [
    row.independent === false ? "import only" : "",
    undecidedText(name, row),
    row.abstract_withheld ? "abstract withheld" : "",
  ].filter((x) => x !== "");
  return (
    <>
      <span className="block font-medium">
        {row.id === null ? (
          row.title
        ) : (
          // a new tab: the comparison lives on this page only, and Back would lose it and its file (USAB-M1)
          <Link
            href={paperHref(row.id, q, mode)}
            target="_blank"
            rel="noopener noreferrer"
            className="underline underline-offset-4"
          >
            {row.title}
            <span aria-hidden="true"> ↗</span>
            <span className="sr-only"> (opens in a new tab)</span>
          </Link>
        )}
      </span>
      <span className="block text-xs text-muted-foreground">{joined(facts)}</span>
      {(why !== "" || detail !== "") && (
        <span className="block text-xs">
          {why}
          {why !== "" && detail !== "" && " — "}
          {detail}
        </span>
      )}
      {flags.length > 0 && <span className="block text-xs">{joined(flags)}</span>}
    </>
  );
}

function NotCompared({ c }: { c: Comparison }) {
  const [open, setOpen] = useState(false);
  const { shown, more, row: rowProps } = useRowsShown();
  const listId = useId();
  const total = c.not_compared_total;
  if (total === 0) return null;
  return (
    <section aria-label={`Not compared, ${plural(total, "record")}`} className="space-y-1 border-t pt-2">
      <CountHeading label={LIST_LABELS.not_compared} count={total} />
      <p className="break-words">
        Records of your file whose venue is not recognised as NeurIPS, ICLR or ICML (and no link or DOI names
        an indexed paper), or which are outside the indexed venues and years. They are in none of the lists
        above.
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <ListToggle
          open={open}
          controls={listId}
          name={`${plural(total, "record")} not compared`}
          onToggle={() => setOpen(!open)}
        />
        <button
          type="button"
          aria-label={`Download CSV of the ${plural(total, "record")} not compared`}
          onClick={() =>
            save(c.csv.not_compared, "text/csv;charset=utf-8", downloadName(c, "not_compared", "csv"))
          }
          className={button}
        >
          Download CSV
        </button>
      </div>
      {open && (
        <div id={listId} className="space-y-2">
          <ol className="space-y-2">
            {c.not_compared.slice(0, shown).map((row, i) => (
              <li key={row.ris_record} {...rowProps(i)} className="break-words">
                <span className="block font-medium">{row.title === "" ? "(no title)" : row.title}</span>
                <span className="block text-xs text-muted-foreground">
                  {joined(
                    [
                      row.venue === "" ? "no venue" : row.venue,
                      row.year === null ? "" : String(row.year),
                      `record ${n(row.ris_record)} of your file`,
                      notComparedText(row.reason),
                    ].filter((x) => x !== ""),
                  )}
                </span>
              </li>
            ))}
          </ol>
          {c.not_compared.length > shown && (
            <button type="button" onClick={more} className={button}>
              Show more ({n(Math.min(shown, c.not_compared.length))} of {n(c.not_compared.length)} shown)
            </button>
          )}
        </div>
      )}
    </section>
  );
}
