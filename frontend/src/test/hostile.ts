/**
 * Tests only: values a hostile or corrupt API answer could hold, each with how `clip` (the twin of the backend's
 * `diagnostics.clip`) quotes it, and the check that a message `Coded` draws stays safe (TASK-144, TASK-160).
 */
import { expect } from "vitest";

/** `[value, as clip quotes it]`: a backtick, a newline, NUL, ESC and a right-to-left override. */
export const HOSTILE: readonly (readonly [string, string])[] = [
  ["a`b", "a\\x60b"],
  ["a\nb", "a b"],
  ["a\x00b", "a\\x00b"],
  ["a\x1bb", "a\\x1bb"],
  [`a${String.fromCodePoint(0x202e)}b`, "a\\u202eb"],
];

/** Every backtick pairs up, and the message is one line of visible characters. */
export function quotedSafely(message: string): void {
  expect(message.split("`").length % 2, message).toBe(1);
  for (const c of message) {
    expect(c === " " || !/\s/u.test(c), message).toBe(true);
    expect(/[\p{Cc}\p{Cf}\p{Cs}]/u.test(c), message).toBe(false);
  }
}
