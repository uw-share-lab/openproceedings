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
  const reviewExample = page.getByRole("button", { name: /foundation model.*large language model/i });
  const reviewString = (await reviewExample.innerText()).replace(/^▸\s*/u, "");
  await page.getByRole("combobox", { name: "Syntax" }).selectOption("scholar");
  const editor = page.getByRole("textbox", { name: "Query" });
  await editor.focus();
  await page.keyboard.insertText(reviewString);
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
  const displayedIndex = await page
    .locator("strong")
    .filter({ hasText: /^\d+ papers?$/ })
    .first()
    .locator("..")
    .locator("code")
    .innerText();
  const shown = new URL(page.url()).searchParams;
  const apiQuery = new URLSearchParams({
    q: shown.get("q") as string,
    mode: shown.get("mode") ?? "native",
  });
  const searchResponse = await page.request.get(`http://127.0.0.1:8000/api/v1/search?${apiQuery}`);
  expect(searchResponse.ok()).toBe(true);
  const searched = (await searchResponse.json()) as { total: number; index_version: string };
  expect(total).toBe(searched.total);
  expect(displayedIndex).toBe(searched.index_version);

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
  const records = body.split("ER  - \n").filter((record) => record.trim() !== "");
  expect(body.endsWith("ER  - \n\n")).toBe(true);
  expect(records).toHaveLength(total);
  for (const record of records) {
    const normalized = record.trimStart();
    expect(normalized.startsWith("TY  - ")).toBe(true);
    expect(normalized).toContain(`N1  - openproceedings ${displayedIndex} · query `);
  }

  await page.getByRole("button", { name: "Save search record" }).click();
  const dialog = page.getByRole("dialog", { name: "Save this search as a permanent record?" });
  const save = dialog.getByRole("button", { name: "Save" });
  await expect(save).toBeFocused();
  await save.press("Enter");
  const recordLink = page.getByRole("link", { name: /\/record\// }).last();
  await expect(recordLink).toBeVisible();
  await recordLink.click();
  await expect(page).toHaveURL(/\/record\/[A-Za-z0-9_-]{12}$/);
  await expect(page.getByText(/Reproduced on .*same .* papers/i)).toBeVisible();
});

test("the home coverage line states /coverage's facts in its words", async ({ page }) => {
  await page.goto("/coverage");
  await expect(page.getByRole("region", { name: "Coverage table" })).toBeVisible();
  const built = await page.getByText(/^Built /).innerText();
  const window = built.split(" · ")[1];
  expect(window).toMatch(
    /^(Crawled|Google Scholar searches run|Collected) (on \d{4}-\d{2}-\d{2}|\d{4}-\d{2}-\d{2} to \d{4}-\d{2}-\d{2})$/,
  );
  const range = (window ?? "").match(/(\d{4}-\d{2}-\d{2}) to (\d{4}-\d{2}-\d{2})$/);
  if (range) expect(range[1]).not.toBe(range[2]); // a same-day window reads "on <day>"
  const records = (await page.getByText(/ records · /).innerText()).split(" ")[0];

  await page.goto("/");
  const line = page.getByText(/records indexed/);
  await expect(line).toBeVisible();
  const text = await line.innerText();
  expect(text).toContain(`${records} records indexed`);
  expect(text).toContain(` · ${window} · `);
  await expect(line.getByRole("link", { name: "Coverage ▸" })).toHaveAttribute("href", "/coverage");
});

test("the editor exposes completion, diagnostics and submission to the keyboard", async ({ page }) => {
  await page.goto("/");
  const editor = page.getByRole("textbox", { name: "Query" });
  await expect(editor).toBeFocused();
  await page.keyboard.type("track:");
  await page.keyboard.press("Control+Space");
  const completions = page.getByRole("listbox");
  await expect(completions).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(completions).toBeHidden();
  await page.keyboard.press("Control+Space");
  await expect(completions).toBeVisible();
  await page.keyboard.press("ArrowDown", { delay: 100 });
  await page.keyboard.press("Enter");
  await expect(editor).toContainText(/^track:\w+/);

  await expect(editor).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(editor).not.toBeFocused();
  await page.goto("/");
  await expect(editor).toBeFocused();
  await page.keyboard.press("ControlOrMeta+A");
  await page.keyboard.type("trust");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/search\?q=trust/);
  await expect(page.getByRole("heading", { name: /Results, page 1 of/ })).toBeVisible();

  await page.goto(`/search?${new URLSearchParams({ q: "(trust" })}`);
  await expect(page.getByRole("region", { name: "Diagnostics" })).toBeVisible();
  const errorEditor = page.getByRole("textbox", { name: "Query" });
  await tabTo(page, errorEditor);
  await page.keyboard.press("ControlOrMeta+Shift+KeyM");
  await expect(page.locator(".cm-panel-lint")).toBeVisible();
});

test("Load with parentheses loads the server's whole reading of a mixed AND/OR query, unsearched", async ({
  page,
}) => {
  // over 120 code points, so the warning's message quotes a shortened reading: the button uses the
  // diagnostic's `reading` field (TASK-099), which never is
  const terms = ["reliance", "overreliance", "appropriate reliance", "human-AI teaming", "calibrated trust"];
  const tail = terms.map((t) => (t.includes(" ") ? `"${t}"` : t)).join(" OR ");
  const q = `trust calibration OR ${tail} OR automation bias OR complacency`;
  const read = `(trust calibration) OR ${tail} OR (automation bias) OR complacency`;
  expect(q.length).toBeGreaterThan(120);
  await page.goto("/");
  const editor = page.getByRole("textbox", { name: "Query" });
  await expect(editor).toBeFocused();
  await page.keyboard.type(q);
  const load = page.getByRole("button", { name: "Load with parentheses" });
  await expect(load).toBeVisible();
  await load.click();
  await expect(editor).toHaveText(read);
  await expect(page).toHaveURL(/\/$/); // loaded as a draft: nothing was searched
  await expect(load).toBeHidden(); // the loaded text no longer mixes AND and OR
});

test("the Text and Builder tabs and builder editing work by keyboard alone", async ({ page }) => {
  await page.goto(`/search?${new URLSearchParams({ q: "(trust OR reliance) AND benchmark" })}`);
  await expect(page.getByText(/\d+ papers/).first()).toBeVisible();
  const textTab = page.getByRole("tab", { name: "Text" });
  await tabTo(page, textTab);
  await page.keyboard.press("ArrowRight");
  const builderTab = page.getByRole("tab", { name: "Builder" });
  await expect(builderTab).toBeFocused();
  await expect(builderTab).toHaveAttribute("aria-selected", "true");
  await page.keyboard.press("Enter");

  const trust = page.getByRole("button", { name: "trust", exact: true });
  await expect(trust).toBeFocused();
  await page.keyboard.press("Tab");
  const scope = page.getByLabel("Search in:").first();
  await expect(scope).toBeFocused();
  await page.keyboard.press("t");
  await expect(scope).toHaveValue("title");

  const scopedTrust = page.getByRole("button", { name: "title:trust", exact: true });
  await page.keyboard.press("Shift+Tab");
  await expect(scopedTrust).toBeFocused();
  await page.keyboard.press("Alt+ArrowDown");
  await expect(page.getByText("Group moved down: now group 2 of 2.")).toBeAttached();
  await page.keyboard.press("Delete");
  const addTerm = page
    .getByRole("group", { name: /Group 2 of 2.*reliance/ })
    .getByRole("button", { name: "+ term" });
  await expect(addTerm).toBeFocused();
  await page.keyboard.press("Enter");
  const input = page.getByRole("textbox", { name: /Term in group/ });
  await expect(input).toBeFocused();
  await page.keyboard.type("governance");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("button", { name: "governance", exact: true })).toBeVisible();

  const group = page.getByRole("group", { name: /^Group 2 of 2/ });
  const removeGroup = group.getByRole("button", { name: "Remove group" });
  for (let i = 0; i < 12 && !(await removeGroup.evaluate((el) => el === document.activeElement)); i += 1) {
    await page.keyboard.press("Shift+Tab");
  }
  await expect(removeGroup).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByText(/Group 2 removed\. 1 group\./)).toBeAttached();
  await expect(page.locator("h3:focus")).toContainText("Group 1 of 1");

  await page.goto(`/search?${new URLSearchParams({ q: "trust NEAR/5 calibrat*" })}`);
  await expect(page.getByText(/\d+ papers/).first()).toBeVisible();
  const readOnlyTextTab = page.getByRole("tab", { name: "Text" });
  await tabTo(page, readOnlyTextTab);
  await page.keyboard.press("ArrowRight");
  const readOnlyTab = page.getByRole("tab", { name: "Builder" });
  await expect(readOnlyTab).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(
    page.getByRole("heading", { name: "This query is too complex for the builder" }),
  ).toBeFocused();
});

test("filters, exclusions and paging work by keyboard and move focus to updated results", async ({
  page,
}) => {
  await page.goto("/search?q=trust");
  await expect(page.getByText(/\d+ papers/).first()).toBeVisible();

  const main = page.getByRole("checkbox", { name: /main\s*,\s*.* papers/ });
  await tabTo(page, main);
  const initiallyChecked = await main.isChecked();
  await page.keyboard.press("Space");
  await expect(main).toBeChecked({ checked: !initiallyChecked });

  await page.goto("/search?q=trust");
  await expect(page.getByText(/\d+ papers/).first()).toBeVisible();
  const workshop = page.getByRole("button", { name: /Include \d+ workshop papers/ });
  await tabTo(page, workshop);
  await page.keyboard.press("Enter");
  await expect(
    page
      .locator("strong")
      .filter({ hasText: /^\d+ papers?$/ })
      .first(),
  ).toBeFocused();

  const next = page.getByRole("button", { name: /Next/ });
  await tabTo(page, next, 120);
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: /Results, page 2 of/ })).toBeFocused();
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

test("dismissing a pending save preserves its eventual server result", async ({ page }) => {
  let release: () => void = () => {};
  const held = new Promise<void>((resolve) => (release = resolve));
  let committed: () => void = () => {};
  const serverCommitted = new Promise<void>((resolve) => (committed = resolve));
  await page.route(
    (url) => url.pathname === "/api/v1/records",
    async (route) => {
      const response = await route.fetch();
      committed();
      await held;
      await route.fulfill({ response });
    },
  );

  try {
    await page.goto("/search?q=trust");
    await expect(page.getByText(/\d+ papers/).first()).toBeVisible();
    await page.getByRole("button", { name: "Save search record" }).click();
    const dialog = page.getByRole("dialog", { name: "Save this search as a permanent record?" });
    await dialog.getByRole("button", { name: "Save" }).click();
    await serverCommitted;

    await dialog.press("Escape");
    await expect(dialog).toBeHidden();
    await expect(page.getByRole("button", { name: "Saving…" })).toBeFocused();

    release();
    const recordLink = page.getByRole("link", { name: /\/record\// }).last();
    await expect(recordLink).toBeVisible();
    await recordLink.click();
    await expect(page.getByText(/Reproduced on .*same .* papers/i)).toBeVisible();
  } finally {
    release();
  }
});
