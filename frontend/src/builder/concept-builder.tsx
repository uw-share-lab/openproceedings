"use client";

/**
 * The Builder tab (spec 05 §Components 3; docs/design/2026-09-27-concept-group-builder.md, states and B1/B2;
 * copy deck §3 BD-1–BD-9; accessibility skill §Keyboard flows 3–4).
 *
 * The draft text is canonical. The builder reads the server's `ast` of the draft (`read.ts`) and, on an edit,
 * rewrites the draft from its groups (`write.ts`); an untouched query is never rewritten, so Text → Builder →
 * Text leaves it byte for byte as typed. A query the builder can't show is read-only here, naming the first
 * construct that doesn't fit, and is never changed; the parts that do fit are shown under the notice, dimmed
 * and not editable (B2). Builder edits are draft edits: only Search changes the URL. After a search, each group
 * shows its own wildcards' expansions from that `/search` answer (TASK-111).
 */
import { useQuery } from "@tanstack/react-query";
import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import type { Schemas } from "@/api/client";
import { CopyButton } from "@/components/copy-button";
import { useApi } from "@/components/providers";
import { ExpansionLine } from "@/components/search/expansions-row";
import { countText, itemsOf, type Item } from "@/editor/diagnostics";
import type { ParseOutcome } from "@/editor/parse";
import { parseQuery } from "@/editor/use-parse";
import type { Mode } from "@/lib/search-state";
import {
  addExclude,
  addGroup,
  addTerm,
  commitTerm,
  groupAt,
  moveGroup,
  removeExclude,
  removeGroup,
  removeTerm,
  setScope,
  splitTerm,
  type GroupKey,
} from "./edits";
import {
  emptyModel,
  SCOPE_LABELS,
  termWritten,
  type Blocker,
  type BuilderGroup,
  type BuilderModel,
  type BuilderTerm,
  type CodePoints,
  type Scope,
} from "./model";
import { termWildcards } from "./expansions";
import { constructText, modelOf, readAst, readFitting, sourceSpans } from "./read";
import { listItems } from "./terms";
import { readsAsWritten, writeModel } from "./write";

export interface ConceptBuilderProps {
  readonly text: string;
  readonly mode: Mode;
  /** A builder edit: the new draft text (never the URL). */
  readonly onEdit: (text: string) => void;
  /** Go to the Text tab; with a span (code points into `text`), select it there. */
  readonly onEditInText: (span?: CodePoints) => void;
  /** The tab was just chosen: move focus into the panel once it has something to focus. */
  readonly focusOnOpen: boolean;
  readonly onFocused: () => void;
  /** The last answered `/search`'s expansions, keyed `<stem><op>`; `null` before a search. */
  readonly expansions?: Expansions | null;
}

export type Expansions = Schemas["QueryInfo"]["expansions"];

/** Per term id, the `/search` keys of its wildcards (`expansions.ts`). */
type WildcardKeys = ReadonlyMap<number, readonly string[]>;

/** What the builder is editing, and the draft text it belongs to. */
interface Session {
  readonly text: string;
  readonly mode: Mode;
  readonly model: BuilderModel;
  /** Each term's place in `text` (the read query's leaves, or where the builder wrote it). */
  readonly spans: ReadonlyMap<number, CodePoints>;
  /** The builder wrote `text` (so the server's reading of it can be checked against the model). */
  readonly written: boolean;
  /** Each term's wildcards, as last known: kept for an unchanged term while the server reads an edit. */
  readonly keys: WildcardKeys;
}

type Initial =
  | { readonly kind: "loading" }
  | { readonly kind: "fits"; readonly session: Session }
  | { readonly kind: "errors"; readonly items: readonly Item[] }
  | {
      readonly kind: "blocked";
      readonly blocker: Blocker;
      /** The parts that fit, shown dimmed under the notice (design B2). */
      readonly fitting: BuilderModel;
      readonly keys: WildcardKeys;
    }
  | { readonly kind: "unchecked" };

const blank = (q: string) => q.trim() === "";

function initialOf(text: string, mode: Mode, outcome: ParseOutcome | null): Initial {
  if (blank(text)) {
    return {
      kind: "fits",
      session: { text, mode, model: emptyModel(), spans: new Map(), written: false, keys: new Map() },
    };
  }
  if (outcome === null || outcome.q !== text || outcome.mode !== mode) return { kind: "loading" };
  if (outcome.kind !== "parsed") return { kind: "unchecked" };
  const { result } = outcome;
  if (result.errors.length > 0 || result.ast === null) return { kind: "errors", items: itemsOf(result) };
  const reading = readAst(result.ast);
  if (reading.kind === "blocked") {
    const shape = readFitting(result.ast);
    const fitting = modelOf(text, shape);
    const keys = termWildcards(result.ast, sourceSpans(fitting, shape));
    return { kind: "blocked", blocker: reading.blocker, fitting, keys };
  }
  const model = modelOf(text, reading.shape);
  const spans = sourceSpans(model, reading.shape);
  return {
    kind: "fits",
    session: { text, mode, model, spans, written: false, keys: termWildcards(result.ast, spans) },
  };
}

/** How a screen reader says a term: "trustworth star" (design §Screen reader structure). */
const spoken = (t: string) => t.replace(/\*/gu, " star").replace(/\$/gu, " dollar");

const termList = (group: BuilderGroup) =>
  group.terms
    .filter((t) => t.text !== "")
    .map((t) => spoken(termWritten(t)))
    .join(", ") || "no terms yet";
/** A group's accessible name: "Group 2 of 3, any of: trustworth star, trust". */
const groupLabel = (index: number, n: number, group: BuilderGroup) =>
  `Group ${index + 1} of ${n}, any of: ${termList(group)}`;
const excludeLabel = (group: BuilderGroup) => `Leave out papers with any of: ${termList(group)}`;

/** The terms' wildcards that `keys` knows, carried to `next` for each term whose written text is unchanged. */
function carryKeys(model: BuilderModel, keys: WildcardKeys, next: BuilderModel): WildcardKeys {
  const all = (m: BuilderModel) =>
    [...m.groups, ...(m.exclude === null ? [] : [m.exclude])].flatMap((g) => g.terms);
  const was = new Map(all(model).map((t) => [t.id, termWritten(t)] as const));
  const carried = new Map<number, readonly string[]>();
  for (const t of all(next)) {
    const k = keys.get(t.id);
    if (k !== undefined && was.get(t.id) === termWritten(t)) carried.set(t.id, k);
  }
  return carried;
}

const BUTTON = "min-h-6 rounded-sm border px-1.5 text-xs hover:bg-muted aria-disabled:opacity-50";
const GLYPH = { error: "✖", warning: "⚠", info: "↻" } as const;
const PREFIX = { error: "Error:", warning: "Warning:", info: "Read as:" } as const;
const TONE = { error: "text-diag-error", warning: "text-diag-warning", info: "text-diag-info" } as const;

interface Editing {
  readonly termId: number;
  readonly value: string;
  /** The term had no text before this edit: Esc removes it rather than restoring it. */
  readonly fresh: boolean;
  readonly problem: string | null;
}

export function ConceptBuilder(props: ConceptBuilderProps) {
  const { text, mode } = props;
  const api = useApi();
  const query = useQuery({ ...parseQuery(api, text, mode), enabled: !blank(text) });
  const outcome = blank(text) ? null : (query.data ?? null);

  const [session, setSession] = useState<Session | null>(null);
  const live = session !== null && session.text === text && session.mode === mode ? session : null;
  const initial = useMemo(
    () => (live === null ? initialOf(text, mode, outcome) : null),
    [live, text, mode, outcome],
  );
  const current = live ?? (initial?.kind === "fits" ? initial.session : null);

  const [editing, setEditing] = useState<Editing | null>(null);
  const [announcement, setAnnouncement] = useState("");
  const root = useRef<HTMLDivElement>(null);
  const pendingFocus = useRef<string | null>(null);
  const hintId = useId();
  const termHelpId = useId();

  // "Reading the query…" only once the answer is slow (BD-8, after 300 ms)
  const loading = initial?.kind === "loading";
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    if (!loading) return;
    const timer = setTimeout(() => setSlow(true), 300);
    return () => {
      clearTimeout(timer);
      setSlow(false);
    };
  }, [loading]);

  const focus = (key: string) => {
    pendingFocus.current = key;
  };
  useEffect(() => {
    const key = pendingFocus.current;
    if (key === null) return;
    const el = root.current?.querySelector<HTMLElement>(`[data-focus="${key}"]`);
    if (el) {
      pendingFocus.current = null;
      el.focus();
    }
  });

  // Moving focus in when the tab was chosen (design §Interaction spec: Switching)
  const { focusOnOpen, onFocused } = props;
  useEffect(() => {
    if (!focusOnOpen || initial?.kind === "loading") return;
    const first = current?.model.groups[0]?.terms[0];
    focus(current === null ? "notice" : first === undefined ? "add-group" : `term:${first.id}`);
    onFocused();
  }, [focusOnOpen, onFocused, initial?.kind, current]);

  const written = useMemo(() => (current === null ? null : writeModel(current.model)), [current]);

  // The server's answer for the text shown: per-term diagnostics, the check of the builder's own query, and
  // each term's wildcards (kept from before the edit while it is in flight)
  const parsed =
    outcome?.kind === "parsed" && outcome.q === text && outcome.mode === mode ? outcome.result : null;
  const keys = useMemo(
    () =>
      current === null
        ? new Map<number, readonly string[]>()
        : parsed?.ast != null && parsed.errors.length === 0
          ? termWildcards(parsed.ast, current.spans)
          : current.keys,
    [current, parsed],
  );

  /** An edit: the model changes and the draft is rewritten from it. */
  const apply = (model: BuilderModel, say?: string) => {
    const next = writeModel(model);
    if (next.limitsUnsafe) return; // never written: the notice below says why
    const spans = new Map(next.terms.map((t) => [t.termId, t.span] as const));
    const carried = current === null ? new Map() : carryKeys(current.model, keys, model);
    setSession({ text: next.q, mode, model, spans, written: true, keys: carried });
    if (next.q !== text) props.onEdit(next.q);
    if (say !== undefined) setAnnouncement(say);
  };

  if (current === null || written === null) {
    return (
      <div ref={root} className="space-y-2 text-sm">
        <ReadOnly
          initial={initial}
          slow={slow}
          text={text}
          onEditInText={props.onEditInText}
          onRetry={() => void query.refetch()}
          expansions={props.expansions ?? null}
        />
      </div>
    );
  }

  const model = current.model;
  const nGroups = model.groups.length;
  const groupNumber = (key: GroupKey) => (key === "exclude" ? null : key + 1);

  const items = parsed === null ? [] : itemsOf(parsed);
  const termItems = new Map<number, Item[]>();
  for (const item of items) {
    if (item.span === null) continue;
    const [s, e] = item.span;
    for (const [id, [ts, te]] of current.spans) {
      if (s < te && e > ts) termItems.set(id, [...(termItems.get(id) ?? []), item]);
      else if (s === e && s === ts) termItems.set(id, [...(termItems.get(id) ?? []), item]);
    }
  }
  const misread =
    current.written &&
    parsed !== null &&
    parsed.ast !== null &&
    parsed.errors.length === 0 &&
    !readsAsWritten(model, written, readAst(parsed.ast));
  const unsafe = new Set(written.unsafe);

  // ---- term editing
  const startEdit = (term: BuilderTerm) => {
    // the box holds the term without its scope (the chip's select keeps that); a typed prefix sets it
    setEditing({ termId: term.id, value: term.text, fresh: term.text === "", problem: null });
    focus(`term:${term.id}`);
  };

  /** Focus after a term goes: the previous term, or `+ term` if it was the first (design §Focus after removal). */
  const focusAfterRemoval = (key: GroupKey, termId: number) => {
    const group = groupAt(model, key);
    const index = group?.terms.findIndex((t) => t.id === termId) ?? -1;
    const previous = index > 0 ? group?.terms[index - 1] : undefined;
    focus(previous === undefined ? `add:${String(group?.id)}` : `term:${previous.id}`);
  };

  const dropTerm = (key: GroupKey, term: BuilderTerm) => {
    focusAfterRemoval(key, term.id);
    setEditing(null);
    apply(removeTerm(model, key, term.id));
  };

  /**
   * Enter ("next": commit and open a new empty term in the group) or leaving the box ("blur": commit, and
   * leave focus where the reader put it).
   */
  const commit = (key: GroupKey, termId: number, value: string, then: "next" | "blur") => {
    const items = listItems(value);
    if (items !== null) {
      split(key, termId, items, then === "next");
      return;
    }
    const result = commitTerm(model, key, termId, value);
    if (result.kind === "unwritable") {
      setEditing((e) =>
        e === null ? e : { ...e, problem: "Nothing here can be searched: type a word or a phrase." },
      );
      return;
    }
    if (result.kind === "removed") {
      if (then === "next") focusAfterRemoval(key, termId);
      setEditing(null);
      apply(result.model);
      return;
    }
    const term = groupAt(result.model, key)?.terms.find((t) => t.id === termId);
    const was = groupAt(model, key)?.terms.find((t) => t.id === termId);
    const say =
      was?.text === "" && term !== undefined
        ? key === "exclude"
          ? `Term ${termWritten(term)} added to the excluded terms.`
          : `Term ${termWritten(term)} added to group ${key + 1}.`
        : undefined;
    if (then === "next") {
      const added = addTerm(result.model, key, termId);
      setEditing({ termId: added.id, value: "", fresh: true, problem: null });
      focus(`term:${added.id}`);
      apply(added.model, say);
    } else {
      setEditing(null);
      apply(result.model, say);
    }
  };

  const split = (key: GroupKey, termId: number, items: readonly string[], moveFocus: boolean) => {
    const { model: next, ids } = splitTerm(model, key, termId, items);
    setEditing(null);
    const last = ids[ids.length - 1];
    if (moveFocus && last === undefined) focusAfterRemoval(key, termId);
    else if (moveFocus) focus(`term:${last}`);
    apply(
      next,
      `${ids.length} terms added to ${key === "exclude" ? "the excluded terms" : `group ${key + 1}`}.`,
    );
  };

  const cancel = (key: GroupKey, e: Editing) => {
    const term = groupAt(model, key)?.terms.find((t) => t.id === e.termId);
    setEditing(null);
    if (e.fresh && term?.text === "") {
      focusAfterRemoval(key, e.termId);
      apply(removeTerm(model, key, e.termId));
    } else {
      focus(`term:${e.termId}`);
    }
  };

  const newTerm = (key: GroupKey) => {
    const added = addTerm(model, key);
    setEditing({ termId: added.id, value: "", fresh: true, problem: null });
    focus(`term:${added.id}`);
    apply(added.model);
  };

  // ---- groups
  const move = (index: number, by: -1 | 1) => {
    const to = index + by;
    if (to < 0 || to >= nGroups) return;
    apply(
      moveGroup(model, index, by),
      `Group moved ${by < 0 ? "up" : "down"}: now group ${to + 1} of ${nGroups}.`,
    );
  };

  const dropGroup = (index: number) => {
    const previous = model.groups[index - 1] ?? model.groups[index + 1];
    focus(previous === undefined ? "add-group" : `heading:${previous.id}`);
    setEditing(null);
    const left = nGroups - 1;
    apply(
      removeGroup(model, index),
      `Group ${index + 1} removed. ${left} ${left === 1 ? "group" : "groups"}.`,
    );
  };

  const newGroup = () => {
    const next = addGroup(model);
    const group = next.groups[next.groups.length - 1];
    const term = group?.terms[0];
    if (term !== undefined) {
      setEditing({ termId: term.id, value: "", fresh: true, problem: null });
      focus(`term:${term.id}`);
    }
    apply(next, `Group ${next.groups.length} added.`);
  };

  const newExclude = () => {
    const next = addExclude(model);
    const term = next.exclude?.terms[0];
    if (term !== undefined) {
      setEditing({ termId: term.id, value: "", fresh: true, problem: null });
      focus(`term:${term.id}`);
    }
    apply(next);
  };

  const renderTerms = (key: GroupKey, group: BuilderGroup) => (
    <ul className="flex flex-wrap items-start gap-2">
      {group.terms.map((term) => {
        // a term with no text is always an open box (the Empty state, a new term), edited or not yet
        const edit: Editing | null =
          editing?.termId === term.id
            ? editing
            : term.text === ""
              ? { termId: term.id, value: "", fresh: true, problem: null }
              : null;
        return (
          <TermChip
            key={term.id}
            term={term}
            groupNumber={groupNumber(key)}
            editing={edit}
            items={termItems.get(term.id) ?? []}
            leftOut={unsafe.has(term.id)}
            helpId={termHelpId}
            onStartEdit={() => startEdit(term)}
            onChange={(value) =>
              setEditing({ termId: term.id, value, fresh: edit?.fresh ?? false, problem: null })
            }
            onCommit={(then) => edit !== null && commit(key, term.id, edit.value, then)}
            onSplit={(items, moveFocus) => split(key, term.id, items, moveFocus)}
            onKeepPhrase={() => {
              if (edit === null) return;
              // one phrase: the list separators stay inside the quotes, where they are punctuation
              const result = commitTerm(model, key, term.id, edit.value, "phrase");
              if (result.kind === "ok") {
                setEditing(null);
                focus(`term:${term.id}`);
                apply(result.model);
              }
            }}
            onCancel={() => edit !== null && cancel(key, edit)}
            onRemove={() => dropTerm(key, term)}
            onScope={(scope) => apply(setScope(model, key, term.id, scope))}
          />
        );
      })}
      <li>
        <button type="button" data-focus={`add:${group.id}`} className={BUTTON} onClick={() => newTerm(key)}>
          + term
        </button>
      </li>
    </ul>
  );

  return (
    <div ref={root} className="space-y-3 text-sm">
      <p id={hintId} className="text-muted-foreground">
        Papers must match every group. Within a group, any term is enough (OR).
      </p>
      <span id={termHelpId} className="sr-only">
        Enter edits the term, Delete removes it.
      </span>
      {misread && (
        <p role="alert" className="rounded-md border border-warn-border bg-warn-bg p-2 text-warn-fg">
          The server reads the builder&apos;s query differently from these groups, so don&apos;t rely on them
          —{" "}
          <button
            type="button"
            className="inline-flex min-h-6 min-w-6 items-center underline"
            onClick={() => props.onEditInText()}
          >
            check it in Text
          </button>
          .
        </p>
      )}
      {written.limitsUnsafe && (
        <p role="alert" className="rounded-md border border-warn-border bg-warn-bg p-2 text-warn-fg">
          The builder can&apos;t rewrite this query without changing its limits, so edits here aren&apos;t
          applied. Edit it in Text.
        </p>
      )}
      <ol className="space-y-2" aria-describedby={hintId}>
        {model.groups.map((group, index) => (
          <li key={group.id} className="space-y-2">
            {index > 0 && <p className="text-xs font-bold tracking-wide">AND</p>}
            <GroupBox
              label={groupLabel(index, nGroups, group)}
              onMove={(by) => move(index, by)}
              heading={
                <h3 tabIndex={-1} data-focus={`heading:${group.id}`} className="font-medium">
                  Group {index + 1} <span className="text-muted-foreground">of {nGroups}</span>
                </h3>
              }
              actions={
                <>
                  <button
                    type="button"
                    aria-label="Move group up"
                    aria-disabled={index === 0}
                    className={BUTTON}
                    onClick={() => move(index, -1)}
                  >
                    <span aria-hidden="true">↑</span>
                  </button>
                  <button
                    type="button"
                    aria-label="Move group down"
                    aria-disabled={index === nGroups - 1}
                    className={BUTTON}
                    onClick={() => move(index, 1)}
                  >
                    <span aria-hidden="true">↓</span>
                  </button>
                  <button type="button" className={BUTTON} onClick={() => dropGroup(index)}>
                    Remove group
                  </button>
                </>
              }
            >
              {renderTerms(index, group)}
              <GroupExpansions group={group} keys={keys} expansions={props.expansions ?? null} />
            </GroupBox>
          </li>
        ))}
      </ol>
      {model.exclude !== null && (
        <div className="space-y-2">
          <p className="text-xs font-bold tracking-wide">AND NOT</p>
          <GroupBox
            label={excludeLabel(model.exclude)}
            heading={
              <h3 tabIndex={-1} data-focus="heading:exclude" className="font-medium">
                Leave out papers with any of:
              </h3>
            }
            actions={
              <button
                type="button"
                className={BUTTON}
                onClick={() => {
                  focus("add-group");
                  setEditing(null);
                  apply(removeExclude(model), "Excluded terms removed.");
                }}
              >
                Remove excluded terms
              </button>
            }
          >
            {renderTerms("exclude", model.exclude)}
            <GroupExpansions group={model.exclude} keys={keys} expansions={props.expansions ?? null} />
          </GroupBox>
        </div>
      )}
      <div className="flex flex-wrap gap-2">
        <button type="button" data-focus="add-group" className={BUTTON} onClick={newGroup}>
          + Add group
        </button>
        {model.exclude === null && (
          <button type="button" className={BUTTON} onClick={newExclude}>
            + Exclude terms
          </button>
        )}
      </div>
      {model.limits.length > 0 && (
        <p className="break-words">
          Limits:{" "}
          {model.limits.map((limit, i) => (
            <code key={i} className="mr-2 rounded-sm border px-1 font-mono wrap-anywhere">
              {limit}
            </code>
          ))}
          <span className="text-muted-foreground">
            (search first to edit them in Filters, or edit them in Text)
          </span>
        </p>
      )}
      <div className="flex flex-wrap items-start gap-2">
        <span>Query text:</span>
        <code className="min-w-0 flex-1 font-mono break-all">{text === "" ? "(empty query)" : text}</code>
        {text !== "" && <CopyButton text={text} label="Copy query text" />}
      </div>
      <div aria-live="polite" className="sr-only">
        {announcement}
      </div>
    </div>
  );
}

function GroupBox({
  label,
  heading,
  actions,
  onMove,
  children,
}: {
  label: string;
  heading: ReactNode;
  actions?: ReactNode;
  onMove?: (by: -1 | 1) => void;
  children: ReactNode;
}) {
  // Alt+↑/↓ anywhere in a group moves it, as its buttons do (design §Keyboard)
  const onKeyDown = (e: KeyboardEvent) => {
    if (onMove === undefined || !e.altKey || (e.key !== "ArrowUp" && e.key !== "ArrowDown")) return;
    e.preventDefault();
    onMove(e.key === "ArrowUp" ? -1 : 1);
  };
  return (
    <section
      role="group"
      aria-label={label}
      onKeyDown={onKeyDown}
      className="space-y-2 rounded-md border p-2"
    >
      <div className="flex flex-wrap items-center gap-2">
        {heading}
        {actions !== undefined && <div className="ml-auto flex gap-1">{actions}</div>}
      </div>
      {children}
    </section>
  );
}

interface TermChipProps {
  readonly term: BuilderTerm;
  readonly groupNumber: number | null;
  readonly editing: Editing | null;
  readonly items: readonly Item[];
  readonly leftOut: boolean;
  readonly helpId: string;
  readonly onStartEdit: () => void;
  readonly onChange: (value: string) => void;
  readonly onCommit: (then: "next" | "blur") => void;
  readonly onSplit: (items: readonly string[], moveFocus: boolean) => void;
  readonly onKeepPhrase: () => void;
  readonly onCancel: () => void;
  readonly onRemove: () => void;
  readonly onScope: (scope: Scope) => void;
}

function TermChip(p: TermChipProps) {
  const inputId = useId();
  const scopeId = useId();
  const noteId = useId();
  const container = useRef<HTMLLIElement>(null);
  // Set once a key has settled the edit, so the blur of the box going away doesn't settle it again
  const settled = useRef(false);
  const shown = termWritten(p.term);

  if (p.editing !== null) {
    const { value, problem } = p.editing;
    const items = listItems(value);
    const settle = (f: () => void) => {
      settled.current = true;
      f();
    };
    return (
      <li ref={container} className="flex flex-wrap items-center gap-1">
        <label htmlFor={inputId} className="sr-only">
          {p.groupNumber === null ? "Term to leave out" : `Term in group ${p.groupNumber}`}
        </label>
        <input
          id={inputId}
          data-focus={`term:${p.term.id}`}
          value={value}
          aria-describedby={problem === null ? undefined : noteId}
          aria-invalid={problem !== null}
          onChange={(e) => {
            settled.current = false;
            p.onChange(e.target.value);
          }}
          onPaste={(e) => {
            // an <input> drops line breaks, so a pasted column of terms keeps them as list separators
            const pasted = e.clipboardData.getData("text");
            if (!pasted.includes("\n")) return;
            e.preventDefault();
            const el = e.currentTarget;
            const at = el.selectionStart ?? value.length;
            const end = el.selectionEnd ?? at;
            p.onChange(value.slice(0, at) + pasted.replace(/\r?\n/gu, "; ") + value.slice(end));
          }}
          onFocus={() => {
            settled.current = false;
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault(); // never submits the search form: Enter is the term's own action
              settle(() => (items !== null ? p.onSplit(items, true) : p.onCommit("next")));
            } else if (e.key === "Escape") {
              e.preventDefault();
              settle(p.onCancel);
            } else if (e.key === "Backspace" && value === "") {
              e.preventDefault();
              settle(p.onRemove);
            }
          }}
          onBlur={(e) => {
            if (settled.current) return;
            if (e.relatedTarget instanceof Node && container.current?.contains(e.relatedTarget)) return;
            if (items !== null) p.onSplit(items, false);
            else p.onCommit("blur");
          }}
          className="min-h-8 w-48 rounded-md border border-input bg-background px-2 font-mono"
        />
        {items !== null && (
          <>
            <button type="button" className={BUTTON} onClick={() => settle(() => p.onSplit(items, true))}>
              Split into {items.length} terms
            </button>
            <button type="button" className={BUTTON} onClick={() => settle(p.onKeepPhrase)}>
              Keep as one phrase
            </button>
          </>
        )}
        {problem !== null && (
          <p id={noteId} className="w-full text-diag-error">
            <span aria-hidden="true">✖ </span>
            <span className="sr-only">Error: </span>
            {problem}
          </p>
        )}
      </li>
    );
  }

  const notes = [
    ...(p.term.phrased ? ["searched as one phrase"] : []),
    ...(p.leftOut
      ? ["left out of the query: next to the other terms it wouldn't be read as one term — edit it"]
      : []),
  ];
  return (
    <li className="space-y-1">
      <span className="inline-flex items-center gap-1 rounded-md border bg-muted/40 px-1">
        <button
          type="button"
          data-focus={`term:${p.term.id}`}
          aria-describedby={`${p.helpId}${notes.length > 0 || p.items.length > 0 ? ` ${noteId}` : ""}`}
          className="min-h-6 px-1 font-mono hover:underline"
          onClick={p.onStartEdit}
          onKeyDown={(e) => {
            if (e.key === "Delete" || e.key === "Backspace") {
              e.preventDefault();
              p.onRemove();
            }
          }}
        >
          {shown === "" ? "(empty)" : shown}
        </button>
        <label htmlFor={scopeId} className="sr-only">
          Search in:
        </label>
        <select
          id={scopeId}
          value={p.term.scope}
          onChange={(e) =>
            p.onScope(
              e.target.value === "title" ? "title" : e.target.value === "abstract" ? "abstract" : "any",
            )
          }
          className="min-h-6 rounded-sm border-0 bg-transparent text-xs text-muted-foreground"
        >
          {(Object.keys(SCOPE_LABELS) as Scope[]).map((s) => (
            <option key={s} value={s}>
              {SCOPE_LABELS[s]}
            </option>
          ))}
        </select>
        <button
          type="button"
          aria-label={`Remove term ${shown}`}
          className="min-h-6 min-w-6 rounded-sm hover:bg-muted"
          onClick={p.onRemove}
        >
          <span aria-hidden="true">×</span>
        </button>
      </span>
      {(notes.length > 0 || p.items.length > 0) && (
        <div id={noteId} className="text-xs">
          {notes.map((n) => (
            <p key={n} className={p.leftOut ? "text-diag-error" : "text-muted-foreground"}>
              {n}
            </p>
          ))}
          {p.items.map((item, i) => (
            <p key={i} className="break-words">
              <span aria-hidden="true" className={`mr-1 font-bold ${TONE[item.severity]}`}>
                {GLYPH[item.severity]}
              </span>
              <span className="sr-only">{PREFIX[item.severity]} </span>
              {item.message}
            </p>
          ))}
        </div>
      )}
    </li>
  );
}

/** A group's wildcards that the last `/search` expanded, one line each (as the Expansions row words them). */
function GroupExpansions({
  group,
  keys,
  expansions,
}: {
  group: BuilderGroup;
  keys: WildcardKeys;
  expansions: Expansions | null;
}) {
  if (expansions === null) return null;
  const stems = [...new Set(group.terms.flatMap((t) => keys.get(t.id) ?? []))].filter((k) =>
    Object.hasOwn(expansions, k),
  );
  if (stems.length === 0) return null;
  return (
    <ul aria-label="Expansions" className="space-y-1 text-xs">
      {stems.map((stem) => (
        <ExpansionLine key={stem} stem={stem} terms={expansions[stem] ?? []} />
      ))}
    </ul>
  );
}

/**
 * The parts of a read-only query that fit (design B2; copy BD-11): its groups, Exclude row and limits, dimmed
 * and with no editing controls (a long expansion's `+N more` is the only button), so the reader sees what the
 * builder understood. Groups are numbered without "of m": the parts that don't fit aren't counted. No BD-4
 * tail on the limits, since nothing here is editable.
 */
function FittingParts({
  model,
  keys,
  expansions,
}: {
  model: BuilderModel;
  keys: WildcardKeys;
  expansions: Expansions | null;
}) {
  const headingId = useId();
  const n = model.groups.length;
  if (n === 0 && model.exclude === null && model.limits.length === 0) return null;
  const terms = (group: BuilderGroup) => (
    <>
      <ul className="flex flex-wrap items-start gap-2">
        {group.terms.map((t) => (
          <li key={t.id}>
            <code className="rounded-md border border-dashed px-1 font-mono wrap-anywhere">
              {termWritten(t)}
            </code>
          </li>
        ))}
      </ul>
      <GroupExpansions group={group} keys={keys} expansions={expansions} />
    </>
  );
  return (
    <section aria-labelledby={headingId} className="space-y-2 text-muted-foreground">
      <h3 id={headingId} className="font-medium">
        Parts that fit the builder
      </h3>
      <p>Anything that doesn&apos;t fit is left out. Nothing here can be edited.</p>
      <ol className="space-y-2">
        {model.groups.map((group, index) => (
          <li key={group.id} className="space-y-2">
            {index > 0 && <p className="text-xs font-bold tracking-wide">AND</p>}
            <GroupBox
              label={`Group ${index + 1}, any of: ${termList(group)}`}
              heading={<h4 className="font-medium">Group {index + 1}</h4>}
            >
              {terms(group)}
            </GroupBox>
          </li>
        ))}
      </ol>
      {model.exclude !== null && (
        <div className="space-y-2">
          {n > 0 && <p className="text-xs font-bold tracking-wide">AND NOT</p>}
          <GroupBox
            label={excludeLabel(model.exclude)}
            heading={<h4 className="font-medium">Leave out papers with any of:</h4>}
          >
            {terms(model.exclude)}
          </GroupBox>
        </div>
      )}
      {model.limits.length > 0 && (
        <p className="break-words">
          Limits:{" "}
          {model.limits.map((limit, i) => (
            <code key={i} className="mr-2 rounded-sm border border-dashed px-1 font-mono wrap-anywhere">
              {limit}
            </code>
          ))}
        </p>
      )}
    </section>
  );
}

function ReadOnly({
  initial,
  slow,
  text,
  onEditInText,
  onRetry,
  expansions,
}: {
  initial: Initial | null;
  slow: boolean;
  text: string;
  onEditInText: (span?: CodePoints) => void;
  onRetry: () => void;
  expansions: Expansions | null;
}) {
  const box = "space-y-2 rounded-md border border-warn-border bg-warn-bg p-3 text-warn-fg";
  const edit = (
    <button type="button" className={BUTTON} onClick={() => onEditInText()}>
      Edit in Text
    </button>
  );
  switch (initial?.kind) {
    case "errors":
      return (
        <div className={box}>
          <h3 tabIndex={-1} data-focus="notice" className="font-medium">
            The query has errors, so the builder can&apos;t show it.
          </h3>
          <p>Fix them in Text. ({countText(initial.items)})</p>
          {edit}
        </div>
      );
    case "blocked": {
      const { blocker } = initial;
      return (
        <>
          <div className={box}>
            <h3 tabIndex={-1} data-focus="notice" className="font-medium">
              This query is too complex for the builder
            </h3>
            <p className="break-words">
              <code className="font-mono wrap-anywhere">{constructText(text, blocker)}</code> ({blocker.kind})
              doesn&apos;t fit groups of alternatives. The builder shows lists of terms joined by OR, combined
              with AND. Your query is unchanged.
            </p>
            <div className="flex flex-wrap gap-2">
              {edit}
              <button type="button" className={BUTTON} onClick={() => onEditInText(blocker.span)}>
                Show it in the text
              </button>
            </div>
          </div>
          <FittingParts model={initial.fitting} keys={initial.keys} expansions={expansions} />
        </>
      );
    }
    case "unchecked":
      return (
        <div className={box}>
          <h3 tabIndex={-1} data-focus="notice" className="font-medium">
            The query couldn&apos;t be checked, so the builder can&apos;t show it yet.
          </h3>
          <div className="flex flex-wrap gap-2">
            <button type="button" className={BUTTON} onClick={onRetry}>
              Check again
            </button>
            {edit}
          </div>
        </div>
      );
    default:
      return (
        <p role="status" className="min-h-5 text-muted-foreground">
          {slow ? "Reading the query…" : ""}
        </p>
      );
  }
}
