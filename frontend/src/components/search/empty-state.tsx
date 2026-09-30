"use client";

/**
 * The empty workspace (`/`, and `/search` without `q`; design W1, copy ED-2 and ED-3): a syntax hint, the
 * review's main string and two plain examples, and the coverage line. An example loads into the editor as a
 * draft (with its syntax) and focuses it; it never searches, since a search is always the reader's own act.
 * The coverage line is `CoverageLine` (`GET /coverage` alone, in `/coverage`'s words).
 */
import Link from "next/link";
import { CoverageLine } from "@/components/coverage/coverage-line";
import { MORE_EXAMPLES, REVIEW_EXAMPLE, type Example } from "./examples";

function ExampleButton({ example, onLoad }: { example: Example; onLoad: (e: Example) => void }) {
  return (
    <li>
      <button
        type="button"
        onClick={() => onLoad(example)}
        className="min-h-6 text-left font-mono break-all underline-offset-4 hover:underline"
      >
        <span aria-hidden="true">▸ </span>
        {example.q}
      </button>
      {example.mode === "scholar" && (
        <span className="ml-2 text-xs text-muted-foreground">[Scholar syntax]</span>
      )}
    </li>
  );
}

export function EmptyState({ onLoad }: { onLoad: (example: Example) => void }) {
  return (
    <div className="space-y-3 text-sm">
      <p>
        Write words, &quot;phrases&quot;, wildcards (<code className="font-mono">bench*</code>) and{" "}
        <code className="font-mono">AND</code> / <code className="font-mono">OR</code> /{" "}
        <code className="font-mono">NOT</code>. Filters go in the query:{" "}
        <code className="font-mono">venue:ICLR year:2020..2026</code>.{" "}
        <Link href="/help/syntax" className="underline underline-offset-4">
          Syntax help ▸
        </Link>
      </p>
      <div className="space-y-1">
        <p>The Trust-Evals review&apos;s main search string (Google Scholar syntax, loaded as written):</p>
        <ul>
          <ExampleButton example={REVIEW_EXAMPLE} onLoad={onLoad} />
        </ul>
      </div>
      <div className="space-y-1">
        <p>More examples (native syntax):</p>
        <ul className="space-y-1">
          {MORE_EXAMPLES.map((e) => (
            <ExampleButton key={e.q} example={e} onLoad={onLoad} />
          ))}
        </ul>
      </div>
      <CoverageLine />
    </div>
  );
}
