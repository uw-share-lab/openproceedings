/**
 * The sidebar's Abstract field (decision-049; copy SB-1, SB-12): on an index that counts `abstract_kind` (the
 * fixture API's index is built at the current schema, 4), the field is drawn after Status, each value by its
 * label, and a click rewrites the query's `abstract_kind:` clause like any other facet (guarantee 3). The
 * synthetic fixture corpus has no OpenAlex abstract, so the "Abstract via OpenAlex" label is checked by the unit
 * tests only.
 */
import { expect, test } from "@playwright/test";
import { expectNoAxeViolations, search } from "./helpers";

test("the Abstract field follows Status, and ticking Official alone writes abstract_kind:(official)", async ({
  page,
}) => {
  await search(page, "trust");
  const sidebar = page.getByRole("region", { name: "Filters" });
  const legends = await sidebar.locator("fieldset > legend").allTextContents();
  expect(legends.map((l) => l.trim())).toEqual([
    "Venue",
    "Year",
    "Track (default)",
    "Status (default)",
    "Abstract",
  ]);
  const abstract = sidebar.getByRole("group", { name: "Abstract" });
  const official = abstract.getByRole("checkbox", { name: /^Official\s*, [\d,]+ papers$/ });
  const openalex = abstract.getByRole("checkbox", { name: /^OpenAlex\s*, [\d,]+ papers$/ });
  const none = abstract.getByRole("checkbox", { name: /^No abstract\s*, [\d,]+ papers$/ });
  for (const box of [official, openalex, none]) await expect(box).toBeChecked();
  await expectNoAxeViolations(page, "/search with the Abstract field");

  await openalex.click();
  await expect(page).toHaveURL(/abstract_kind/);
  await expect(abstract.getByRole("checkbox", { name: /^No abstract\s*,/ })).toBeEnabled();
  await expect(abstract.getByRole("checkbox", { name: /^OpenAlex\s*,/ })).not.toBeChecked();
  await abstract.getByRole("checkbox", { name: /^No abstract\s*,/ }).click();
  const editor = page.getByRole("textbox", { name: "Query" });
  await expect(editor).toContainText("abstract_kind:(official)");
  await expect(abstract.getByRole("checkbox", { name: /^Official\s*,/ })).toBeChecked();
  await expect(abstract.getByRole("checkbox", { name: /^No abstract\s*,/ })).not.toBeChecked();
});
