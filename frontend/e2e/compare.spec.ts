/**
 * "Compare with your records" beyond the run in accessibility.spec.ts (TASK-177; spec 04 §Comparing with a
 * RIS file, spec 05 §Components 9, decision-035): a file with a paper in each list, every list opened and
 * downloaded, and the states only another instance gives: comparisons not offered (`plain`), a file over the
 * instance's cap and the network's cooldown after a comparison (`tight`).
 */
import { readFile } from "node:fs/promises";
import { expect, type Page, test } from "@playwright/test";
import {
  chooseTheme,
  expectNoAxeViolations,
  expectNoSidewaysScroll,
  expectTargets,
  search,
  tabTo,
  THEMES,
  WIDTHS,
} from "./helpers";
import { apiUrl, useInstance } from "./instances";

const RIS_TYPE = "application/x-research-info-systems";
const Q = "benchmark";
const record = (title: string, venue: string) =>
  `TY  - JOUR\nTI  - ${title}\nJF  - ${venue}\nPY  - 2024\nER  - \n\n`;
const UNKNOWN = record("a paper no index holds about benchmark", "NeurIPS");
const ELSEWHERE = record("benchmark at another venue", "AISTATS");

const panel = (page: Page) => page.getByRole("region", { name: "Compare with your records" });
const list = (page: Page, name: RegExp) => panel(page).getByRole("region", { name });

/** A file a reviewer could hold: this instance's export of another search, one paper no index holds, one
 * record from another venue and one repeat. */
async function heldFile(page: Page): Promise<Buffer> {
  const params = new URLSearchParams({ q: "trust venue:ICLR", format: "ris" });
  const held = await page.request.get(`${apiUrl()}/api/v1/export?${params}`);
  expect(held.ok()).toBe(true);
  return Buffer.concat([await held.body(), Buffer.from(UNKNOWN + ELSEWHERE + UNKNOWN)]);
}

async function choose(page: Page, buffer: Buffer, name = "my-records.ris"): Promise<void> {
  await page.getByRole("button", { name: /Compare with your records/ }).click();
  await panel(page).getByLabel("RIS file").setInputFiles({ name, mimeType: RIS_TYPE, buffer });
}

async function compare(page: Page, buffer: Buffer): Promise<void> {
  await choose(page, buffer);
  await panel(page).getByRole("button", { name: "Compare", exact: true }).click();
}

/**
 * Press Compare until the answer is drawn. On `tight` this network pauses after each comparison (and the
 * tests share one network), so an earlier test's pause is waited out here, by the panel's own Retry.
 */
async function compareWhenAllowed(page: Page): Promise<void> {
  const table = panel(page).getByRole("table");
  await panel(page).getByRole("button", { name: "Compare", exact: true }).click();
  await expect(async () => {
    const retry = panel(page).getByRole("alert").getByRole("button", { name: "Retry" });
    if ((await retry.count()) > 0 && (await retry.getAttribute("aria-disabled")) !== "true")
      await retry.click();
    await expect(table).toBeVisible({ timeout: 1_000 });
  }).toPass({ timeout: 90_000 });
}

async function saved(page: Page, click: () => Promise<void>): Promise<{ name: string; text: string }> {
  const [download] = await Promise.all([page.waitForEvent("download"), click()]);
  return { name: download.suggestedFilename(), text: await readFile(await download.path(), "utf8") };
}

test("a file's papers land in the four lists, each opens, and each downloads as the server wrote it", async ({
  page,
}) => {
  test.setTimeout(90_000);
  await search(page, Q);
  const file = await heldFile(page);
  const answered = page.waitForResponse((r) => r.url().includes("/api/v1/compare") && r.status() === 200);
  await compare(page, file);
  const answer = await (await answered).json();
  const table = panel(page).getByRole("table", { name: "What this search does to the papers in your file" });
  await expect(table).toBeVisible({ timeout: 60_000 });
  const counts = (await table.getByRole("cell").allTextContents()).map((t) => Number(t.replace(/,/g, "")));
  expect(counts).toEqual([
    answer.kept_total,
    answer.dropped_total,
    answer.not_in_index_total,
    answer.added_total,
  ]);
  expect(Math.min(...counts)).toBeGreaterThan(0); // every list has a paper
  expect(answer.not_in_index_total).toBe(1);
  expect(answer.not_compared_total).toBeGreaterThan(1);
  await expect(panel(page)).toContainText(
    `${answer.not_compared_total.toLocaleString("en-US")} records from other venues, and 1 record that repeats a paper already counted`,
  );
  const hash = answer.query.canonical_hash.slice(0, 12);
  const stem = `openproceedings-${answer.index_version}-${hash}`;

  const lists = [
    { key: "kept", name: /kept papers?$/, file: "kept" },
    { key: "dropped", name: /dropped papers?$/, file: "dropped" },
    { key: "not_in_index", name: /papers? not in the index$/, file: "not-in-index" },
    { key: "added", name: /added papers?$/, file: "added" },
  ] as const;
  for (const { key, name, file: suffix } of lists) {
    const section = list(page, name);
    const total: number = answer[`${key}_total`];
    const show = section.getByRole("button", { name: /^Show the / });
    await expect(show).toHaveAttribute("aria-expanded", "false");
    await show.click();
    await expect(section.getByRole("listitem")).toHaveCount(Math.min(total, 100));
    await expect(section.getByRole("listitem").first()).toContainText(answer[key][0].title);
    const csv = await saved(page, () => section.getByRole("button", { name: /^Download CSV/ }).click());
    expect(csv.name).toBe(`${stem}-${suffix}.csv`);
    expect(csv.text).toBe(answer.csv[key]); // the server's text, BOM included, saved as sent
    expect(csv.text.charCodeAt(0)).toBe(0xfeff);
    expect(csv.text.trimEnd().split("\r\n")).toHaveLength(total + 1);
    await section.getByRole("button", { name: /^Hide the / }).click();
    await expect(section.getByRole("listitem")).toHaveCount(0);
  }
  // a paper the index holds links to its page; one it doesn't hold can't
  await list(page, /papers? not in the index$/)
    .getByRole("button", { name: /^Show the / })
    .click();
  const gap = list(page, /papers? not in the index$/).getByRole("listitem");
  await expect(gap).toContainText("a paper no index holds about benchmark");
  await expect(gap).toContainText("2 times in your file");
  await expect(gap.getByRole("link")).toHaveCount(0);
  await expect(list(page, /dropped papers?$/)).toContainText(
    /papers? (has|have) no exact match in (its|their) title or abstract/,
  );
  await expect(list(page, /added papers?$/)).toContainText(
    `${answer.added_total.toLocaleString("en-US")} papers match exactly and are not in your file`,
  );

  const added = list(page, /added papers?$/);
  expect(await added.getByRole("button", { name: /^Download RIS/ }).count()).toBe(1);
  expect(
    await panel(page)
      .getByRole("button", { name: /^Download RIS/ })
      .count(),
  ).toBe(1); // RIS is the added list's
  const ris = await saved(page, () => added.getByRole("button", { name: /^Download RIS/ }).click());
  expect(ris.name).toBe(`${stem}-added.ris`);
  expect(ris.text).toBe(answer.added_ris);
  expect(ris.text.match(/^TY {2}- /gm)).toHaveLength(answer.added_total);

  const out = panel(page).getByRole("region", { name: /^Not compared/ });
  await out.getByRole("button", { name: /^Show the / }).click();
  await expect(out.getByRole("listitem").filter({ hasText: "benchmark at another venue" })).toContainText(
    "its venue is not NeurIPS, ICLR or ICML",
  );
  const left = await saved(page, () => out.getByRole("button", { name: /^Download CSV/ }).click());
  expect(left.name).toBe(`${stem}-not-compared.csv`);
  expect(left.text).toBe(answer.csv.not_compared);
});

test("a row's title opens its paper in a new tab, and the comparison stays", async ({ page, context }) => {
  test.setTimeout(90_000);
  await search(page, Q);
  await compare(page, await heldFile(page));
  const heading = panel(page).getByRole("heading", { name: /^Comparison with my-records\.ris$/ });
  await expect(heading).toBeVisible({ timeout: 60_000 });
  const kept = list(page, /kept papers?$/);
  await kept.getByRole("button", { name: /^Show the / }).click();
  const link = kept.getByRole("listitem").first().getByRole("link");
  const [paper] = await Promise.all([context.waitForEvent("page", { timeout: 10_000 }), link.click()]);
  await paper.waitForLoadState();
  expect(new URL(paper.url()).pathname).toMatch(/^\/paper\//);
  await paper.close();
  await expect(link).toHaveAccessibleName(/\(opens in a new tab\)$/); // said before it is followed
  // this tab never left the search: the file's answer is still drawn, the list still open
  expect(new URL(page.url()).pathname).toBe("/search");
  await expect(heading).toBeVisible();
  await expect(kept.getByRole("listitem").first()).toBeVisible();
});

test("Cancel, pressed by keyboard, hands focus back to Compare", async ({ page }) => {
  await search(page, Q);
  let release = () => {};
  const held = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route("**/api/v1/compare?**", async (route) => {
    await held; // the comparison is still running when Cancel is pressed
    await route.continue().catch(() => {});
  });
  await choose(page, Buffer.from(UNKNOWN));
  const start = panel(page).getByRole("button", { name: "Compare", exact: true });
  await start.focus();
  await page.keyboard.press("Enter");
  const cancel = panel(page).getByRole("button", { name: "Cancel" });
  await tabTo(page, cancel, 3);
  await page.keyboard.press("Enter");
  await expect(cancel).toHaveCount(0);
  await expect(start).toBeFocused();
  await expect(panel(page).getByRole("status").first()).toHaveText("Comparison cancelled.");
  release();
});

test("Retry, pressed by keyboard, hands focus to Compare while the new comparison runs", async ({ page }) => {
  test.setTimeout(90_000);
  await search(page, Q);
  let calls = 0;
  await page.route("**/api/v1/compare?**", async (route) => {
    calls += 1;
    if (calls === 1)
      await route.abort("connectionrefused"); // the first try never reaches the server
    else await route.continue();
  });
  await choose(page, Buffer.from(UNKNOWN));
  await panel(page).getByRole("button", { name: "Compare", exact: true }).click();
  const alert = panel(page).getByRole("alert");
  await expect(alert).toContainText("Couldn't reach the server.");
  const retry = alert.getByRole("button", { name: "Retry" });
  await tabTo(page, retry, 6);
  await page.keyboard.press("Enter");
  await expect(retry).toHaveCount(0);
  await expect(panel(page).getByRole("button", { name: "Compare", exact: true })).toBeFocused();
  // then the answer takes focus, as after Compare
  await expect(panel(page).getByRole("heading", { name: /^Comparison with my-records\.ris$/ })).toBeFocused({
    timeout: 60_000,
  });
});

test("the last Show more hands focus to the first row it drew", async ({ page }) => {
  test.setTimeout(90_000);
  await search(page, Q);
  // 101 records from another venue: one more than a list draws at once
  const others = Array.from({ length: 101 }, (_, i) => record(`a workshop paper number ${i + 1}`, "AISTATS"));
  await compare(page, Buffer.from(UNKNOWN + others.join("")));
  const out = panel(page).getByRole("region", { name: /^Not compared/ });
  await expect(out).toBeVisible({ timeout: 60_000 });
  await out.getByRole("button", { name: /^Show the / }).click();
  await expect(out.getByRole("listitem")).toHaveCount(100);
  const more = out.getByRole("button", { name: /^Show more/ });
  await tabTo(page, more, 10);
  await page.keyboard.press("Enter");
  await expect(more).toHaveCount(0); // it was the last
  await expect(out.getByRole("listitem")).toHaveCount(101);
  await expect(out.getByRole("listitem").nth(100)).toBeFocused();
});

test("an instance without comparisons doesn't offer the panel", async ({ page }) => {
  await useInstance(page, "plain");
  const meta = page.waitForResponse((r) => r.url().includes("/api/v1/meta") && r.status() === 200);
  await search(page, Q);
  expect((await (await meta).json()).limits.compare).toBeNull();
  await expect(page.getByRole("button", { name: /^Export \d/ })).toBeVisible(); // the header is drawn
  await expect(page.getByRole("button", { name: "Save search record" })).toBeVisible();
  await expect(page.getByRole("button", { name: /Compare with your records/ })).toHaveCount(0);
  await expect(page.getByRole("region", { name: "Compare with your records" })).toHaveCount(0);
  await expect(page.getByText(/RIS file/)).toHaveCount(0);
});

test("a file over the instance's cap is refused in the browser, with both sizes, and never sent", async ({
  page,
}) => {
  await useInstance(page, "tight"); // comparison files up to 2,048 bytes
  await search(page, Q);
  let sent = 0;
  page.on("request", (r) => {
    if (r.url().includes("/api/v1/compare")) sent += 1;
  });
  await choose(page, Buffer.from(UNKNOWN.repeat(40))); // about 3 KB
  await expect(panel(page)).toContainText("Up to 2.0 KB and 5,000 records");
  const alert = panel(page).getByRole("alert");
  await expect(alert).toHaveText(
    /^This file is \d\.\d KB; this server compares files up to 2\.0 KB\. Export it without abstracts/,
  );
  const button = panel(page).getByRole("button", { name: "Compare", exact: true });
  await expect(button).toHaveAttribute("aria-disabled", "true");
  await button.click({ force: true });
  await expect(panel(page).getByRole("table")).toHaveCount(0);
  expect(sent).toBe(0);
  // a file within the cap, chosen next, is not refused
  await panel(page)
    .getByLabel("RIS file")
    .setInputFiles({ name: "small.ris", mimeType: RIS_TYPE, buffer: Buffer.from(UNKNOWN) });
  await expect(alert).toHaveCount(0);
  await expect(button).not.toHaveAttribute("aria-disabled", "true");
  expect(sent).toBe(0);
});

test("after a comparison the network waits: the refusal counts down, and searching still works", async ({
  page,
}) => {
  await useInstance(page, "tight"); // the rate limit on, with the comparison cooldown (decision-035)
  test.setTimeout(180_000);
  await search(page, Q);
  await choose(page, Buffer.from(UNKNOWN));
  await compareWhenAllowed(page);
  const refused = page.waitForResponse((r) => r.url().includes("/api/v1/compare") && r.status() === 429);
  await panel(page).getByRole("button", { name: "Compare", exact: true }).click();
  const response = await refused;
  const seconds = Number(response.headers()["retry-after"]);
  expect(seconds).toBeGreaterThanOrEqual(1);
  const alert = panel(page).getByRole("alert");
  await expect(alert).toContainText(
    "One comparison at a time from this network, with a pause after each in proportion to how long it ran " +
      `(searching is not affected); try again in ${seconds} s.`,
  );
  await expect(alert.getByRole("status")).toHaveText(
    new RegExp(`^Retry in ${seconds} s$|^You can retry now$`),
  );
  await expect(panel(page)).toContainText(
    "The new comparison didn't run. The results below are from the earlier comparison with my-records.ris.",
  );
  await expect(panel(page)).not.toContainText("Nothing was compared");
  await expect(panel(page)).toContainText("you can keep searching while you wait");
  await expectNoAxeViolations(page, "a refused comparison above an earlier answer");
  // the earlier answer (the same query, index and file) stays, under its own heading: it is still true
  await expect(panel(page).getByRole("heading", { name: /^Comparison with my-records\.ris$/ })).toBeVisible();
  // the countdown ends in a Retry that works
  const retry = alert.getByRole("button", { name: "Retry" });
  await expect(retry).toHaveAttribute("aria-disabled", "true");
  await expect(alert.getByRole("status")).toHaveText("You can retry now", { timeout: (seconds + 5) * 1000 });
  await expect(retry).not.toHaveAttribute("aria-disabled", "true");
  // and a search is answered meanwhile, as the message says
  const again = await page.request.get(
    `${apiUrl("tight")}/api/v1/search?${new URLSearchParams({ q: Q, limit: "0" })}`,
  );
  expect(again.status()).toBe(200);
  await retry.click();
  await expect(panel(page).getByRole("table")).toBeVisible({ timeout: 30_000 });
});

test("the cooldown's refusal is read and retried by keyboard", async ({ page }) => {
  await useInstance(page, "tight");
  test.setTimeout(180_000);
  await search(page, Q);
  const trigger = page.getByRole("button", { name: /Compare with your records/ });
  await page.getByRole("button", { name: /^Export \d/ }).focus(); // the results header's first control
  await tabTo(page, trigger, 4);
  await page.keyboard.press("Enter");
  await expect(trigger).toHaveAttribute("aria-expanded", "true");
  await page.keyboard.press("Tab");
  await expect(panel(page).getByLabel("RIS file")).toBeFocused(); // the file input is the next stop
  await panel(page)
    .getByLabel("RIS file")
    .setInputFiles({ name: "k.ris", mimeType: RIS_TYPE, buffer: Buffer.from(UNKNOWN) });
  await page.keyboard.press("Tab");
  await expect(panel(page).getByRole("button", { name: "Compare", exact: true })).toBeFocused();
  // this network may still be pausing after another test's comparison: Enter again until it is answered
  const heading = panel(page).getByRole("heading", { name: /^Comparison with k\.ris$/ });
  await expect(async () => {
    await panel(page).getByRole("button", { name: "Compare", exact: true }).focus();
    await page.keyboard.press("Enter");
    await expect(heading).toBeFocused({ timeout: 2_000 }); // the answer takes focus
  }).toPass({ timeout: 90_000 });
  await page.keyboard.press("Shift+Tab"); // back from the answer's heading to Compare
  await expect(panel(page).getByRole("button", { name: "Compare", exact: true })).toBeFocused();
  await page.keyboard.press("Enter");
  const alert = panel(page).getByRole("alert");
  await expect(alert).toContainText("try again in");
  const retry = alert.getByRole("button", { name: "Retry" });
  await tabTo(page, retry, 10);
  await expect(retry).toHaveAttribute("aria-disabled", "true"); // focusable while it counts down, and says so
});

for (const theme of THEMES) {
  for (const width of WIDTHS) {
    test(`the comparison's other states pass axe and fit the page (${theme}, ${width}px)`, async ({
      page,
    }) => {
      test.setTimeout(120_000);
      await page.setViewportSize({ width, height: 900 });
      await chooseTheme(page, theme);
      // every list open at once, on the default instance
      await search(page, Q);
      await compare(page, await heldFile(page));
      await expect(panel(page).getByRole("table")).toBeVisible({ timeout: 60_000 });
      const shows = panel(page).getByRole("button", { name: /^Show the / });
      while ((await shows.count()) > 0) await shows.first().click();
      await expectNoAxeViolations(page, `every list open, ${theme} ${width}px`);
      await expectNoSidewaysScroll(page, `every list open at ${width}px`);
      await expectTargets(panel(page));

      await useInstance(page, "tight");
      await search(page, Q);
      await choose(page, Buffer.from(UNKNOWN.repeat(40)));
      await expect(panel(page).getByRole("alert")).toContainText("this server compares files up to 2.0 KB");
      await expectNoAxeViolations(page, `a file over the cap, ${theme} ${width}px`);
      await expectNoSidewaysScroll(page, `a file over the cap at ${width}px`);

      await panel(page)
        .getByLabel("RIS file")
        .setInputFiles({ name: "s.ris", mimeType: RIS_TYPE, buffer: Buffer.from(UNKNOWN) });
      // compare until this network is told to wait (it may already be pausing after another test)
      await expect(async () => {
        await panel(page).getByRole("button", { name: "Compare", exact: true }).click();
        await expect(panel(page).getByRole("alert")).toContainText("try again in", { timeout: 2_000 });
      }).toPass({ timeout: 90_000 });
      await expectNoAxeViolations(page, `the cooldown's refusal, ${theme} ${width}px`);
      await expectNoSidewaysScroll(page, `the cooldown's refusal at ${width}px`);
      await expectTargets(panel(page));

      await page.unrouteAll({ behavior: "ignoreErrors" });
      await useInstance(page, "plain");
      await search(page, Q);
      await expect(page.getByRole("button", { name: "Save search record" })).toBeVisible();
      await expect(page.getByRole("button", { name: /Compare with your records/ })).toHaveCount(0);
      await expectNoAxeViolations(page, `comparisons not offered, ${theme} ${width}px`);
      await expectNoSidewaysScroll(page, `comparisons not offered at ${width}px`);
    });
  }
}
