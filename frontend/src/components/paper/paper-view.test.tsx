// @vitest-environment jsdom
import { cleanup, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { Schemas } from "@/api/client";
import PaperPage from "@/app/paper/[id]/page";
import { json, META, renderWithApi, type Call, type Handler } from "@/test/api-stub";
import { fetchedText, PaperView } from "./paper-view";
import { ABSTRACT_WITHHELD, seeAlsoLead } from "../search/hit-item";

afterEach(cleanup);

type Paper = Schemas["PaperResponse"];

const PAPER: Paper["paper"] = {
  id: "op:iclr:2024:abc",
  title: "𝔘 Trustworthy models",
  abstract: "We study trust.",
  authors: ["Ada Lovelace", "Alan Turing"],
  venue: "ICLR",
  venue_name: "International Conference on Learning Representations (ICLR 2024)",
  year: 2024,
  track: "main",
  status: "accepted",
  presentation: "oral",
  venue_id_raw: "ICLR.cc/2024/Conference",
  urls: {
    forum: "https://openreview.net/forum?id=abc",
    pdf: "https://openreview.net/pdf?id=abc",
    proceedings: null,
    doi: null,
  },
  keywords: [],
  provenance: [
    {
      field: "title",
      value: "𝔘 Trustworthy models",
      source: "openreview_v2",
      url: "https://openreview.net/forum?id=abc",
      fetched_at: "2026-09-18T10:02:33Z",
      evidence: "note.content.title",
    },
  ],
  content_hash: "c0ffee",
};

function answer(over: Partial<Paper> = {}): Paper {
  return {
    index_version: "a1b2c3d4e5f6",
    tokenizer_version: "t1",
    query_version: "q1",
    paper: PAPER,
    matched: null,
    highlights: null,
    abstract_withheld: false,
    twins: [],
    abstract_note: null,
    ...over,
  };
}

/** The API's `abstract_note` for a submission-time abstract (TASK-210; `ingest/dedup.py::SUBMISSION_NOTE`). */
const NOTE =
  "Submission-time abstract: as the authors submitted it, which may differ from the published paper's.";

const papers = (calls: Call[]) => calls.filter((c) => c.path.startsWith("/api/v1/papers/"));

function api(paper: (call: Call) => Response): Handler {
  return (call) => {
    if (call.path === "/api/v1/meta") return json(META);
    if (call.path.startsWith("/api/v1/papers/")) return paper(call);
    return json({ error: { code: "API_NOT_FOUND", message: "no" } }, 404);
  };
}

const draw = (q: string | null, handler: Handler, mode: "native" | "scholar" = "native") =>
  renderWithApi(<PaperView id="op:iclr:2024:abc" q={q} mode={mode} />, handler);

describe("P1 matched (reached from a hit)", () => {
  it("asks with q and mode, and draws the API's highlights as <mark> over the raw text", async () => {
    const { calls } = draw(
      "trust*",
      api(() => json(answer({ matched: true, highlights: { title: [[2, 13]], abstract: [[9, 14]] } }))),
    );
    await screen.findByRole("heading", { level: 1 });
    const call = papers(calls)[0];
    expect(decodeURIComponent(call?.path ?? "")).toBe("/api/v1/papers/op:iclr:2024:abc");
    expect(Object.fromEntries(call?.query ?? [])).toEqual({ q: "trust*", mode: "native" });
    expect([...document.querySelectorAll("mark")].map((m) => m.textContent)).toEqual([
      "Trustworthy",
      "trust",
    ]);
    expect(document.body.textContent).toContain(
      "Matches trust* (native syntax): matched terms are highlighted.",
    );
    expect(screen.getByText("Ada Lovelace, Alan Turing")).toBeTruthy();
    expect(screen.getByRole("link", { name: /Back to results/ }).getAttribute("href")).toBe(
      "/search?q=trust*&mode=native",
    );
  });

  it("has the record's links, identifiers and a provenance table with header cells", async () => {
    draw(
      null,
      api(() => json(answer())),
    );
    await screen.findByRole("heading", { level: 1 });
    const links = within(screen.getByRole("list", { name: "Links" })).getAllByRole("link");
    expect(links.map((l) => l.textContent)).toEqual(["OpenReview", "PDF"]);
    expect(screen.getByRole("button", { name: "Copy paper id" })).toBeTruthy();
    expect(screen.getByText("ICLR.cc/2024/Conference")).toBeTruthy();
    const table = screen.getByRole("table");
    expect(
      within(table)
        .getAllByRole("columnheader")
        .map((h) => h.textContent),
    ).toEqual(["Field", "Value", "Source", "Fetched", "Evidence"]);
    expect(within(table).getByRole("rowheader").textContent).toBe("title");
    expect(within(table).getByText("2026-09-18 10:02 UTC")).toBeTruthy();
    expect(document.body.textContent).toContain("Index a1b2c3d4e5f6 · tokenizer t1 · query version q1");
  });

  it("says a paper that isn't accepted is not in the proceedings, naming the conference in full", async () => {
    draw(
      null,
      api(() => json(answer({ paper: { ...PAPER, status: "rejected" } }))),
    );
    expect(
      await screen.findByText(
        "Status: rejected — submitted to International Conference on Learning Representations (ICLR 2024), not in its proceedings.",
      ),
    ).toBeTruthy();
  });
});

describe("a withheld abstract (TASK-136, decision-022, PA-8)", () => {
  it("says the abstract was removed, and that terms matched in it aren't shown", async () => {
    draw(
      "trust*",
      api(() =>
        json(
          answer({
            paper: { ...PAPER, abstract: null },
            matched: true,
            highlights: { title: [[2, 13]], abstract: [] },
            abstract_withheld: true,
          }),
        ),
      ),
    );
    await screen.findByRole("heading", { level: 1 });
    expect(screen.getByText(ABSTRACT_WITHHELD)).toBeTruthy();
    expect(screen.queryByText("No abstract in the index")).toBeNull();
    expect(document.body.textContent).toContain(
      "Matches trust* (native syntax): matched terms are highlighted. Any terms it matched in the removed abstract aren't shown.",
    );
    expect([...document.querySelectorAll("mark")].map((m) => m.textContent)).toEqual(["Trustworthy"]);
  });

  it("says nothing about removed terms for an abstract that isn't withheld", async () => {
    draw(
      "trust*",
      api(() => json(answer({ matched: true, highlights: { title: [], abstract: [] } }))),
    );
    await screen.findByRole("heading", { level: 1 });
    expect(document.body.textContent).not.toContain("removed abstract");
  });
});

describe("a submission-time abstract (TASK-210, PA-11)", () => {
  it("says so under the abstract, in the API's words", async () => {
    draw(
      null,
      api(() => json(answer({ abstract_note: NOTE }))),
    );
    const heading = await screen.findByRole("heading", { level: 2, name: "Abstract" });
    const section = heading.closest("section");
    expect(section).not.toBeNull();
    const note = within(section as HTMLElement).getByText(NOTE);
    expect(note.previousElementSibling?.textContent).toBe(PAPER.abstract); // right under the text
  });

  it("says nothing for any other abstract", async () => {
    draw(
      null,
      api(() => json(answer())),
    );
    await screen.findByRole("heading", { level: 1 });
    expect(document.body.textContent).not.toContain("Submission-time");
  });

  it("says nothing when the abstract is withheld, whatever a client was sent", async () => {
    draw(
      null,
      api(() =>
        json(answer({ paper: { ...PAPER, abstract: null }, abstract_withheld: true, abstract_note: NOTE })),
      ),
    );
    await screen.findByText(ABSTRACT_WITHHELD);
    expect(screen.queryByText(NOTE)).toBeNull();
  });
});

describe("a record's twins (TASK-162, decision-029, PA-10)", () => {
  const COPY = "op:iclr:2024:Hy-Copy01";
  const COPY2 = "op:iclr:2024:Hy-Copy02";
  const seeAlso = () =>
    [...document.querySelectorAll("p")].find((p) => p.textContent?.startsWith("See also"));

  it("says nothing for a paper with no twin", async () => {
    draw(
      null,
      api(() => json(answer())),
    );
    await screen.findByRole("heading", { level: 1 });
    expect(seeAlso()).toBeUndefined();
  });

  it("links one twin's paper page; from a direct link, without a query", async () => {
    draw(
      null,
      api(() => json(answer({ twins: [COPY] }))),
    );
    await screen.findByRole("heading", { level: 1 });
    expect(seeAlso()?.textContent).toBe(`${seeAlsoLead(1)} ${COPY}`);
    expect(within(seeAlso()!).getByRole("link", { name: COPY }).getAttribute("href")).toBe(
      `/paper/${encodeURIComponent(COPY)}`,
    );
  });

  it("links each of two twins, keeping the query and mode", async () => {
    draw(
      "trust*",
      api(() =>
        json(answer({ twins: [COPY, COPY2], matched: true, highlights: { title: [], abstract: [] } })),
      ),
      "scholar",
    );
    await screen.findByRole("heading", { level: 1 });
    const links = within(seeAlso()!).getAllByRole("link");
    expect(links.map((a) => a.textContent)).toEqual([COPY, COPY2]);
    expect(links[1]?.getAttribute("href")).toBe(
      `/paper/${encodeURIComponent(COPY2)}?${new URLSearchParams({ q: "trust*", mode: "scholar" }).toString()}`,
    );
  });
});

describe("a record's twins when the link's query was refused (PA-10, PA-4)", () => {
  it("links the twin without the refused query", async () => {
    const twin = "op:iclr:2024:Hy-Copy01";
    draw(
      "tr*",
      api((call) =>
        call.query.has("q")
          ? json({ error: { code: "WILDCARD_TOO_MANY_EXPANSIONS", message: "m" } }, 422)
          : json(answer({ twins: [twin] })),
      ),
    );
    await screen.findByRole("heading", { level: 1 });
    expect(screen.getByRole("link", { name: twin }).getAttribute("href")).toBe(
      `/paper/${encodeURIComponent(twin)}`,
    );
  });
});

describe("P2 not matched", () => {
  it("says the query doesn't match and lights nothing", async () => {
    draw(
      "trust",
      api(() => json(answer({ matched: false, highlights: { title: [], abstract: [] } }))),
      "scholar",
    );
    await screen.findByRole("heading", { level: 1 });
    expect(document.body.textContent).toContain(
      "Doesn't match trust (Google Scholar syntax). Nothing is highlighted. A filter may remove it (for example the default track or status filter), or it lacks a term the query requires.",
    );
    expect(document.querySelectorAll("mark")).toHaveLength(0);
  });
});

describe("P3 direct link", () => {
  it("asks without q or mode and says nothing about a query", async () => {
    const { calls } = draw(
      null,
      api(() => json(answer())),
    );
    await screen.findByRole("heading", { level: 1 });
    expect([...(papers(calls)[0]?.query ?? [])]).toEqual([]);
    expect(document.body.textContent).not.toMatch(/Matches|Doesn't match|couldn't be run/);
  });
});

describe("P4 query refused", () => {
  it.each([
    [
      422,
      "WILDCARD_TOO_MANY_EXPANSIONS",
      "The query in this link couldn't be run (WILDCARD_TOO_MANY_EXPANSIONS), so the paper is shown without highlights.",
    ],
    [
      503,
      "API_BUSY",
      "The query in this link couldn't be run (API_BUSY), so the paper is shown without highlights.",
    ],
    [
      429,
      "API_RATE_LIMITED",
      "The query in this link couldn't be run just now (too many requests), so the paper is shown without highlights.",
    ],
  ])("a %i %s fetches the paper without q and says so in one line", async (status, code, line) => {
    const { calls } = draw(
      "tr*",
      api((call) => (call.query.has("q") ? json({ error: { code, message: "m" } }, status) : json(answer()))),
    );
    await screen.findByRole("heading", { level: 1 });
    expect(screen.getAllByRole("status").map((el) => el.textContent)).toContain(`ⓘ ${line}`);
    expect(papers(calls).map((c) => c.query.has("q"))).toEqual([true, false]);
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe(PAPER.title);
  });
});

describe("P5 not found", () => {
  it.each([
    [404, "API_PAPER_NOT_FOUND"],
    [422, "API_BAD_PARAM"],
  ])("%i %s is the not-found state, naming the served index", async (status, code) => {
    draw(
      "trust",
      api(() => json({ error: { code, message: "m" } }, status)),
    );
    expect(await screen.findByRole("heading", { name: "Paper not found" })).toBeTruthy();
    await waitFor(() =>
      expect(document.body.textContent).toContain(
        "No paper with that id in index a1b2c3d4e5f6. The link may be mistyped, or the paper isn't in the index this instance serves.",
      ),
    );
  });

  it("any other failure is a retry state, not not-found", async () => {
    draw(
      null,
      api(() => json({ error: { code: "API_INDEX_NOT_LOADED", message: "No index is loaded yet." } }, 503)),
    );
    expect(await screen.findByRole("heading", { name: "Search index loading" })).toBeTruthy();
  });
});

describe("the page reads the link", () => {
  it("passes q and mode through, reads an unknown mode as native, and treats a blank q as a direct link", async () => {
    const seen: Call[] = [];
    const handler = api((call) => {
      seen.push(call);
      return json(answer());
    });
    renderWithApi(
      await PaperPage({
        params: Promise.resolve({ id: "op%3Aiclr%3A2024%3Aabc" }),
        searchParams: Promise.resolve({ q: "trust", mode: "bing" }),
      }),
      handler,
    );
    await screen.findByRole("heading", { level: 1 });
    expect(decodeURIComponent(seen[0]?.path ?? "")).toBe("/api/v1/papers/op:iclr:2024:abc");
    expect(Object.fromEntries(seen[0]?.query ?? [])).toEqual({ q: "trust", mode: "native" });
    cleanup();
    seen.length = 0;
    renderWithApi(
      await PaperPage({
        params: Promise.resolve({ id: "op:iclr:2024:abc" }),
        searchParams: Promise.resolve({ q: "  " }),
      }),
      handler,
    );
    await screen.findByRole("heading", { level: 1 });
    expect([...(seen[0]?.query ?? [])]).toEqual([]);
  });
});

describe("fetchedText", () => {
  it("writes an ISO time as date, minutes and UTC", () => {
    expect(fetchedText("2026-09-18T10:02:33Z")).toBe("2026-09-18 10:02 UTC");
    expect(fetchedText("not a date")).toBe("not a date");
  });
});
