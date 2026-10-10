"use client";

/**
 * The home page's coverage line (design W1, copy deck CV-1; TASK-110): one `GET /coverage` answer, in the
 * same words `/coverage` uses for the same facts (the pages fetch separately, so right after an index swap
 * they can briefly show different answers). It shows only what the API
 * serves (no owner-accepted exceptions: those live in the gate report, spec 07 §C). While the answer is
 * loading, or when it fails, the line is left out: never a placeholder number.
 */
import Link from "next/link";
import { useCoverage } from "@/api/hooks";
import type { Schemas } from "@/api/client";
import { spanRange, yearSpans } from "./coverage-report";
import { corpusWindow, count } from "./format";

/** Each venue with records and its first and last year, A–Z, in `/coverage`'s words (CV-7's `yearSpans`), so a
 * reader sees on the home page that the venues cover different years (IASEAI one, AIES two). */
function venues(coverage: Schemas["CoverageResponse"]): string[] {
  return yearSpans(coverage.venue_years).map(spanRange);
}

export function CoverageLine() {
  const coverage = useCoverage();
  if (coverage === null) return null;
  const window = corpusWindow(coverage.snapshot);
  const names = venues(coverage);
  return (
    <p className="text-muted-foreground">
      Index <code className="font-mono break-all">{coverage.index_version}</code> ·{" "}
      <span className="tabular-nums">{count(coverage.totals.records)}</span> records indexed
      {names.length > 0 ? ` · ${names.join(", ")}` : null}
      {window === null ? null : (
        <>
          {" · "}
          <span className="tabular-nums">{window}</span>
        </>
      )}
      {" · "}
      <Link href="/coverage" className="underline underline-offset-4">
        Coverage ▸
      </Link>
    </p>
  );
}
