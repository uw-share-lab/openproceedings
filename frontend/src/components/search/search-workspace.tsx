"use client";

/**
 * The query half of the search workspace (spec 05 §Components 1–2; design W1, W3, W6, W7, W11; TASK-041):
 * Syntax select, editor, Search and Revert edits, the diagnostics summary and row, and "How we read your
 * query". Results, sidebar and banner are TASK-042's, which passes a `/search` refusal in as `refusal`.
 *
 * **The draft is `(text, mode)`** (pre-pass M7). It is not state until submitted: Search (or Enter) runs the
 * reducer's `submit` and pushes the URL, which changes only `q` and `mode` (and resets the page). Typing, the
 * Syntax select, an example or an action in the row change only the draft. While the draft differs from the
 * searched `(q, mode)` it is **dirty** (`DRAFT_DIRTY`, design W13): the row and the tree show the draft's
 * `/parse`, labelled "Draft — not searched", and the searched query's warnings stay one click away.
 */
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useId, useMemo, useRef, useState, type ReactNode } from "react";
import { useMeta } from "@/api/hooks";
import { codePointLength, codePointSpanToUtf16 } from "@/api/spans";
import { ConceptBuilder, type Expansions } from "@/builder/concept-builder";
import type { SearchedGroups } from "@/builder/group-counts";
import { panelId, QueryTabList, tabId, type QueryTab } from "@/builder/query-tabs";
import { countText, editorDiagnostics, itemOf, itemsOf, plural, type Item } from "@/editor/diagnostics";
import type { ErrorEnvelope, ParseOutcome, ParseResponse } from "@/editor/parse";
import { QueryEditor, type QueryEditorHandle } from "@/editor/query-editor";
import { useDraftParse, useSearchedParse } from "@/editor/use-parse";
import {
  DEFAULT_LIMITS,
  reduce,
  searchHref,
  type Mode,
  type SearchAction,
  type SearchState,
} from "@/lib/search-state";
import { DiagnosticsRow } from "./diagnostics-row";
import { EmptyState } from "./empty-state";
import type { Example } from "./examples";
import { QueryTree } from "./query-tree";
import { WorkspaceSlotContext } from "./workspace-slot";

export interface Draft {
  readonly text: string;
  readonly mode: Mode;
}

/** A `/search` 422 for a submitted `(q, mode)` (design W6, W7): its diagnostics are drawn on that query. */
export interface SearchRefusal {
  readonly q: string;
  readonly mode: Mode;
  readonly error: ErrorEnvelope["error"];
}

export interface SearchWorkspaceProps {
  /** The search the URL holds (`fromURL`). */
  readonly state: SearchState;
  /** Set by the results (TASK-042) when `/search` refused the searched query with diagnostics. */
  readonly refusal?: SearchRefusal | null;
  /** Open "How we read your query" (zero results, W8; TASK-042). */
  readonly openTree?: boolean;
  /** TASK-042: the results, sidebar and banner, drawn below the query half; they read `useWorkspaceSlot()`. */
  readonly results?: ReactNode;
  /** The last answered `/search`'s `query.expansions`: the builder shows each group's own (TASK-111). */
  readonly expansions?: Expansions | null;
  /** The last answered `/search`'s total and group counts: the builder shows each group's own (TASK-176). */
  readonly searchedGroups?: SearchedGroups | null;
}

/** `DRAFT_DIRTY`: the draft differs from the searched query (design W13; copy SB-6). */
export function isDirty(draft: Draft, state: Pick<SearchState, "q" | "mode">): boolean {
  return draft.text !== state.q || draft.mode !== state.mode;
}

export const DRAFT_DIRTY_MESSAGE =
  "The editor has changes you haven't searched — a filter would edit the last searched query and discard " +
  "them. Search first, or revert the edits.";

/** What the row, summary and squiggles show: which text they belong to, and what was said about it. */
interface Shown {
  readonly text: string;
  readonly mode: Mode;
  readonly items: readonly Item[];
  readonly parsed: ParseResponse | null;
  readonly refused: boolean;
  readonly lead: string | null;
  /** Not a server diagnostic: the query wasn't checked (413, busy, unreachable). */
  readonly notice: "too_large" | "unchecked" | null;
  readonly outcome: ParseOutcome | null;
}

function shownFor(outcome: ParseOutcome | null, refusal: SearchRefusal | null, draft: Draft): Shown | null {
  if (refusal !== null && refusal.q === draft.text && refusal.mode === draft.mode) {
    const items: Item[] = (refusal.error.diagnostics ?? []).map((d) => itemOf("error", d));
    return {
      text: refusal.q,
      mode: refusal.mode,
      items,
      parsed: null,
      refused: true,
      lead: refusal.error.code.startsWith("API_") ? refusal.error.message : null,
      notice: null,
      outcome: null,
    };
  }
  if (outcome === null) return null;
  const base = { text: outcome.q, mode: outcome.mode, refused: false, lead: null, outcome };
  switch (outcome.kind) {
    case "parsed":
      return { ...base, items: itemsOf(outcome.result), parsed: outcome.result, notice: null };
    case "too_large":
      return { ...base, items: [], parsed: null, notice: "too_large" };
    default:
      return { ...base, items: [], parsed: null, notice: "unchecked" };
  }
}

/** The summary line (ED-5, ED-6, ED-14): a polite live region, changed only when an answer lands. */
function summaryText(shown: Shown | null, draft: Draft, state: SearchState): string {
  if (shown === null) return isDirty(draft, state) && draft.text.trim() !== "" ? "not searched yet" : "";
  const errors = shown.items.filter((i) => i.severity === "error").length;
  if (shown.refused) return `The query wasn't searched: ${plural(Math.max(errors, 1), "error")}`;
  const counts =
    shown.notice === "too_large"
      ? plural(1, "error")
      : shown.notice === "unchecked"
        ? "The query couldn't be checked"
        : countText(shown.items);
  const dirty = isDirty(shown, state);
  if (!dirty) return counts;
  const marker = shown.text === state.q ? "syntax changed — not searched yet" : "not searched yet";
  return counts === "" ? marker : `${counts} — ${marker}`;
}

function TooLarge({
  outcome,
  maxLength,
}: {
  outcome: Extract<ParseOutcome, { kind: "too_large" }>;
  maxLength: number;
}) {
  const bytes = /over ([0-9][0-9,]*) bytes/.exec(outcome.message)?.[1];
  const refused =
    bytes !== undefined
      ? `the server refused a request over ${bytes} bytes`
      : "the server refused it as too large";
  return (
    <p className="break-words">
      <span aria-hidden="true" className="mr-1.5 font-bold text-diag-error">
        ✖
      </span>
      <span className="sr-only">Error: </span>
      The query is far too long to send ({refused}). A valid query is at most{" "}
      {maxLength.toLocaleString("en-US")} characters; this one is{" "}
      {codePointLength(outcome.q).toLocaleString("en-US")}. Shorten it.
    </p>
  );
}

type UncheckedOutcome = Extract<ParseOutcome, { kind: "refused" | "no_answer" | "unreachable" }>;

function Unchecked({ outcome, onRetry }: { outcome: UncheckedOutcome; onRetry: () => void }) {
  // the server's own message is a whole sentence, so it follows a full stop rather than a colon
  const why =
    outcome.kind === "refused"
      ? `. ${outcome.error.message}`
      : outcome.kind === "no_answer"
        ? `: the server is busy or restarting (${outcome.status === null ? "" : `HTTP ${outcome.status}, `}not from the search service).`
        : ": the server couldn't be reached. Check your connection.";
  return (
    <p className="break-words">
      <span aria-hidden="true" className="mr-1.5 font-bold text-diag-info">
        ⓘ
      </span>
      <span className="sr-only">Note: </span>
      The query couldn&apos;t be checked{why}{" "}
      <button
        type="button"
        onClick={onRetry}
        className="min-h-6 rounded-sm border px-1.5 text-xs hover:bg-muted"
      >
        Check again
      </button>
    </p>
  );
}

function SearchedWarnings({ items }: { items: readonly Item[] }) {
  const [open, setOpen] = useState(false);
  const region = useId();
  if (items.length === 0) return null;
  return (
    <div className="text-sm">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={region}
        onClick={() => setOpen(!open)}
        className="min-h-6 underline-offset-4 hover:underline"
      >
        Searched query: {plural(items.length, "warning")} <span aria-hidden="true">{open ? "▾" : "▸"}</span>
      </button>
      {open && (
        <ul id={region} className="mt-1 space-y-1">
          {items.map((item, i) => (
            <li key={i}>
              <span aria-hidden="true" className="mr-1.5 font-bold text-diag-warning">
                ⚠
              </span>
              <span className="sr-only">Warning: </span>
              {item.message}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function SearchWorkspace({
  state,
  refusal = null,
  openTree = false,
  results,
  expansions = null,
  searchedGroups = null,
}: SearchWorkspaceProps) {
  const router = useRouter();
  const meta = useMeta();
  const editor = useRef<QueryEditorHandle>(null);
  const treeButton = useRef<HTMLButtonElement>(null);
  const summaryId = useId();
  const modeId = useId();
  const revertId = useId();

  const [draft, setDraft] = useState<Draft>({ text: state.q, mode: state.mode });
  // A new URL (a submit, Back, a link) is a new searched query: the draft follows it.
  const [searched, setSearched] = useState({ q: state.q, mode: state.mode });
  if (searched.q !== state.q || searched.mode !== state.mode) {
    setSearched({ q: state.q, mode: state.mode });
    setDraft({ text: state.q, mode: state.mode });
  }

  const { outcome, refetch } = useDraftParse(draft.text, draft.mode);
  const searchedParse = useSearchedParse(state.q, state.mode);
  const shown = useMemo(() => shownFor(outcome, refusal, draft), [outcome, refusal, draft]);
  const squiggles = useMemo(
    () => (shown === null ? [] : editorDiagnostics(shown.text, shown.items)),
    [shown],
  );
  const dirty = isDirty(draft, state);

  const [treeChoice, setTreeChoice] = useState<boolean | null>(null);
  const hasMixed = shown?.items.some((i) => i.code === "WARN_MIXED_AND_OR") ?? false;
  const treeOpen = treeChoice ?? (openTree || hasMixed);
  // "Show how it was read" opens the tree and then moves focus to it, once it is rendered open.
  const focusTree = useRef(false);
  useEffect(() => {
    if (focusTree.current) {
      focusTree.current = false;
      treeButton.current?.focus();
    }
  });
  // TASK-042's slot: point at a clause in the editor; draftAndSelect selects once the editor holds the new
  // draft (the editor's own effect runs first).
  const pendingSelect = useRef<[number, number] | null>(null);
  const select = (from: number, to: number) => editor.current?.select(from, to);
  const draftAndSelect = (text: string, from: number, to: number) => {
    pendingSelect.current = [from, to];
    setDraft((d) => ({ ...d, text }));
  };
  useEffect(() => {
    const range = pendingSelect.current;
    if (range !== null) {
      pendingSelect.current = null;
      editor.current?.select(range[0], range[1]);
    }
  });

  // ---- Text/Builder tabs (TASK-043): see src/builder/query-tabs.tsx and concept-builder.tsx
  const [tab, setTab] = useState<QueryTab>("text");
  const [enterBuilder, setEnterBuilder] = useState(false);
  const tabsId = useId();
  // Where the editor's cursor goes once the Text panel is showing again (UTF-16 offsets)
  const editorSelection = useRef<readonly [number, number] | null>(null);
  useEffect(() => {
    const at = editorSelection.current;
    if (tab !== "text" || at === null) return;
    editorSelection.current = null;
    editor.current?.select(at[0], at[1]);
  });
  const toText = (span?: readonly [number, number]) => {
    setTab("text");
    editorSelection.current =
      span === undefined ? [draft.text.length, draft.text.length] : codePointSpanToUtf16(draft.text, span);
  };
  const selectTab = (next: QueryTab, enter: boolean) => {
    if (next === "text" && enter) toText();
    else setTab(next);
    setEnterBuilder(next === "builder" && enter);
  };
  const builderFocused = useCallback(() => setEnterBuilder(false), []);

  const submit = () => {
    // From the Builder tab, Search dispatches builderEdit (design §Interaction spec); a Syntax change goes too
    const action: SearchAction =
      tab === "builder" && draft.mode === state.mode
        ? { type: "builderEdit", q: draft.text }
        : { type: "submit", q: draft.text, mode: draft.mode };
    const next = reduce(state, action, meta?.limits ?? DEFAULT_LIMITS);
    router.push(searchHref(next));
  };

  const load = (next: Draft) => {
    setDraft(next);
    if (tab === "text") editor.current?.focus();
  };

  const shownDirty = shown !== null && isDirty(shown, state);
  const searchedWarnings =
    dirty && searchedParse?.kind === "parsed"
      ? itemsOf(searchedParse.result).filter((i) => i.severity === "warning")
      : [];

  return (
    <div className="space-y-3">
      <form
        role="search"
        aria-label="Query"
        className="space-y-2"
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
          <QueryTabList tab={tab} onSelect={selectTab} idBase={tabsId} />
          <label htmlFor={modeId} className="flex items-center gap-2">
            Syntax
            <select
              id={modeId}
              value={draft.mode}
              onChange={(e) =>
                setDraft({ ...draft, mode: e.target.value === "scholar" ? "scholar" : "native" })
              }
              className="min-h-8 rounded-md border border-input bg-background px-2"
            >
              <option value="native">native</option>
              <option value="scholar">Google Scholar / PoP</option>
            </select>
          </label>
          <div className="ml-auto flex items-center gap-2">
            {dirty && (
              <>
                <button
                  type="button"
                  aria-describedby={revertId}
                  onClick={() => load({ text: state.q, mode: state.mode })}
                  className="min-h-8 rounded-md border px-3 hover:bg-muted"
                >
                  Revert edits
                </button>
                <span id={revertId} className="sr-only">
                  Put the last searched query back in the editor
                </span>
              </>
            )}
            <button
              type="submit"
              className="min-h-8 rounded-md bg-primary px-4 font-medium text-primary-foreground hover:opacity-90"
            >
              Search
            </button>
          </div>
        </div>
        <div
          role="tabpanel"
          id={panelId(tabsId, "text")}
          aria-labelledby={tabId(tabsId, "text")}
          hidden={tab !== "text"}
        >
          <QueryEditor
            handle={editor}
            value={draft.text}
            onChange={(text) => setDraft((d) => ({ ...d, text }))}
            onSubmit={submit}
            diagnostics={squiggles}
            diagnosticsFor={shown?.text ?? null}
            describedBy={summaryId}
            meta={meta}
            autoFocus={state.q === ""}
          />
        </div>
        <div
          role="tabpanel"
          id={panelId(tabsId, "builder")}
          aria-labelledby={tabId(tabsId, "builder")}
          hidden={tab !== "builder"}
        >
          {tab === "builder" && (
            <ConceptBuilder
              text={draft.text}
              mode={draft.mode}
              onEdit={(text) => setDraft((d) => ({ ...d, text }))}
              onEditInText={toText}
              focusOnOpen={enterBuilder}
              onFocused={builderFocused}
              expansions={expansions}
              searched={searchedGroups}
            />
          )}
        </div>
      </form>

      <p id={summaryId} role="status" aria-live="polite" className="min-h-5 text-sm text-muted-foreground">
        {summaryText(shown, draft, state)}
      </p>

      {shown !== null && (
        <DiagnosticsRow
          items={shown.items}
          draft={shownDirty && (shown.items.length > 0 || shown.notice !== null)}
          lead={shown.lead}
          notice={
            shown.notice === "too_large" && shown.outcome?.kind === "too_large" ? (
              <TooLarge
                outcome={shown.outcome}
                maxLength={meta?.limits.max_query_length ?? DEFAULT_LIMITS.max_query_length}
              />
            ) : shown.notice === "unchecked" &&
              shown.outcome !== null &&
              shown.outcome.kind !== "parsed" &&
              shown.outcome.kind !== "too_large" ? (
              <Unchecked outcome={shown.outcome} onRetry={refetch} />
            ) : null
          }
          text={shown.text}
          textIsDraft={shown.text === draft.text}
          wordForms={shown.parsed?.word_forms ?? []}
          nativeMode={draft.mode === "native"}
          searchedAs={!shownDirty ? (shown.parsed?.canonical ?? null) : null}
          treeAvailable={shown.parsed != null && shown.parsed.effective_ast !== null}
          onShowTree={() => {
            setTreeChoice(true);
            focusTree.current = true;
          }}
          onLoad={(text) => load({ ...draft, text })}
          onReadAsScholar={() => setDraft({ ...draft, mode: "scholar" })}
        />
      )}

      <SearchedWarnings items={searchedWarnings} />

      {shown?.parsed != null && shown.parsed.effective_ast !== null && (
        <QueryTree
          ref={treeButton}
          result={shown.parsed}
          open={treeOpen}
          onToggle={() => setTreeChoice(!treeOpen)}
          draft={shownDirty}
        />
      )}

      {state.q === "" && <EmptyState onLoad={(e: Example) => load({ text: e.q, mode: e.mode })} />}

      {results !== undefined && (
        <WorkspaceSlotContext.Provider value={{ dirty, select, draftAndSelect }}>
          {results}
        </WorkspaceSlotContext.Provider>
      )}
    </div>
  );
}
