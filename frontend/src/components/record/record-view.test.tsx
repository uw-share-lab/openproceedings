// @vitest-environment jsdom
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { json, renderWithApi, type Call, type Handler } from "@/test/api-stub";
import { copy, RECORDS, type RecordCase } from "@/test/record-fixture";
import { methodsText, type RecordResponse } from "@/lib/methods-text";
import { RecordView } from "./record-view";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: () => {} }), usePathname: () => "/record/x" }));

beforeEach(() => {
  URL.createObjectURL = vi.fn(() => "blob:test");
  URL.revokeObjectURL = vi.fn();
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

type Replay = NonNullable<RecordResponse["replay"]>;

/** A fixture case, its record made citable (the fixture corpus is RIS-only, never citable) when asked. */
function caseOf(name: keyof typeof RECORDS, citable: boolean): RecordCase {
  const c = copy(RECORDS[name]);
  if (citable) {
    for (const r of [c.stored, c.replayed]) {
      r.record.identification_citable = true;
      r.record.crawl_dates_kind = { "*": "crawl", ris: "crawl" };
    }
  }
  return c;
}

/** The API: the stored read, the replay (as given), `/parse`, `/export` and `/diff`. */
function api(c: RecordCase, replay: Response | ((call: Call) => Response) = json(c.replayed)): Handler {
  return (call) => {
    if (call.path === "/api/v1/parse") {
      const q = (call.body as { q: string }).q;
      if (q === c.stored.record.canonical) return json(c.parse_canonical);
      if (q === c.stored.record.identification_query) return json(c.parse_identification);
      return json({ error: { code: "API_NOT_FOUND", message: "unexpected parse" } }, 404);
    }
    if (call.path === "/api/v1/export") {
      return new Response("TY  - CPAPER\nER  - \n", {
        headers: {
          "X-Index-Version": c.stored.record.index_version,
          "X-Total": String(c.stored.record.total),
          "Content-Disposition": 'attachment; filename="openproceedings-x.ris"',
        },
      });
    }
    if (call.path.endsWith("/diff")) {
      return json({
        ...c.replayed,
        record_id: c.stored.record.record_id,
        status: "drifted",
        recorded_index_version: c.stored.record.index_version,
        refused: null,
        changed: [],
        offset: Number(call.query.get("offset")),
        limit: Number(call.query.get("limit")),
        added_total: 2,
        removed_total: 1,
        added: [
          { id: "op:iclr:2024:new1", title: "A new paper" },
          { id: "op:iclr:2024:new2", title: null },
        ],
        removed: [{ id: "op:iclr:2023:old1", title: "An old paper" }],
        membership_identical: false,
        verified_clauses: 0,
      });
    }
    if (call.path === `/api/v1/records/${c.stored.record.record_id}`) {
      if (call.query.get("replay") === "false") return json(c.stored);
      return typeof replay === "function" ? replay(call) : replay.clone();
    }
    return json({ error: { code: "API_NOT_FOUND", message: "-" } }, 404);
  };
}

function withReplay(c: RecordCase, over: Partial<Replay>): Response {
  const body = copy(c.replayed);
  if (body.replay === null) throw new Error("the fixture's replay is null");
  body.replay = { ...body.replay, ...over };
  return json(body);
}

const ID = RECORDS.limits.stored.record.record_id;

/** An element's text without its leading status glyph (aria-hidden: the words say the status). */
const said = (el: HTMLElement) => (el.textContent ?? "").replace(/^[⚠✔✖] /, "");

describe("reproduced (design R1)", () => {
  it("reads the stored record first, then replays it, and shows the recorded values", async () => {
    const c = caseOf("limits", true);
    const { calls } = renderWithApi(<RecordView id={ID} />, api(c));
    await screen.findByText(/^Reproduced on /);
    const reads = calls.filter((x) => x.path === `/api/v1/records/${ID}`);
    expect(reads.map((x) => x.query.get("replay"))).toEqual(["false", null]);
    const r = c.stored.record;
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe(`Search record ${ID}`);
    const today = new Date().toISOString().slice(0, 10);
    expect(said(screen.getByText(/^Reproduced on /))).toBe(
      `Reproduced on ${today}: the same index and query version give the same ${r.total} papers and the same exclusions.`,
    );
    expect(
      screen.getByText(
        `${r.identified_total} identified · ${r.excluded.total} removed before screening · ${r.total} screened`,
        { exact: false },
      ),
    ).toBeTruthy();
    expect(screen.getAllByText(r.index_version).length).toBeGreaterThan(0);
    expect(screen.getByText("Crawl run")).toBeTruthy();
  });

  it("shows the methods text the record generates, every number the record's, and a Copy button", async () => {
    const c = caseOf("limits", true);
    renderWithApi(<RecordView id={ID} />, api(c));
    const region = await screen.findByRole("region", { name: "Methods text to cite" });
    expect(region.textContent).toBe(
      methodsText({
        record: c.stored.record,
        parseCanonical: c.parse_canonical,
        parseIdentification: c.parse_identification,
        url: `${window.location.origin}/record/${ID}`,
      }),
    );
    expect(region.textContent).toContain(`index \`${c.stored.record.index_version}\``);
    expect(screen.getByRole("button", { name: "Copy methods text" })).toBeTruthy();
  });

  it("exports the record's own ids by record_id (AC#3), checked against its total", async () => {
    const c = caseOf("limits", true);
    const { calls } = renderWithApi(<RecordView id={ID} />, api(c));
    const ris = await screen.findByRole("button", { name: `RIS, ${c.stored.record.total} papers` });
    fireEvent.click(ris);
    await screen.findByText("Download ready.");
    const exported = calls.filter((x) => x.path === "/api/v1/export");
    expect(exported).toHaveLength(1);
    expect(Object.fromEntries(exported[0]?.query ?? [])).toEqual({ format: "ris", record_id: ID });
    expect(URL.createObjectURL).toHaveBeenCalledOnce();
  });

  it("shows the CLI's caution instead of the methods text for a bootstrap corpus, and keeps the exports", async () => {
    const c = caseOf("limits", false);
    renderWithApi(<RecordView id={ID} />, api(c));
    await screen.findByText(/^Reproduced on /);
    expect(await screen.findByText(/bootstrap corpus \(sources: ris\)/)).toBeTruthy();
    expect(screen.queryByRole("region", { name: "Methods text to cite" })).toBeNull();
    expect(screen.getByRole("button", { name: `RIS, ${c.stored.record.total} papers` })).toBeTruthy();
  });

  it("waits for the replay before the methods text and exports", async () => {
    const c = caseOf("limits", true);
    let answer: (r: Response) => void = () => {};
    const pending = new Promise<Response>((resolve) => (answer = resolve));
    renderWithApi(
      <RecordView id={ID} />,
      api(c, () => pending as unknown as Response),
    );
    await screen.findByText("Checking the record: re-running its search on this instance…");
    expect(screen.queryByRole("region", { name: "Methods text to cite" })).toBeNull();
    expect(screen.queryByRole("button", { name: /^RIS/ })).toBeNull();
    answer(json(c.replayed));
    await screen.findByRole("region", { name: "Methods text to cite" });
  });
});

describe("mismatch (design R4; AC#2)", () => {
  it("is a blocking do-not-cite alert with no methods text and no export", async () => {
    const c = caseOf("limits", true);
    const { calls } = renderWithApi(<RecordView id={ID} />, api(c, withReplay(c, { status: "mismatch" })));
    const alert = await screen.findByRole("alert");
    expect(within(alert).getByRole("heading").textContent).toContain("Do not cite — replay mismatch");
    expect(alert.textContent).toContain(
      `Re-run on the same index (${c.stored.record.index_version}) and query version (${c.stored.record.query_version})`,
    );
    expect(screen.queryByText("Methods text")).toBeNull();
    expect(screen.queryByRole("region", { name: "Methods text to cite" })).toBeNull();
    expect(screen.queryByRole("button", { name: /^(RIS|CSV|BibTeX|JSONL)/ })).toBeNull();
    expect(calls.some((x) => x.path === "/api/v1/export")).toBe(false);
    expect(within(alert).getByText("Show the record's details anyway")).toBeTruthy();
  });
});

describe("drifted (design R2, R5)", () => {
  const other = "9f8e7d6c5b4a";
  const drifted = (c: RecordCase, over: Partial<Replay> = {}) =>
    withReplay(c, {
      status: "drifted",
      index_version: other,
      changed: [
        { input: "snapshot_hash", kind: "corpus", recorded: c.stored.record.snapshot_hash, current: "0d4b" },
      ],
      total: c.stored.record.total + 1,
      added_total: 2,
      removed_total: 1,
      ids_match: false,
      excluded_match: false,
      excluded: { total: 3, track: { workshop: 2, unknown: 0 }, status: { rejected: 1, unknown: 0 } },
      membership_identical: false,
      ...over,
    });

  it("names the changed input, the counts against the record, and the re-run's exclusions beside the recorded", async () => {
    const c = caseOf("limits", true);
    const r = c.stored.record;
    renderWithApi(<RecordView id={ID} />, api(c, drifted(c)));
    const status = await screen.findByText(/^Drifted: this instance no longer has index/);
    expect(said(status)).toBe(
      `Drifted: this instance no longer has index ${r.index_version}, so the search was re-run on index ${other}. ` +
        `It now finds ${r.total + 1} papers: +2 / −1 against the record.`,
    );
    expect(screen.getByText(/the corpus \(papers added or re-crawled\)/)).toBeTruthy();
    expect(
      screen.getByText(/^Removed before screening on re-run: 2 workshop · 1 rejected \(recorded: /),
    ).toBeTruthy();
    expect(
      screen.getByText(/^Cite the recorded counts below; they describe the search as it was run on /),
    ).toBeTruthy();
  });

  it("disables the exports with the reason when the record's index isn't here, and keeps the methods text", async () => {
    const c = caseOf("limits", true);
    renderWithApi(<RecordView id={ID} />, api(c, drifted(c)));
    const ris = await screen.findByRole("button", { name: `RIS, ${c.stored.record.total} papers` });
    expect(ris.getAttribute("aria-disabled")).toBe("true");
    expect(screen.getByText(/which this record's papers come from, isn't on this instance/)).toBeTruthy();
    expect(await screen.findByRole("region", { name: "Methods text to cite" })).toBeTruthy();
  });

  it("pages the diff on request: added, removed, and an id the index doesn't hold", async () => {
    const c = caseOf("limits", true);
    const { calls } = renderWithApi(<RecordView id={ID} />, api(c, drifted(c)));
    const open = await screen.findByRole("button", { name: /See the 2 added and 1 removed papers/ });
    expect(calls.some((x) => x.path.endsWith("/diff"))).toBe(false);
    fireEvent.click(open);
    expect(await screen.findByRole("heading", { name: "Added (2)" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Removed (1)" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "A new paper" }).getAttribute("href")).toBe(
      "/paper/op%3Aiclr%3A2024%3Anew1",
    );
    expect(screen.getByText(/\(not in index/)).toBeTruthy();
    const diff = calls.find((x) => x.path.endsWith("/diff"));
    expect(diff?.query.get("limit")).toBe("50");
  });

  it("says membership-identical on +0 / −0", async () => {
    const c = caseOf("limits", true);
    renderWithApi(
      <RecordView id={ID} />,
      api(
        c,
        drifted(c, { added_total: 0, removed_total: 0, membership_identical: true, excluded_match: true }),
      ),
    );
    expect(
      await screen.findByText(
        "+0 / −0: the re-run finds exactly the recorded papers (membership-identical), though the index or query version changed.",
      ),
    ).toBeTruthy();
    expect(screen.getByText("Removed before screening on re-run: same exclusions")).toBeTruthy();
  });

  it("says the query rules changed when only the query version did, on the record's own index", async () => {
    const c = caseOf("limits", true);
    const r = c.stored.record;
    renderWithApi(
      <RecordView id={ID} />,
      api(
        c,
        drifted(c, {
          index_version: r.index_version,
          query_version: "99",
          changed: [{ input: "query_version", kind: "method", recorded: r.query_version, current: "99" }],
        }),
      ),
    );
    expect(said(await screen.findByText(/^Drifted: the query rules changed/))).toBe(
      `Drifted: the query rules changed (query version ${r.query_version} → 99). Re-run on the record's own index, ` +
        `it finds ${r.total + 1} papers: +2 / −1 against the record.`,
    );
    const ris = await screen.findByRole("button", { name: `RIS, ${r.total} papers` });
    expect(ris.getAttribute("aria-disabled")).toBeNull(); // its own index is here
  });
});

describe("could not be re-run (design R3)", () => {
  const nulls = {
    status: "drifted" as const,
    total: null,
    excluded: null,
    ids_hash: null,
    ids_match: null,
    excluded_match: null,
    added_total: null,
    removed_total: null,
    membership_identical: null,
    identified_total: null,
    unclassified_total: null,
  };

  it("names the refusal and compares no counts", async () => {
    const c = caseOf("limits", true);
    renderWithApi(
      <RecordView id={ID} />,
      api(c, withReplay(c, { ...nulls, refused: "WILDCARD_TOO_MANY_EXPANSIONS" })),
    );
    expect(said(await screen.findByText(/could not be re-run/))).toBe(
      "Drifted — could not be re-run: WILDCARD_TOO_MANY_EXPANSIONS. No counts were compared.",
    );
    expect(screen.queryByText(/membership-identical/)).toBeNull();
  });

  it("gives the withheld wording with the record's verified clauses, and keeps the exports", async () => {
    const c = caseOf("limits", true);
    renderWithApi(
      <RecordView id={ID} />,
      api(
        c,
        withReplay(c, {
          ...nulls,
          refused: "API_TOO_MANY_VERIFIED_CLAUSES",
          verified_clauses: 18,
          changed: [],
        }),
      ),
    );
    expect(said(await screen.findByText(/^Could not be re-run/))).toBe(
      "Could not be re-run: API_TOO_MANY_VERIFIED_CLAUSES — this instance's limit is below the record's 18 " +
        "position-verified clauses. The record and its exports are unchanged.",
    );
    const ris = await screen.findByRole("button", { name: /^RIS/ });
    expect(ris.getAttribute("aria-disabled")).toBeNull();
  });

  it("says Replay: waiting on a 429 and still shows the recorded values, methods text and exports", async () => {
    const c = caseOf("limits", true);
    renderWithApi(
      <RecordView id={ID} />,
      api(
        c,
        json({ error: { code: "API_RATE_LIMITED", message: "Too many requests." } }, 429, {
          "Retry-After": "5",
        }),
      ),
    );
    expect(await screen.findByText(/Replay: waiting/)).toBeTruthy();
    expect(await screen.findByRole("region", { name: "Methods text to cite" })).toBeTruthy();
    expect(screen.getByRole("button", { name: /^RIS/ })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Retry" }).getAttribute("aria-disabled")).toBe("true");
  });
});

describe("not found and can't load", () => {
  it.each([
    [404, "API_RECORD_NOT_FOUND"],
    [422, "API_BAD_PARAM"],
  ])("%i %s is the not-found state", async (status, code) => {
    renderWithApi(<RecordView id="nope" />, () => json({ error: { code, message: "-" } }, status));
    expect(await screen.findByRole("heading", { name: "Search record not found" })).toBeTruthy();
    expect(screen.getByText(/a record id is 12 characters/)).toBeTruthy();
  });

  it("offers Retry when the stored read fails", async () => {
    let fail = true;
    const c = caseOf("limits", true);
    const inner = api(c);
    renderWithApi(<RecordView id={ID} />, (call) => {
      if (fail && call.query.get("replay") === "false")
        return new Response("<html>busy</html>", { status: 503 });
      return inner(call);
    });
    const retry = await screen.findByRole("button", { name: "Retry" });
    expect(screen.getByRole("alert").textContent).toContain("The record couldn't be loaded just now");
    fail = false;
    fireEvent.click(retry);
    await waitFor(() => expect(screen.getByText(/^Reproduced on /)).toBeTruthy());
  });
});
