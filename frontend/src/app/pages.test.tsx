// @vitest-environment jsdom
import { EditorView } from "@codemirror/view";
import { cleanup, render, screen, within } from "@testing-library/react";
import { readFileSync } from "node:fs";
import path from "node:path";
import type { ReactNode } from "react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { json, polyfillLayout, renderWithApi } from "@/test/api-stub";
import { metadata as coverageMeta } from "./coverage/page";
import SyntaxHelpPage, { metadata as syntaxMeta } from "./help/syntax/page";
import NotFound, { metadata as notFoundMeta } from "./not-found";
import HomePage from "./page";
import { metadata as paperMeta } from "./paper/[id]/page";
import { generateMetadata as recordMeta } from "./record/[id]/page";
import SearchPage, { metadata as searchMeta } from "./search/page";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: () => {} }), usePathname: () => "/search" }));
beforeAll(polyfillLayout);
afterEach(cleanup);

/** The workspace's API calls answer "not found": these tests are about the pages, not the answers. */
const withApi = (ui: ReactNode) =>
  renderWithApi(ui, () => json({ error: { code: "API_NOT_FOUND", message: "-" } }, 404));

async function renderSearch(searchParams: Record<string, string | string[]>) {
  // A server component: await it, then render what it returned.
  return withApi(
    await SearchPage({ searchParams: Promise.resolve(searchParams), params: Promise.resolve({}) }),
  );
}

describe("page titles (layout template `%s · openproceedings`)", () => {
  it.each([
    [searchMeta, "Search"],
    [coverageMeta, "Coverage"],
    [syntaxMeta, "Query syntax"],
    [paperMeta, "Paper"],
    [notFoundMeta, "Page not found"],
  ])("%j", (meta, title) => {
    expect(meta.title).toBe(title);
  });
});

describe("record page title (copy RC-1)", () => {
  it("names the record", async () => {
    const meta = await recordMeta({
      params: Promise.resolve({ id: "Ab3dE5fG7hJ9" }),
      searchParams: Promise.resolve({}),
    });
    expect(meta.title).toBe("Search record Ab3dE5fG7hJ9");
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
    ["home", () => withApi(<HomePage />)],
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

  it("heads the notices with what they are, and opens the workspace on the URL's q and mode", async () => {
    const { container } = await renderSearch({ q: "trust*", mode: "scholar", utm: "x" });
    expect(screen.getByText("This link had parameters that weren't used:")).toBeTruthy();
    const view = EditorView.findFromDOM(container.querySelector(".cm-editor") as HTMLElement);
    expect(view?.state.doc.toString()).toBe("trust*");
    expect((screen.getByRole("combobox", { name: "Syntax" }) as HTMLSelectElement).value).toBe("scholar");
  });
});

describe("favicon", () => {
  it("is a static .ico, so /favicon.ico is not a 404", () => {
    const ico = readFileSync(path.join(import.meta.dirname, "favicon.ico"));
    expect([...ico.subarray(0, 4)]).toEqual([0, 0, 1, 0]);
  });
});
