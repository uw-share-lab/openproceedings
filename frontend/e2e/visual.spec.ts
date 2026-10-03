import path from "node:path";
import { expect, test } from "@playwright/test";

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
