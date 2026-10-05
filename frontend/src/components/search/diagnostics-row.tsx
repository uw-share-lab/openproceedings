"use client";

/**
 * The diagnostics row (spec 05 §Components 1; ui-design-system §Transparency; design W3, W5–W7; copy ED-8–17).
 * Errors, then the translations ("Read as native syntax:"), then warnings, each in span order, every message
 * the server's, verbatim, its backticked runs drawn as code (`Coded`). A code that repeats is one line ("9 ×",
 * the first message, "Show all 9"); the Scholar-mode `$` notices are one line that says what `$` does, with the
 * server's notices behind "Show" (USAB-N4: after Add `$` they would otherwise warn about what it wrote). Each line has
 * a Help link, and four codes carry an action: `WARN_MIXED_AND_OR` (Show how it was read, when the tree can
 * render; Load with parentheses, when it has a reading), `FIELD_COMPAT_ONLY` (Read as Google Scholar syntax),
 * `WILDCARD_TOO_MANY_EXPANSIONS` (why it appeared only after Search) and `COMPAT_NO_STEMMING` (Add `$`, to
 * every term the server says can take one or to the ones ticked: an edit of the draft, never a search;
 * TASK-175). The row is absent when there is nothing to say.
 */
import Link from "next/link";
import { useId, useState, type ReactNode } from "react";
import { Coded } from "@/components/coded";
import { CopyButton } from "@/components/copy-button";
import {
  groupRepeats,
  helpHref,
  withParentheses,
  type Group,
  type Item,
  type Severity,
} from "@/editor/diagnostics";
import { clip } from "@/lib/clip";
import { byTerm, withWordForms, type WordForm } from "@/lib/word-forms";

const GLYPH: Readonly<Record<Severity, { glyph: string; prefix: string; className: string }>> = {
  error: { glyph: "✖", prefix: "Error:", className: "text-diag-error" },
  warning: { glyph: "⚠", prefix: "Warning:", className: "text-diag-warning" },
  info: { glyph: "↻", prefix: "Read as:", className: "text-diag-info" },
};

export interface DiagnosticsRowProps {
  readonly items: readonly Item[];
  /** "Draft — not searched" while the row is the unsearched draft's (ED-14). */
  readonly draft: boolean;
  /** An API refusal's envelope message, which heads the row (W7: the two slow-clause codes). */
  readonly lead: string | null;
  /** A line that isn't a server diagnostic: the 413 text (W11) or "couldn't be checked". */
  readonly notice: ReactNode;
  /** The text the items were reported for, and whether it is still the editor's text. */
  readonly text: string;
  readonly textIsDraft: boolean;
  /** `/parse`'s `word_forms` for `text`: where a `$` can be added to the terms `COMPAT_NO_STEMMING` names. */
  readonly wordForms: readonly WordForm[];
  /** The draft is read as native syntax, so "Read as Google Scholar syntax" can be offered. */
  readonly nativeMode: boolean;
  /** The canonical string the translations produced ("Searched as:"), when the row is the searched query's. */
  readonly searchedAs: string | null;
  /** The query tree can render (the parse has an `effective_ast`, so no errors): only then is "Show how it was
   * read" offered, since a query with errors has no tree to open (TASK-140). */
  readonly treeAvailable: boolean;
  readonly onShowTree: () => void;
  readonly onLoad: (text: string) => void;
  readonly onReadAsScholar: () => void;
}

function Actions({ group, props }: { group: Group; props: DiagnosticsRowProps }) {
  const describe = useId();
  const first = group.items[0];
  if (first === undefined) return null;
  const buttons: ReactNode[] = [];
  const button = "min-h-6 rounded-sm border px-1.5 text-xs hover:bg-muted";
  if (group.code === "WARN_MIXED_AND_OR") {
    if (props.treeAvailable) {
      buttons.push(
        <button key="show" type="button" className={button} onClick={props.onShowTree}>
          Show how it was read
        </button>,
      );
    }
    const loaded = props.textIsDraft ? withParentheses(props.text, first) : null;
    if (loaded !== null) {
      buttons.push(
        <span key="load">
          <button
            type="button"
            className={button}
            aria-describedby={`${describe}-load`}
            onClick={() => props.onLoad(loaded)}
          >
            Load with parentheses
          </button>
          <span id={`${describe}-load`} className="sr-only">
            Puts the query as it was read, with its parentheses, into the editor. Nothing is searched until
            you press Search.
          </span>
        </span>,
      );
    }
  }
  if (group.code === "FIELD_COMPAT_ONLY" && props.nativeMode) {
    buttons.push(
      <span key="scholar">
        <button
          type="button"
          className={button}
          aria-describedby={`${describe}-scholar`}
          onClick={props.onReadAsScholar}
        >
          Read as Google Scholar syntax
        </button>
        <span id={`${describe}-scholar`} className="sr-only">
          Sets Syntax to Google Scholar / PoP. Your text is unchanged; press Search to run it.
        </span>
      </span>,
    );
  }
  buttons.push(
    <Link
      key="help"
      href={helpHref(group.code)}
      aria-label={`Syntax help for ${group.code}`}
      className="underline underline-offset-4"
    >
      Help ▸
    </Link>,
  );
  return <span className="ml-2 inline-flex flex-wrap items-center gap-2 align-middle">{buttons}</span>;
}

const BUTTON = "min-h-6 rounded-sm border px-1.5 text-xs hover:bg-muted";

/**
 * Said under the no-stemming notice in both of its states (copy ED-19): word forms are the smaller part of a
 * lower count than Google Scholar's, so `$` is not presented as the way to close the gap.
 */
const FULL_TEXT = (
  <p className="text-muted-foreground">
    Google Scholar also reads the full text of a paper; openproceedings matches titles and abstracts only.
    Most of a difference in counts can come from that, and <code className="font-mono">$</code> does not
    recover it.
  </p>
);

/**
 * The one line that stands for the Scholar-mode `$` notices (`COMPAT_POP_DOLLAR`, one per `$` the query holds):
 * what the wildcard does and that counts differ from a Scholar run because of it. Presentation only: the
 * server's notices are listed under it, unchanged.
 */
function DollarSummary({ n }: { n: number }) {
  return (
    <>
      <code className="font-mono">$</code> is read as a wildcard in {n.toLocaleString("en-US")}{" "}
      {n === 1 ? "place" : "places"}: each matches its word and the word with one more letter or digit, as in
      Web of Science (Google Scholar gives <code className="font-mono">$</code> no meaning). That widening is
      what <code className="font-mono">$</code> is for, so counts differ from a Google Scholar run of the same
      string.
    </>
  );
}

/** Why a term the notice names has no `$` on offer (spec 02 §Word forms; copy ED-19). */
const NOT_OFFERED = (
  <>
    A term is left as typed when it has too few letters or digits, has a symbol or another{" "}
    <code className="font-mono">$</code> beside it, or is a lowercase <code className="font-mono">and</code>,{" "}
    <code className="font-mono">or</code> or <code className="font-mono">not</code>.
  </>
);

/**
 * "Add `$`" under the no-stemming notice (TASK-175): the notice's own suggestion, written into the draft at
 * the places the server reported (`word_forms`), for every term or for the ones ticked. Offered only while the
 * editor still holds the text the forms were reported for.
 */
function WordForms({ props }: { props: DiagnosticsRowProps }) {
  const id = useId();
  const [choosing, setChoosing] = useState(false);
  const [ticked, setTicked] = useState<ReadonlySet<string>>(new Set());
  const terms = byTerm(props.wordForms);
  if (!props.textIsDraft || withWordForms(props.text, props.wordForms) === null) return null;
  if (terms.length === 0) {
    // the notice names terms, and the server found no place for a `$` (or the query can't grow): say so
    return (
      <div className="mt-1 space-y-1.5">
        <p className="text-muted-foreground">
          <code className="font-mono">$</code> can&apos;t be added to these terms for you. {NOT_OFFERED} The
          same happens when the query would be over the length limit with <code className="font-mono">$</code>{" "}
          added. Type a wildcard yourself where one is valid.
        </p>
        {FULL_TEXT}
      </div>
    );
  }
  const picked = terms.filter((t) => ticked.has(t.term));
  const add = (forms: readonly WordForm[]) => {
    const text = withWordForms(props.text, forms);
    if (text === null) return;
    setTicked(new Set());
    props.onLoad(text);
  };
  const n = terms.length.toLocaleString("en-US");
  return (
    <div className="mt-1 space-y-1.5">
      <p className="text-muted-foreground">
        <code className="font-mono">$</code> after a term also matches it with one more letter or digit:{" "}
        <code className="font-mono">benchmark$</code> matches <code className="font-mono">benchmark</code> and{" "}
        <code className="font-mono">benchmarks</code>, not <code className="font-mono">benchmarking</code>.
        That is fewer forms than Google Scholar counts; type <code className="font-mono">*</code> for any
        ending.
      </p>
      {FULL_TEXT}
      <p className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          className={BUTTON}
          aria-describedby={`${id}-all`}
          onClick={() => add(props.wordForms)}
        >
          {terms.length === 1 ? "Add $ to 1 term" : `Add $ to all ${n} terms`}
        </button>
        <span id={`${id}-all`} className="sr-only">
          Puts $ in the editor after each term this notice names that can take one. A phrase gets it on its
          last word. Nothing is searched until you press Search.
        </span>
        {terms.length > 1 && (
          <button
            type="button"
            className={BUTTON}
            aria-expanded={choosing}
            aria-controls={`${id}-terms`}
            onClick={() => setChoosing(!choosing)}
          >
            Choose terms
          </button>
        )}
      </p>
      {terms.length > 1 && choosing && (
        <fieldset id={`${id}-terms`} className="space-y-1 rounded-sm border px-2 pb-2">
          <legend className="px-1 text-xs font-semibold">Add $ to</legend>
          <ul className="flex flex-wrap gap-x-4 gap-y-0.5">
            {terms.map(({ term, forms }) => (
              <li key={term}>
                <label className="flex min-h-6 items-center gap-2">
                  <input
                    type="checkbox"
                    className="size-4 shrink-0"
                    checked={ticked.has(term)}
                    onChange={(e) => {
                      const next = new Set(ticked);
                      if (e.target.checked) next.add(term);
                      else next.delete(term);
                      setTicked(next);
                    }}
                  />
                  <span>
                    <code className="font-mono">{clip(term)}</code>
                    {term.includes(" ") && " (phrase: on its last word)"}
                    {forms.length > 1 && ` (written ${forms.length.toLocaleString("en-US")} times)`}
                  </span>
                </label>
              </li>
            ))}
          </ul>
          <p className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              className={`${BUTTON} ${picked.length === 0 ? "opacity-60" : ""}`}
              aria-disabled={picked.length === 0 ? true : undefined}
              aria-describedby={`${id}-picked`}
              onClick={() => {
                if (picked.length > 0) add(picked.flatMap((t) => t.forms));
              }}
            >
              Add $ to the ticked terms
            </button>
            {/* the reason a dimmed button does nothing is read by everyone, not only by a screen reader */}
            <span id={`${id}-picked`} className={picked.length === 0 ? "text-muted-foreground" : "sr-only"}>
              {picked.length === 0
                ? "Tick at least one term first."
                : "Puts $ in the editor after each ticked term. Nothing is searched until you press Search."}
            </span>
          </p>
          <p className="text-muted-foreground">
            A term the notice names that is not listed here can&apos;t take{" "}
            <code className="font-mono">$</code> as typed. {NOT_OFFERED}
          </p>
        </fieldset>
      )}
    </div>
  );
}

function Line({ group, props }: { group: Group; props: DiagnosticsRowProps }) {
  const [all, setAll] = useState(false);
  const { glyph, prefix, className } = GLYPH[group.severity];
  const first = group.items[0];
  if (first === undefined) return null;
  const n = group.items.length;
  const dollars = group.code === "COMPAT_POP_DOLLAR";
  const count = n.toLocaleString("en-US");
  return (
    <li className="break-words">
      <span aria-hidden="true" className={`mr-1.5 font-bold ${className}`}>
        {glyph}
      </span>
      <span className="sr-only">{prefix} </span>
      {n > 1 && !dollars && <span className="font-semibold tabular-nums">{count} × </span>}
      {dollars ? <DollarSummary n={n} /> : <Coded text={first.message} />}
      <Actions group={group} props={props} />
      {group.code === "COMPAT_NO_STEMMING" && <WordForms props={props} />}
      {group.code === "WILDCARD_TOO_MANY_EXPANSIONS" && (
        <span className="block text-muted-foreground">
          Only a search can count expansions, so this appears after Search, not while typing.
        </span>
      )}
      {(n > 1 || dollars) && (
        <>
          {" "}
          <button
            type="button"
            aria-expanded={all}
            onClick={() => setAll(!all)}
            className="min-h-6 rounded-sm border px-1.5 text-xs hover:bg-muted"
          >
            {dollars
              ? all
                ? n === 1
                  ? "Hide the notice"
                  : "Hide the notices"
                : n === 1
                  ? "Show the notice"
                  : `Show all ${count} notices`
              : all
                ? "Show fewer"
                : `Show all ${count}`}
          </button>
          {all && (
            <ul className="mt-1 ml-5 list-disc space-y-0.5">
              {group.items.map((item, i) => (
                <li key={i}>
                  <Coded text={item.message} />
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </li>
  );
}

export function DiagnosticsRow(props: DiagnosticsRowProps) {
  const groups = groupRepeats(props.items);
  const of = (severity: Severity) => groups.filter((g) => g.severity === severity);
  const [errors, translations, warnings] = [of("error"), of("info"), of("warning")];
  if (groups.length === 0 && props.lead === null && !props.notice) return null;
  const list = (gs: Group[], label: string) =>
    gs.length > 0 && (
      <ul aria-label={label} className="space-y-1">
        {gs.map((g) => (
          <Line key={`${g.severity}-${g.code}`} group={g} props={props} />
        ))}
      </ul>
    );
  return (
    <section aria-label="Diagnostics" className="space-y-1.5 text-sm">
      {props.draft && <h2 className="text-xs font-semibold">Draft — not searched</h2>}
      {props.lead !== null && <p className="font-semibold">{props.lead}</p>}
      {props.notice}
      {list(errors, "Errors")}
      {translations.length > 0 && (
        <div className="space-y-1">
          <h3 className="font-semibold">Read as native syntax:</h3>
          {list(translations, "Translations")}
          {props.searchedAs !== null && (
            <p className="flex flex-wrap items-start gap-2">
              <span>Searched as:</span>
              <code className="font-mono break-all">{props.searchedAs}</code>
              <CopyButton text={props.searchedAs} label="Copy the query as searched" />
            </p>
          )}
        </div>
      )}
      {list(warnings, "Warnings")}
    </section>
  );
}
