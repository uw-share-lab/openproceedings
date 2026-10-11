// @vitest-environment jsdom
/**
 * Gate C round 2 (ruling 2): the save panel and the record page write the same methods text for the same record,
 * the OpenAlex sentence included. Its count is the record GET's `openalex_abstracts` (derived on the server from
 * the record's ids on its own index), never a search response's facet.
 */
import { cleanup, fireEvent, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { json, renderWithApi, type Handler } from "@/test/api-stub";
import { copy, RECORDS } from "@/test/record-fixture";
import { RecordView } from "./record-view";
import { SaveRecord } from "./save-record";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: () => {} }), usePathname: () => "/x" }));
afterEach(cleanup);

const C = RECORDS.limits;
const R = C.stored.record;
const PROPS = { q: C.q, mode: C.mode, indexVersion: R.index_version, total: R.total, disabledReason: null };
const SENTENCE = /12 of the [\d,]+ records have abstracts supplied by OpenAlex/;

/** The API with the record (citable) answering `openalex_abstracts`: `stored` without a replay, `replayed` with. */
function api(stored: number | null, replayed: number | null): Handler {
  const s = copy(C.stored);
  const r = copy(C.replayed);
  for (const body of [s, r]) {
    body.record.identification_citable = true;
    body.record.crawl_dates_kind = { "*": "crawl", ris: "crawl" };
  }
  s.openalex_abstracts = stored;
  r.openalex_abstracts = replayed;
  return (call) => {
    if (call.method === "POST" && call.path === "/api/v1/records") return json(C.created, 201);
    if (call.path === `/api/v1/records/${R.record_id}`) {
      return json(call.query.get("replay") === "false" ? s : r);
    }
    if (call.path === "/api/v1/parse") {
      const q = (call.body as { q: string }).q;
      return json(q === R.canonical ? C.parse_canonical : C.parse_identification);
    }
    return json({ error: { code: "API_NOT_FOUND", message: "-" } }, 404);
  };
}

async function savePanelText(handler: Handler): Promise<string> {
  renderWithApi(<SaveRecord {...PROPS} />, handler);
  fireEvent.click(screen.getByRole("button", { name: "Save search record" }));
  const dialog = screen.getByRole("dialog", { name: "Save this search as a permanent record?" });
  fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
  const text = (await screen.findByRole("region", { name: "Methods text to cite" })).textContent ?? "";
  cleanup();
  return text;
}

async function recordPageText(handler: Handler): Promise<string> {
  renderWithApi(<RecordView id={R.record_id} />, handler);
  const text = (await screen.findByRole("region", { name: "Methods text to cite" })).textContent ?? "";
  cleanup();
  return text;
}

describe("one methods text per record (gate C round 2)", () => {
  it("is the same in the save panel and on the record page, with the record's own OpenAlex count", async () => {
    const handler = api(12, 12);
    const panel = await savePanelText(handler);
    const page = await recordPageText(handler);
    expect(panel).toMatch(SENTENCE);
    expect(page).toBe(panel);
  });

  it("reads the count from the record, so a record with none gives no sentence on either", async () => {
    const handler = api(null, null);
    const panel = await savePanelText(handler);
    expect(panel).not.toMatch(/OpenAlex/);
    expect(await recordPageText(handler)).toBe(panel);
  });

  it("takes the record page's count from the replay read, the one the save panel reads", async () => {
    // the stored read (replay=false) has no count when the served index isn't the record's; the replay has it
    expect(await recordPageText(api(null, 12))).toMatch(SENTENCE);
  });
});
