"use client";

/**
 * The methods text of a record, or the caution that replaces it (spec 05 §Components 8; design §Methods text
 * rules, R6; copy RC-11, RC-12). A read-only region with Copy, not a textarea (no accidental edits). The
 * caller renders it only when the replay isn't a `mismatch` (design R4).
 */
import { useId } from "react";
import { citabilityCaution, methodsText, type SearchRecord } from "@/lib/methods-text";
import { CopyButton } from "../copy-button";
import { useRecordParses } from "./use-record";

export function MethodsBlock({ record, url }: { record: SearchRecord; url: string }) {
  const headingId = useId();
  const caution = citabilityCaution(record);
  const parses = useRecordParses(caution === null ? record : null);
  if (caution !== null) {
    return (
      <section
        aria-label="Methods text"
        className="rounded-md border border-warn-border bg-warn-bg p-3 text-sm text-warn-fg"
      >
        <p className="break-words">
          <span aria-hidden="true">⚠ </span>
          {caution}.
        </p>
      </section>
    );
  }
  const text = parses.settled
    ? methodsText({
        record,
        parseCanonical: parses.canonical,
        parseIdentification: parses.identification,
        url,
      })
    : null;
  return (
    <section aria-labelledby={headingId} className="space-y-2 text-sm">
      <div className="flex flex-wrap items-center gap-3">
        <h2 id={headingId} className="text-base font-semibold">
          Methods text
        </h2>
        {text !== null && <CopyButton text={text} label="Copy methods text" />}
      </div>
      {text === null ? (
        <p role="status" className="text-muted-foreground">
          Writing the methods text…
        </p>
      ) : (
        <p
          role="region"
          aria-label="Methods text to cite"
          className="rounded-md border bg-muted/40 p-3 break-words"
        >
          {text}
        </p>
      )}
    </section>
  );
}
