/**
 * The no-stemming notice's "Add $" (TASK-175, TASK-181; spec 02 §Word forms, spec 05 §Components 1): a
 * Google Scholar string has no `$`, the notice names its terms, and the reader has `$` written after all of
 * them or the ones they tick. It is an edit of the query text: nothing is searched until Search, the URL then
 * carries the `$`s, and Back is the typed query again.
 */
import { expect, type Page, test } from "@playwright/test";
import {
  chooseTheme,
  expectNoAxeViolations,
  expectNoSidewaysScroll,
  expectTargets,
  search,
  tabTo,
  THEMES,
  typeQuery,
  WIDTHS,
} from "./helpers";

const TYPED = 'trust benchmark "language model"';
const WITH_ALL = 'trust$ benchmark$ "language model$"';

// the notice's own item, not the items of the "Left as typed:" list inside it
const notice = (page: Page) => page.getByRole("list", { name: "Translations" }).locator(":scope > li");
const q = (page: Page) => new URL(page.url()).searchParams.get("q");

test("Add $ to all terms edits the query, Search carries it in the URL, and Back is the typed query", async ({
  page,
}) => {
  await search(page, TYPED, "scholar");
  const editor = page.getByRole("textbox", { name: "Query" });
  await expect(editor).toHaveText(TYPED);
  await expect(notice(page)).toContainText(
    "Google Scholar stems words; openproceedings matches them exactly",
  );
  const typedTotal = await page
    .getByText(/^\d[\d,]* papers?$/)
    .first()
    .innerText();

  await page.getByRole("button", { name: "Add $ to all 3 terms" }).click();
  await expect(editor).toHaveText(WITH_ALL);
  expect(q(page)).toBe(TYPED); // an edit of the text: nothing is searched yet
  await expect(page.getByRole("heading", { name: "Draft — not searched", exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Search", exact: true }).click();
  await expect.poll(() => q(page)).toBe(WITH_ALL);
  expect(new URL(page.url()).searchParams.get("mode")).toBe("scholar");
  // every `$` is shown with the terms it matched (guarantee 6)
  const expansions = page.getByRole("region", { name: "Expansions" });
  await expect(expansions).toBeVisible();
  for (const stem of ["trust$", "benchmark$", "model$"]) await expect(expansions).toContainText(stem);
  await expect(expansions).toContainText("benchmarks");
  await expect(page.getByRole("button", { name: /^Add \$ to/ })).toHaveCount(0); // nothing left to offer
  await expect(page.getByText(/^\d[\d,]* papers?$/).first()).not.toHaveText(typedTotal);

  await page.goBack();
  await expect.poll(() => q(page)).toBe(TYPED);
  await expect(editor).toHaveText(TYPED);
  await expect(page.getByText(/^\d[\d,]* papers?$/).first()).toHaveText(typedTotal);
  await expect(page.getByRole("button", { name: "Add $ to all 3 terms" })).toBeVisible();
});

test("Choose terms adds $ to the ticked terms only", async ({ page }) => {
  await search(page, TYPED, "scholar");
  const editor = page.getByRole("textbox", { name: "Query" });
  const choose = page.getByRole("button", { name: "Choose terms" });
  await expect(choose).toHaveAttribute("aria-expanded", "false");
  await choose.click();
  await expect(choose).toHaveAttribute("aria-expanded", "true");
  const terms = page.getByRole("group", { name: "Add $ to" });
  await expect(terms.getByRole("checkbox")).toHaveCount(3);
  const add = terms.getByRole("button", { name: "Add $ to the ticked terms" });
  await expect(add).toHaveAttribute("aria-disabled", "true");
  await add.click({ force: true }); // nothing ticked (aria-disabled): nothing happens
  await expect(editor).toHaveText(TYPED);

  await terms.getByRole("checkbox", { name: /^benchmark/ }).check();
  await terms.getByRole("checkbox", { name: /language model.*phrase: on its last word/ }).check();
  await expect(add).not.toHaveAttribute("aria-disabled", "true");
  await add.click();
  await expect(editor).toHaveText('trust benchmark$ "language model$"');

  await page.getByRole("button", { name: "Search", exact: true }).click();
  await expect.poll(() => q(page)).toBe('trust benchmark$ "language model$"');
  const expansions = page.getByRole("region", { name: "Expansions" });
  await expect(expansions).toContainText("benchmark$");
  await expect(expansions).not.toContainText("trust$");
  // the term left as typed is still named, and still offered
  await expect(page.getByRole("button", { name: "Add $ to 1 term" })).toBeVisible();
});

test("a lowercase and is named by the notice and never offered a $", async ({ page }) => {
  await page.goto("/");
  const editor = await typeQuery(page, "trust and benchmark", "scholar");
  // the message's backticked runs are drawn as code, not as backticks: the sentence's own code, a direct child
  // of the notice's item (the "Left as typed:" list under it has `and` in code too)
  await expect(notice(page).first().locator(":scope > code").filter({ hasText: /^and$/ })).toHaveCount(1);
  await expect(notice(page)).toContainText("trust, and, benchmark");
  await expect(notice(page)).not.toContainText("`");
  await expect(page.getByRole("list", { name: "Warnings" })).toContainText("and is searched as a word");
  await page.getByRole("button", { name: "Choose terms" }).click();
  const terms = page.getByRole("group", { name: "Add $ to" });
  await expect(terms.getByRole("checkbox")).toHaveCount(2);
  await expect(terms.getByRole("checkbox", { name: /^and/ })).toHaveCount(0);
  // why it is left out is said with the chooser open or closed (TASK-192)
  await expect(page.getByRole("list", { name: "Left as typed:" })).toHaveText(
    "and: a lowercase and, or or not.",
  );
  await page.getByRole("button", { name: "Add $ to all 2 terms" }).click();
  await expect(editor).toHaveText("trust$ and benchmark$");
});

test("when no term can take a $, the notice says so and offers nothing", async ({ page }) => {
  await page.goto("/");
  await typeQuery(page, "ai and ml", "scholar");
  await expect(notice(page)).toContainText("ai, and, ml");
  await expect(notice(page)).toContainText("$ can't be added to these terms for you.");
  await expect(notice(page)).toContainText("Type a wildcard yourself where one is valid.");
  await expect(notice(page)).toContainText("Google Scholar also reads the full text of a paper");
  await expect(page.getByRole("button", { name: /^Add \$/ })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Choose terms" })).toHaveCount(0);
});

test("Add $ is worked by keyboard alone", async ({ page }) => {
  await page.goto("/");
  const editor = await typeQuery(page, TYPED, "scholar");
  const choose = page.getByRole("button", { name: "Choose terms" });
  await expect(choose).toBeVisible();
  await tabTo(page, choose);
  await page.keyboard.press("Enter");
  const terms = page.getByRole("group", { name: "Add $ to" });
  await page.keyboard.press("Tab"); // the first term's checkbox
  await expect(terms.getByRole("checkbox").first()).toBeFocused();
  await page.keyboard.press("Space");
  await expect(terms.getByRole("checkbox").first()).toBeChecked();
  await tabTo(page, terms.getByRole("button", { name: "Add $ to the ticked terms" }), 6);
  await page.keyboard.press("Enter");
  await expect(editor).toHaveText('trust$ benchmark "language model"');
  await expect(editor).toBeFocused(); // the button is gone with the edit: focus is on the edit, not lost
  // the rest in one press: back to the all-terms button, which now counts what is left
  const rest = page.getByRole("button", { name: "Add $ to all 2 terms" });
  await page.keyboard.press("Shift+Tab");
  await tabTo(page, rest, 10);
  await page.keyboard.press("Enter");
  await expect(editor).toHaveText(WITH_ALL);
  await expect(editor).toBeFocused();
  await page.keyboard.press("Enter"); // Enter in the editor searches
  await expect.poll(() => q(page)).toBe(WITH_ALL);
});

test("Add $ from the Builder tab leaves focus on the Builder tab, not on the page", async ({ page }) => {
  await page.goto("/");
  await typeQuery(page, TYPED, "scholar");
  const builderTab = page.getByRole("tab", { name: "Builder" });
  await page.getByRole("tab", { name: "Text" }).focus();
  await page.keyboard.press("ArrowRight"); // selects Builder, focus stays on the tabs
  await expect(builderTab).toHaveAttribute("aria-selected", "true");
  const all = page.getByRole("button", { name: "Add $ to all 3 terms" });
  await tabTo(page, all);
  await page.keyboard.press("Enter");
  await expect(all).toHaveCount(0);
  await expect(builderTab).toBeFocused();
  await expect(page.getByRole("heading", { name: "Draft — not searched", exact: true })).toBeVisible();
  await page.getByRole("tab", { name: "Text" }).click(); // the edit is in the editor
  await expect(page.getByRole("textbox", { name: "Query" })).toHaveText(WITH_ALL);
});

test("after Add $ and Search, the $ notices are one line about the widening, the server's behind Show", async ({
  page,
}) => {
  await search(page, WITH_ALL, "scholar");
  const dollars = notice(page).filter({ hasText: "is read as a wildcard in 3 places" });
  await expect(dollars).toHaveCount(1);
  await expect(dollars).toContainText("That widening is what $ is for");
  const show = dollars.getByRole("button", { name: "Show all 3 notices" });
  await expect(show).toHaveAttribute("aria-expanded", "false");
  await show.click();
  await expect(dollars.getByRole("listitem")).toHaveCount(3);
  await expect(dollars.getByRole("listitem").first()).toContainText("has no documented wildcard meaning");
  await expect(dollars.getByRole("button", { name: "Hide the notices" })).toHaveAttribute(
    "aria-expanded",
    "true",
  );
});

for (const theme of THEMES) {
  for (const width of WIDTHS) {
    test(`the Add $ states pass axe and fit the page (${theme}, ${width}px)`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await chooseTheme(page, theme);
      await search(page, TYPED, "scholar");
      await page.getByRole("button", { name: "Choose terms" }).click();
      await page.getByRole("group", { name: "Add $ to" }).getByRole("checkbox").first().check();
      await expectNoAxeViolations(page, `Choose terms open, ${theme} ${width}px`);
      await expectNoSidewaysScroll(page, `Choose terms open at ${width}px`);
      await expectTargets(notice(page));

      await page.goto("/");
      await typeQuery(page, "ai and ml", "scholar");
      await expect(notice(page)).toContainText("$ can't be added to these terms for you.");
      await expectNoAxeViolations(page, `nothing to offer, ${theme} ${width}px`);
      await expectNoSidewaysScroll(page, `nothing to offer at ${width}px`);
    });
  }
}
