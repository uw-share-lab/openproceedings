/**
 * Highlight spans as the page draws them, and the result list's abstract excerpt (design W5 "Excerpt rule";
 * nextjs-conventions non-negotiable 3). Nothing here matches anything: the spans are the API's, converted
 * once from code points (`spans.ts`), and the excerpt only chooses which part of the text to show, from
 * those spans.
 */
import { codePointLength, codePointSpanToUtf16, type Utf16Span } from "@/api/spans";

/**
 * The API's code-point spans over `text` as UTF-16 ranges, sorted, overlapping or touching ones joined.
 * `null` when a span does not fit the text (a server bug): the caller draws the text unhighlighted rather
 * than guess where a match was.
 */
export function utf16Spans(text: string, spans: readonly (readonly number[])[]): Utf16Span[] | null {
  const out: [number, number][] = [];
  try {
    for (const span of spans) {
      if (span.length !== 2) return null;
      const [start = -1, end = -1] = span;
      const [a, b] = codePointSpanToUtf16(text, [start, end]);
      if (a < b) out.push([a, b]);
    }
  } catch {
    return null;
  }
  out.sort((x, y) => x[0] - y[0] || x[1] - y[1]);
  const merged: [number, number][] = [];
  for (const s of out) {
    const last = merged.at(-1);
    if (last !== undefined && s[0] <= last[1]) last[1] = Math.max(last[1], s[1]);
    else merged.push([s[0], s[1]]);
  }
  return merged;
}

/** An abstract up to this many characters (code points) is shown whole in the result list. */
export const EXCERPT_CHARS = 600;
/** How much text the excerpt keeps before the first highlight. */
const LEAD_CHARS = 150;
/** How far a cut may move to land on a space instead of inside a word. */
const SNAP_CHARS = 40;

export interface Excerpt {
  /** The UTF-16 range of `text` shown. */
  readonly start: number;
  readonly end: number;
  /** The highlight spans inside it, relative to `start`. */
  readonly spans: Utf16Span[];
  /** Whether text was cut before `start` / after `end` (drawn as `…`). */
  readonly cutBefore: boolean;
  readonly cutAfter: boolean;
}

const isLow = (text: string, i: number) => {
  const c = text.charCodeAt(i);
  return c >= 0xdc00 && c <= 0xdfff;
};

/**
 * The part of `text` the result list shows: all of it up to `EXCERPT_CHARS` code points; otherwise a window
 * of about that size starting a little before the first highlight (or at the start when there is none),
 * cut at spaces where one is near and never inside a surrogate pair. The first highlight is always wholly
 * inside the window.
 */
export function excerpt(text: string, spans: readonly Utf16Span[], limit = EXCERPT_CHARS): Excerpt {
  if (codePointLength(text) <= limit) {
    return { start: 0, end: text.length, spans: [...spans], cutBefore: false, cutAfter: false };
  }
  const first = spans[0];
  let start = first === undefined ? 0 : Math.max(0, first[0] - LEAD_CHARS);
  if (start > 0) {
    const space = text.slice(start, start + SNAP_CHARS).search(/\s/);
    if (space >= 0 && (first === undefined || start + space < first[0])) start += space + 1;
  }
  if (start < text.length && isLow(text, start)) start += 1;
  let end = Math.min(text.length, start + limit);
  if (first !== undefined && end < first[1]) end = first[1];
  if (end < text.length) {
    const back = text.slice(Math.max(start, end - SNAP_CHARS), end).search(/\s\S*$/);
    const at = Math.max(start, end - SNAP_CHARS) + back;
    if (back >= 0 && (first === undefined || at >= first[1])) end = at;
    if (end > start && isLow(text, end)) end -= 1;
  }
  const inside: Utf16Span[] = [];
  for (const [a, b] of spans) {
    const lo = Math.max(a, start);
    const hi = Math.min(b, end);
    if (lo < hi) inside.push([lo - start, hi - start]);
  }
  return { start, end, spans: inside, cutBefore: start > 0, cutAfter: end < text.length };
}
