import { describe, expect, it, vi } from "vitest";
import { TAKEDOWN_FALLBACK_URL, takedownContact } from "./takedown-contact";

const fallback = {
  kind: "fallback",
  href: "https://github.com/uw-share-lab/openproceedings/issues",
  label: "github.com/uw-share-lab/openproceedings/issues",
};

describe("takedownContact", () => {
  it("falls back to the repository's issues page when no contact is set", () => {
    const warn = vi.fn();
    for (const raw of [undefined, "", "   "]) expect(takedownContact(raw, warn)).toEqual(fallback);
    expect(TAKEDOWN_FALLBACK_URL).toBe(fallback.href);
    expect(warn).not.toHaveBeenCalled();
  });

  it.each([
    ["takedown@example.org", "takedown@example.org"],
    ["  takedown@example.org\n", "takedown@example.org"],
    ["mailto:takedown@example.org", "takedown@example.org"],
    ["MAILTO:rights@lab.example.ca", "rights@lab.example.ca"],
  ])("reads %j as an email address", (raw, address) => {
    expect(takedownContact(raw)).toEqual({ kind: "email", href: `mailto:${address}`, label: address });
  });

  it.each([
    ["https://example.org/takedown", "https://example.org/takedown", "example.org/takedown"],
    ["https://example.org", "https://example.org/", "example.org"],
    [
      "http://example.org/abuse?topic=abstracts",
      "http://example.org/abuse?topic=abstracts",
      "example.org/abuse?topic=abstracts",
    ],
  ])("reads %j as a page", (raw, href, label) => {
    expect(takedownContact(raw)).toEqual({ kind: "url", href, label });
  });

  it.each([
    "javascript:alert(1)",
    "not an address",
    "takedown@localhost",
    "a b@example.org",
    "https://",
    "ftp://example.org",
  ])("falls back, with a warning, on the unusable value %j", (raw) => {
    const warn = vi.fn();
    expect(takedownContact(raw, warn)).toEqual(fallback);
    expect(warn).toHaveBeenCalledOnce();
    expect(warn.mock.calls[0]?.[0]).toMatch(/^NEXT_PUBLIC_TAKEDOWN_CONTACT is neither an email address nor/);
  });
});
