"use client";

import { useState } from "react";

/** Copies `value` (an index version, a hash) to the clipboard; says "Copied" once it has, in a live region. */
export function CopyButton({ value, label }: { value: string; label: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      aria-label={`Copy ${label}`}
      className="rounded-sm border px-1.5 text-xs hover:bg-muted"
      onClick={() => {
        void navigator.clipboard
          ?.writeText(value)
          .then(() => setCopied(true))
          .catch(() => setCopied(false));
      }}
    >
      Copy
      <span role="status" className="sr-only">
        {copied ? `${label} copied` : ""}
      </span>
    </button>
  );
}
