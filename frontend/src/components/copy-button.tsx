"use client";

import { useState } from "react";

/**
 * A Copy button that says "Copied" in a polite live region (design §Keyboard and screen reader; TR-2), or, where
 * the clipboard can't be written (no Clipboard API outside a secure context, or a refusal), that the text must
 * be selected instead: never a press that does nothing silently. Each press clears the region and says it again
 * on the next frame, since the same text set twice is no change a screen reader announces. `onFailed` is for an
 * owner that can select the text itself (focus a field and `.select()` it); the message then says it is selected.
 */
export function CopyButton({
  text,
  label,
  onFailed,
}: {
  text: string;
  label: string;
  onFailed?: () => void;
}) {
  const [said, setSaid] = useState("");
  const say = (message: string) => {
    setSaid("");
    requestAnimationFrame(() => setSaid(message));
  };
  return (
    <span className="inline-flex items-center gap-2">
      <button
        type="button"
        aria-label={label}
        className="min-h-6 rounded-sm border px-1.5 text-xs hover:bg-muted"
        onClick={() => {
          const failed = () => {
            if (onFailed === undefined) return say("Couldn't copy: select the text and copy it");
            onFailed();
            say("Couldn't copy: the text is selected; copy it");
          };
          if (navigator.clipboard === undefined) return failed();
          setSaid("");
          void navigator.clipboard.writeText(text).then(() => say("Copied"), failed);
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
