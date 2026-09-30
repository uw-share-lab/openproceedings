// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { Schemas } from "@/api/client";
import { HitItem, shownAuthors, sourceName } from "./hit-item";

afterEach(cleanup);

type Hit = Schemas["Hit"];

const PMLR_PAGE = "https://proceedings.mlr.press/v202/okafor23a.html";
const HIT: Hit = {
  id: "op:icml:2023:pmlr-v202-okafor23a",
  title: "Calibrated trust in model outputs",
  abstract: "We measure trust in models.",
  authors: ["Ada Okafor", "Bo Lindqvist", "Chen Wei", "Dana Haddad", "Emil Novak"],
  venue: "ICML",
  year: 2023,
  track: "main",
  status: "accepted",
  presentation: null,
  score: 1.5,
  highlights: { title: [], abstract: [] },
  urls: { forum: null, pdf: null, proceedings: PMLR_PAGE, doi: null },
  abstract_source: { source: "pmlr", url: PMLR_PAGE },
};

function show(over: Partial<Hit> = {}) {
  render(<HitItem hit={{ ...HIT, ...over }} q="trust" mode="native" />);
  return screen.getByRole("article");
}

/** The attribution line: the paragraph that starts "Abstract:". */
function attribution(article: HTMLElement): HTMLElement | undefined {
  return [...article.querySelectorAll("p")].find((p) => p.textContent?.startsWith("Abstract:"));
}

describe("authors (ui-design-system §Result item, RH-13)", () => {
  it("shows the first three and et al., and the full list behind a button that says how many", () => {
    const article = show();
    expect(within(article).getByText(/Ada Okafor, Bo Lindqvist, Chen Wei et al\./)).toBeTruthy();
    expect(within(article).queryByText(/Dana Haddad/)).toBeNull();
    const more = within(article).getByRole("button", { name: "Show all 5 authors" });
    expect(more.getAttribute("aria-expanded")).toBe("false");
    const names = document.getElementById(more.getAttribute("aria-controls") ?? "");
    expect(names?.textContent).toBe("Authors: Ada Okafor, Bo Lindqvist, Chen Wei et al.");
    fireEvent.click(more);
    expect(names?.textContent).toBe("Authors: Ada Okafor, Bo Lindqvist, Chen Wei, Dana Haddad, Emil Novak");
    expect(more.getAttribute("aria-expanded")).toBe("true");
    expect(more.textContent).toBe("Show fewer authors");
  });

  it("shows three or fewer in full with no button, and nothing for a paper with none", () => {
    const article = show({ authors: ["Ada Okafor", "Bo Lindqvist", "Chen Wei"] });
    expect(within(article).getByText("Ada Okafor, Bo Lindqvist, Chen Wei")).toBeTruthy();
    expect(within(article).queryByRole("button", { name: /authors/ })).toBeNull();
    cleanup();
    expect(show({ authors: [] }).textContent).not.toContain("Authors:");
  });

  it("cuts after exactly AUTHORS_SHOWN names", () => {
    expect(shownAuthors(["A", "B", "C", "D"], false)).toEqual({ names: "A, B, C", cut: true });
    expect(shownAuthors(["A", "B", "C", "D"], true)).toEqual({ names: "A, B, C, D", cut: false });
    expect(shownAuthors(["A"], false)).toEqual({ names: "A", cut: false });
  });
});

describe("the abstract's attribution (decision-018, RH-12)", () => {
  it("a PMLR abstract links to its PMLR page, with the citation (title, authors, venue, year) on the result", () => {
    const article = show();
    const line = attribution(article);
    expect(line?.textContent).toBe("Abstract: PMLR");
    const link = within(line as HTMLElement).getByRole("link", { name: "PMLR" });
    expect(link.getAttribute("href")).toBe(PMLR_PAGE);
    expect(link.getAttribute("rel")).toBe("noopener noreferrer");
    expect(link.className).toContain("underline"); // a link cue that isn't colour
    expect(within(article).getByRole("heading", { level: 3 }).textContent).toBe(HIT.title);
    expect(article.textContent).toContain("Ada Okafor");
    const badges = within(article).getByRole("list", { name: "Details" });
    expect(badges.textContent).toContain("ICML");
    expect(badges.textContent).toContain("2023");
  });

  it("names each source and links to its page: OpenReview's forum, the NeurIPS proceedings page", () => {
    const forum = "https://openreview.net/forum?id=abc";
    let line = attribution(show({ abstract_source: { source: "openreview_v2", url: forum } }));
    expect(
      within(line as HTMLElement)
        .getByRole("link", { name: "OpenReview" })
        .getAttribute("href"),
    ).toBe(forum);
    cleanup();
    const page = "https://proceedings.neurips.cc/paper/2020/hash/x-Abstract.html";
    line = attribution(show({ abstract_source: { source: "neurips_proceedings", url: page } }));
    expect(
      within(line as HTMLElement)
        .getByRole("link", { name: "NeurIPS Proceedings" })
        .getAttribute("href"),
    ).toBe(page);
  });

  it("names a source with no page without a link, and a source this code doesn't know as it came", () => {
    let line = attribution(show({ abstract_source: { source: "ris", url: null } }));
    expect(line?.textContent).toBe("Abstract: an imported RIS file");
    expect(within(line as HTMLElement).queryByRole("link")).toBeNull();
    expect(sourceName("arxiv")).toBe("arxiv");
    cleanup();
    line = attribution(show({ abstract_source: null }));
    expect(line).toBeUndefined();
  });

  it("has no attribution when there is no abstract", () => {
    const article = show({ abstract: null, abstract_source: null });
    expect(within(article).getByText("No abstract in the index")).toBeTruthy();
    expect(attribution(article)).toBeUndefined();
  });
});
