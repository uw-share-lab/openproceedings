import type { Metadata } from "next";
import { SyntaxHelp } from "@/components/help/syntax-help";

// Spec 05 §Pages: the language reference, generated from the spec 02 goldens (src/help/syntax-golden.json,
// which a backend test keeps equal to what the parser says), so it can't drift from the parser.
export const metadata: Metadata = { title: "Query syntax" };

export default function SyntaxHelpPage() {
  return (
    <article className="mx-auto max-w-4xl space-y-4">
      <h1 className="text-lg font-semibold">Query syntax</h1>
      <SyntaxHelp />
    </article>
  );
}
