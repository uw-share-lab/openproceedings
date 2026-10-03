import { afterEach, describe, expect, it, vi } from "vitest";
import {
  checkTakedownContactEnv,
  TAKEDOWN_FALLBACK_URL,
  TakedownContactError,
  takedownContact,
} from "./takedown-contact";

const fallback = {
  kind: "fallback",
  href: "https://github.com/uw-share-lab/openproceedings/issues",
  label: "github.com/uw-share-lab/openproceedings/issues",
};

describe("takedownContact", () => {
  it("falls back to the repository's issues page when no contact is set", () => {
    for (const raw of [undefined, "", "   "]) expect(takedownContact(raw)).toEqual(fallback);
    expect(TAKEDOWN_FALLBACK_URL).toBe(fallback.href);
  });

  it.each([
    ["takedown@example.org", "takedown@example.org"],
    ["  takedown@example.org\n", "takedown@example.org"],
    ["first.last+rights@lab-1.example.co.uk", "first.last+rights@lab-1.example.co.uk"],
    ["mailto:takedown@example.org", "takedown@example.org"],
    ["MAILTO:rights@lab.example.ca", "rights@lab.example.ca"],
  ])("reads %j as an email address", (raw, address) => {
    expect(takedownContact(raw)).toEqual({ kind: "email", href: `mailto:${address}`, label: address });
  });

  it.each([
    ["https://example.org/takedown", "https://example.org/takedown", "example.org/takedown"],
    ["https://example.org", "https://example.org/", "example.org"],
    // The label is host and path only: neither the query nor the hash is shown.
    [
      "http://example.org/abuse?topic=abstracts",
      "http://example.org/abuse?topic=abstracts",
      "example.org/abuse",
    ],
    ["https://example.org/policy#takedown", "https://example.org/policy#takedown", "example.org/policy"],
  ])("reads %j as a page", (raw, href, label) => {
    expect(takedownContact(raw)).toEqual({ kind: "url", href, label });
  });

  it.each([
    // not an address or an http(s) URL
    "javascript:alert(1)",
    "not an address",
    "takedown@localhost",
    "a b@example.org",
    "ftp://example.org",
    "https://",
    // characters that add mailto headers or encode a newline
    "a@b.org?cc=evil%40x.org",
    "a@b.org%0Afoo",
    "a%40b@example.org",
    "a@b.org#x",
    "a&b@example.org",
    "a/b@example.org",
    "a=b@example.org",
    "mailto:a@b.org?cc=evil@x.org",
    "mailto:a@b.org%0Abcc:evil@x.org",
    "mailto:a@b.org?subject=x",
    "mailto:",
    // non-ASCII and invisible characters
    "tаkedown@example.org", // Cyrillic а
    "takedown@exämple.org",
    "take‮down@example.org",
    "take​down@example.org",
    "mailto:take​down@example.org",
    "https://example.org/‮takedown",
    "https://exämple.org/takedown",
    "https://example.org/a b",
    // credentials in a URL
    "https://user@example.org/takedown",
    "https://user:secret@example.org/takedown",
  ])("refuses the unusable value %j", (raw) => {
    expect(() => takedownContact(raw)).toThrow(TakedownContactError);
    expect(() => takedownContact(raw)).toThrow(/^NEXT_PUBLIC_TAKEDOWN_CONTACT /);
  });
});

describe("checkTakedownContactEnv (next.config.ts)", () => {
  it("fails the build on a set but unusable value", () => {
    expect(() => checkTakedownContactEnv("a@b.org?cc=evil%40x.org", true, vi.fn())).toThrow(
      TakedownContactError,
    );
    expect(() => checkTakedownContactEnv("javascript:alert(1)", false, vi.fn())).toThrow(
      TakedownContactError,
    );
  });

  it("warns once in a production build when the contact is unset", () => {
    const warn = vi.fn();
    checkTakedownContactEnv(undefined, true, warn);
    expect(warn).toHaveBeenCalledOnce();
    expect(warn.mock.calls[0]?.[0]).toMatch(
      /ublicly reachable instances must set NEXT_PUBLIC_TAKEDOWN_CONTACT/,
    );
  });

  it("is quiet when a contact is set, and outside production", () => {
    const warn = vi.fn();
    checkTakedownContactEnv("takedown@example.org", true, warn);
    checkTakedownContactEnv("https://example.org/takedown", true, warn);
    checkTakedownContactEnv(undefined, false, warn);
    expect(warn).not.toHaveBeenCalled();
  });
});

describe("OPENPROCEEDINGS_INSTANCE (TASK-136: a public build needs a contact)", () => {
  it("refuses a public instance without a contact, whatever the build mode", () => {
    for (const production of [true, false]) {
      for (const raw of [undefined, "", "  "]) {
        expect(() => checkTakedownContactEnv(raw, production, vi.fn(), "public")).toThrow(
          /^OPENPROCEEDINGS_INSTANCE=public needs NEXT_PUBLIC_TAKEDOWN_CONTACT/,
        );
      }
    }
  });

  it("builds a public instance with a contact, and a private or undeclared one without", () => {
    const warn = vi.fn();
    checkTakedownContactEnv("takedown@example.org", true, warn, "public");
    checkTakedownContactEnv("https://example.org/takedown", true, warn, " public ");
    checkTakedownContactEnv(undefined, false, warn, "private");
    checkTakedownContactEnv(undefined, false, warn, "");
    expect(warn).not.toHaveBeenCalled();
    checkTakedownContactEnv(undefined, true, warn, "private"); // still warned about in production
    expect(warn).toHaveBeenCalledOnce();
  });

  it("refuses any other instance kind", () => {
    for (const kind of ["Public", "yes", "prod", "true"]) {
      expect(() => checkTakedownContactEnv("takedown@example.org", true, vi.fn(), kind)).toThrow(
        /OPENPROCEEDINGS_INSTANCE must be "public" or "private"/,
      );
    }
  });
});

describe("next.config.ts", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
    vi.resetModules();
  });

  it("fails to load (so the build fails) on an unusable contact", async () => {
    vi.resetModules();
    vi.stubEnv("NEXT_PUBLIC_TAKEDOWN_CONTACT", "a@b.org?cc=evil%40x.org");
    await expect(import("../../next.config")).rejects.toThrow(/^NEXT_PUBLIC_TAKEDOWN_CONTACT /);
  });

  it("fails to load for a public instance without a contact, and loads for a private one (TASK-136)", async () => {
    vi.resetModules();
    vi.stubEnv("OPENPROCEEDINGS_INSTANCE", "public");
    vi.stubEnv("NEXT_PUBLIC_TAKEDOWN_CONTACT", "");
    await expect(import("../../next.config")).rejects.toThrow(/^OPENPROCEEDINGS_INSTANCE=public needs/);
    vi.resetModules();
    vi.stubEnv("OPENPROCEEDINGS_INSTANCE", "private");
    await expect(import("../../next.config")).resolves.toBeTruthy();
  });

  it("warns once when a production build has no contact", async () => {
    vi.resetModules();
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("NEXT_PUBLIC_TAKEDOWN_CONTACT", "");
    await import("../../next.config");
    expect(warn).toHaveBeenCalledOnce();
  });
});
