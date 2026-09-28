// @vitest-environment jsdom
import { cleanup, fireEvent, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { json, renderWithApi, type Handler } from "@/test/api-stub";
import { copy, RECORDS } from "@/test/record-fixture";
import { SaveRecord, STORE_FULL_KEY, STORE_FULL_MESSAGE } from "./save-record";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: () => {} }), usePathname: () => "/search" }));

beforeEach(() => window.sessionStorage.clear());
afterEach(cleanup);

const C = RECORDS.limits;
const R = C.stored.record;
const PROPS = { q: C.q, mode: C.mode, indexVersion: R.index_version, total: R.total, disabledReason: null };

/** POST /records answers `post`; GET /records/{id} the fixture's replayed record (citable when asked). */
function api(post: Response, citable = true, get?: Response): Handler {
  const replayed = copy(C.replayed);
  if (citable) {
    replayed.record.identification_citable = true;
    replayed.record.crawl_dates_kind = { "*": "crawl", ris: "crawl" };
  }
  return (call) => {
    if (call.method === "POST" && call.path === "/api/v1/records") return post.clone();
    if (call.path === `/api/v1/records/${R.record_id}`) return get?.clone() ?? json(replayed);
    if (call.path === "/api/v1/parse") {
      const q = (call.body as { q: string }).q;
      return json(q === R.canonical ? C.parse_canonical : C.parse_identification);
    }
    return json({ error: { code: "API_NOT_FOUND", message: "-" } }, 404);
  };
}

const created = (over: Partial<typeof C.created> = {}) => json({ ...C.created, ...over }, 201);

function openConfirm() {
  fireEvent.click(screen.getByRole("button", { name: "Save search record" }));
  return screen.getByRole("dialog", { name: "Save this search as a permanent record?" });
}

describe("confirm (design S1; copy SV-2)", () => {
  it("names permanence and publicity, shows what will be saved, and starts on Save", () => {
    renderWithApi(<SaveRecord {...PROPS} />, api(created()));
    const dialog = openConfirm();
    expect(dialog.getAttribute("aria-modal")).toBe("true");
    expect(dialog.textContent).toContain(C.q);
    expect(dialog.textContent).toContain(`${R.total} papers · index ${R.index_version}`);
    expect(dialog.textContent).toContain(
      "Anyone with the link can see the record, including the query text. It can't be edited or deleted.",
    );
    expect(document.activeElement).toBe(within(dialog).getByRole("button", { name: "Save" }));
  });

  it("keeps focus inside, and Esc cancels and returns focus to the button", () => {
    const { calls } = renderWithApi(<SaveRecord {...PROPS} />, api(created()));
    const dialog = openConfirm();
    fireEvent.keyDown(dialog, { key: "Tab" });
    expect(document.activeElement).toBe(within(dialog).getByRole("button", { name: "Cancel" }));
    fireEvent.keyDown(dialog, { key: "Tab", shiftKey: true });
    expect(document.activeElement).toBe(within(dialog).getByRole("button", { name: "Save" }));
    fireEvent.keyDown(dialog, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Save search record" }));
    expect(calls).toHaveLength(0);
  });

  it("keeps the focused dialog mounted and announces progress while the save is pending", async () => {
    let answer: (response: Response) => void = () => {};
    const pending = new Promise<Response>((resolve) => (answer = resolve));
    renderWithApi(<SaveRecord {...PROPS} />, (call) =>
      call.method === "POST" ? pending : api(created())(call),
    );
    const dialog = openConfirm();
    fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    const saving = within(dialog).getByRole("button", { name: "Saving…" });
    expect(screen.getByRole("dialog")).toBe(dialog);
    expect(document.activeElement).toBe(saving);
    expect(within(saving).getByRole("status").textContent).toBe("Saving…");
    answer(created());
    expect(
      await screen.findByRole("heading", { name: `Saved as search record ${R.record_id}` }),
    ).toBeTruthy();
  });

  it("is disabled with the reason while the results aren't the searched query's", () => {
    renderWithApi(<SaveRecord {...PROPS} disabledReason="Search first." />, api(created()));
    const button = screen.getByRole("button", { name: "Save search record" });
    expect(button.getAttribute("aria-disabled")).toBe("true");
    expect(screen.getByText("Search first.").id).toBe(button.getAttribute("aria-describedby"));
    fireEvent.click(button);
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});

describe("saved (design S2; copy SV-3, SV-4, SV-5)", () => {
  it("saves the searched query pinned to the shown index, then reads the record back", async () => {
    const { calls } = renderWithApi(<SaveRecord {...PROPS} />, api(created()));
    fireEvent.click(within(openConfirm()).getByRole("button", { name: "Save" }));
    const heading = await screen.findByRole("heading", { name: `Saved as search record ${R.record_id}` });
    expect(calls[0]?.body).toEqual({ q: C.q, mode: C.mode, index_version: R.index_version });
    await screen.findByText(`Reproduced just now on index`, { exact: false });
    expect(document.activeElement).toBe(heading);
    const url = `${window.location.origin}/record/${R.record_id}`;
    expect(screen.getByRole("link", { name: url }).getAttribute("href")).toBe(url);
    expect(screen.getByRole("link", { name: /Open record page/ }).getAttribute("href")).toBe(
      `/record/${R.record_id}`,
    );
    const region = await screen.findByRole("region", { name: "Methods text to cite" });
    expect(region.textContent).toContain(`Search record: ${url}.`);
    expect(region.textContent).toContain(`identified ${R.identified_total} records`);
  });

  it("gives the caution instead of the methods text for a record that isn't citable", async () => {
    renderWithApi(<SaveRecord {...PROPS} />, api(created(), false));
    fireEvent.click(within(openConfirm()).getByRole("button", { name: "Save" }));
    expect(await screen.findByText(/bootstrap corpus \(sources: ris\)/)).toBeTruthy();
    expect(screen.queryByRole("region", { name: "Methods text to cite" })).toBeNull();
  });

  it("keeps the link and points to the record page when the read-back is refused", async () => {
    renderWithApi(
      <SaveRecord {...PROPS} />,
      api(
        created(),
        true,
        json({ error: { code: "API_BUSY", message: "busy" } }, 503, { "Retry-After": "3" }),
      ),
    );
    fireEvent.click(within(openConfirm()).getByRole("button", { name: "Save" }));
    expect(
      await screen.findByText(/The record is saved\. Its methods text is on the record page\./),
    ).toBeTruthy();
    expect(screen.getByRole("link", { name: /Open record page/ })).toBeTruthy();
  });

  it("warns when the save ran on another index than the one shown (SV-8)", async () => {
    renderWithApi(<SaveRecord {...PROPS} />, api(created({ index_version: "9f8e7d6c5b4a" })));
    fireEvent.click(within(openConfirm()).getByRole("button", { name: "Save" }));
    const warning = await screen.findByText(/the index changed after your search/);
    expect(warning.textContent).toContain(`Saved on index 9f8e7d6c5b4a, not ${R.index_version}`);
  });
});

describe("refused (design S3)", () => {
  it("saves nothing on a moved index (409) and says so", async () => {
    const { calls } = renderWithApi(
      <SaveRecord {...PROPS} />,
      api(json({ error: { code: "API_INDEX_VERSION_UNAVAILABLE", message: "-" } }, 409)),
    );
    fireEvent.click(within(openConfirm()).getByRole("button", { name: "Save" }));
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain(
      `Index ${R.index_version} is no longer served here, so the search wasn't saved`,
    );
    expect(calls.filter((c) => c.method === "GET")).toHaveLength(0);
  });

  it("turns saving off for the session when the store is full", async () => {
    renderWithApi(
      <SaveRecord {...PROPS} />,
      api(json({ error: { code: "API_RECORDS_STORE_FULL", message: "full" } }, 503)),
    );
    fireEvent.click(within(openConfirm()).getByRole("button", { name: "Save" }));
    expect((await screen.findAllByText(STORE_FULL_MESSAGE)).length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "Save search record" }).getAttribute("aria-disabled")).toBe(
      "true",
    );
    expect(window.sessionStorage.getItem(STORE_FULL_KEY)).toBe("1");
    cleanup();
    renderWithApi(<SaveRecord {...PROPS} />, api(created()));
    expect(screen.getByRole("button", { name: "Save search record" }).getAttribute("aria-disabled")).toBe(
      "true",
    );
  });

  it("gives the server's message and a countdown on a 429", async () => {
    renderWithApi(
      <SaveRecord {...PROPS} />,
      api(
        json({ error: { code: "API_RATE_LIMITED", message: "This network is at its save ceiling." } }, 429, {
          "Retry-After": "30",
        }),
      ),
    );
    fireEvent.click(within(openConfirm()).getByRole("button", { name: "Save" }));
    expect(await screen.findByText("This network is at its save ceiling.")).toBeTruthy();
    expect(screen.getByText("Retry in 30 s")).toBeTruthy();
  });

  it("lists the diagnostics when the query no longer runs (422)", async () => {
    renderWithApi(
      <SaveRecord {...PROPS} />,
      api(
        json(
          {
            error: {
              code: "WILDCARD_TOO_MANY_EXPANSIONS",
              message: "too many",
              diagnostics: [
                {
                  code: "WILDCARD_TOO_MANY_EXPANSIONS",
                  message: "`t*` expands to too many words.",
                  span: [0, 2],
                },
              ],
            },
          },
          422,
        ),
      ),
    );
    fireEvent.click(within(openConfirm()).getByRole("button", { name: "Save" }));
    expect(await screen.findByText("expands to too many words.", { exact: false })).toBeTruthy();
  });
});
