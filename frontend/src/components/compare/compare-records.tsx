"use client";

/**
 * "Compare with your records" (spec 05 §Components 9; design docs/design/2026-10-05-ris-comparison.md, C1–C8;
 * copy CM-1–CM-16; TASK-177). A reviewer chooses a RIS file they already hold (a Google Scholar export) and
 * sees what the searched query does to it: the papers it keeps, drops (and why), and adds, and the papers the
 * index doesn't hold. Counts first, each list on demand, each list downloadable.
 *
 * Offered only when this instance does comparisons (`GET /meta` `limits.compare`; null draws nothing). The
 * comparison is for the search shown, `(q, mode)` on the shown index: it is off while the draft or the results
 * are stale, and an answer for another query or index is never drawn as the current one. Every number is the
 * server's (`*_total`, `reason_totals`), and each download is the response's own text, saved as sent.
 *
 * The file goes to the server for this one request and is not kept there (spec 04). Its name never leaves the
 * browser.
 */
import Link from "next/link";
import { useEffect, useId, useRef, useState } from "react";
import { useMeta } from "@/api/hooks";
import type { Failure } from "@/api/outcome";
import { useApi } from "@/components/providers";
import { plural } from "@/editor/diagnostics";
import {
  doneText,
  downloadName,
  fileProblem,
  limitsLine,
  listCount,
  LIST_LABELS,
  LIST_MEANINGS,
  LISTS,
  matchedByText,
  megabytes,
  notComparedText,
  postCompare,
  reasonsLine,
  reasonText,
  type CompareRow,
  type Comparison,
  type ListName,
} from "@/lib/compare";
import { saveBlob } from "@/lib/export";
import type { Mode } from "@/lib/search-state";
import { box, button, FailureNotice, warnBox } from "../export/export-notice";
import { paperHref } from "../search/hit-item";

export interface CompareRecordsProps {
  /** The search shown: the comparison is of exactly this query on this index. */
  readonly q: string;
  readonly mode: Mode;
  readonly indexVersion: string;
  readonly total: number;
  /** Why comparing is off (a dirty draft, stale results), or `null`. */
  readonly disabledReason: string | null;
}

/** Rows drawn at once in an open list; "Show more" adds as many again (C6). */
export const ROWS_SHOWN = 100;

const n = (x: number) => x.toLocaleString("en-US");

interface Done {
  readonly key: string;
  readonly fileName: string;
  readonly comparison: Comparison;
}

type Run =
  | { readonly kind: "idle" }
  | { readonly kind: "running"; readonly fileName: string; readonly size: number }
  | { readonly kind: "failed"; readonly key: string; readonly failure: Failure };

export function CompareRecords({ q, mode, indexVersion, total, disabledReason }: CompareRecordsProps) {
  const limits = useMeta()?.limits.compare ?? null;
  const api = useApi();
  const [open, setOpen] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [run, setRun] = useState<Run>({ kind: "idle" });
  const [done, setDone] = useState<Done | null>(null);
  const [announcement, setAnnouncement] = useState("");
  const aborter = useRef<AbortController | null>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const focusResult = useRef(false);
  const panelId = useId();
  const fileId = useId();
  const noteId = useId();
  const reasonId = useId();
  const key = `${q}\u0000${mode}\u0000${indexVersion}`;

  useEffect(() => () => aborter.current?.abort(), []);
  useEffect(() => {
    if (focusResult.current && done !== null) {
      focusResult.current = false;
      heading.current?.focus();
    }
  }, [done]);

  if (limits === null) return null; // this instance doesn't offer comparisons (C8)

  const problem = file === null ? null : fileProblem(file, limits);
  const running = run.kind === "running";
  const off = disabledReason !== null || file === null || problem !== null || running;

  const start = () => {
    if (off || file === null) return;
    aborter.current?.abort();
    const controller = new AbortController();
    aborter.current = controller;
    const asked = key;
    setRun({ kind: "running", fileName: file.name, size: file.size });
    setAnnouncement(`Comparing ${file.name} with this search.`);
    void postCompare(api, { q, mode }, file, controller.signal).then(
      (outcome) => {
        if (controller.signal.aborted) return;
        if (outcome.kind === "ok") {
          focusResult.current = true;
          setDone({ key: asked, fileName: file.name, comparison: outcome.data });
          setRun({ kind: "idle" });
          setAnnouncement(doneText(outcome.data));
        } else {
          setRun({ kind: "failed", key: asked, failure: outcome });
          setAnnouncement("The comparison didn't run.");
        }
      },
      () => {
        if (controller.signal.aborted) return;
        setRun({ kind: "failed", key: asked, failure: { kind: "unreachable" } });
        setAnnouncement("The comparison didn't run.");
      },
    );
  };

  const cancel = () => {
    aborter.current?.abort();
    setRun({ kind: "idle" });
    setAnnouncement("Comparison cancelled.");
  };

  const current = done !== null && done.key === key ? done : null;
  const stale = done !== null && done.key !== key;

  return (
    <>
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        data-compare-trigger=""
        onClick={() => setOpen(!open)}
        className={button}
      >
        Compare with your records <span aria-hidden="true">{open ? "▾" : "▸"}</span>
      </button>
      <section
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
              onChange={(e) => {
                setFile(e.target.files?.[0] ?? null);
                if (run.kind === "failed") setRun({ kind: "idle" });
              }}
              className="block w-full max-w-full min-w-0 text-sm file:mr-3 file:min-h-8 file:rounded-md file:border file:border-solid file:bg-background file:px-3"
            />
          </div>
          <button
            type="button"
            aria-disabled={off ? true : undefined}
            aria-describedby={disabledReason !== null ? reasonId : undefined}
            onClick={start}
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
        <p id={noteId} className="text-xs break-words text-muted-foreground">
          The file is sent to this server for this one comparison. It is not stored, not logged and not added
          to the index. {limitsLine(limits)}
        </p>
        {disabledReason !== null && (
          <p id={reasonId} className="text-xs break-words text-muted-foreground">
            {disabledReason}
          </p>
        )}
        {problem !== null && (
          <p role="alert" className="break-words">
            {problem}
          </p>
        )}
        <p role="status" aria-live="polite" className="sr-only">
          {announcement}
        </p>
        {run.kind === "running" && (
          <p className="break-words">
            Comparing <span className="break-all">{run.fileName}</span> ({megabytes(run.size)}) with this
            search… Each paper is checked against the query, so a large file can take up to{" "}
            {n(limits.max_seconds)} seconds.
          </p>
        )}
        {run.kind === "failed" && run.key === key && (
          <div className="space-y-2">
            <p className="font-medium">The comparison didn&apos;t run. Nothing was compared.</p>
            <FailureNotice failure={run.failure} onRetry={start} />
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
}: {
  done: Done;
  shownIndex: string;
  shownTotal: number;
  q: string;
  mode: Mode;
  heading: React.RefObject<HTMLHeadingElement | null>;
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
        <p role="alert" className={box}>
          <span aria-hidden="true">✖ </span>The index changed after this search: the comparison ran on index{" "}
          <code className="font-mono break-all">{c.index_version}</code>, and the results shown are from{" "}
          <code className="font-mono break-all">{shownIndex}</code>, so its numbers are not shown. Search
          again, then compare again.
        </p>
      </div>
    );
  }
  if (c.total !== shownTotal) {
    return (
      <div className="space-y-2">
        {title}
        <p role="alert" className={`${box} border-destructive`}>
          <span aria-hidden="true">✖ </span>The comparison counted {plural(c.total, "paper")} for this search,
          not the {n(shownTotal)} shown, on the same index. That shouldn&apos;t happen: it is a bug in
          openproceedings. Its numbers are not shown.
        </p>
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
        {plural(c.total, "paper")} of this search · index{" "}
        <code className="font-mono break-all">{c.index_version}</code>
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
        comparison: {plural(c.not_compared_total, "record")} from other venues
        {c.duplicates_total > 0 &&
          `, and ${plural(c.duplicates_total, "record")} that ${c.duplicates_total === 1 ? "repeats" : "repeat"} a paper already counted`}
        .
      </p>
      <p className={`${box} break-words`}>
        <span className="font-semibold">What &ldquo;dropped&rdquo; means.</span> The index holds the paper,
        and this search doesn&apos;t return it: the query&apos;s words are not in its title or abstract as
        written, or a default filter excludes it. Google Scholar also matches full text and other word forms,
        which this search never does. A dropped paper is not judged irrelevant: check the reasons before
        leaving it out of a review.
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

function save(text: string, type: string, name: string) {
  saveBlob(new Blob([text], { type }), name);
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
  const [shown, setShown] = useState(ROWS_SHOWN);
  const listId = useId();
  const reasons = reasonsLine(name, c.reason_totals[name]);
  const label = LIST_LABELS[name];
  return (
    <section aria-label={listCount(name, total)} className="space-y-1 border-t pt-2">
      <h4 className="font-semibold">
        {label} <span className="tabular-nums">· {n(total)}</span>
      </h4>
      {reasons !== "" && <p className="break-words">{reasons}</p>}
      {total > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            aria-expanded={open}
            aria-controls={listId}
            onClick={() => setOpen(!open)}
            className={button}
          >
            {open ? "Hide" : "Show"} the {listCount(name, total)}
          </button>
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
              <li key={`${row.id ?? ""}:${row.ris_record ?? i}`} className="break-words">
                <RowLine name={name} row={row} q={q} mode={mode} />
              </li>
            ))}
          </ol>
          {rows.length > shown && (
            <button type="button" onClick={() => setShown(shown + ROWS_SHOWN)} className={button}>
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
  const why = name === "not_in_index" ? "" : reasonText(name, row.reason);
  return (
    <>
      <span className="block font-medium">
        {row.id === null ? (
          row.title
        ) : (
          <Link href={paperHref(row.id, q, mode)} className="underline underline-offset-4">
            {row.title}
          </Link>
        )}
      </span>
      <span className="block text-xs text-muted-foreground">{facts.join(" · ")}</span>
      {(why !== "" || row.detail !== "") && (
        <span className="block text-xs">
          {why}
          {why !== "" && row.detail !== "" && " — "}
          {row.detail}
        </span>
      )}
      {(row.independent === false || !row.settled || row.abstract_withheld) && (
        <span className="block text-xs">
          {[
            row.independent === false ? "import only" : "",
            row.settled ? "" : "needs a person to decide",
            row.abstract_withheld ? "abstract withheld" : "",
          ]
            .filter((x) => x !== "")
            .join(" · ")}
        </span>
      )}
    </>
  );
}

function NotCompared({ c }: { c: Comparison }) {
  const [open, setOpen] = useState(false);
  const [shown, setShown] = useState(ROWS_SHOWN);
  const listId = useId();
  const total = c.not_compared_total;
  if (total === 0) return null;
  return (
    <section aria-label={`Not compared, ${plural(total, "record")}`} className="space-y-1 border-t pt-2">
      <h4 className="font-semibold">
        {LIST_LABELS.not_compared} <span className="tabular-nums">· {n(total)}</span>
      </h4>
      <p className="break-words">
        Records of your file that are not NeurIPS, ICLR or ICML papers as far as their venue and links say.
        They are in none of the lists above.
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          aria-expanded={open}
          aria-controls={listId}
          onClick={() => setOpen(!open)}
          className={button}
        >
          {open ? "Hide" : "Show"} the {plural(total, "record")} not compared
        </button>
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
            {c.not_compared.slice(0, shown).map((row) => (
              <li key={row.ris_record} className="break-words">
                <span className="block font-medium">{row.title === "" ? "(no title)" : row.title}</span>
                <span className="block text-xs text-muted-foreground">
                  {[
                    row.venue === "" ? "no venue" : row.venue,
                    row.year === null ? "" : String(row.year),
                    `record ${n(row.ris_record)} of your file`,
                    notComparedText(row.reason),
                  ]
                    .filter((x) => x !== "")
                    .join(" · ")}
                </span>
              </li>
            ))}
          </ol>
          {c.not_compared.length > shown && (
            <button type="button" onClick={() => setShown(shown + ROWS_SHOWN)} className={button}>
              Show more ({n(Math.min(shown, c.not_compared.length))} of {n(c.not_compared.length)} shown)
            </button>
          )}
        </div>
      )}
    </section>
  );
}
