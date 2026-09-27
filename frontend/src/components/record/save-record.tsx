"use client";

/**
 * "Save search record" (spec 05 §Components 8; design S1–S3; copy SV-1–SV-8). A confirm dialog says the record
 * is public and permanent and shows exactly what will be saved: the **searched** `(q, mode)`, never the draft.
 * The save is pinned to the shown index (`POST /records {q, mode, index_version}`, TASK-091): a hot swap is 409
 * `API_INDEX_VERSION_UNAVAILABLE` with nothing saved. After the 201 the panel reads the record back
 * (`GET /records/{id}`, one replay) for its status and methods text; if that read is refused the record is
 * still saved and the panel says where the methods text is. `API_RECORDS_STORE_FULL` turns saving off for the
 * session (searching, exports and existing records keep working).
 */
import Link from "next/link";
import { useEffect, useId, useRef, useState, useSyncExternalStore, type KeyboardEvent } from "react";
import { outcomeOf, type Failure } from "@/api/outcome";
import { useApi } from "@/components/providers";
import { plural } from "@/editor/diagnostics";
import type { RecordResponse } from "@/lib/methods-text";
import { savedLine } from "@/lib/replay-status";
import type { Mode } from "@/lib/search-state";
import { Coded } from "../coded";
import { CopyButton } from "../copy-button";
import { box, button, FailureNotice, warnBox } from "../export/export-notice";
import { modeWords } from "../paper/paper-view";
import { MethodsBlock } from "./methods-block";
import { getRecord, type RecordOutcome } from "./use-record";
import { useOrigin } from "./record-view";

export const STORE_FULL_KEY = "openproceedings:records-store-full";
export const STORE_FULL_MESSAGE =
  "Saving search records is paused on this instance: its record store is full. Your search, exports and " +
  "existing records still work.";

function storeFullBefore(): boolean {
  try {
    return window.sessionStorage.getItem(STORE_FULL_KEY) === "1";
  } catch {
    return false;
  }
}

const noSubscription = () => () => {};

function rememberStoreFull(): void {
  try {
    window.sessionStorage.setItem(STORE_FULL_KEY, "1");
  } catch {
    // private mode: saving stays off for this page only
  }
}

export interface SaveRecordProps {
  readonly q: string;
  readonly mode: Mode;
  readonly indexVersion: string;
  readonly total: number;
  /** Why saving is off (a dirty draft, stale results), or `null`. */
  readonly disabledReason: string | null;
}

type Created = { record_id: string; page: string; index_version: string };

type Phase =
  | { readonly kind: "idle" }
  | { readonly kind: "confirm" }
  | { readonly kind: "saving" }
  | { readonly kind: "saved"; readonly created: Created; readonly record: RecordOutcome | null }
  | { readonly kind: "index_moved" }
  | { readonly kind: "refused"; readonly failure: Failure };

export function SaveRecord({ q, mode, indexVersion, total, disabledReason }: SaveRecordProps) {
  const api = useApi();
  const [phase, setPhase] = useState<Phase>({ kind: "idle" });
  // full earlier this session (sessionStorage), or on this page's last save
  const fullBefore = useSyncExternalStore(noSubscription, storeFullBefore, () => false);
  const [fullNow, setStoreFull] = useState(false);
  const storeFull = fullBefore || fullNow;
  const trigger = useRef<HTMLButtonElement>(null);
  const reasonId = useId();
  const reason = storeFull ? STORE_FULL_MESSAGE : disabledReason;

  const save = async () => {
    setPhase({ kind: "saving" });
    const posted = await outcomeOf(() =>
      api.POST("/api/v1/records", { body: { q, mode, index_version: indexVersion } }),
    );
    if (posted.kind !== "ok") {
      if (posted.kind === "refused" && posted.error.code === "API_RECORDS_STORE_FULL") {
        rememberStoreFull();
        setStoreFull(true);
      }
      if (posted.kind === "refused" && posted.error.code === "API_INDEX_VERSION_UNAVAILABLE") {
        setPhase({ kind: "index_moved" });
        return;
      }
      setPhase({ kind: "refused", failure: posted });
      return;
    }
    const created = posted.data;
    setPhase({ kind: "saved", created, record: null });
    const record = await getRecord(api, created.record_id, true);
    setPhase({ kind: "saved", created, record });
  };

  return (
    <div className="inline-flex flex-wrap items-center gap-2">
      <button
        ref={trigger}
        type="button"
        aria-disabled={reason !== null || phase.kind === "saving" ? true : undefined}
        aria-describedby={reason !== null ? reasonId : undefined}
        onClick={() => {
          if (reason === null && phase.kind !== "saving") setPhase({ kind: "confirm" });
        }}
        className={`${button} ${reason !== null ? "opacity-60" : ""}`}
      >
        {phase.kind === "saving" ? "Saving…" : "Save search record"}
      </button>
      {reason !== null && (
        <span id={reasonId} className="w-full text-xs text-muted-foreground">
          {reason}
        </span>
      )}
      {phase.kind === "confirm" && (
        <Confirm
          q={q}
          mode={mode}
          indexVersion={indexVersion}
          total={total}
          onCancel={() => {
            setPhase({ kind: "idle" });
            trigger.current?.focus();
          }}
          onSave={() => void save()}
        />
      )}
      {phase.kind === "saved" && (
        <Saved created={phase.created} record={phase.record} shownIndex={indexVersion} shownTotal={total} />
      )}
      {phase.kind === "index_moved" && (
        <div role="alert" className={`${box} w-full`}>
          <p className="break-words">
            <span aria-hidden="true">✖ </span>Index{" "}
            <code className="font-mono break-all">{indexVersion}</code> is no longer served here, so the
            search wasn&apos;t saved: it would have been frozen on another index than the one whose counts you
            saw. Search again to see the current results, then save.
          </p>
        </div>
      )}
      {phase.kind === "refused" && (
        <div className="w-full">
          {phase.failure.kind === "refused" && phase.failure.error.code === "API_RECORDS_STORE_FULL" ? (
            <p role="alert" className={box}>
              {STORE_FULL_MESSAGE}
            </p>
          ) : phase.failure.kind === "refused" && phase.failure.status === 422 ? (
            <div role="alert" className={box}>
              <p>The search couldn&apos;t be saved: it no longer runs on this index.</p>
              <ul className="list-disc pl-5">
                {(
                  phase.failure.error.diagnostics ?? [
                    { code: phase.failure.error.code, message: phase.failure.error.message },
                  ]
                ).map((d, i) => (
                  <li key={i} className="break-words">
                    <Coded text={d.message} />
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <FailureNotice failure={phase.failure} onRetry={() => void save()} />
          )}
        </div>
      )}
    </div>
  );
}

/** S1: a modal dialog; focus starts on Save and stays inside; Esc cancels. */
function Confirm({
  q,
  mode,
  indexVersion,
  total,
  onCancel,
  onSave,
}: {
  q: string;
  mode: Mode;
  indexVersion: string;
  total: number;
  onCancel: () => void;
  onSave: () => void;
}) {
  const titleId = useId();
  const saveRef = useRef<HTMLButtonElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);
  useEffect(() => saveRef.current?.focus(), []);
  const onKey = (e: KeyboardEvent) => {
    if (e.key === "Escape") {
      e.preventDefault();
      onCancel();
    } else if (e.key === "Tab") {
      // two controls: Tab and Shift+Tab move between them and never leave the dialog
      e.preventDefault();
      (document.activeElement === saveRef.current ? cancelRef : saveRef).current?.focus();
    }
  };
  return (
    <div className="fixed inset-0 z-30 flex items-center justify-center bg-black/40 p-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onKeyDown={onKey}
        className="w-full max-w-lg space-y-3 rounded-md border bg-background p-4 text-sm shadow-lg"
      >
        <h2 id={titleId} className="text-base font-semibold">
          Save this search as a permanent record?
        </h2>
        <p className="break-words">
          <code className="font-mono break-all">{q}</code> · {modeWords(mode)}
        </p>
        <p>
          {plural(total, "paper")} · index <code className="font-mono break-all">{indexVersion}</code>
        </p>
        <p>
          Anyone with the link can see the record, including the query text. It can&apos;t be edited or
          deleted.
        </p>
        <div className="flex justify-end gap-2">
          <button ref={cancelRef} type="button" onClick={onCancel} className={button}>
            Cancel
          </button>
          <button
            ref={saveRef}
            type="button"
            onClick={onSave}
            className="min-h-8 rounded-md border bg-primary px-3 text-primary-foreground hover:opacity-90"
          >
            Save
          </button>
        </div>
      </div>
    </div>
  );
}

/** S2: the link, the status right after saving, and the methods text (or the caution; or where to find it). */
function Saved({
  created,
  record,
  shownIndex,
  shownTotal,
}: {
  created: Created;
  record: RecordOutcome | null;
  shownIndex: string;
  shownTotal: number;
}) {
  const origin = useOrigin();
  const heading = useRef<HTMLHeadingElement>(null);
  const statusId = useId();
  useEffect(() => heading.current?.focus(), []);
  const url = `${origin}${created.page}`;
  const data: RecordResponse | null = record?.kind === "ok" ? record.data : null;
  const replay = data?.replay ?? null;
  const today = new Date().toISOString().slice(0, 10);
  const line = data !== null && replay !== null ? savedLine(data.record, replay, today) : null;
  const mismatch = replay?.status === "mismatch";
  return (
    <section aria-labelledby={`${statusId}-h`} className={`${box} w-full`}>
      <h2
        id={`${statusId}-h`}
        ref={heading}
        tabIndex={-1}
        aria-describedby={statusId}
        className="font-semibold"
      >
        <span aria-hidden="true">✔ </span>Saved as search record{" "}
        <span className="font-mono">{created.record_id}</span>
      </h2>
      {created.index_version !== shownIndex && (
        <p role="alert" className={`${warnBox} break-words`}>
          <span aria-hidden="true">⚠ </span>Saved on index{" "}
          <code className="font-mono break-all">{created.index_version}</code>, not{" "}
          <code className="font-mono break-all">{shownIndex}</code>: the index changed after your search. The
          record cites {data === null ? "its own number of papers" : plural(data.record.total, "paper")} from
          index <code className="font-mono break-all">{created.index_version}</code>, which may differ from
          the {shownTotal.toLocaleString("en-US")} shown. Search again to see them, and check the record
          before citing it.
        </p>
      )}
      <p className="flex flex-wrap items-center gap-2 break-all">
        <a href={url} className="underline underline-offset-4">
          {url}
        </a>
        <CopyButton text={url} label="Copy link" />
      </p>
      <p id={statusId} className="break-words">
        {record === null ? (
          <span role="status">Checking the record…</span>
        ) : data === null ? (
          "The record is saved. Its methods text is on the record page."
        ) : mismatch ? (
          <strong>Do not cite — replay mismatch. The record page says why.</strong>
        ) : (
          <Coded text={line ?? ""} />
        )}{" "}
        <Link href={created.page} className="underline underline-offset-4">
          Open record page <span aria-hidden="true">▸</span>
        </Link>
      </p>
      {data !== null && !mismatch && <MethodsBlock record={data.record} url={url} />}
    </section>
  );
}
