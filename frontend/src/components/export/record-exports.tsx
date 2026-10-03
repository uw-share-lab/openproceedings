"use client";

/**
 * A record's exports (spec 05 §Pages: they **must** call `/export?record_id=`; design R1, R5; copy RC-13): the
 * record's stored ids, from the index it names, never a re-run of its query. The row states the count before
 * the click. When the replay shows the record's index isn't on this instance, the buttons are disabled with
 * the reason (the record and its methods text stay valid).
 */
import { useId } from "react";
import { plural } from "@/editor/diagnostics";
import { FORMATS } from "@/lib/export";
import { CovidenceHelp } from "./covidence-help";
import { button, ExportNotice, RemovedNotice, WithheldNotice } from "./export-notice";
import { useExport } from "./use-export";

export function RecordExports({
  recordId,
  indexVersion,
  total,
  indexGone,
}: {
  recordId: string;
  indexVersion: string;
  total: number;
  indexGone: boolean;
}) {
  const exporter = useExport({ kind: "record", recordId, indexVersion, total });
  const headingId = useId();
  const reasonId = useId();
  return (
    <section aria-labelledby={headingId} className="space-y-2 text-sm">
      <h2 id={headingId} className="text-base font-semibold">
        Export
      </h2>
      <p className="break-words">
        Export the {plural(total, "paper")} this record cites, from index{" "}
        <code className="font-mono break-all">{indexVersion}</code>:
      </p>
      {indexGone && (
        <p id={reasonId} className="break-words text-muted-foreground">
          Index <code className="font-mono break-all">{indexVersion}</code>, which this record&apos;s papers
          come from, isn&apos;t on this instance, so they can&apos;t be exported here. The record and its
          methods text are still valid.
        </p>
      )}
      <div className="flex flex-wrap gap-2">
        {FORMATS.map((f) => {
          const busy = exporter.busy === f.format;
          const off = indexGone || exporter.busy !== null;
          return (
            <button
              key={f.format}
              type="button"
              aria-disabled={off ? true : undefined}
              aria-describedby={indexGone ? reasonId : undefined}
              aria-label={
                busy ? `Preparing ${plural(total, "paper")}…` : `${f.label}, ${plural(total, "paper")}`
              }
              onClick={() => {
                if (!off) exporter.start(f.format);
              }}
              className={`${button} ${off && !busy ? "opacity-60" : ""}`}
            >
              {busy ? "Preparing…" : f.label}
            </button>
          );
        })}
      </div>
      <p role="status" aria-live="polite" className="sr-only">
        {exporter.announcement}
      </p>
      {exporter.notice !== null && (
        <ExportNotice result={exporter.notice} onRetry={exporter.retry} onSearchAgain={null} />
      )}
      {exporter.withheld && <WithheldNotice />}
      {exporter.removed > 0 && <RemovedNotice n={exporter.removed} />}
      <CovidenceHelp />
    </section>
  );
}
