// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { readFileSync } from "node:fs";
import path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { parsed } from "@/test/api-stub";
import { MORE_EXAMPLES, REVIEW_EXAMPLE } from "./examples";
import { ExpansionsRow } from "./expansions-row";
import { QueryTree } from "./query-tree";

afterEach(cleanup);

describe("ExpansionsRow (EX-1–5)", () => {
  const twelve = Array.from({ length: 12 }, (_, i) => `benchmark${i}`);

  it("shows the first 8 terms and +N more, which expands in place and keeps focus", () => {
    render(
      <ExpansionsRow
        expansions={{ "benchmark*": twelve, "trustworth*": ["trustworthy", "trustworthiness"] }}
      />,
    );
    const [bench, trust] = screen.getAllByRole("listitem");
    expect(bench?.textContent).toBe(
      `benchmark* → expands to 12 words: ${twelve.slice(0, 8).join(", ")} +4 more`,
    );
    const more = within(bench!).getByRole("button", { name: "+4 more" });
    expect(more.getAttribute("aria-expanded")).toBe("false");
    more.focus();
    fireEvent.click(more);
    expect(bench?.textContent).toContain(twelve.join(", "));
    expect(document.activeElement).toBe(within(bench!).getByRole("button", { name: "Show fewer" }));
    expect(trust?.textContent).toBe("trustworth* → expands to 2 words: trustworthy, trustworthiness");
  });

  it("says a dead wildcard expanded to nothing, and a query without wildcards has none", () => {
    render(<ExpansionsRow expansions={{ model$: [] }} />);
    expect(screen.getByRole("listitem").textContent).toBe(
      "model$ → (no indexed words) expands to no indexed words",
    );
    cleanup();
    render(<ExpansionsRow expansions={{}} />);
    expect(screen.getByText("(none: the query has no wildcards)")).toBeTruthy();
  });
});

describe("QueryTree (How we read your query)", () => {
  const result = parsed("trust");

  it("is a disclosure naming the defaults, closed when asked", () => {
    render(<QueryTree result={result} open={false} onToggle={() => {}} draft={false} />);
    const button = screen.getByRole("button", { name: /How we read your query/ });
    expect(button.textContent).toBe("▸ How we read your query (defaults: track, status)");
    expect(button.getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByRole("list", { name: "Query tree" })).toBeNull();
  });

  it("shows canonical and identification strings with Copy, and labels default clauses in text", () => {
    render(<QueryTree result={result} open onToggle={() => {}} draft />);
    expect(screen.getByRole("button", { name: /How we read your query/ }).textContent).toContain(
      "Draft — not searched: ",
    );
    expect(screen.getByText(result.canonical!)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Copy canonical query" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Copy identification string" })).toBeTruthy();
    const tree = screen.getByRole("list", { name: "Query tree" });
    const items = within(tree)
      .getAllByRole("listitem")
      .map((li) => li.textContent);
    expect(items).toEqual([
      "ANDtrusttrack: datasets_benchmarks OR main OR positiondefaultstatus: accepteddefault",
      "trust",
      "track: datasets_benchmarks OR main OR positiondefault",
      "status: accepteddefault",
    ]);
  });

  it("draws the server's tree: NOT, NEAR, phrases, fields, wildcards and year ranges", () => {
    const ast = {
      kind: "and" as const,
      span: [0, 1] as [number, number],
      children: [
        {
          kind: "near" as const,
          distance: 3,
          span: [0, 1] as [number, number],
          left: {
            kind: "wildcard" as const,
            field: "title" as const,
            stem: "trust",
            op: "*" as const,
            span: [0, 1] as [number, number],
          },
          right: {
            kind: "phrase" as const,
            field: null,
            span: [0, 1] as [number, number],
            items: [
              { kind: "term" as const, field: null, token: "large", span: [0, 1] as [number, number] },
              {
                kind: "wildcard" as const,
                field: null,
                stem: "model",
                op: "$" as const,
                span: [0, 1] as [number, number],
              },
            ],
          },
        },
        {
          kind: "not" as const,
          span: [0, 1] as [number, number],
          child: {
            kind: "filter" as const,
            field: "track" as const,
            values: ["workshop"],
            span: [0, 1] as [number, number],
          },
        },
        {
          kind: "filter" as const,
          field: "year" as const,
          values: [
            { lo: 2020, hi: 2026 },
            { lo: 2024, hi: 2024 },
          ],
          span: [0, 1] as [number, number],
        },
      ],
    };
    render(
      <QueryTree
        result={{ ...result, defaults: [], effective_ast: ast }}
        open
        onToggle={() => {}}
        draft={false}
      />,
    );
    const items = within(screen.getByRole("list", { name: "Query tree" }))
      .getAllByRole("listitem")
      .map((li) => li.textContent);
    expect(items.slice(1)).toEqual([
      'NEAR/3title:trust*"large model$"',
      "title:trust*",
      '"large model$"',
      "NOTtrack: workshop",
      "track: workshop", // under NOT: never labelled default
      "year: 2020..2026 OR 2024",
    ]);
  });
});

describe("the review's example string", () => {
  it("is main-7-most-updated from the Trust-Evals fixture, verbatim, in Scholar syntax", () => {
    const fixture = readFileSync(
      path.join(import.meta.dirname, "../../../../backend/tests/fixtures/queries/trust-evals.txt"),
      "utf8",
    ).split("\n");
    const line = fixture[fixture.indexOf("## main-7-most-updated") + 1];
    expect(REVIEW_EXAMPLE).toEqual({ q: line, mode: "scholar" });
    expect(MORE_EXAMPLES.every((e) => e.mode === "native")).toBe(true);
  });
});
