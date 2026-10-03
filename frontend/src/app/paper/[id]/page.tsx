import type { Metadata } from "next";
import { PaperView } from "@/components/paper/paper-view";
import { fromURL } from "@/lib/search-state";

// A paper's full record (spec 05 §Pages; design P1–P5). The query the result list linked with rides in the
// URL (`?q=&mode=`), so a shared or reloaded link shows the same highlights.
export const metadata: Metadata = { title: "Paper" };

export default async function PaperPage({ params, searchParams }: PageProps<"/paper/[id]">) {
  const { id } = await params;
  const raw = await searchParams;
  const one = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v);
  const q = one(raw["q"]);
  const mode = one(raw["mode"]);
  // `mode` is read as /search reads it (an unknown one is native); a blank or missing `q` is a direct link.
  const { state } = fromURL(new URLSearchParams(mode === undefined ? {} : { mode }));
  return <PaperView id={decoded(id)} q={q === undefined || q.trim() === "" ? null : q} mode={state.mode} />;
}

/** The id as written (`op:iclr:2024:abc`), whether or not the router already decoded `%3A`. */
function decoded(id: string): string {
  try {
    return decodeURIComponent(id);
  } catch {
    return id; // not percent-encoding: the API answers 422 API_BAD_PARAM, the not-found state
  }
}
