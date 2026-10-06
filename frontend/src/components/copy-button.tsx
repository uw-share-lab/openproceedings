"use client";

import { useState } from "react";

/**
 * A Copy button that says "Copied" in a polite live region (design §Keyboard and screen reader; TR-2), or, where
 * the clipboard can't be written (no Clipboard API outside a secure context, or a refusal), that the text must
 * be selected instead: never a press that does nothing silently.
 */
export function CopyButton({ text, label }: { text: string; label: string }) {
  const [said, setSaid] = useState("");
  return (
    <span className="inline-flex items-center gap-2">
      <button
        type="button"
        aria-label={label}
        className="min-h-6 rounded-sm border px-1.5 text-xs hover:bg-muted"
        onClick={() => {
          const failed = () => setSaid("Couldn't copy: select the text and copy it");
          if (navigator.clipboard === undefined) return failed();
          void navigator.clipboard.writeText(text).then(() => setSaid("Copied"), failed);
        }}
      >
        Copy
      </button>
      <span role="status" aria-live="polite" className="text-xs text-muted-foreground">
        {said}
      </span>
    </span>
  );
}
