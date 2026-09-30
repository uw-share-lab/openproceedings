"use client";

/**
 * The expansions of a search's wildcards (guarantee 6; ui-design-system §Transparency; design W5, W8; copy
 * EX-1–5): one line per key of `query.expansions`, as the server keys it, the first 8 terms and a `+N more`
 * button that shows the rest in place. Never truncated without the count; a wildcard that expanded to nothing
 * says so. The terms are the server's list, in its order. The builder shows the same lines under each group
 * (`ExpansionLine`, TASK-111).
 */
import { useState } from "react";
import type { Schemas } from "@/api/client";
import { plural } from "@/editor/diagnostics";

export const SHOWN_TERMS = 8;

export function ExpansionLine({ stem, terms }: { stem: string; terms: readonly string[] }) {
  const [all, setAll] = useState(false);
  const hidden = terms.length - SHOWN_TERMS;
  const shown = all || hidden <= 0 ? terms : terms.slice(0, SHOWN_TERMS);
  return (
    <li className="break-words">
      <code className="font-mono">{stem}</code>
      <span aria-hidden="true"> →</span>
      {terms.length === 0 ? (
        <>
          <span aria-hidden="true"> (no indexed words)</span>
          <span className="sr-only"> expands to no indexed words</span>
        </>
      ) : (
        <>
          <span className="sr-only"> expands to {plural(terms.length, "word")}:</span>{" "}
          <span className="font-mono">{shown.join(", ")}</span>
          {hidden > 0 && (
            <>
              {" "}
              <button
                type="button"
                aria-expanded={all}
                onClick={() => setAll(!all)}
                className="min-h-6 min-w-6 rounded-sm border px-1.5 text-xs hover:bg-muted"
              >
                {all ? "Show fewer" : `+${hidden.toLocaleString("en-US")} more`}
              </button>
            </>
          )}
        </>
      )}
    </li>
  );
}

export function ExpansionsRow({ expansions }: { expansions: Schemas["QueryInfo"]["expansions"] }) {
  const stems = Object.keys(expansions);
  return (
    <section aria-label="Expansions" className="flex flex-wrap gap-x-3 text-sm">
      <h2 className="font-semibold">Expansions</h2>
      {stems.length === 0 ? (
        <p className="text-muted-foreground">(none: the query has no wildcards)</p>
      ) : (
        <ul className="min-w-0 flex-1 space-y-1">
          {stems.map((stem) => (
            <ExpansionLine key={stem} stem={stem} terms={expansions[stem] ?? []} />
          ))}
        </ul>
      )}
    </section>
  );
}
