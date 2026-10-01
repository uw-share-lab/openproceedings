// @vitest-environment jsdom
import { act, cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { json, renderWithApi, type Handler } from "@/test/api-stub";
import { copy, RECORDS } from "@/test/record-fixture";
import { SaveRecord, SaveRecordProvider, STORE_FULL_KEY, STORE_FULL_MESSAGE } from "./save-record";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: () => {} }), usePathname: () => "/search" }));

beforeEach(() => window.sessionStorage.clear());
afterEach(cleanup);

const C = RECORDS.limits;
const R = C.stored.record;
const PROPS = { q: C.q, mode: C.mode, indexVersion: R.index_version, total: R.total, disabledReason: null };

function SavePage({
  show,
  q = PROPS.q,
  responseDeadlineMs = 1_000,
}: {
  show: boolean;
  q?: string;
  responseDeadlineMs?: number;
}) {
  return (
    <SaveRecordProvider responseDeadlineMs={responseDeadlineMs}>
      {show && <SaveRecord {...PROPS} q={q} />}
    </SaveRecordProvider>
  );
}

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

  it("lets Escape dismiss a pending save, then shows its eventual outcome", async () => {
    let answer: (response: Response) => void = () => {};
    const pending = new Promise<Response>((resolve) => (answer = resolve));
    const { calls } = renderWithApi(<SaveRecord {...PROPS} />, (call) =>
      call.method === "POST" ? pending : api(created())(call),
    );
    const dialog = openConfirm();
    fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0]?.signal.aborted).toBe(false);

    fireEvent.keyDown(dialog, { key: "Escape" });

    expect(calls[0]?.signal.aborted).toBe(false);
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Saving…" }));
    answer(created());
    expect(
      await screen.findByRole("heading", { name: `Saved as search record ${R.record_id}` }),
    ).toBeTruthy();
  });

  it("offers Close while a save is pending without aborting it", async () => {
    let answer: (response: Response) => void = () => {};
    const pending = new Promise<Response>((resolve) => (answer = resolve));
    const { calls } = renderWithApi(<SaveRecord {...PROPS} />, (call) =>
      call.method === "POST" ? pending : api(created())(call),
    );
    const dialog = openConfirm();
    fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(calls).toHaveLength(1));
    const close = within(dialog).getByRole("button", { name: "Close" });

    expect(close.getAttribute("aria-disabled")).toBeNull();
    fireEvent.click(close);

    expect(calls[0]?.signal.aborted).toBe(false);
    expect(screen.queryByRole("dialog")).toBeNull();
    answer(created());
    expect(
      await screen.findByRole("heading", { name: `Saved as search record ${R.record_id}` }),
    ).toBeTruthy();
  });

  it("finishes an irreversible save after unmount without starting its replay read", async () => {
    let answer: (response: Response) => void = () => {};
    const pending = new Promise<Response>((resolve) => (answer = resolve));
    const { calls, unmount } = renderWithApi(<SaveRecord {...PROPS} />, (call) =>
      call.method === "POST" ? pending : api(created())(call),
    );
    const dialog = openConfirm();
    fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(calls).toHaveLength(1));

    unmount();

    expect(calls[0]?.signal.aborted).toBe(false);
    await act(async () => {
      answer(created());
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
    expect(calls).toHaveLength(1);
  });

  it("keeps ownership across a control remount and exposes a late successful save", async () => {
    let answer: (response: Response) => void = () => {};
    const pending = new Promise<Response>((resolve) => (answer = resolve));
    const view = renderWithApi(<SavePage show />, (call) =>
      call.method === "POST" ? pending : api(created())(call),
    );
    fireEvent.click(within(openConfirm()).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(view.calls).toHaveLength(1));

    view.rerender(<SavePage show={false} />);
    await act(async () => {
      answer(created());
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
    expect(view.calls).toHaveLength(1);

    view.rerender(<SavePage show />);
    expect(
      await screen.findByRole("heading", { name: `Saved as search record ${R.record_id}` }),
    ).toBeTruthy();
    await waitFor(() => expect(view.calls).toHaveLength(2));
    expect(view.calls[1]?.method).toBe("GET");
  });

  it("keeps an ambiguous save blocked across a control remount", async () => {
    let fail: (reason: unknown) => void = () => {};
    const pending = new Promise<Response>((_resolve, reject) => (fail = reject));
    const view = renderWithApi(<SavePage show />, (call) =>
      call.method === "POST" ? pending : api(created())(call),
    );
    fireEvent.click(within(openConfirm()).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(view.calls).toHaveLength(1));

    view.rerender(<SavePage show={false} />);
    await act(async () => fail(new TypeError("response lost after commit")));
    view.rerender(<SavePage show />);

    expect((await screen.findByRole("alert")).textContent).toContain("The save outcome is unknown");
    const saveAgain = screen.getByRole("button", { name: "Save search record" });
    expect(saveAgain.getAttribute("aria-disabled")).toBe("true");
    fireEvent.click(saveAgain);
    expect(view.calls).toHaveLength(1);
  });

  it("marks a hung save unknown without aborting it, then reconciles its late success", async () => {
    let answer: (response: Response) => void = () => {};
    const pending = new Promise<Response>((resolve) => (answer = resolve));
    const view = renderWithApi(<SavePage show responseDeadlineMs={10} />, (call) =>
      call.method === "POST" ? pending : api(created())(call),
    );
    fireEvent.click(within(openConfirm()).getByRole("button", { name: "Save" }));

    expect((await screen.findByRole("alert")).textContent).toContain("The save outcome is unknown");
    expect(view.calls[0]?.signal.aborted).toBe(false);
    await act(async () => answer(created()));

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

  it("accepts a valid hand-named index version in RecordCreated", async () => {
    renderWithApi(<SaveRecord {...PROPS} />, api(created({ index_version: "a-b" })));
    fireEvent.click(within(openConfirm()).getByRole("button", { name: "Save" }));
    expect(
      await screen.findByRole("heading", { name: `Saved as search record ${R.record_id}` }),
    ).toBeTruthy();
  });

  it("shows a saved outcome only beside its own request", async () => {
    const view = renderWithApi(<SavePage show q="request B" />, api(created()));
    fireEvent.click(within(openConfirm()).getByRole("button", { name: "Save" }));
    await screen.findByRole("heading", { name: `Saved as search record ${R.record_id}` });

    view.rerender(<SavePage show q="unrelated request C" />);
    expect(screen.queryByRole("heading", { name: `Saved as search record ${R.record_id}` })).toBeNull();

    view.rerender(<SavePage show q="request B" />);
    expect(screen.getByRole("heading", { name: `Saved as search record ${R.record_id}` })).toBeTruthy();
  });

  it("does not let an older replay completion replace a newer saved record", async () => {
    const first = {
      ...C.created,
      record_id: "A23456789012",
      page: "/record/A23456789012",
      index_version: R.index_version,
    };
    const second = {
      ...C.created,
      record_id: "B23456789012",
      page: "/record/B23456789012",
      index_version: R.index_version,
    };
    let finishFirstReplay: (response: Response) => void = () => {};
    const firstReplay = new Promise<Response>((resolve) => (finishFirstReplay = resolve));
    const replayed = copy(C.replayed);
    const view = renderWithApi(<SaveRecord {...PROPS} />, (call) => {
      if (call.method === "POST") {
        const body = call.body as { q: string };
        return json(body.q === C.q ? first : second, 201);
      }
      if (call.path === `/api/v1/records/${first.record_id}`) return firstReplay;
      if (call.path === `/api/v1/records/${second.record_id}`) return json(replayed);
      return api(created())(call);
    });
    fireEvent.click(within(openConfirm()).getByRole("button", { name: "Save" }));
    await screen.findByRole("heading", { name: `Saved as search record ${first.record_id}` });

    view.rerender(<SaveRecord {...PROPS} q="a newer confirmed query" />);
    fireEvent.click(screen.getByRole("button", { name: "Save search record" }));
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Save" }));
    await screen.findByRole("heading", { name: `Saved as search record ${second.record_id}` });
    await act(async () => {
      finishFirstReplay(json(replayed));
      await new Promise((resolve) => setTimeout(resolve, 25));
    });

    expect(screen.getByRole("heading", { name: `Saved as search record ${second.record_id}` })).toBeTruthy();
    expect(screen.queryByRole("heading", { name: `Saved as search record ${first.record_id}` })).toBeNull();
    expect(view.calls.filter((call) => call.method === "POST")).toHaveLength(2);
  });

  it("does not let replay A completion close confirmation B", async () => {
    let finishReplay: (response: Response) => void = () => {};
    const replay = new Promise<Response>((resolve) => (finishReplay = resolve));
    const view = renderWithApi(<SaveRecord {...PROPS} />, (call) => {
      if (call.method === "POST") return created();
      if (call.path === `/api/v1/records/${R.record_id}`) return replay;
      return api(created())(call);
    });
    fireEvent.click(within(openConfirm()).getByRole("button", { name: "Save" }));
    await screen.findByRole("heading", { name: `Saved as search record ${R.record_id}` });

    view.rerender(<SaveRecord {...PROPS} q="confirmation B" />);
    const dialog = openConfirm();
    expect(dialog.textContent).toContain("confirmation B");
    await act(async () => finishReplay(json(C.replayed)));

    expect(screen.getByRole("dialog")).toBe(dialog);
    expect(dialog.textContent).toContain("confirmation B");
  });
});

describe("refused (design S3)", () => {
  it("retries the exact search the user confirmed even after the shown results change", async () => {
    let answer: (response: Response) => void = () => {};
    const pending = new Promise<Response>((resolve) => (answer = resolve));
    let posts = 0;
    const view = renderWithApi(<SaveRecord {...PROPS} />, (call) => {
      if (call.method === "POST") {
        posts += 1;
        return posts === 1
          ? pending
          : json({ error: { code: "API_RATE_LIMITED", message: "still unavailable" } }, 429, {
              "Retry-After": "0",
            });
      }
      return api(created())(call);
    });
    fireEvent.click(within(openConfirm()).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(view.calls).toHaveLength(1));

    view.rerender(
      <SaveRecord
        {...PROPS}
        q="a different shown query"
        mode="scholar"
        indexVersion="0123456789ab"
        total={7}
      />,
    );
    await act(async () =>
      answer(
        json({ error: { code: "API_RATE_LIMITED", message: "unavailable" } }, 429, { "Retry-After": "0" }),
      ),
    );
    expect(screen.queryByRole("button", { name: "Retry" })).toBeNull();
    view.rerender(<SaveRecord {...PROPS} />);
    fireEvent.click(await screen.findByRole("button", { name: "Retry" }));
    await waitFor(() => expect(view.calls).toHaveLength(2));

    expect(view.calls[1]?.body).toEqual({ q: C.q, mode: C.mode, index_version: R.index_version });
  });

  it.each([
    ["lost response", () => Promise.reject(new TypeError("connection dropped after commit"))],
    ["malformed 201", () => new Response("not JSON", { status: 201 })],
    ["empty object", () => json({}, 201)],
    ["null body", () => json(null, 201)],
    ["missing record id", () => json({ page: C.created.page, index_version: R.index_version }, 201)],
    [
      "missing tokenizer version",
      () =>
        json(
          {
            record_id: C.created.record_id,
            page: C.created.page,
            index_version: C.created.index_version,
            query_version: C.created.query_version,
          },
          201,
        ),
    ],
    [
      "missing query version",
      () =>
        json(
          {
            record_id: C.created.record_id,
            page: C.created.page,
            index_version: C.created.index_version,
            tokenizer_version: C.created.tokenizer_version,
          },
          201,
        ),
    ],
    ["API_INTERNAL", () => json({ error: { code: "API_INTERNAL", message: "failed after commit" } }, 500)],
  ])("does not retry an ambiguous committed save (%s)", async (_case, answer) => {
    const committed: string[] = [];
    const { calls } = renderWithApi(<SaveRecord {...PROPS} />, (call) => {
      if (call.method === "POST") {
        committed.push("A23456789012");
        return answer();
      }
      return api(created())(call);
    });
    fireEvent.click(within(openConfirm()).getByRole("button", { name: "Save" }));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("The save outcome is unknown");
    expect(alert.textContent).toContain("this page won't send the same save again");
    expect(screen.queryByRole("button", { name: "Retry" })).toBeNull();
    const saveAgain = screen.getByRole("button", { name: "Save search record" });
    expect(saveAgain.getAttribute("aria-disabled")).toBe("true");
    fireEvent.click(saveAgain);

    expect(committed).toEqual(["A23456789012"]);
    expect(calls.filter((call) => call.method === "POST")).toHaveLength(1);
  });

  it("retries API_INDEX_NOT_LOADED because it is refused before a record can commit", async () => {
    const { calls } = renderWithApi(
      <SaveRecord {...PROPS} />,
      api(json({ error: { code: "API_INDEX_NOT_LOADED", message: "index is loading" } }, 503)),
    );
    fireEvent.click(within(openConfirm()).getByRole("button", { name: "Save" }));
    fireEvent.click(await screen.findByRole("button", { name: "Retry" }));
    await waitFor(() => expect(calls).toHaveLength(2));
  });

  it("shows a refused outcome only beside its own request", async () => {
    const view = renderWithApi(
      <SavePage show q="request B" />,
      api(json({ error: { code: "API_INDEX_NOT_LOADED", message: "index is loading" } }, 503)),
    );
    fireEvent.click(within(openConfirm()).getByRole("button", { name: "Save" }));
    await screen.findByRole("button", { name: "Retry" });

    view.rerender(<SavePage show q="unrelated request C" />);
    expect(screen.queryByRole("button", { name: "Retry" })).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();

    view.rerender(<SavePage show q="request B" />);
    expect(screen.getByRole("button", { name: "Retry" })).toBeTruthy();
  });

  it("keeps the confirmed request when the shown search changes behind its dialog", async () => {
    const { calls, rerender } = renderWithApi(<SaveRecord {...PROPS} />, (call) => {
      if (call.method === "POST") throw new TypeError("response lost after commit");
      return api(created())(call);
    });
    fireEvent.click(within(openConfirm()).getByRole("button", { name: "Save" }));
    await screen.findByRole("alert");

    rerender(<SaveRecord {...PROPS} q="a different safe request" />);
    const dialog = openConfirm();
    rerender(<SaveRecord {...PROPS} />);
    expect(dialog.textContent).toContain("a different safe request");
    fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(calls.filter((call) => call.method === "POST")).toHaveLength(2));

    const bodies = calls.filter((call) => call.method === "POST").map((call) => call.body);
    expect(bodies.filter((body) => (body as { q: string }).q === C.q)).toHaveLength(1);
    expect((bodies[1] as { q: string }).q).toBe("a different safe request");
  });

  it.each([
    [
      "moved index",
      () => json({ error: { code: "API_INDEX_VERSION_UNAVAILABLE", message: "moved" } }, 409),
      "is no longer served here",
    ],
    [
      "invalid query",
      () =>
        json(
          {
            error: {
              code: "WILDCARD_TOO_MANY_EXPANSIONS",
              message: "too many",
              diagnostics: [{ code: "WILDCARD_TOO_MANY_EXPANSIONS", message: "too many", span: [0, 2] }],
            },
          },
          422,
        ),
      "couldn't be saved",
    ],
  ])(
    "retains a late conclusive refusal for its request after save B starts (%s)",
    async (_case, reply, text) => {
      let answer: (response: Response) => void = () => {};
      const pending = new Promise<Response>((resolve) => (answer = resolve));
      const view = renderWithApi(<SavePage show responseDeadlineMs={10} />, (call) => {
        if (call.method === "POST" && (call.body as { q: string }).q === C.q) return pending;
        if (call.method === "POST") {
          return json({ error: { code: "API_INDEX_NOT_LOADED", message: "loading" } }, 503);
        }
        return api(created())(call);
      });
      fireEvent.click(within(openConfirm()).getByRole("button", { name: "Save" }));
      await screen.findByRole("alert");

      view.rerender(<SavePage show q="request B" responseDeadlineMs={10} />);
      fireEvent.click(within(openConfirm()).getByRole("button", { name: "Save" }));
      await screen.findByRole("button", { name: "Retry" });
      await act(async () => answer(reply()));
      view.rerender(<SavePage show responseDeadlineMs={10} />);

      expect(await screen.findByText(text, { exact: false })).toBeTruthy();
      expect(screen.queryByText("The save outcome is unknown.", { exact: false })).toBeNull();
    },
  );

  it("retains late success A after timed-out A is followed by save B", async () => {
    let finishA: (response: Response) => void = () => {};
    const pendingA = new Promise<Response>((resolve) => (finishA = resolve));
    const view = renderWithApi(<SavePage show responseDeadlineMs={10} />, (call) => {
      if (call.method === "POST" && (call.body as { q: string }).q === C.q) return pendingA;
      if (call.method === "POST") {
        return json({ error: { code: "API_INDEX_NOT_LOADED", message: "loading" } }, 503);
      }
      return api(created())(call);
    });
    fireEvent.click(within(openConfirm()).getByRole("button", { name: "Save" }));
    await screen.findByRole("alert");

    view.rerender(<SavePage show q="request B" responseDeadlineMs={10} />);
    fireEvent.click(within(openConfirm()).getByRole("button", { name: "Save" }));
    await screen.findByRole("button", { name: "Retry" });
    await act(async () => finishA(created()));
    view.rerender(<SavePage show responseDeadlineMs={10} />);

    expect(
      await screen.findByRole("heading", { name: `Saved as search record ${R.record_id}` }),
    ).toBeTruthy();
    expect(view.calls.filter((call) => call.method === "POST")).toHaveLength(2);
  });

  it("saves nothing on a moved index (409) and says so", async () => {
    const { calls } = renderWithApi(
      <SaveRecord {...PROPS} />,
      api(json({ error: { code: "API_INDEX_VERSION_UNAVAILABLE", message: "-" } }, 409)),
    );
    fireEvent.click(within(openConfirm()).getByRole("button", { name: "Save" }));
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain(
      `Index ${R.index_version} is no longer served here, so the search wasn't saved: the record would cite ` +
        "a different index from the one whose counts you saw. Search again to see the current results, then save.",
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
