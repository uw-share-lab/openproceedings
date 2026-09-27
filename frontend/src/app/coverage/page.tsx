import type { Metadata } from "next";
import { CoverageView } from "@/components/coverage/coverage-view";

// Spec 05 §Pages; design docs/design/2026-09-27-coverage-and-syntax-help.md. Every number is a
// `GET /coverage` field, fetched on each visit.
export const metadata: Metadata = { title: "Coverage" };

export default function CoveragePage() {
  return (
    <section className="mx-auto max-w-6xl space-y-4">
      <h1 className="text-lg font-semibold">Coverage</h1>
      <CoverageView />
    </section>
  );
}
