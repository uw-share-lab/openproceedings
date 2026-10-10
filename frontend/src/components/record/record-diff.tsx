"use client";

/**
 * A drifted record's diff (design R2; copy RC-14): `GET /records/{id}/diff`, 50 per page, two lists, "Added"
 * and "Removed", each paper a link to its page or, when the index the replay ran on doesn't hold it, its id.
 * Opened on request (the diff re-runs the query: the export weight). Each removed paper says why the re-run
 * no longer finds it, and a line tallies the causes over the whole removed list (TASK-227; copy RC-14a).
 */
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useId, useState } from "react";
import { outcomeOf } from "@/api/outcome";
import type { components } from "@/api/schema";
import { statusWords, trackDisplay } from "@/components/paper-badges";
import { useApi } from "@/components/providers";
import { button, FailureNotice } from "../export/export-notice";

export const DIFF_PAGE = 50;

type Entry = components["schemas"]["DiffEntry"];
type Causes = components["schemas"]["RemovalCauses"];

/** Why the re-run no longer finds a removed paper that the index still holds (RC-14a). An unknown cause gets no words. */
function causeWords(e: Entry): string | null {
  switch (e.cause) {
    case "track_changed":
      return `moved to the ${trackDisplay(e.track ?? "unknown").short} track (not in this search's tracks)`;
    case "status_changed":
      return `its status is now ${statusWords(e.status ?? "unknown")} (not in this search's statuses)`;
    case "filter_changed":
      return e.failed_filter === null
        ? "no longer passes one of this search's filters"
        : `no longer passes this search's ${e.failed_filter}: filter`;
    case "still_eligible":
      return "no longer matches the query (its title, abstract or details changed)";
    default:
      return null;
  }
}

/** The removed list's causes in one line, counted over the whole list (RC-14a). */
function causesLine(total: number, t: Causes): string {
  const n = (k: number) => k.toLocaleString("en-US");
  return (
    `Of the ${n(total)} removed: ${n(t.track_changed)} moved to a track this search doesn't include · ` +
    `${n(t.status_changed)} with a status this search doesn't include · ${n(t.filter_changed)} failing another ` +
    `of its filters · ${n(t.not_in_index)} no longer in the index · ${n(t.still_eligible)} no longer matching ` +
    "the query."
  );
}

export function RecordDiff({ id, added, removed }: { id: string; added: number; removed: number }) {
  const [open, setOpen] = useState(false);
  const [offset, setOffset] = useState(0);
  const panelId = useId();
  const api = useApi();
  const query = useQuery({
    queryKey: ["record-diff", id, offset],
    queryFn: ({ signal }) =>
      outcomeOf(
        () =>
          api.GET("/api/v1/records/{id}/diff", {
            params: { path: { id }, query: { offset, limit: DIFF_PAGE } },
            signal,
          }),
        signal,
      ),
    enabled: open,
    staleTime: (q) => (q.state.data?.kind === "ok" ? Infinity : 0),
  });
  const most = Math.max(added, removed);
  const answer = query.data;
  return (
    <div className="space-y-2">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen(!open)}
        className="underline underline-offset-4"
      >
        See the {added.toLocaleString("en-US")} added and {removed.toLocaleString("en-US")} removed papers{" "}
        <span aria-hidden="true">{open ? "▴" : "▾"}</span>
      </button>
      {open && (
        <div id={panelId} className="space-y-3">
          {answer === undefined && (
            <p role="status" className="text-muted-foreground">
              Loading the differences…
            </p>
          )}
          {answer !== undefined && answer.kind !== "ok" && (
            <FailureNotice failure={answer} onRetry={() => void query.refetch()} />
          )}
          {answer?.kind === "ok" && (
            <>
              {(
                [
                  ["Added", answer.data.added_total ?? added, answer.data.added, null],
                  [
                    "Removed",
                    answer.data.removed_total ?? removed,
                    answer.data.removed,
                    answer.data.removed_causes,
                  ],
                ] as const
              ).map(([label, n, entries, causes]) => (
                <section key={label} aria-labelledby={`${panelId}-${label}`} className="space-y-1">
                  <h3 id={`${panelId}-${label}`} className="font-semibold">
                    {label} ({n.toLocaleString("en-US")})
                  </h3>
                  {causes !== null && n > 0 && <p>{causesLine(n, causes)}</p>}
                  {entries.length === 0 ? (
                    <p className="text-muted-foreground">None on this page.</p>
                  ) : (
                    <ul className="list-disc space-y-1 pl-5">
                      {entries.map((e) => {
                        if (e.cause === "not_in_index") {
                          return (
                            <li key={e.id} className="break-words">
                              <code className="font-mono break-all">{e.id}</code> — no longer in index{" "}
                              <code className="font-mono break-all">{answer.data.index_version}</code> (left
                              the corpus, or now counted as not a paper)
                            </li>
                          );
                        }
                        const why = causeWords(e);
                        return (
                          <li key={e.id} className="break-words">
                            {e.title === null ? (
                              <>
                                <code className="font-mono break-all">{e.id}</code> (not in index{" "}
                                <code className="font-mono break-all">{answer.data.index_version}</code>)
                              </>
                            ) : (
                              <Link
                                href={`/paper/${encodeURIComponent(e.id)}`}
                                className="underline underline-offset-4"
                              >
                                {e.title}
                              </Link>
                            )}
                            {why !== null && ` — ${why}`}
                          </li>
                        );
                      })}
                    </ul>
                  )}
                </section>
              ))}
              {most > DIFF_PAGE && (
                <nav aria-label="Differences pages" className="flex flex-wrap items-center gap-3">
                  <button
                    type="button"
                    aria-disabled={offset === 0 ? true : undefined}
                    onClick={() => offset > 0 && setOffset(Math.max(0, offset - DIFF_PAGE))}
                    className={`${button} ${offset === 0 ? "opacity-60" : ""}`}
                  >
                    <span aria-hidden="true">◂ </span>Previous
                  </button>
                  <span className="tabular-nums">
                    {(offset + 1).toLocaleString("en-US")}–
                    {Math.min(offset + DIFF_PAGE, most).toLocaleString("en-US")} of{" "}
                    {most.toLocaleString("en-US")}
                  </span>
                  <button
                    type="button"
                    aria-disabled={offset + DIFF_PAGE >= most ? true : undefined}
                    onClick={() => offset + DIFF_PAGE < most && setOffset(offset + DIFF_PAGE)}
                    className={`${button} ${offset + DIFF_PAGE >= most ? "opacity-60" : ""}`}
                  >
                    Next<span aria-hidden="true"> ▸</span>
                  </button>
                </nav>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
