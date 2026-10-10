import { SearchWorkspace } from "@/components/search/search-workspace";
import { INITIAL_STATE } from "@/lib/search-state";

// Search home (spec 05 §Pages; design W1): the editor with the review's example strings and the coverage
// line. Searching goes to /search with the query in the URL.
export default function HomePage() {
  return (
    <section className="mx-auto max-w-5xl space-y-3">
      <h1 className="text-lg font-semibold">openproceedings</h1>
      <p className="text-sm text-muted-foreground">
        Exact, reproducible Boolean search over NeurIPS, ICLR, ICML, AAAI, AIES and IASEAI titles and
        abstracts.
      </p>
      <SearchWorkspace state={INITIAL_STATE} />
    </section>
  );
}
