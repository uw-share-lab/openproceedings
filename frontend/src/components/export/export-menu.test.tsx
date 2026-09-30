// @vitest-environment jsdom
import { cleanup, fireEvent, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { json, renderWithApi, type Handler } from "@/test/api-stub";
import { SEARCHES } from "@/test/record-fixture";
import { fieldWarning, type FieldWarning } from "@/lib/export";
import type { ParsedFilters } from "@/lib/search-state";
import { ExportMenu } from "./export-menu";

beforeEach(() => {
  URL.createObjectURL = vi.fn(() => "blob:test");
  URL.revokeObjectURL = vi.fn();
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const S = SEARCHES.statuses;
const SOURCE = {
  kind: "search" as const,
  q: S.q,
  mode: S.mode,
  indexVersion: S.search.index_version,
  total: S.search.total,
};
const papers = `${S.search.total} papers`;

function warningsOf(name: keyof typeof SEARCHES): FieldWarning[] {
  const c = SEARCHES[name];
  const filters = c.parse.filters as unknown as ParsedFilters;
  return (["status", "track"] as const).flatMap((f) => {
    const w = fieldWarning(f, filters, c.parse.defaults, c.search.facets[f]);
    return w === null ? [] : [w];
  });
}

function file(headers: Record<string, string> = {}): Response {
  return new Response("TY  - CPAPER\nER  - \n", {
    headers: {
      "X-Index-Version": SOURCE.indexVersion,
      "X-Total": String(SOURCE.total),
      "Content-Disposition": 'attachment; filename="openproceedings-x.ris"',
      ...headers,
    },
  });
}

function draw(handler: Handler = () => file(), over: Partial<Parameters<typeof ExportMenu>[0]> = {}) {
  const onShowFilter = vi.fn();
  const onSearchAgain = vi.fn();
  const r = renderWithApi(
    <ExportMenu
      source={SOURCE}
      disabledReason={null}
      warnings={warningsOf("statuses")}
      onShowFilter={onShowFilter}
      onSearchAgain={onSearchAgain}
      {...over}
    />,
    handler,
  );
  return {
    ...r,
    onShowFilter,
    onSearchAgain,
    trigger: screen.getByRole("button", { name: `Export ${papers}` }),
  };
}

describe("the menu button (design §Keyboard and screen reader)", () => {
  it("opens on ↓ at the first format; arrows, Home and End move; Esc closes and returns focus", () => {
    const { trigger } = draw();
    expect(trigger.getAttribute("aria-haspopup")).toBe("menu");
    fireEvent.keyDown(trigger, { key: "ArrowDown" });
    const menu = screen.getByRole("menu", { name: `Export ${papers}` });
    const items = within(menu).getAllByRole("menuitem");
    expect(items.map((i) => i.getAttribute("aria-label"))).toEqual([
      `RIS, for Covidence, Zotero, EndNote, ${papers}`,
      `CSV, spreadsheet, UTF-8, ${papers}`,
      `BibTeX, ${papers}`,
      `JSONL, every field, one line each, ${papers}`,
    ]);
    expect(document.activeElement).toBe(items[0]);
    fireEvent.keyDown(menu, { key: "ArrowDown" });
    expect(document.activeElement).toBe(items[1]);
    fireEvent.keyDown(menu, { key: "End" });
    expect(document.activeElement).toBe(items[3]);
    fireEvent.keyDown(menu, { key: "ArrowDown" });
    expect(document.activeElement).toBe(items[0]);
    fireEvent.keyDown(menu, { key: "ArrowUp" });
    expect(document.activeElement).toBe(items[3]);
    fireEvent.keyDown(menu, { key: "Home" });
    expect(document.activeElement).toBe(items[0]);
    fireEvent.keyDown(menu, { key: "Escape" });
    expect(screen.queryByRole("menu")).toBeNull();
    expect(document.activeElement).toBe(trigger);
    expect(trigger.getAttribute("aria-expanded")).toBe("false");
  });

  it("opens on ↑ at the last format", () => {
    const { trigger } = draw();
    fireEvent.keyDown(trigger, { key: "ArrowUp" });
    expect(document.activeElement?.getAttribute("aria-label")).toMatch(/^JSONL/);
  });

  it("says the export is of all the papers, from the shown index", () => {
    const { trigger } = draw();
    fireEvent.click(trigger);
    expect(screen.getByText(/^Export all/).textContent).toBe(
      `Export all ${papers} of this search from index ${SOURCE.indexVersion}`,
    );
    expect(screen.getByText("Importing into Covidence")).toBeTruthy();
  });

  it("is disabled with the reason while the results aren't the searched query's", () => {
    const { trigger } = draw(undefined, { disabledReason: "The results shown are from an earlier query." });
    expect(trigger.getAttribute("aria-disabled")).toBe("true");
    fireEvent.click(trigger);
    expect(screen.queryByRole("menu")).toBeNull();
    expect(screen.getByText("The results shown are from an earlier query.").id).toBe(
      trigger.getAttribute("aria-describedby"),
    );
  });
});

describe("the status warning (design E2)", () => {
  const facets = S.search.facets.status;

  it("sits beside the closed button and describes the open menu, with each count listed", () => {
    const { trigger } = draw();
    const line = screen.getByRole("button", { name: /Includes/ });
    expect(line.textContent).toContain(
      `Includes ${facets["rejected"]} rejected, ${facets["withdrawn"]} withdrawn papers`,
    );
    fireEvent.click(trigger);
    const menu = screen.getByRole("menu");
    const described = (menu.getAttribute("aria-describedby") ?? "")
      .split(" ")
      .map((id) => document.getElementById(id)?.textContent);
    expect(described.join(" ")).toContain("This export includes papers that were not accepted");
    expect(described.join(" ")).toContain("Covidence doesn't show a paper's status to screeners");
  });

  it("closes the menu and hands focus to the Status filter on request", () => {
    const { trigger, onShowFilter } = draw();
    fireEvent.click(trigger);
    fireEvent.click(screen.getByRole("button", { name: "Show the Status filter" }));
    expect(screen.queryByRole("menu")).toBeNull();
    expect(onShowFilter).toHaveBeenCalledWith("status");
  });

  it("has no warning while the default status filter applies", () => {
    draw(undefined, { warnings: warningsOf("accepted") });
    expect(screen.queryByRole("button", { name: /Includes|May include/ })).toBeNull();
  });

  it("warns about tracks outside the default, with Show the Track filter", () => {
    const { trigger } = draw(undefined, { warnings: warningsOf("workshop") });
    fireEvent.click(trigger);
    expect(screen.getByText(/workshop papers\. Covidence doesn't show a paper's track/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Show the Track filter" })).toBeTruthy();
  });

  it("holds the formats back until the query's filters are known", () => {
    const { trigger } = draw(undefined, { warnings: null });
    fireEvent.click(trigger);
    expect(screen.getByText("Checking the query's filters…")).toBeTruthy();
    for (const item of screen.getAllByRole("menuitem"))
      expect(item.getAttribute("aria-disabled")).toBe("true");
  });
});

describe("exporting (design E1, E3)", () => {
  it("downloads the file pinned to the shown search and announces it", async () => {
    const { trigger, calls } = draw();
    fireEvent.click(trigger);
    fireEvent.click(screen.getAllByRole("menuitem")[0] as HTMLElement);
    expect(await screen.findByText("Download ready.")).toBeTruthy();
    expect(Object.fromEntries(calls[0]?.query ?? [])).toEqual({
      format: "ris",
      q: SOURCE.q,
      mode: SOURCE.mode,
      index_version: SOURCE.indexVersion,
    });
    expect(URL.createObjectURL).toHaveBeenCalledOnce();
  });

  it("saves a file whose abstracts were withheld, and says so until the next export (EX-E8)", async () => {
    let header = "unavailable";
    const { trigger } = draw(() => file({ "X-Abstract-Source": header }));
    expect(screen.queryByText(/This file has no abstracts/)).toBeNull();
    fireEvent.click(trigger);
    fireEvent.click(screen.getAllByRole("menuitem")[0] as HTMLElement);
    expect(await screen.findByText(/^Download ready\. This file has no abstracts/)).toBeTruthy();
    expect(URL.createObjectURL).toHaveBeenCalledOnce();
    const notice = screen.getByText(/Covidence doesn't show that note to screeners/);
    expect(notice.textContent).toContain("This file has no abstracts: their source couldn't be attributed");
    header = "attributed";
    fireEvent.click(screen.getAllByRole("menuitem")[0] as HTMLElement);
    expect(await screen.findByText("Download ready.")).toBeTruthy();
    expect(screen.queryByText(/Covidence doesn't show that note to screeners/)).toBeNull();
  });

  it("downloads nothing when the index changed, and offers Search again", async () => {
    const { trigger, onSearchAgain } = draw(() => file({ "X-Index-Version": "9f8e7d6c5b4a" }));
    fireEvent.click(trigger);
    fireEvent.click(screen.getAllByRole("menuitem")[0] as HTMLElement);
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain(
      `The index changed after this search: the export would come from index 9f8e7d6c5b4a, not ${SOURCE.indexVersion}`,
    );
    expect(URL.createObjectURL).not.toHaveBeenCalled();
    fireEvent.click(within(alert).getByRole("button", { name: "Search again" }));
    expect(onSearchAgain).toHaveBeenCalledOnce();
  });

  it("calls a different count on the same index a bug", async () => {
    const { trigger } = draw(() => file({ "X-Total": String(SOURCE.total - 1) }));
    fireEvent.click(trigger);
    fireEvent.click(screen.getAllByRole("menuitem")[0] as HTMLElement);
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain(`not the ${SOURCE.total} shown, from the same index`);
    expect(alert.textContent).toContain("it is a bug in openproceedings");
    expect(URL.createObjectURL).not.toHaveBeenCalled();
  });

  it("waits out a 429 with the server's message", async () => {
    const { trigger } = draw(() =>
      json({ error: { code: "API_RATE_LIMITED", message: "Slow down." } }, 429, { "Retry-After": "4" }),
    );
    fireEvent.click(trigger);
    fireEvent.click(screen.getAllByRole("menuitem")[1] as HTMLElement);
    expect(await screen.findByText("Slow down.")).toBeTruthy();
    expect(screen.getByText("Retry in 4 s")).toBeTruthy();
  });
});
