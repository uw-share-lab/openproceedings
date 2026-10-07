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

/** The day the comparison surface's clock and file are pinned to (any fixed day: never today). */
const FIXED_DAY = "2026-10-05";

/**
 * The surfaces TASK-175, TASK-176, TASK-177 and TASK-210 added, each as its own element (TASK-182): the page
 * around them is the baseline above. The fixture is fixed, so every number in them is.
 */
const surfaces: { name: string; open: (page: Page) => Promise<Locator> }[] = [
  {
    // a result whose abstract is a submission's (TASK-210): its attribution and the note under it. The fixture
    // gives one paper of this search such an abstract, off the default search's page (fixture_server.py)
    name: "submission-note",
    open: async (page) => {
      await page.goto(`/search?${new URLSearchParams({ q: "trust venue:ICML" })}`);
      await expect(page.getByText(/\d+ papers?/).first()).toBeVisible();
      const note = page.locator("p").filter({ hasText: /^Submission-time abstract: / });
      await expect(note).toHaveCount(1);
      return page.locator("article").filter({ has: note });
    },
  },
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
      // the citable sentence (TASK-195) states the day the answer came and the file's sha256, so both are
      // pinned: the page's clock to one fixed UTC instant (Date only; timers run), and the export's own
      // "exported <date>" provenance, which the server writes from its clock, to that same day. Unpinned, the
      // baseline changed at every UTC midnight
      await page.clock.setFixedTime(new Date(`${FIXED_DAY}T12:00:00Z`));
      const params = new URLSearchParams({ q: "trust venue:ICLR", format: "ris" });
      const held = await page.request.get(`${apiUrl()}/api/v1/export?${params}`);
      const file = (await held.text()).replace(/exported \d{4}-\d{2}-\d{2}/g, `exported ${FIXED_DAY}`);
      const extra = "TY  - JOUR\nTI  - a paper no index holds\nJF  - NeurIPS\nPY  - 2024\nER  - \n";
      await page.goto("/search?q=benchmark");
      await expect(page.getByText(/\d+ papers?/).first()).toBeVisible();
      await page.getByRole("button", { name: /Compare with your records/ }).click();
      const panel = page.getByRole("region", { name: "Compare with your records" });
      await panel.getByLabel("RIS file").setInputFiles({
        name: "my-records.ris",
        mimeType: "application/x-research-info-systems",
        buffer: Buffer.from(file + extra),
      });
      await panel.getByRole("button", { name: "Compare", exact: true }).click();
      await expect(panel.getByRole("table")).toBeVisible({ timeout: 60_000 });
      await panel.getByRole("button", { name: /^List the \d+ papers? not in the index$/ }).click();
      // the sentence is drawn with the pinned day, whatever today is
      await expect(
        panel.getByRole("textbox", { name: /^This comparison in one sentence, to cite/ }),
      ).toHaveValue(
        new RegExp(
          `, on ${FIXED_DAY} \\(UTC\\) we compared the RIS file my-records\\.ris \\(sha256 \`[0-9a-f]{64}\``,
        ),
      );
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
