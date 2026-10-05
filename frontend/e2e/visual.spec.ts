import path from "node:path";
import { expect, type Locator, type Page, test } from "@playwright/test";
import { apiUrl } from "./instances";

for (const theme of ["light", "dark"] as const) {
  test(`/search visual regression in ${theme} theme`, async ({ page }) => {
    await page.addInitScript((value) => localStorage.setItem("theme", value), theme);
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto("/search?q=trust");
    await expect(page.getByText(/\d+ papers/).first()).toBeVisible();
    await expect(page.locator("html")).toHaveClass(new RegExp(theme));
    await expect(page).toHaveScreenshot(`search-${theme}.png`, {
      fullPage: true,
      stylePath: path.join(process.cwd(), "e2e", "visual.css"),
    });
  });
}

/**
 * The three surfaces TASK-175, TASK-176 and TASK-177 added, each as its own element (TASK-182): the page
 * around them is the baseline above. The fixture is fixed, so every number in them is.
 */
const surfaces: { name: string; open: (page: Page) => Promise<Locator> }[] = [
  {
    name: "word-forms",
    open: async (page) => {
      await page.goto(
        `/search?${new URLSearchParams({ q: 'trust benchmark "language model"', mode: "scholar" })}`,
      );
      await expect(page.getByText(/\d+ papers?/).first()).toBeVisible();
      await page.getByRole("button", { name: "Choose terms" }).click();
      await page.getByRole("group", { name: "Add $ to" }).getByRole("checkbox").first().check();
      return page.getByRole("region", { name: "Diagnostics" });
    },
  },
  {
    name: "group-counts",
    open: async (page) => {
      const q = "(trust OR reliance) AND benchmark AND (trust OR reliance) AND (agent OR model)";
      await page.goto(`/search?${new URLSearchParams({ q })}`);
      await expect(page.getByText(/\d+ papers?/).first()).toBeVisible();
      await page.getByRole("tab", { name: "Builder" }).click();
      const builder = page.getByRole("tabpanel", { name: "Builder" });
      await expect(builder.getByText(/this group by itself/)).toHaveCount(3);
      return builder;
    },
  },
  {
    name: "comparison",
    open: async (page) => {
      const params = new URLSearchParams({ q: "trust venue:ICLR", format: "ris" });
      const held = await page.request.get(`${apiUrl()}/api/v1/export?${params}`);
      const extra = "TY  - JOUR\nTI  - a paper no index holds\nJF  - NeurIPS\nPY  - 2024\nER  - \n";
      await page.goto("/search?q=benchmark");
      await expect(page.getByText(/\d+ papers?/).first()).toBeVisible();
      await page.getByRole("button", { name: /Compare with your records/ }).click();
      const panel = page.getByRole("region", { name: "Compare with your records" });
      await panel.getByLabel("RIS file").setInputFiles({
        name: "my-records.ris",
        mimeType: "application/x-research-info-systems",
        buffer: Buffer.concat([await held.body(), Buffer.from(extra)]),
      });
      await panel.getByRole("button", { name: "Compare", exact: true }).click();
      await expect(panel.getByRole("table")).toBeVisible({ timeout: 60_000 });
      await panel.getByRole("button", { name: /^List the \d+ papers? not in the index$/ }).click();
      return panel;
    },
  },
];

for (const theme of ["light", "dark"] as const) {
  for (const surface of surfaces) {
    test(`${surface.name} visual regression in ${theme} theme`, async ({ page }) => {
      await page.addInitScript((value) => localStorage.setItem("theme", value), theme);
      await page.setViewportSize({ width: 1440, height: 1000 });
      const element = await surface.open(page);
      await expect(page.locator("html")).toHaveClass(new RegExp(theme));
      await expect(element).toHaveScreenshot(`${surface.name}-${theme}.png`, {
        stylePath: path.join(process.cwd(), "e2e", "visual.css"),
      });
    });
  }
}
