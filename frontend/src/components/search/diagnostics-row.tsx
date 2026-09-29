"use client";

/**
 * The diagnostics row (spec 05 §Components 1; ui-design-system §Transparency; design W3, W5–W7; copy ED-8–17).
 * Errors, then the translations ("Read as native syntax:"), then warnings, each in span order, every message
 * the server's, verbatim. A code that repeats is one line ("9 ×", the first message, "Show all 9"). Each line has
 * a Help link, and three codes carry an action: `WARN_MIXED_AND_OR` (Show how it was read, Load with
 * parentheses), `FIELD_COMPAT_ONLY` (Read as Google Scholar syntax) and `WILDCARD_TOO_MANY_EXPANSIONS` (why it
 * appeared only after Search). The row is absent when there is nothing to say.
 */
import Link from "next/link";
import { useId, useState, type ReactNode } from "react";
import { CopyButton } from "@/components/copy-button";
import {
  groupRepeats,
  helpHref,
  withParentheses,
  type Group,
  type Item,
  type Severity,
} from "@/editor/diagnostics";

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
  /** The draft is read as native syntax, so "Read as Google Scholar syntax" can be offered. */
  readonly nativeMode: boolean;
  /** The canonical string the translations produced ("Searched as:"), when the row is the searched query's. */
  readonly searchedAs: string | null;
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
    buttons.push(
      <button key="show" type="button" className={button} onClick={props.onShowTree}>
        Show how it was read
      </button>,
    );
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

function Line({ group, props }: { group: Group; props: DiagnosticsRowProps }) {
  const [all, setAll] = useState(false);
  const { glyph, prefix, className } = GLYPH[group.severity];
  const first = group.items[0];
  if (first === undefined) return null;
  const n = group.items.length;
  return (
    <li className="break-words">
      <span aria-hidden="true" className={`mr-1.5 font-bold ${className}`}>
        {glyph}
      </span>
      <span className="sr-only">{prefix} </span>
      {n > 1 && <span className="font-semibold tabular-nums">{n.toLocaleString("en-US")} × </span>}
      {first.message}
      <Actions group={group} props={props} />
      {group.code === "WILDCARD_TOO_MANY_EXPANSIONS" && (
        <span className="block text-muted-foreground">
          Only a search can count expansions, so this appears after Search, not while typing.
        </span>
      )}
      {n > 1 && (
        <>
          {" "}
          <button
            type="button"
            aria-expanded={all}
            onClick={() => setAll(!all)}
            className="min-h-6 rounded-sm border px-1.5 text-xs hover:bg-muted"
          >
            {all ? "Show fewer" : `Show all ${n.toLocaleString("en-US")}`}
          </button>
          {all && (
            <ul className="mt-1 ml-5 list-disc space-y-0.5">
              {group.items.map((item, i) => (
                <li key={i}>{item.message}</li>
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
