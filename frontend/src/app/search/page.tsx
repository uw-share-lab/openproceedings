import type { Metadata } from "next";
import Link from "next/link";
import { describeNotice, fromURL, searchHref } from "@/lib/search-state";

// Placeholder (TASK-039 skeleton): shows the state read from the URL, which is the whole search
// (guarantee 3). The workspace (editor, sidebar, results) arrives in TASK-041/042.
export const metadata: Metadata = { title: "Search" };

export default async function SearchPage({ searchParams }: PageProps<"/search">) {
  const raw = await searchParams;
  const params = new URLSearchParams();
  for (const [name, value] of Object.entries(raw)) {
    for (const v of Array.isArray(value) ? value : value === undefined ? [] : [value]) params.append(name, v);
  }
  const { state, notices } = fromURL(params);

  return (
    <section className="mx-auto max-w-3xl space-y-3 text-sm">
      <h1 className="text-lg font-semibold">Search</h1>
      <p className="text-muted-foreground">
        The search workspace is not built yet. This is the search the address holds.
      </p>
      {notices.length > 0 && (
        // Not redirected: the reader sees what was wrong with the address and chooses the corrected one.
        <div className="space-y-2 rounded-md border border-warn-border bg-warn-bg p-2 text-warn-fg">
          <ul aria-label="Address notices" className="space-y-1">
            {notices.map((n, i) => (
              <li key={i}>
                {describeNotice(n).map((run, j) =>
                  "code" in run ? (
                    <code key={j} className="font-mono wrap-anywhere">
                      {run.code}
                    </code>
                  ) : (
                    <span key={j}>{run.text}</span>
                  ),
                )}
              </li>
            ))}
          </ul>
          <p>
            <Link href={searchHref(state)} className="font-semibold underline underline-offset-4">
              Use corrected link
            </Link>
          </p>
        </div>
      )}
      <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1">
        <dt>q</dt>
        <dd className="break-all">
          {state.q === "" ? (
            <span className="text-muted-foreground italic">(empty)</span>
          ) : (
            <span className="font-mono">{state.q}</span>
          )}
        </dd>
        <dt>mode</dt>
        <dd className="font-mono">{state.mode}</dd>
        <dt>sort</dt>
        <dd className="font-mono">{state.sort}</dd>
        <dt>page</dt>
        <dd className="font-mono tabular-nums">{state.page}</dd>
      </dl>
    </section>
  );
}
