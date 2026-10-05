import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";

type Theme = "light" | "dark";
type State = { name: string; open: (page: Page) => Promise<void> };

const axeTags = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];

async function chooseTheme(page: Page, theme: Theme): Promise<void> {
  await page.addInitScript((value) => localStorage.setItem("theme", value), theme);
}

async function search(page: Page, q = "trust"): Promise<void> {
  await page.goto(`/search?${new URLSearchParams({ q })}`);
  await expect(page.getByText(/\d+ papers/).first()).toBeVisible();
}

/**
 * Search `benchmark`, then compare it with a RIS file a reviewer could hold: this instance's own export of
 * another search (`trust`), so some of its papers are kept, some dropped and others added (TASK-177).
 */
async function compare(page: Page): Promise<void> {
  // the fixture API's port: 8000 unless OP_E2E_API_PORT moves it (playwright.config.ts)
  const api = `http://127.0.0.1:${process.env.OP_E2E_API_PORT ?? "8000"}`;
  const held = await page.request.get(
    `${api}/api/v1/export?${new URLSearchParams({ q: "trust venue:ICLR", format: "ris" })}`,
  );
  expect(held.ok()).toBe(true);
  await search(page, "benchmark");
  await page.getByRole("button", { name: /Compare with your records/ }).click();
  await page.getByLabel("RIS file").setInputFiles({
    name: "my-records.ris",
    mimeType: "application/x-research-info-systems",
    buffer: await held.body(),
  });
  await page.getByRole("button", { name: "Compare", exact: true }).click();
  await expect(
    page.getByRole("table", { name: "What this search does to the papers in your file" }),
  ).toBeVisible({
    timeout: 60_000,
  });
}

/** A record's "See also" line (copy RH-18, PA-10): the fixture's two twins draw one each. */
const seeAlso = (page: Page) => page.locator("p").filter({ hasText: /^See also \(the same paper/ });

const states: State[] = [
  {
    name: "home",
    open: async (page) => {
      await page.goto("/");
      await expect(page.getByRole("button", { name: "Search", exact: true })).toBeVisible();
      await expect(page.getByText(/records indexed/)).toBeVisible();
    },
  },
  {
    name: "search results",
    open: async (page) => {
      await search(page);
      // the fixture makes the first two `trust` results twins (fixture_server.py, TASK-162)
      await expect(seeAlso(page).first()).toBeVisible();
    },
  },
  {
    name: "parse error",
    open: async (page) => {
      await page.goto(`/search?${new URLSearchParams({ q: "(trust" })}`);
      await expect(page.getByRole("region", { name: "Diagnostics" })).toBeVisible();
    },
  },
  {
    name: "expanded query explanation",
    open: async (page) => {
      await search(page);
      await page.getByRole("button", { name: /How we read your query/ }).click();
      await expect(page.getByRole("list", { name: "Query tree" })).toBeVisible();
    },
  },
  {
    name: "expanded exclusions explanation",
    open: async (page) => {
      await search(page);
      await page.getByRole("button", { name: "About these exclusions" }).click();
      await expect(page.getByRole("button", { name: "Close" })).toBeVisible();
    },
  },
  {
    name: "editable builder",
    open: async (page) => {
      await search(page, "(trust* OR reliance) AND benchmark");
      await page.getByRole("tab", { name: "Builder" }).click();
      const group = page.getByRole("group", { name: /Group 1 of 2/ });
      await expect(group.getByRole("list", { name: "Expansions" })).toBeVisible();
    },
  },
  {
    name: "read-only builder",
    open: async (page) => {
      // the parts that fit (TASK-111) are drawn dimmed under the notice, with a wildcard's expansions
      await search(page, "(abstract:trust* OR reliance) (venue:ICLR OR venue:ICML) trust NEAR/3 bias");
      await page.getByRole("tab", { name: "Builder" }).click();
      await expect(
        page.getByRole("heading", { name: "This query is too complex for the builder" }),
      ).toBeVisible();
      const parts = page.getByRole("region", { name: "Parts that fit the builder" });
      await expect(parts.getByRole("list", { name: "Expansions" })).toBeVisible();
    },
  },
  {
    name: "save confirmation dialog",
    open: async (page) => {
      await search(page);
      await page.getByRole("button", { name: "Save search record" }).click();
      await expect(
        page.getByRole("dialog", { name: "Save this search as a permanent record?" }),
      ).toBeVisible();
    },
  },
  {
    name: "paper detail",
    open: async (page) => {
      await search(page);
      await page.getByRole("list", { name: "Results" }).getByRole("link").first().click();
      await expect(page.locator("main h1").first()).toBeVisible();
      await expect(page).toHaveURL(/\/paper\//);
      await expect(seeAlso(page)).toHaveCount(1); // the first result is a twin; the results are gone
      await expect(seeAlso(page)).toBeVisible();
    },
  },
  {
    name: "reproduced record",
    open: async (page) => {
      await search(page);
      await page.getByRole("button", { name: "Save search record" }).click();
      await page.getByRole("dialog").getByRole("button", { name: "Save" }).click();
      const link = page.getByRole("link", { name: /\/record\// }).last();
      await expect(link).toBeVisible();
      await link.click();
      await expect(page.getByText(/Reproduced on .*same .* papers/i)).toBeVisible();
    },
  },
  {
    name: "comparison with a RIS file",
    open: async (page) => {
      await compare(page);
      await page.getByRole("button", { name: /^Show the \d+ dropped papers?$/ }).click();
      await expect(
        page
          .getByRole("region", { name: /dropped papers?$/ })
          .getByRole("listitem")
          .first(),
      ).toBeVisible();
    },
  },
  {
    name: "coverage",
    open: async (page) => {
      await page.goto("/coverage");
      await expect(page.getByRole("region", { name: "Coverage table" })).toBeVisible();
    },
  },
  {
    name: "syntax help with instance limits",
    open: async (page) => {
      await page.goto("/help/syntax");
      await expect(page.getByText(/At most .* characters .* in a query/)).toBeVisible();
    },
  },
];

for (const theme of ["light", "dark"] as const) {
  for (const width of [1280, 320]) {
    test(`axe finds no WCAG 2.2 AA violations in selected UI states (${theme}, ${width}px)`, async ({
      page,
    }) => {
      // twelve page loads and axe runs over pages of 50 results, each with its links and toggles
      test.setTimeout(120_000);
      await page.setViewportSize({ width, height: 900 });
      await chooseTheme(page, theme);
      for (const state of states) {
        await test.step(state.name, async () => {
          await state.open(page);
          const result = await new AxeBuilder({ page }).withTags(axeTags).analyze();
          expect(result.violations, `${state.name} in ${theme} at ${width}px`).toEqual([]);
        });
      }
    });
  }
}

test("compact controls meet the 24px WCAG 2.2 target minimum", async ({ page }) => {
  await page.goto("/coverage");
  await expect(page.getByRole("region", { name: "Coverage table" })).toBeVisible();
  const copies = page.getByRole("button", { name: /^Copy / });
  await expect(copies.first()).toBeVisible();
  for (const button of await copies.all()) {
    const bounds = await button.boundingBox();
    expect(bounds?.width).toBeGreaterThanOrEqual(24);
    expect(bounds?.height).toBeGreaterThanOrEqual(24);
  }
});

test("each result's author toggle and abstract source link meet the 24px target minimum", async ({
  page,
}) => {
  await page.goto(`/search?${new URLSearchParams({ q: "trust" })}`);
  await expect(page.getByText(/\d+ papers/).first()).toBeVisible();
  const targets = [
    page.getByRole("button", { name: /^Show all \d+ authors$/ }),
    page
      .locator("article p")
      .filter({ hasText: /^Abstract: / })
      .getByRole("link"),
    seeAlso(page).getByRole("link"), // TASK-162
  ];
  for (const found of targets) {
    await expect(found.first()).toBeVisible();
    for (const target of await found.all()) {
      const bounds = await target.boundingBox();
      expect(bounds?.width).toBeGreaterThanOrEqual(24);
      expect(bounds?.height).toBeGreaterThanOrEqual(24);
    }
  }
});

test("the 320px pages do not overflow sideways", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 900 });
  // the first result's paper page: a twin, so its "See also" line (a long monospace id) is drawn (TASK-162)
  await search(page);
  const first = page.getByRole("list", { name: "Results" }).getByRole("link").first();
  const paper = await first.getAttribute("href");
  expect(paper).not.toBeNull();
  for (const path of ["/", "/search?q=trust", "/coverage", "/help/syntax", paper ?? ""]) {
    await page.goto(path);
    if (path.startsWith("/search?")) await expect(page.getByText(/\d+ papers/).first()).toBeVisible();
    else if (path.startsWith("/paper/")) await expect(seeAlso(page)).toBeVisible();
    else if (path === "/coverage")
      await expect(page.getByRole("region", { name: "Coverage table" })).toBeVisible();
    else if (path === "/help/syntax") await expect(page.getByText(/At most .* characters/)).toBeVisible();
    else await expect(page.getByText(/records indexed/)).toBeVisible();
    const sizes = await page.evaluate(() => {
      const viewport = document.documentElement.clientWidth;
      const overflowing = [...document.querySelectorAll<HTMLElement>("body *")]
        .filter((element) => {
          const rect = element.getBoundingClientRect();
          if (rect.right <= viewport + 1 && rect.left >= -1) return false;
          for (let ancestor = element.parentElement; ancestor; ancestor = ancestor.parentElement) {
            const overflowX = getComputedStyle(ancestor).overflowX;
            if (["auto", "hidden", "scroll"].includes(overflowX)) return false;
          }
          return true;
        })
        .slice(0, 5)
        .map((element) => `${element.tagName.toLowerCase()}.${element.className}`);
      const layout = [
        "main",
        "main > section",
        "[aria-label='Coverage table']",
        "[aria-label='Coverage table'] table",
      ].map((selector) => {
        const element = document.querySelector<HTMLElement>(selector);
        if (!element) return `${selector}=missing`;
        const rect = element.getBoundingClientRect();
        return `${selector}=${Math.round(rect.width)}/${element.clientWidth}/${element.scrollWidth}`;
      });
      const before = document.scrollingElement?.scrollLeft ?? 0;
      document.scrollingElement?.scrollTo({ left: 10_000 });
      const rootScrollLeft = document.scrollingElement?.scrollLeft ?? 0;
      document.scrollingElement?.scrollTo({ left: before });
      layout.push(
        `html=${document.documentElement.clientWidth}/${document.documentElement.scrollWidth}`,
        `body=${document.body.clientWidth}/${document.body.scrollWidth}`,
        `rootScrollLeft=${rootScrollLeft}`,
      );
      return { viewport, page: document.documentElement.scrollWidth, overflowing, layout };
    });
    expect(
      sizes.page,
      `${path}: ${sizes.overflowing.join(", ")} (${sizes.layout.join(", ")})`,
    ).toBeLessThanOrEqual(sizes.viewport);
  }
});

test("every page ends with the takedown contact footer (decision-018)", async ({ page }) => {
  const pages: State[] = [
    states[0],
    states[1],
    states.find((s) => s.name === "paper detail"),
    states.find((s) => s.name === "coverage"),
  ].filter((s): s is State => s !== undefined);
  expect(pages.map((s) => s.name)).toEqual(["home", "search results", "paper detail", "coverage"]);
  for (const width of [1280, 320]) {
    await page.setViewportSize({ width, height: 900 });
    for (const state of pages) {
      await test.step(`${state.name} at ${width}px`, async () => {
        await state.open(page);
        const footer = page.getByRole("contentinfo");
        await expect(footer).toHaveCount(1);
        await expect(footer).toHaveText(
          "To have an abstract removed from this site, email takedown@example.org.",
        );
        const link = footer.getByRole("link", { name: "takedown@example.org" });
        await expect(link).toHaveAttribute("href", "mailto:takedown@example.org");
        const box = await link.boundingBox();
        const viewport = await page.evaluate(() => document.documentElement.clientWidth);
        expect(
          box && box.x >= 0 && box.x + box.width <= viewport + 1,
          `${state.name} link inside ${viewport}px`,
        ).toBe(true);
      });
    }
  }
});

test("a comparison with a RIS file is run and read by keyboard, and fits 320px", async ({ page }) => {
  test.setTimeout(120_000);
  await page.setViewportSize({ width: 320, height: 900 });
  await compare(page);
  // the answer's heading has focus, so a screen reader starts at the result; the counts come first
  const heading = page.getByRole("heading", { name: /^Comparison with my-records\.ris$/ });
  await expect(heading).toBeFocused();
  const table = page.getByRole("table", { name: "What this search does to the papers in your file" });
  await expect(table.getByRole("rowheader")).toHaveText([/^Kept/, /^Dropped/, /^Not in the index/, /^Added/]);
  const counts = (await table.getByRole("cell").allTextContents()).map((text) =>
    Number(text.replace(/,/g, "")),
  );
  expect(counts.every((count) => Number.isInteger(count))).toBe(true);
  const [kept = 0, dropped = 0, , added = 0] = counts;
  expect(kept).toBeGreaterThan(0);
  expect(dropped).toBeGreaterThan(0);
  expect(added).toBeGreaterThan(0);
  // kept and added are this search's papers, as the results header counts them
  const shown = await page
    .getByText(/^[\d,]+ papers$/)
    .first()
    .textContent();
  expect(kept + added).toBe(Number((shown ?? "").replace(/[^\d]/g, "")));
  // from the heading, Tab reaches each list's controls in order; Enter opens a list
  await page.keyboard.press("Tab");
  await expect(page.getByRole("button", { name: /^Show the [\d,]+ kept papers?$/ })).toBeFocused();
  await page.keyboard.press("Enter");
  const keptList = page.getByRole("region", { name: /kept papers?$/ });
  await expect(keptList.getByRole("listitem")).toHaveCount(Math.min(kept, 100));
  await expect(page.getByRole("button", { name: /^Hide the [\d,]+ kept papers?$/ })).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(keptList.getByRole("button", { name: /^Download CSV/ })).toBeFocused();
  for (const target of await page
    .getByRole("region", { name: "Compare with your records" })
    .getByRole("button")
    .all()) {
    const bounds = await target.boundingBox();
    expect(bounds?.height).toBeGreaterThanOrEqual(24);
    expect(bounds?.width).toBeGreaterThanOrEqual(24);
  }
  const widths = await page.evaluate(() => ({
    client: document.documentElement.clientWidth,
    scroll: document.documentElement.scrollWidth,
  }));
  expect(widths.scroll).toBeLessThanOrEqual(widths.client);
});
