/**
 * Server diagnostics as the editor shows them (spec 05 §Components 1; codemirror-lezer skill;
 * docs/design/2026-09-27-search-workspace.md W3, W6, W7). Nothing here originates a diagnostic or rewords
 * one: the server's `code` and `message` are carried through verbatim. What happens here is display only:
 * the order (errors, then warnings, then translations, each in span order), the squiggle positions (code-point
 * spans converted to UTF-16 once, through `src/api/spans.ts`), repeated codes collapsed into one line, and
 * the summary counts.
 */
import type { Diagnostic as EditorDiagnostic } from "@codemirror/lint";
import { codePointLength, codePointSpanToUtf16 } from "@/api/spans";

/**
 * A server diagnostic: `{code, message, span, reading}` (spec 04 §Conventions), from `/parse` or an error
 * envelope. `reading` is set on `WARN_MIXED_AND_OR` only (TASK-099).
 */
export interface ServerDiagnostic {
  readonly code: string;
  readonly message: string;
  readonly span: readonly number[] | null;
  readonly reading: string | null;
}

/** errors → "error", warnings → "warning", translations → "info" (codemirror-lezer skill). */
export type Severity = "error" | "warning" | "info";

export interface Item {
  readonly severity: Severity;
  readonly code: string;
  readonly message: string;
  /** Half-open code points into the text the diagnostic was reported for; `null` when it has no place. */
  readonly span: readonly [number, number] | null;
  /** `WARN_MIXED_AND_OR`'s text at `span` as the server read it, parenthesised; `null` on every other code. */
  readonly reading: string | null;
}

export interface DiagnosticLists {
  readonly errors: readonly ServerDiagnostic[];
  readonly warnings: readonly ServerDiagnostic[];
  readonly translations: readonly ServerDiagnostic[];
}

/** A span as `[start, end)`, or `null` when it isn't two whole numbers in order (never guessed at). */
function spanOf(span: readonly number[] | null): readonly [number, number] | null {
  if (span === null || span.length !== 2) return null;
  const [start = -1, end = -1] = span;
  return Number.isInteger(start) && Number.isInteger(end) && 0 <= start && start <= end ? [start, end] : null;
}

export function itemOf(severity: Severity, d: ServerDiagnostic): Item {
  return { severity, code: d.code, message: d.message, span: spanOf(d.span), reading: d.reading };
}

const bySpan = (a: Item, b: Item) => (a.span?.[0] ?? Infinity) - (b.span?.[0] ?? Infinity);

/** Errors first, then warnings, then translations; each in span order (a diagnostic without a span last). */
export function itemsOf(lists: DiagnosticLists): Item[] {
  const as = (severity: Severity, list: readonly ServerDiagnostic[]): Item[] =>
    list.map((d) => itemOf(severity, d)).sort(bySpan);
  return [...as("error", lists.errors), ...as("warning", lists.warnings), ...as("info", lists.translations)];
}

/**
 * The squiggles for `items` over `text`: each span clamped to the text, a zero-width span widened by one code
 * point so it is visible, then converted to UTF-16 (the one conversion, spans.ts). The message is the
 * server's, verbatim; `source` is its code.
 */
export function editorDiagnostics(text: string, items: readonly Item[]): EditorDiagnostic[] {
  const length = codePointLength(text);
  const out: EditorDiagnostic[] = [];
  for (const item of items) {
    if (item.span === null) continue;
    let start = Math.min(Math.max(item.span[0], 0), length);
    let end = Math.min(Math.max(item.span[1], start), length);
    if (start === end) {
      if (end < length) end += 1;
      else if (start > 0) start -= 1;
    }
    const [from, to] = codePointSpanToUtf16(text, [start, end]);
    out.push({ from, to, severity: item.severity, message: item.message, source: item.code });
  }
  return out;
}

/** Several diagnostics with one code, shown as one line: "9 ×" and the first message (pre-pass M8). */
export interface Group {
  readonly severity: Severity;
  readonly code: string;
  readonly items: readonly Item[];
}

/** `items` grouped by severity and code, each group where its first diagnostic was, in order. */
export function groupRepeats(items: readonly Item[]): Group[] {
  const groups = new Map<string, { severity: Severity; code: string; items: Item[] }>();
  for (const item of items) {
    const key = `${item.severity}\u0000${item.code}`;
    const group = groups.get(key);
    if (group === undefined) groups.set(key, { severity: item.severity, code: item.code, items: [item] });
    else group.items.push(item);
  }
  return [...groups.values()];
}

export function plural(n: number, word: string): string {
  return `${n.toLocaleString("en-US")} ${word}${n === 1 ? "" : "s"}`;
}

/** "1 error, 2 warnings" (copy deck ED-5): zero parts left out, "" when there are none. */
export function countText(items: readonly Item[]): string {
  const errors = items.filter((i) => i.severity === "error").length;
  const warnings = items.filter((i) => i.severity === "warning").length;
  return [errors > 0 ? plural(errors, "error") : "", warnings > 0 ? plural(warnings, "warning") : ""]
    .filter(Boolean)
    .join(", ");
}

/** The two codes about slow clauses share one help section; every other code has its own anchor (N10). */
const SLOW_CLAUSES = new Set(["API_TOO_MANY_VERIFIED_CLAUSES", "API_QUERY_TOO_COSTLY"]);

export function helpHref(code: string): string {
  return `/help/syntax#${SLOW_CLAUSES.has(code) ? "slow-clauses" : code.toLowerCase()}`;
}

/**
 * "Load with parentheses" (pre-pass S7): the server's `reading` of a `WARN_MIXED_AND_OR` (a field, TASK-099;
 * the message is never parsed) spliced over the warning's span in `text`, or `null` when there is nothing to
 * load faithfully (another code, no reading, no span, or a span that doesn't fit `text`).
 */
export function withParentheses(text: string, item: Item): string | null {
  const { reading } = item;
  if (item.code !== "WARN_MIXED_AND_OR" || item.span === null || reading === null) return null;
  try {
    const [from, to] = codePointSpanToUtf16(text, item.span);
    return text.slice(0, from) + reading + text.slice(to);
  } catch {
    return null; // the span doesn't fit this text: it was reported for another one
  }
}
