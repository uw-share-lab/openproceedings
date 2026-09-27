import { fromURL } from "@/lib/search-state";

// Placeholder (TASK-039 skeleton): shows the state read from the URL, which is the whole search
// (guarantee 3). The workspace (editor, sidebar, results) arrives in TASK-041/042.
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
        The search workspace is not built yet. This is the state the URL holds.
      </p>
      <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1">
        <dt>q</dt>
        <dd className="font-mono break-all">{state.q === "" ? "(empty)" : state.q}</dd>
        <dt>mode</dt>
        <dd className="font-mono">{state.mode}</dd>
        <dt>sort</dt>
        <dd className="font-mono">{state.sort}</dd>
        <dt>page</dt>
        <dd className="font-mono tabular-nums">{state.page}</dd>
      </dl>
      {notices.length > 0 && (
        <ul
          className="rounded-md border border-warn-border bg-warn-bg p-2 text-warn-fg"
          aria-label="URL notices"
        >
          {notices.map((n, i) => (
            <li key={i}>
              <span className="font-mono">
                {n.param}={n.value}
              </span>{" "}
              {n.reason === "unknown_param"
                ? "is not a search parameter and was ignored"
                : n.reason === "repeated_param"
                  ? `was repeated; using ${n.used ?? ""}`
                  : `is not valid; using ${n.used ?? ""}`}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
