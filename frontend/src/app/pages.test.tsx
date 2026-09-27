// @vitest-environment jsdom
import { cleanup, render, screen, within } from "@testing-library/react";
import { readFileSync } from "node:fs";
import path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { metadata as coverageMeta } from "./coverage/page";
import SyntaxHelpPage, { metadata as syntaxMeta } from "./help/syntax/page";
import NotFound from "./not-found";
import HomePage from "./page";
import { metadata as paperMeta } from "./paper/[id]/page";
import { metadata as recordMeta } from "./record/[id]/page";
import SearchPage, { metadata as searchMeta } from "./search/page";

afterEach(cleanup);

async function renderSearch(searchParams: Record<string, string | string[]>) {
  // A server component: await it, then render what it returned.
  render(await SearchPage({ searchParams: Promise.resolve(searchParams), params: Promise.resolve({}) }));
}

describe("page titles (layout template `%s · openproceedings`)", () => {
  it.each([
    [searchMeta, "Search"],
    [coverageMeta, "Coverage"],
    [syntaxMeta, "Query syntax"],
    [paperMeta, "Paper"],
    [recordMeta, "Search record"],
  ])("%j", (meta, title) => {
    expect(meta.title).toBe(title);
  });
});

describe("not-found page", () => {
  it("has a heading and a link home, in project tokens", () => {
    render(<NotFound />);
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("Page not found");
    expect(screen.getByRole("link").getAttribute("href")).toBe("/");
  });
});

describe("visible copy has no internal task ids or route paths", () => {
  it.each([
    ["home", () => render(<HomePage />)],
    ["placeholder", () => render(<SyntaxHelpPage />)],
  ])("%s", (_name, draw) => {
    draw();
    const text = document.body.textContent ?? "";
    expect(text).not.toMatch(/TASK-\d+/);
    expect(text).not.toMatch(/\/search\b/);
  });
});

describe("/search URL notices", () => {
  it("renders the notice sentence with values in code, and offers the corrected link without redirecting", async () => {
    await renderSearch({ q: ["", "trust"], sort: "random" });
    const list = screen.getByRole("list", { name: "Address notices" });
    const items = within(list).getAllByRole("listitem");
    expect(items.map((li) => li.textContent)).toEqual([
      'q appears more than once; using the first value "" and ignoring trust.',
      "sort=random is not a sort order — sort orders are relevance, year_desc, year_asc, title. " +
        "Sorted by relevance instead.",
    ]);
    expect(items[0]?.querySelectorAll("code")).toHaveLength(3);
    const fix = screen.getByRole("link", { name: "Use corrected link" });
    expect(fix.getAttribute("href")).toBe("/search?q=&mode=native");
  });

  it("shows no notices or corrected link for a clean URL", async () => {
    await renderSearch({ q: "trust", mode: "native" });
    expect(screen.queryByRole("list", { name: "Address notices" })).toBeNull();
    expect(screen.queryByRole("link", { name: "Use corrected link" })).toBeNull();
  });

  it("shows an empty q as a label, not as monospace query text", async () => {
    await renderSearch({});
    const empty = screen.getByText("(empty)");
    expect(empty.className).toMatch(/italic/);
    expect(empty.className).not.toMatch(/font-mono/);
    expect(empty.closest(".font-mono")).toBeNull();
  });
});

describe("favicon", () => {
  it("is a static .ico, so /favicon.ico is not a 404", () => {
    const ico = readFileSync(path.join(import.meta.dirname, "favicon.ico"));
    expect([...ico.subarray(0, 4)]).toEqual([0, 0, 1, 0]);
  });
});
