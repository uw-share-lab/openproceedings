import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";

type Theme = "light" | "dark";

async function chooseTheme(page: Page, theme: Theme): Promise<void> {
  await page.addInitScript((value) => localStorage.setItem("theme", value), theme);
}

async function ready(page: Page, path: string): Promise<void> {
  await page.goto(path);
  if (path.startsWith("/search?")) {
    await expect(page.getByText(/\d+ papers/).first()).toBeVisible();
  } else if (path === "/coverage") {
    await expect(page.getByRole("region", { name: "Coverage table" })).toBeVisible();
  } else if (path === "/help/syntax") {
    await expect(page.getByRole("heading", { name: "Query syntax", level: 1 })).toBeVisible();
  } else {
    await expect(page.getByRole("button", { name: "Search", exact: true })).toBeVisible();
  }
}

for (const theme of ["light", "dark"] as const) {
  for (const width of [1280, 320]) {
    test(`axe finds no WCAG 2.2 AA violations on core pages (${theme}, ${width}px)`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await chooseTheme(page, theme);
      for (const path of ["/", "/search?q=trust", "/coverage", "/help/syntax"]) {
        await ready(page, path);
        const result = await new AxeBuilder({ page })
          .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
          .analyze();
        expect(result.violations, `${path} in ${theme} at ${width}px`).toEqual([]);
      }
    });
  }
}

test("the 320px pages do not overflow sideways", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 900 });
  for (const path of ["/", "/search?q=trust", "/coverage", "/help/syntax"]) {
    await ready(page, path);
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
