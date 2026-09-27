/**
 * Text with the API's highlight spans drawn as `<mark>` + bold (spec 05 §6 and §Non-functional: never colour
 * alone). Text nodes cut at the spans, never HTML built from strings (react/no-danger).
 */
import type { Utf16Span } from "@/api/spans";

export function Highlighted({ text, spans }: { text: string; spans: readonly Utf16Span[] }) {
  const parts: React.ReactNode[] = [];
  let at = 0;
  for (const [a, b] of spans) {
    if (a > at) parts.push(text.slice(at, a));
    parts.push(
      <mark key={a} className="rounded-sm bg-hl-bg font-bold text-hl-fg">
        {text.slice(a, b)}
      </mark>,
    );
    at = b;
  }
  if (at < text.length) parts.push(text.slice(at));
  return <>{parts}</>;
}
