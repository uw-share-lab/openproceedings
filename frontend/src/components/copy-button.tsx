"use client";

import { useState } from "react";

/** A Copy button that says "Copied" in a polite live region (design §Keyboard and screen reader; TR-2). */
export function CopyButton({ text, label }: { text: string; label: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <span className="inline-flex items-center gap-2">
      <button
        type="button"
        aria-label={label}
        className="min-h-6 rounded-sm border px-1.5 text-xs hover:bg-muted"
        onClick={() => {
          void navigator.clipboard?.writeText(text).then(
            () => setCopied(true),
            () => setCopied(false),
          );
        }}
      >
        Copy
      </button>
      <span role="status" aria-live="polite" className="text-xs text-muted-foreground">
        {copied ? "Copied" : ""}
      </span>
    </span>
  );
}
