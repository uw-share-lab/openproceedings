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

const states: State[] = [
  {
    name: "home",
    open: async (page) => {
      await page.goto("/");
      await expect(page.getByRole("button", { name: "Search", exact: true })).toBeVisible();
    },
  },
  { name: "search results", open: (page) => search(page) },
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
      await search(page, "(trust OR reliance) AND benchmark");
      await page.getByRole("tab", { name: "Builder" }).click();
      await expect(page.getByRole("group", { name: /Group 1 of 2/ })).toBeVisible();
    },
  },
  {
    name: "read-only builder",
    open: async (page) => {
      await search(page, "trust NEAR/5 calibrat*");
      await page.getByRole("tab", { name: "Builder" }).click();
      await expect(
        page.getByRole("heading", { name: "This query is too complex for the builder" }),
      ).toBeVisible();
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
    test(`axe finds no WCAG 2.2 AA violations in every UI state (${theme}, ${width}px)`, async ({ page }) => {
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

test("the 320px pages do not overflow sideways", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 900 });
  for (const path of ["/", "/search?q=trust", "/coverage", "/help/syntax"]) {
    await page.goto(path);
    if (path.startsWith("/search?")) await expect(page.getByText(/\d+ papers/).first()).toBeVisible();
    else if (path === "/coverage")
      await expect(page.getByRole("region", { name: "Coverage table" })).toBeVisible();
    else if (path === "/help/syntax") await expect(page.getByText(/At most .* characters/)).toBeVisible();
    else await expect(page.getByRole("button", { name: "Search", exact: true })).toBeVisible();
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
