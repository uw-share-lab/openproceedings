import { CompletionContext } from "@codemirror/autocomplete";
import { EditorState } from "@codemirror/state";
import { describe, expect, it } from "vitest";
import { META } from "@/test/api-stub";
import { queryCompletions } from "./complete";
import { query } from "./lang";

function complete(doc: string, explicit = true, meta: typeof META | null = META) {
  const state = EditorState.create({ doc, extensions: [query()] });
  const result = queryCompletions(() => meta)(new CompletionContext(state, doc.length, explicit));
  if (result === null || result instanceof Promise) return null;
  return { from: result.from, labels: result.options.map((o) => o.label) };
}

describe("completion from /meta only", () => {
  it("offers the field names /meta lists", () => {
    expect(complete("trust ti")).toEqual({
      from: 6,
      labels: ["title:", "abstract:", "venue:", "year:", "track:", "status:"],
    });
  });

  it("offers a field's values right after its colon, with or without a space", () => {
    expect(complete("trust track:")?.labels).toEqual(META.values.track);
    expect(complete("trust track: wo")).toEqual({ from: 13, labels: META.values.track });
    expect(complete("venue:")?.labels).toEqual(META.values.venue);
    expect(complete("Status:")?.labels).toEqual(["accepted", "rejected"]);
  });

  it("offers values inside the field's OR group", () => {
    expect(complete("x track:(main OR ")?.labels).toEqual(META.values.track);
    expect(complete("x track:(main | wor")?.labels).toEqual(META.values.track);
  });

  it("never offers a value /meta doesn't list (an unknown track stays unknown)", () => {
    const labels = complete("track:")?.labels ?? [];
    expect(labels).not.toContain("poster");
    expect(labels.every((l) => (META.values.track as readonly string[]).includes(l))).toBe(true);
  });

  it("offers fields, not values, after a closed group or another word", () => {
    expect(complete("track:(main) ")?.labels).toContain("title:");
    expect(complete("track:main x")?.labels).toContain("title:");
    expect(complete("year:")?.labels).toContain("title:"); // years are typed, not picked
  });

  it("offers nothing before /meta answers, and never opens by itself on an empty word", () => {
    expect(complete("tr", true, null)).toBeNull();
    expect(complete("trust ", false)).toBeNull();
  });
});
