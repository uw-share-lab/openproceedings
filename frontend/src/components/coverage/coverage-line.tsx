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
import { corpusWindow, count } from "./format";

/** The venues with records, in the API's order (venue A–Z, as `/coverage` lists them). */
function venues(coverage: Schemas["CoverageResponse"]): string[] {
  // a Set keeps first-insertion order, so this keeps the API's order and drops only repeats, never a venue
  return [...new Set(coverage.venue_years.map((vy) => vy.venue))];
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
