"use client";

/**
 * "Save search record" (spec 05 §Components 8; design S1–S3; copy SV-1–SV-9). A confirm dialog says the record
 * is public and permanent and shows exactly what will be saved: the **searched** `(q, mode)`, never the draft.
 * The save is pinned to the shown index (`POST /records {q, mode, index_version}`, TASK-091): a hot swap is 409
 * `API_INDEX_VERSION_UNAVAILABLE` with nothing saved. After the 201 the panel reads the record back
 * (`GET /records/{id}`, one replay) for its status and methods text; if that read is refused the record is
 * still saved and the panel says where the methods text is. `API_RECORDS_STORE_FULL` turns saving off for the
 * session (searching, exports and existing records keep working).
 */
import Link from "next/link";
import {
  createContext,
  useContext,
  useEffect,
  useId,
  useRef,
  useState,
  useSyncExternalStore,
  type KeyboardEvent,
  type ReactNode,
} from "react";
import { outcomeOf, type Failure } from "@/api/outcome";
import type { Schemas } from "@/api/client";
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
export const SAVE_OUTCOME_UNKNOWN_MESSAGE =
  "The save outcome is unknown. The server may already have created this permanent public-by-link record. " +
  "To avoid creating a duplicate, this page won't send the same save again.";
export const SAVE_RESPONSE_DEADLINE_MS = 30_000;

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

type Created = Schemas["RecordCreated"];
type SaveRequest = {
  readonly q: string;
  readonly mode: Mode;
  readonly indexVersion: string;
  readonly total: number;
};

type Phase =
  | { readonly kind: "idle" }
  | { readonly kind: "confirm"; readonly request: SaveRequest }
  | { readonly kind: "saving"; readonly dialogOpen: boolean; readonly request: SaveRequest }
  | {
      readonly kind: "saved";
      readonly attempt: number;
      readonly created: Created;
      readonly record: RecordOutcome | null;
      readonly request: SaveRequest;
    }
  | { readonly kind: "index_moved"; readonly request: SaveRequest }
  | { readonly kind: "unknown"; readonly failure: Failure; readonly request: SaveRequest }
  | { readonly kind: "refused"; readonly failure: Failure; readonly request: SaveRequest };

function requestKey(request: SaveRequest): string {
  return JSON.stringify([request.q, request.mode, request.indexVersion]);
}

function isCreated(value: unknown): value is Created {
  if (value === null || typeof value !== "object") return false;
  const candidate = value as Partial<Created>;
  return (
    typeof candidate.record_id === "string" &&
    /^[A-Za-z0-9_-]{12}$/.test(candidate.record_id) &&
    candidate.page === `/record/${candidate.record_id}` &&
    typeof candidate.index_version === "string" &&
    /^[0-9a-f][0-9a-f-]{0,63}$/.test(candidate.index_version) &&
    typeof candidate.tokenizer_version === "string" &&
    typeof candidate.query_version === "string"
  );
}

/** These refusals happen before a record is committed; transport failures and 5xx internals are ambiguous. */
function safeToRetry(failure: Failure): boolean {
  return (
    failure.kind === "refused" &&
    (failure.status === 429 ||
      failure.error.code === "API_BUSY" ||
      failure.error.code === "API_INDEX_NOT_LOADED")
  );
}

interface SaveController {
  readonly phase: Phase;
  readonly unknownRequests: ReadonlyMap<string, Failure>;
  readonly savedRequests: ReadonlyMap<string, Extract<Phase, { kind: "saved" }>>;
  readonly fullNow: boolean;
  confirm(request: SaveRequest): void;
  dismiss(): void;
  save(request: SaveRequest): Promise<void>;
  loadRecord(saved: Extract<Phase, { kind: "saved" }>): Promise<void>;
}

const SaveRecordContext = createContext<SaveController | null>(null);

/** Page-scoped owner: survives conditional Results/SaveRecord remounts and reconciles late POST answers. */
export function SaveRecordProvider({
  children,
  responseDeadlineMs = SAVE_RESPONSE_DEADLINE_MS,
}: {
  children: ReactNode;
  responseDeadlineMs?: number;
}) {
  const api = useApi();
  const [phase, setPhase] = useState<Phase>({ kind: "idle" });
  const [fullNow, setStoreFull] = useState(false);
  const activeAttempt = useRef(0);
  const latestByRequest = useRef(new Map<string, number>());
  const mounted = useRef(true);
  const unknownRef = useRef<ReadonlyMap<string, Failure>>(new Map());
  const [unknownRequests, setUnknownRequests] = useState<ReadonlyMap<string, Failure>>(() => new Map());
  const savedRef = useRef<ReadonlyMap<string, Extract<Phase, { kind: "saved" }>>>(new Map());
  const [savedRequests, setSavedRequests] = useState<ReadonlyMap<string, Extract<Phase, { kind: "saved" }>>>(
    () => new Map(),
  );
  const loadingReplay = useRef(new Set<number>());

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const rememberUnknown = (request: SaveRequest, failure: Failure) => {
    const next = new Map(unknownRef.current).set(requestKey(request), failure);
    unknownRef.current = next;
    setUnknownRequests(next);
  };

  const forgetUnknown = (request: SaveRequest) => {
    const next = new Map(unknownRef.current);
    next.delete(requestKey(request));
    unknownRef.current = next;
    setUnknownRequests(next);
  };

  const rememberSaved = (saved: Extract<Phase, { kind: "saved" }>) => {
    const next = new Map(savedRef.current).set(requestKey(saved.request), saved);
    savedRef.current = next;
    setSavedRequests(next);
  };

  const forgetSaved = (request: SaveRequest) => {
    const next = new Map(savedRef.current);
    next.delete(requestKey(request));
    savedRef.current = next;
    setSavedRequests(next);
  };

  const confirm = (request: SaveRequest) => {
    const blocked = unknownRef.current.get(requestKey(request));
    setPhase(
      blocked === undefined ? { kind: "confirm", request } : { kind: "unknown", failure: blocked, request },
    );
  };

  const dismiss = () => {
    setPhase((current) => {
      if (current.kind === "saving") return { ...current, dialogOpen: false };
      if (current.kind === "confirm") return { kind: "idle" };
      return current;
    });
  };

  const save = async (request: SaveRequest) => {
    const key = requestKey(request);
    const blocked = unknownRef.current.get(key);
    if (blocked !== undefined) {
      setPhase({ kind: "unknown", failure: blocked, request });
      return;
    }
    const attempt = ++activeAttempt.current;
    latestByRequest.current.set(key, attempt);
    forgetSaved(request);
    setPhase({ kind: "saving", dialogOpen: true, request });
    const isLatestForRequest = () => mounted.current && latestByRequest.current.get(key) === attempt;
    const isForeground = () => activeAttempt.current === attempt;
    const deadline = window.setTimeout(() => {
      if (!isLatestForRequest()) return;
      const failure: Failure = { kind: "unreachable" };
      rememberUnknown(request, failure);
      if (isForeground()) setPhase({ kind: "unknown", failure, request });
    }, responseDeadlineMs);
    const posted = await outcomeOf(() =>
      api.POST("/api/v1/records", {
        body: { q: request.q, mode: request.mode, index_version: request.indexVersion },
      }),
    );
    window.clearTimeout(deadline);
    if (!isLatestForRequest()) return;
    if (posted.kind !== "ok") {
      if (posted.kind === "refused" && posted.error.code === "API_RECORDS_STORE_FULL") {
        forgetUnknown(request);
        rememberStoreFull();
        setStoreFull(true);
        if (isForeground()) setPhase({ kind: "refused", failure: posted, request });
        return;
      }
      if (posted.kind === "refused" && posted.error.code === "API_INDEX_VERSION_UNAVAILABLE") {
        forgetUnknown(request);
        if (isForeground()) setPhase({ kind: "index_moved", request });
        return;
      }
      if (posted.kind === "refused" && posted.status === 422) {
        forgetUnknown(request);
        if (isForeground()) setPhase({ kind: "refused", failure: posted, request });
        return;
      }
      if (!safeToRetry(posted)) {
        rememberUnknown(request, posted);
        if (isForeground()) setPhase({ kind: "unknown", failure: posted, request });
        return;
      }
      forgetUnknown(request);
      if (isForeground()) setPhase({ kind: "refused", failure: posted, request });
      return;
    }
    if (!isCreated(posted.data)) {
      const failure: Failure = { kind: "no_answer", status: 201 };
      rememberUnknown(request, failure);
      if (isForeground()) setPhase({ kind: "unknown", failure, request });
      return;
    }
    forgetUnknown(request);
    const saved: Extract<Phase, { kind: "saved" }> = {
      kind: "saved",
      attempt,
      created: posted.data,
      record: null,
      request,
    };
    rememberSaved(saved);
    if (isForeground()) setPhase(saved);
  };

  const loadRecord = async (saved: Extract<Phase, { kind: "saved" }>) => {
    const key = requestKey(saved.request);
    const current = savedRef.current.get(key);
    if (
      saved.record !== null ||
      current?.attempt !== saved.attempt ||
      loadingReplay.current.has(saved.attempt)
    ) {
      return;
    }
    loadingReplay.current.add(saved.attempt);
    const record = await getRecord(api, saved.created.record_id, true);
    loadingReplay.current.delete(saved.attempt);
    if (!mounted.current || savedRef.current.get(key)?.attempt !== saved.attempt) return;
    const completed = { ...saved, record };
    rememberSaved(completed);
    setPhase((foreground) =>
      foreground.kind === "saved" && foreground.attempt === saved.attempt ? completed : foreground,
    );
  };

  return (
    <SaveRecordContext.Provider
      value={{ phase, unknownRequests, savedRequests, fullNow, confirm, dismiss, save, loadRecord }}
    >
      {children}
    </SaveRecordContext.Provider>
  );
}

/** Uses the page owner in production; a local owner keeps isolated component tests and reuse safe. */
export function SaveRecord(props: SaveRecordProps) {
  const controller = useContext(SaveRecordContext);
  if (controller === null) {
    return (
      <SaveRecordProvider>
        <SaveRecord {...props} />
      </SaveRecordProvider>
    );
  }
  return <SaveRecordInner {...props} controller={controller} />;
}

function SaveRecordInner({
  q,
  mode,
  indexVersion,
  total,
  disabledReason,
  controller,
}: SaveRecordProps & { controller: SaveController }) {
  const { phase } = controller;
  // full earlier this session (sessionStorage), or on this page's last save
  const fullBefore = useSyncExternalStore(noSubscription, storeFullBefore, () => false);
  const storeFull = fullBefore || controller.fullNow;
  const trigger = useRef<HTMLButtonElement>(null);
  const reasonId = useId();
  const shownRequest: SaveRequest = { q, mode, indexVersion, total };
  const shownKey = requestKey(shownRequest);
  const shownUnknown = controller.unknownRequests.get(shownKey);
  const shownSaved = controller.savedRequests.get(shownKey);
  const visibleSaved =
    shownSaved ?? (shownUnknown === undefined && phase.kind === "saved" ? phase : undefined);
  const visibleUnknown =
    shownSaved === undefined
      ? (shownUnknown ?? (phase.kind === "unknown" ? phase.failure : undefined))
      : undefined;
  const showForegroundTerminal = shownSaved === undefined && shownUnknown === undefined;
  const sameSaveIsUnknown = shownUnknown !== undefined;
  const reason = storeFull
    ? STORE_FULL_MESSAGE
    : sameSaveIsUnknown
      ? SAVE_OUTCOME_UNKNOWN_MESSAGE
      : disabledReason;

  useEffect(() => {
    if (phase.kind === "index_moved" || phase.kind === "refused" || phase.kind === "unknown") {
      trigger.current?.focus();
    }
  }, [phase]);

  useEffect(() => {
    if (visibleSaved?.record === null) void controller.loadRecord(visibleSaved);
  }, [controller, visibleSaved]);

  const dismissConfirmation = () => {
    controller.dismiss();
    trigger.current?.focus();
  };

  return (
    <div className="inline-flex flex-wrap items-center gap-2">
      <button
        ref={trigger}
        type="button"
        aria-disabled={reason !== null || phase.kind === "saving" ? true : undefined}
        aria-describedby={reason !== null ? reasonId : undefined}
        onClick={() => {
          if (reason === null && phase.kind !== "saving") controller.confirm(shownRequest);
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
      {(phase.kind === "confirm" || (phase.kind === "saving" && phase.dialogOpen)) && (
        <Confirm
          q={phase.request.q}
          mode={phase.request.mode}
          indexVersion={phase.request.indexVersion}
          total={phase.request.total}
          onCancel={dismissConfirmation}
          onSave={() => void controller.save(phase.request)}
          saving={phase.kind === "saving"}
        />
      )}
      {visibleSaved !== undefined && (
        <Saved
          created={visibleSaved.created}
          record={visibleSaved.record}
          shownIndex={visibleSaved.request.indexVersion}
          shownTotal={visibleSaved.request.total}
        />
      )}
      {showForegroundTerminal && phase.kind === "index_moved" && (
        <div role="alert" className={`${box} w-full`}>
          <p className="break-words">
            <span aria-hidden="true">✖ </span>Index{" "}
            <code className="font-mono break-all">{phase.request.indexVersion}</code> is no longer served
            here, so the search wasn&apos;t saved: it would have been frozen on another index than the one
            whose counts you saw. Search again to see the current results, then save.
          </p>
        </div>
      )}
      {showForegroundTerminal && phase.kind === "refused" && (
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
            <FailureNotice failure={phase.failure} onRetry={() => void controller.save(phase.request)} />
          )}
        </div>
      )}
      {visibleUnknown !== undefined && <UnknownSave failure={visibleUnknown} />}
    </div>
  );
}

/** A POST without a trustworthy answer may already have committed; do not offer any path that resends it. */
function UnknownSave({ failure }: { failure: Failure }) {
  return (
    <div role="alert" className={`${box} w-full`}>
      <p>{SAVE_OUTCOME_UNKNOWN_MESSAGE}</p>
      {failure.kind === "refused" && (
        <p className="break-words">
          <code className="font-mono">{failure.error.code}</code>: {failure.error.message}
        </p>
      )}
    </div>
  );
}

/** S1: focus starts on Save and stays inside; Esc cancels before dispatch or closes while it finishes. */
function Confirm({
  q,
  mode,
  indexVersion,
  total,
  onCancel,
  onSave,
  saving,
}: {
  q: string;
  mode: Mode;
  indexVersion: string;
  total: number;
  onCancel: () => void;
  onSave: () => void;
  saving: boolean;
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
            {saving ? "Close" : "Cancel"}
          </button>
          <button
            ref={saveRef}
            type="button"
            aria-disabled={saving || undefined}
            onClick={() => !saving && onSave()}
            className="min-h-8 rounded-md border bg-primary px-3 text-primary-foreground hover:opacity-90"
          >
            <span role={saving ? "status" : undefined} aria-live={saving ? "polite" : undefined}>
              {saving ? "Saving…" : "Save"}
            </span>
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
