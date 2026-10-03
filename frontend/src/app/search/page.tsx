import type { Metadata } from "next";
import Link from "next/link";
import { SearchView } from "@/components/search/search-view";
import { describeNotice, fromURL, searchHref } from "@/lib/search-state";

// The search workspace (spec 05 §`/search` layout). The URL is the whole search (guarantee 3): it is read here,
// on the server, and the workspace edits it only through the reducer.
export const metadata: Metadata = { title: "Search" };

export default async function SearchPage({ searchParams }: PageProps<"/search">) {
  const raw = await searchParams;
  const params = new URLSearchParams();
  for (const [name, value] of Object.entries(raw)) {
    for (const v of Array.isArray(value) ? value : value === undefined ? [] : [value]) params.append(name, v);
  }
  const { state, notices } = fromURL(params);

  return (
    <section className="mx-auto max-w-5xl space-y-3">
      <h1 className="sr-only">Search</h1>
      {notices.length > 0 && (
        // Design W2: before everything, and never a redirect: the reader chooses the corrected link.
        <div className="space-y-2 rounded-md border border-warn-border bg-warn-bg p-2 text-sm text-warn-fg">
          <p>
            <span aria-hidden="true">⚠ </span>This link had parameters that weren&apos;t used:
          </p>
          <ul aria-label="Address notices" className="list-disc space-y-1 pl-5">
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
            <Link replace href={searchHref(state)} className="font-semibold underline underline-offset-4">
              Use corrected link
            </Link>
          </p>
        </div>
      )}
      <SearchView state={state} />
    </section>
  );
}
