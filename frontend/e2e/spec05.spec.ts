import { readFile } from "node:fs/promises";
import { expect, type Locator, type Page, test } from "@playwright/test";

async function resultCount(page: Page): Promise<number> {
  const text = await page
    .locator("strong")
    .filter({ hasText: /^\d+ papers?$/ })
    .first()
    .innerText();
  return Number(text.replace(/[^0-9]/g, ""));
}

async function tabTo(page: Page, target: Locator, limit = 80): Promise<void> {
  for (let i = 0; i < limit; i += 1) {
    await page.keyboard.press("Tab");
    if (await target.evaluate((element) => element === document.activeElement)) return;
  }
  throw new Error(`Tab did not reach ${await target.getAttribute("aria-label")}`);
}

test("the spec 05 review flow searches, includes workshops, exports RIS and saves a reproduced record", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByRole("button", { name: /foundation model.*large language model/i }).click();
  await page.getByRole("button", { name: "Search", exact: true }).click();

  await expect(page).toHaveURL(/\/search\?q=/);
  await expect(page.getByText(/\d+ papers/).first()).toBeVisible();
  const tree = page.getByRole("button", { name: /How we read your query/ });
  if ((await tree.getAttribute("aria-expanded")) !== "true") await tree.click();
  await expect(page.getByRole("list", { name: "Query tree" })).toBeVisible();

  const before = await resultCount(page);
  await page.getByRole("button", { name: /Include \d+ workshop papers/ }).click();
  await expect(page).toHaveURL(/track%3A.*workshop/i);
  await expect
    .poll(() => resultCount(page), { message: "the result count changes after workshops are included" })
    .not.toBe(before);
  const total = await resultCount(page);

  const exportButton = page.getByRole("button", { name: `Export ${total} papers` });
  await exportButton.press("ArrowDown");
  const ris = page.getByRole("menuitem", { name: new RegExp(`^RIS,.*${total} papers$`) });
  await expect(ris).toBeFocused();
  const download = page.waitForEvent("download");
  await ris.press("Enter");
  const saved = await download;
  expect(saved.suggestedFilename()).toMatch(/\.ris$/);
  const path = await saved.path();
  expect(path).not.toBeNull();
  const body = await readFile(path as string, "utf8");
  expect(body.match(/^TY  - /gm)).toHaveLength(total);

  await page.getByRole("button", { name: "Save search record" }).click();
  const dialog = page.getByRole("dialog", { name: "Save this search as a permanent record?" });
  const save = dialog.getByRole("button", { name: "Save" });
  await expect(save).toBeFocused();
  await save.press("Enter");
  const recordLink = page.getByRole("link", { name: /\/record\// }).last();
  await expect(recordLink).toBeVisible();
  await recordLink.click();
  await expect(page).toHaveURL(/\/record\/[A-Za-z0-9]{12}$/);
  await expect(page.getByText(/Reproduced on .*same .* papers/i)).toBeVisible();
});

test("the primary search and save controls work by keyboard alone", async ({ page }) => {
  await page.goto("/search?q=trust");
  await expect(page.getByText(/\d+ papers/).first()).toBeVisible();

  const exportButton = page.getByRole("button", { name: /Export \d+ papers/ });
  await tabTo(page, exportButton);
  await page.keyboard.press("ArrowDown");
  const items = page.getByRole("menuitem");
  await expect(items.first()).toBeFocused();
  await page.keyboard.press("End");
  await expect(items.last()).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(exportButton).toBeFocused();

  const saveRecord = page.getByRole("button", { name: "Save search record" });
  await tabTo(page, saveRecord);
  await page.keyboard.press("Enter");
  const dialog = page.getByRole("dialog", { name: "Save this search as a permanent record?" });
  const save = dialog.getByRole("button", { name: "Save" });
  const cancel = dialog.getByRole("button", { name: "Cancel" });
  await expect(save).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(cancel).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(save).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(saveRecord).toBeFocused();
});
