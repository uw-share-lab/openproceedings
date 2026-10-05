import AxeBuilder from "@axe-core/playwright";
import { expect, type Locator, type Page } from "@playwright/test";

export const axeTags = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];

/** `/search?q=&mode=`, waited for until its count is drawn (the data, not only the navigation). */
export async function search(page: Page, q: string, mode: "native" | "scholar" = "native"): Promise<void> {
  await page.goto(`/search?${new URLSearchParams(mode === "native" ? { q } : { q, mode })}`);
  await expect(page.getByText(/\d+ papers?/).first()).toBeVisible();
}

/** Type a query into the editor in a syntax, replacing what it holds; nothing is searched. */
export async function typeQuery(page: Page, text: string, mode: "native" | "scholar"): Promise<Locator> {
  await page.getByRole("combobox", { name: "Syntax" }).selectOption(mode);
  const editor = page.getByRole("textbox", { name: "Query" });
  await editor.focus();
  await page.keyboard.press("ControlOrMeta+A");
  await page.keyboard.insertText(text);
  return editor;
}

/** Tab until `target` has focus (the keyboard's own path to it). */
export async function tabTo(page: Page, target: Locator, limit = 120): Promise<void> {
  for (let i = 0; i < limit; i += 1) {
    await page.keyboard.press("Tab");
    if (await target.evaluate((element) => element === document.activeElement)) return;
  }
  throw new Error("Tab did not reach the target");
}

/** axe, WCAG 2.2 AA, on the page as it stands. */
export async function expectNoAxeViolations(page: Page, what: string): Promise<void> {
  const result = await new AxeBuilder({ page }).withTags(axeTags).analyze();
  expect(result.violations, what).toEqual([]);
}

/** WCAG 1.4.10 at the current width: the page does not scroll sideways. */
export async function expectNoSidewaysScroll(page: Page, what: string): Promise<void> {
  const widths = await page.evaluate(() => ({
    client: document.documentElement.clientWidth,
    scroll: document.documentElement.scrollWidth,
  }));
  expect(widths.scroll, what).toBeLessThanOrEqual(widths.client);
}

/** Every button in `within` is at least 24 × 24 CSS px (WCAG 2.5.8). */
export async function expectTargets(within: Locator): Promise<void> {
  for (const target of await within.getByRole("button").all()) {
    if (!(await target.isVisible())) continue;
    const bounds = await target.boundingBox();
    expect(bounds?.height).toBeGreaterThanOrEqual(24);
    expect(bounds?.width).toBeGreaterThanOrEqual(24);
  }
}

export async function chooseTheme(page: Page, theme: "light" | "dark"): Promise<void> {
  await page.addInitScript((value) => localStorage.setItem("theme", value), theme);
}

/** The states this file's specs check in both themes and at both widths (axe; reflow at 320 px). */
export const THEMES = ["light", "dark"] as const;
export const WIDTHS = [1280, 320] as const;
