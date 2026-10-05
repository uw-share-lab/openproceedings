/**
 * The builder's group counts (TASK-176; spec 04 §SearchResponse `groups`, spec 05 §Components 3; copy BD-12):
 * after a search of a query of several concept groups, each group shows how many papers match it by itself and
 * how many match the query without it (and how many that adds), as the group's description, with a note
 * saying what the numbers are; outside the Builder tab a line points to them. They are the server's, for the
 * searched query only: an edited draft shows none, and a line says so. The `tight` instance counts at most 2 groups and 5
 * terms, so the too-many and too-costly notes are the server's own answers.
 */
import { expect, type Page, test } from "@playwright/test";
import {
  chooseTheme,
  expectNoAxeViolations,
  expectNoSidewaysScroll,
  search,
  tabTo,
  THEMES,
  WIDTHS,
} from "./helpers";
import { apiUrl, useInstance } from "./instances";

const THREE = "(trust OR reliance) AND (benchmark OR evaluation) AND (agent OR model)";
const TWO = "(trust OR reliance) AND (benchmark OR evaluation)";
const COUNT_LINE =
  /^([\d,]+) papers? match(?:es)? this group by itself\s*;?\s*([\d,]+) match(?:es)? the query without it \(\+([\d,]+)\)$/;

const builder = (page: Page) => page.getByRole("tabpanel", { name: "Builder" });
const groups = (page: Page) => builder(page).getByRole("group", { name: /^Group \d+ of \d+/ });
const status = (page: Page) => builder(page).getByRole("status", { name: "Group counts" });
const number = (text: string) => Number(text.replace(/,/g, ""));

async function openBuilder(page: Page, q: string): Promise<void> {
  await search(page, q);
  await page.getByRole("tab", { name: "Builder" }).click();
  await expect(builder(page)).toBeVisible();
}

test("each group of a searched query shows the server's two counts, and a note says what they are", async ({
  page,
}) => {
  await openBuilder(page, THREE);
  const answer = await (
    await page.request.get(`${apiUrl()}/api/v1/search?${new URLSearchParams({ q: THREE, limit: "0" })}`)
  ).json();
  expect(answer.groups.not_counted).toBeNull();
  expect(answer.groups.counts).toHaveLength(3);
  await expect(groups(page)).toHaveCount(3);
  for (const [i, count] of answer.groups.counts.entries()) {
    const line = groups(page)
      .nth(i)
      .getByText(/this group by itself/);
    const said = COUNT_LINE.exec((await line.innerText()).replace(/\s+/g, " ").replace(" ·", ""));
    expect(said, `group ${i + 1}`).not.toBeNull();
    expect([number(said?.[1] ?? ""), number(said?.[2] ?? ""), number(said?.[3] ?? "")]).toEqual([
      count.total,
      count.total_without,
      count.total_without - answer.total,
    ]);
    expect(count.total).toBeGreaterThanOrEqual(answer.total); // a group alone never matches fewer
    expect(count.total_without).toBeGreaterThanOrEqual(answer.total);
  }
  const total = answer.total.toLocaleString("en-US");
  await expect(builder(page)).toContainText(
    `${total} papers match the whole query. Each group shows how many papers`,
  );
  await expect(builder(page)).toContainText(
    "the group whose removal adds the most papers narrows the search most",
  );
  // the same total as the results header's
  await expect(page.getByText(/^\d[\d,]* papers?$/).first()).toHaveText(`${total} papers`);
});

test("the counts are announced when they arrive, without focus moving", async ({ page }) => {
  await openBuilder(page, TWO);
  await expect(status(page)).toHaveText(
    /^Group counts shown for 2 groups: [\d,]+ papers match the whole query\.$/,
  );
  // add a group in the builder and search: the new search's counts are announced in the same region
  await builder(page).getByRole("button", { name: "+ Add group" }).click();
  await page.keyboard.insertText("agent");
  await page.keyboard.press("Enter");
  await expect(status(page)).toHaveText(""); // an edited draft has no counts to announce
  const searchButton = page.getByRole("button", { name: "Search", exact: true });
  await searchButton.focus();
  await page.keyboard.press("Enter");
  await expect(status(page)).toHaveText(
    /^Group counts shown for 3 groups: [\d,]+ papers match the whole query\.$/,
  );
  // announced where the reader is: focus stayed on Search, never moved to the counts
  await expect(searchButton).toBeFocused();
});

test("no count is shown for a draft that differs from the searched query", async ({ page }) => {
  await openBuilder(page, THREE);
  await expect(builder(page).getByText(/this group by itself/)).toHaveCount(3);
  await builder(page).getByRole("button", { name: "Remove term reliance" }).click();
  await expect(builder(page).getByText(/this group by itself/)).toHaveCount(0);
  await expect(builder(page)).not.toContainText("match the whole query");
  await expect(builder(page)).toContainText(
    "Group counts are from the last search. Search again to see them.",
  );
  await expect(status(page)).toHaveText("");
  // back to the searched text (the Text tab shows the draft): the counts are that query's again
  await page.goBack();
  await openBuilder(page, THREE);
  await expect(builder(page).getByText(/this group by itself/)).toHaveCount(3);
});

test("a query of one group shows no counts and no note", async ({ page }) => {
  await openBuilder(page, "trust OR reliance");
  await expect(groups(page)).toHaveCount(1);
  await expect(builder(page).getByText(/this group by itself/)).toHaveCount(0);
  await expect(builder(page)).not.toContainText("Group counts");
  await expect(builder(page)).not.toContainText("match the whole query");
  await expect(status(page)).toHaveText("");
});

test("a group written twice says which group it repeats", async ({ page }) => {
  await openBuilder(page, "(trust OR reliance) AND benchmark AND (trust OR reliance)");
  await expect(groups(page)).toHaveCount(3);
  await expect(
    groups(page)
      .nth(0)
      .getByText(/this group by itself/),
  ).toBeVisible();
  await expect(
    groups(page)
      .nth(1)
      .getByText(/this group by itself/),
  ).toBeVisible();
  await expect(groups(page).nth(2)).toContainText("Same as group 1, so it is counted once.");
  // group 1's "without it" count is the query without group 3 too: the server holds them as one group
  await expect(groups(page).nth(0)).toContainText(
    /match(?:es)? the query without it and group 3 \(\+[\d,]+\)/,
  );
  await expect(groups(page).nth(1)).toContainText(/match(?:es)? the query without it \(\+[\d,]+\)/);
  await expect(
    groups(page)
      .nth(2)
      .getByText(/this group by itself/),
  ).toHaveCount(0);
});

test("an instance that counts fewer groups or terms says why there are no counts", async ({ page }) => {
  await useInstance(page, "tight");
  await openBuilder(page, THREE);
  const many = "Group counts aren't shown: this query has 3 groups, and this instance counts at most 2.";
  await expect(builder(page)).toContainText(many);
  await expect(status(page)).toHaveText(many);
  await expect(builder(page).getByText(/this group by itself/)).toHaveCount(0);
  await expect(page.getByText(/^\d[\d,]* papers?$/).first()).toBeVisible(); // the search itself is whole

  await openBuilder(page, TWO);
  const costly =
    "Group counts aren't shown: counting each group of this query would read more terms, or more " +
    "position-checked matches, than this instance allows. Shorten the leave-out terms, use longer wildcard " +
    "stems, or use fewer NEARs and phrases with a wildcard to see them.";
  await expect(builder(page)).toContainText(costly);
  await expect(status(page)).toHaveText(costly);
  await expect(builder(page).getByText(/this group by itself/)).toHaveCount(0);

  await openBuilder(page, "trust AND benchmark"); // two groups of one term: within both bounds, counted
  await expect(builder(page).getByText(/this group by itself/)).toHaveCount(2);
});

test("the counts are reached and read by keyboard alone", async ({ page }) => {
  await search(page, THREE);
  const tab = page.getByRole("tab", { name: "Builder" });
  await tabTo(page, page.getByRole("tab", { name: "Text" }));
  await page.keyboard.press("ArrowRight");
  await expect(tab).toHaveAttribute("aria-selected", "true");
  await expect(builder(page).getByText(/this group by itself/)).toHaveCount(3);
  // each group's count is its description: a screen reader hears it on entering the group by keyboard
  const first = groups(page).first();
  const trust = first.getByRole("button", { name: "trust", exact: true });
  await tabTo(page, trust);
  await expect(trust).toBeFocused();
  await expect(first).toHaveAccessibleDescription(
    /^[\d,]+ papers? match(?:es)? this group by itself\s*;?\s*[\d,]+ match(?:es)? the query without it \(\+[\d,]+\)$/,
  );
  for (let i = 1; i < 3; i++)
    await expect(groups(page).nth(i)).toHaveAccessibleDescription(/this group by itself/);
});

test("outside the Builder tab a line points to the counts, and opens the tab by keyboard", async ({
  page,
}) => {
  await search(page, THREE);
  const pointer = page.getByText(/^Each of this query's 3 groups has a count in the Builder tab/);
  await expect(pointer).toBeVisible();
  const open = page.getByRole("button", { name: "Show group counts" });
  await tabTo(page, open);
  await page.keyboard.press("Enter");
  await expect(page.getByRole("tab", { name: "Builder" })).toHaveAttribute("aria-selected", "true");
  await expect(builder(page).getByText(/this group by itself/)).toHaveCount(3);
  await expect(pointer).toHaveCount(0);
  // a query of one group has nothing to point to
  await search(page, "trust OR reliance");
  await page.getByRole("tab", { name: "Text" }).click();
  await expect(page.getByRole("button", { name: "Show group counts" })).toHaveCount(0);
});

for (const theme of THEMES) {
  for (const width of WIDTHS) {
    test(`the group-count states pass axe and fit the page (${theme}, ${width}px)`, async ({ page }) => {
      test.setTimeout(60_000);
      await page.setViewportSize({ width, height: 900 });
      await chooseTheme(page, theme);
      await openBuilder(
        page,
        "(trust OR reliance) AND benchmark AND (trust OR reliance) AND (agent OR model)",
      );
      await expect(builder(page).getByText(/this group by itself/)).toHaveCount(3);
      await expectNoAxeViolations(page, `counts and a repeated group, ${theme} ${width}px`);
      await expectNoSidewaysScroll(page, `counts at ${width}px`);
      await useInstance(page, "tight");
      for (const q of [THREE, TWO]) {
        await openBuilder(page, q);
        await expect(builder(page)).toContainText("Group counts aren't shown");
        await expectNoAxeViolations(page, `no counts (${q}), ${theme} ${width}px`);
        await expectNoSidewaysScroll(page, `no counts at ${width}px`);
      }
    });
  }
}
