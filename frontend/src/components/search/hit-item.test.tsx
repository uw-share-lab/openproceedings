// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { Schemas } from "@/api/client";
import {
  ABSTRACT_WITHHELD,
  attributionText,
  HitItem,
  seeAlsoLead,
  shownAuthors,
  WITHHELD_SEARCH_TERMS,
} from "./hit-item";

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
  abstract_source: { source: "pmlr", origin: "pmlr", url: PMLR_PAGE },
  abstract_withheld: false,
  twins: [],
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
  const LINK = `PMLR, abstract source for ${HIT.title}`;

  it("a PMLR abstract links to its PMLR page, with the citation (title, authors, venue, year) on the result", () => {
    const article = show();
    const line = attribution(article);
    expect(line?.textContent).toBe("Abstract: PMLR");
    const link = within(line as HTMLElement).getByRole("link", { name: LINK });
    expect(link.getAttribute("href")).toBe(PMLR_PAGE);
    expect(link.getAttribute("rel")).toBe("noopener noreferrer");
    expect(link.className).toContain("underline"); // a link cue that isn't colour
    expect(link.textContent).toBe("PMLR"); // the name starts with the visible text (WCAG 2.5.3)
    expect(within(article).getByRole("heading", { level: 3 }).textContent).toBe(HIT.title);
    expect(article.textContent).toContain("Ada Okafor");
    const badges = within(article).getByRole("list", { name: "Details" });
    expect(badges.textContent).toContain("ICML");
    expect(badges.textContent).toContain("2023");
  });

  it("its link's name differs from the Links list's, which name the same pages", () => {
    const article = show();
    const outbound = within(article).getByRole("list", { name: `Links for ${HIT.title}` });
    const names = within(outbound)
      .getAllByRole("link")
      .map((a) => a.textContent);
    expect(names).toEqual(["Proceedings"]);
    expect(within(article).getAllByRole("link", { name: /^PMLR/ })).toHaveLength(1);
  });

  it("names each site and links to its page: OpenReview's forum, the NeurIPS and ICLR proceedings pages", () => {
    const forum = "https://openreview.net/forum?id=abc";
    const cases = [
      [{ source: "openreview_v2", origin: "openreview", url: forum }, "OpenReview"],
      [
        {
          source: "neurips_proceedings",
          origin: "neurips_proceedings",
          url: "https://proceedings.neurips.cc/p",
        },
        "NeurIPS Proceedings",
      ],
    ] as const;
    for (const [from, site] of cases) {
      const line = attribution(show({ abstract_source: from }));
      expect(line?.textContent).toBe(`Abstract: ${site}`);
      const link = within(line as HTMLElement).getByRole("link", {
        name: `${site}, abstract source for ${HIT.title}`,
      });
      expect(link.getAttribute("href")).toBe(from.url);
      cleanup();
    }
  });

  it("an abstract that came through an RIS import names its real site, links it, and says it came via RIS", () => {
    const page = "https://proceedings.iclr.cc/paper_files/paper/2024/hash/x-Abstract-Conference.html";
    const line = attribution(
      show({ abstract_source: { source: "ris", origin: "iclr_proceedings", url: page } }),
    );
    expect(line?.textContent).toBe("Abstract: ICLR Proceedings (via RIS import)");
    const link = within(line as HTMLElement).getByRole("link", {
      name: `ICLR Proceedings, abstract source for ${HIT.title}`,
    });
    expect(link.getAttribute("href")).toBe(page);
    cleanup();
    // a known site but no page to link (its evidence and proceedings link disagree, or name another paper)
    const unlinked = attribution(
      show({ abstract_source: { source: "ris", origin: "neurips_proceedings", url: null } }),
    );
    expect(unlinked?.textContent).toBe("Abstract: NeurIPS Proceedings (via RIS import)");
    expect(within(unlinked as HTMLElement).queryByRole("link")).toBeNull();
  });

  it("names a route with no known site without a link, and an origin this code doesn't know as it came", () => {
    const line = attribution(show({ abstract_source: { source: "ris", origin: null, url: null } }));
    expect(line?.textContent).toBe("Abstract: an imported RIS file");
    expect(within(line as HTMLElement).queryByRole("link")).toBeNull();
    const unknown = { source: "ris", origin: "arxiv", url: null } as unknown as Hit["abstract_source"];
    expect(attributionText(unknown as NonNullable<Hit["abstract_source"]>)).toEqual({
      site: "arxiv",
      via: " (via RIS import)",
    });
    cleanup();
    expect(attribution(show({ abstract_source: null }))).toBeUndefined();
  });

  it("has no attribution when there is no abstract", () => {
    const article = show({ abstract: null, abstract_source: null });
    expect(within(article).getByText("No abstract in the index")).toBeTruthy();
    expect(attribution(article)).toBeUndefined();
  });
});

describe("a withheld abstract (TASK-136, decision-022, RH-15)", () => {
  it("says it was removed at a rights holder's request, never that the index has none", () => {
    const article = show({ abstract: null, abstract_source: null, abstract_withheld: true });
    expect(within(article).getByText(`${ABSTRACT_WITHHELD}. ${WITHHELD_SEARCH_TERMS}`)).toBeTruthy();
    expect(within(article).queryByText("No abstract in the index")).toBeNull();
    expect(attribution(article)).toBeUndefined();
    expect(article.querySelectorAll("mark")).toHaveLength(0);
    // the title and the links stay: the record is still found by its title
    expect(within(article).getByRole("heading", { level: 3 }).textContent).toBe(HIT.title);
  });

  it("shows the marker whatever text a client was sent with it", () => {
    const article = show({ abstract_withheld: true, abstract_source: null });
    expect(within(article).getByText(`${ABSTRACT_WITHHELD}. ${WITHHELD_SEARCH_TERMS}`)).toBeTruthy();
    expect(article.textContent).not.toContain(HIT.abstract);
  });
});

describe("a record's twins (TASK-162, decision-029, RH-18)", () => {
  const COPY = "op:iclr:2017:Hy-Copy01";
  const COPY2 = "op:iclr:2017:Hy-Copy02";
  const seeAlso = (article: HTMLElement) =>
    [...article.querySelectorAll("p")].find((p) => p.textContent?.startsWith("See also"));

  it("says nothing for a record with no twin", () => {
    expect(seeAlso(show())).toBeUndefined();
  });

  it("names one twin, a link to its paper page that keeps the query", () => {
    const line = seeAlso(show({ twins: [COPY] }));
    expect(line?.textContent).toBe(`${seeAlsoLead(1)} ${COPY}`);
    const link = within(line!).getByRole("link", { name: COPY });
    expect(link.getAttribute("href")).toBe(`/paper/${encodeURIComponent(COPY)}?q=trust&mode=native`);
  });

  it("names two twins, each its own link, in the API's order", () => {
    const line = seeAlso(show({ twins: [COPY, COPY2] }));
    expect(line?.textContent).toBe(`${seeAlsoLead(2)} ${COPY}, ${COPY2}`);
    expect(
      within(line!)
        .getAllByRole("link")
        .map((a) => a.textContent),
    ).toEqual([COPY, COPY2]);
    expect(seeAlsoLead(2)).toContain("other records");
  });

  it("names the twins of a record whose abstract is withheld too", () => {
    const article = show({ abstract: null, abstract_source: null, abstract_withheld: true, twins: [COPY] });
    expect(within(seeAlso(article)!).getByRole("link", { name: COPY })).toBeTruthy();
  });
});
