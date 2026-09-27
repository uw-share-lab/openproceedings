import Link from "next/link";
import { INITIAL_STATE, searchHref } from "@/lib/search-state";

// Placeholder (TASK-039 skeleton). The query editor, example queries and coverage line arrive in
// TASK-041/045 (spec 05 §Pages).
export default function HomePage() {
  return (
    <section className="mx-auto max-w-3xl space-y-3">
      <h1 className="text-lg font-semibold">openproceedings</h1>
      <p className="text-sm text-muted-foreground">
        Exact, reproducible Boolean search over NeurIPS, ICLR and ICML titles and abstracts.
      </p>
      <p className="text-sm">
        The search workspace is not built yet.{" "}
        <Link
          className="underline underline-offset-4"
          href={searchHref({ ...INITIAL_STATE, q: "trust AND benchmark*" })}
        >
          Open an example search
        </Link>
      </p>
    </section>
  );
}
