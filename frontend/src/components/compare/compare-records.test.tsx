// @vitest-environment jsdom
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Schemas } from "@/api/client";
import { json, META, renderWithApi, type Handler } from "@/test/api-stub";
import { RIS_MEDIA } from "@/lib/compare";
import { COMPARE as fixture } from "@/test/compare-fixture";
import { CompareRecords, ROWS_SHOWN, type CompareRecordsProps } from "./compare-records";

const R = fixture.response;
const LIMITS = fixture.limits.compare;
const META_ON: Schemas["MetaResponse"] = { ...META, limits: { ...META.limits, compare: LIMITS } };
const PROPS: CompareRecordsProps = {
  q: fixture.q,
  mode: "native",
  indexVersion: R.index_version,
  total: R.total,
  disabledReason: null,
};

let saved: { blob: Blob; name: string }[] = [];
beforeEach(() => {
  saved = [];
  let last: Blob | null = null;
  URL.createObjectURL = vi.fn((blob: Blob) => {
    last = blob;
    return "blob:test";
  });
  URL.revokeObjectURL = vi.fn();
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
    if (last !== null) saved.push({ blob: last, name: this.download });
  });
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function serve(compare: Handler = () => json(R), meta: Schemas["MetaResponse"] = META_ON): Handler {
  return (call) => {
    if (call.path === "/api/v1/meta") return json(meta);
    if (call.path === "/api/v1/compare") return compare(call);
    throw new Error(`unexpected call ${call.method} ${call.path}`);
  };
}

function ris(name = "my-records.ris", text: string = fixture.file): File {
  return new File([text], name, { type: "" });
}

async function draw(handler: Handler = serve(), over: Partial<CompareRecordsProps> = {}) {
  const r = renderWithApi(
    <div>
      <CompareRecords {...PROPS} {...over} />
    </div>,
    handler,
  );
  const trigger = await screen.findByRole("button", { name: /Compare with your records/ });
  return { ...r, trigger };
}

/** The panel's live region: outside the panel, so an answer is announced even while it is closed. */
function announced(): HTMLElement {
  const panel = screen.getByRole("region", { name: "Compare with your records" });
  const own = screen.getAllByRole("status", { hidden: true }).find((el) => !panel.contains(el));
  if (own === undefined) throw new Error("no live region beside the panel");
  return own;
}

async function compareWith(file: File = ris()) {
  fireEvent.click(screen.getByRole("button", { name: /Compare with your records/ }));
  fireEvent.change(screen.getByLabelText("RIS file"), { target: { files: [file] } });
  fireEvent.click(screen.getByRole("button", { name: "Compare" }));
}

describe("CompareRecords", () => {
  it("is not offered when the instance doesn't do comparisons", async () => {
    const r = renderWithApi(<CompareRecords {...PROPS} />, serve(undefined, META));
    await waitFor(() => expect(r.calls.some((c) => c.path === "/api/v1/meta")).toBe(true));
    await waitFor(() => expect(r.queryClient.isFetching()).toBe(0));
    expect(screen.queryByRole("button", { name: /Compare with your records/ })).toBeNull();
    expect(r.container.textContent).toBe("");
  });

  it("opens a panel that says what happens to the file and what it may hold", async () => {
    const { trigger } = await draw();
    expect(trigger.getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(trigger);
    expect(trigger.getAttribute("aria-expanded")).toBe("true");
    const panel = screen.getByRole("region", { name: "Compare with your records" });
    expect(panel.textContent).toContain("It is not stored, not logged and not added to the index.");
    expect(panel.textContent).toContain("Up to 16.0 MB and 5,000 records");
    const input = within(panel).getByLabelText("RIS file");
    expect(input.getAttribute("type")).toBe("file");
    expect(input.getAttribute("aria-describedby")).toBeTruthy();
    // nothing can be compared before a file is chosen, and the button says why, visibly and to assistive
    // technology (A11Y-S5)
    const compare = within(panel).getByRole("button", { name: "Compare" });
    expect(compare.getAttribute("aria-disabled")).toBe("true");
    expect(document.getElementById(compare.getAttribute("aria-describedby") ?? "")?.textContent).toBe(
      "Choose a RIS file first.",
    );
    expect(panel.textContent).toContain("sent to this instance");
  });

  it("sends the chosen file for the searched query and shows the counts first", async () => {
    const { calls } = await draw();
    await compareWith();
    const table = await screen.findByRole("table", { name: /What this search does/ });
    const call = calls.find((c) => c.path === "/api/v1/compare");
    expect(call?.contentType).toBe(RIS_MEDIA);
    expect(call?.body).toBe(fixture.file);
    expect(call?.query.get("q")).toBe(fixture.q);
    expect(call?.query.get("mode")).toBe("native");
    expect(JSON.stringify([...(call?.query.entries() ?? [])])).not.toContain("my-records"); // never the name
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows.map((row) => within(row).getByRole("cell").textContent)).toEqual(
      [R.kept_total, R.dropped_total, R.not_in_index_total, R.added_total].map(String),
    );
    expect(rows.map((row) => within(row).getByRole("rowheader").firstElementChild?.textContent)).toEqual([
      "Kept",
      "Dropped",
      "Not in the index",
      "Added",
    ]);
    // the lists are on demand: no row of any list is drawn yet
    expect(screen.queryByText(R.dropped[0]?.title ?? "")).toBeNull();
    expect(screen.getByRole("heading", { name: /Comparison with my-records\.ris/ })).toBe(
      document.activeElement,
    );
    const panel = screen.getByRole("region", { name: "Compare with your records" });
    expect(panel.textContent).toContain(`${R.records_total} records read, ${R.papers_total} papers compared`);
    expect(panel.textContent).toContain(`${R.not_compared_total} record from other venues`);
    expect(panel.textContent).toContain(`${R.duplicates_total} record that repeats a paper already counted`);
    expect(panel.textContent).toContain("What “dropped” means.");
    expect(panel.textContent).toContain("A dropped paper is not judged irrelevant");
    expect(announced().textContent).toBe(
      `Comparison done: ${R.kept_total} kept, ${R.dropped_total} dropped, ${R.not_in_index_total} not in the index, ${R.added_total} added.`,
    );
    expect(panel.contains(announced())).toBe(false);
  });

  it("says why papers were dropped, with the server's counts, and lists them on demand", async () => {
    await draw();
    await compareWith();
    const dropped = await screen.findByRole("region", { name: `${R.dropped_total} dropped papers` });
    // each reason's count with what to do about it (USAB-S3)
    expect([...dropped.querySelectorAll(":scope > p")].map((p) => p.textContent)).toEqual([
      expect.stringMatching(/^2 papers are excluded by a default filter: to include such a paper/),
      expect.stringMatching(
        /^2 papers match only as another word form: type \* after its stem \(e\.g\. evaluat\*\)/,
      ),
      expect.stringMatching(
        /^2 papers have no exact match in their title or abstract: no form of this query/,
      ),
    ]);
    // one name whatever its state: `aria-expanded` says whether it is open (A11Y-N10)
    const show = within(dropped).getByRole("button", { name: `List the ${R.dropped_total} dropped papers` });
    expect(show.getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(show);
    expect(show.getAttribute("aria-expanded")).toBe("true");
    const items = [...dropped.querySelectorAll<HTMLElement>("ol > li")];
    // each title opens its paper in a new tab, and says so (the comparison lives on this page only)
    expect(items.map((li) => within(li).getByRole("link").textContent)).toEqual(
      R.dropped.map((r) => `${r.title} ↗ (opens in a new tab)`),
    );
    expect(
      within(items[0] as HTMLElement)
        .getByRole("link")
        .getAttribute("target"),
    ).toBe("_blank");
    const first = R.dropped[0];
    expect(items[0]?.textContent).toContain(`record ${first?.ris_record} of your file`);
    expect(items[0]?.textContent).toContain(`excluded by a default filter — ${first?.detail}`);
    expect(
      within(items[0] as HTMLElement)
        .getByRole("link")
        .getAttribute("href"),
    ).toBe(`/paper/${encodeURIComponent(first?.id ?? "")}?q=${encodeURIComponent(fixture.q)}&mode=native`);
    fireEvent.click(show);
    expect(show.getAttribute("aria-expanded")).toBe("false");
    expect(dropped.querySelector("ol")).toBeNull();
  });

  it("shows how kept records matched, repeats, and which rest on an import only", async () => {
    await draw();
    await compareWith();
    const kept = await screen.findByRole("region", { name: `${R.kept_total} kept papers` });
    fireEvent.click(within(kept).getByRole("button", { name: /^List the/ }));
    const items = within(kept).getAllByRole("listitem");
    expect(items[0]?.textContent).toContain("matched by its OpenReview link");
    expect(items[1]?.textContent).toContain("matched by title, venue and year");
    expect(items[1]?.textContent).toContain("2 times in your file");
    const importOnly = R.kept.map((r) => r.independent === false);
    expect(items.map((li) => li.textContent?.includes("import only"))).toEqual(importOnly);
    expect(importOnly).toContain(true);
    const panel = screen.getByRole("region", { name: "Compare with your records" });
    expect(panel.textContent).toContain(
      `${R.kept_ris_only_total} of the ${R.kept_total} kept and ${R.dropped_ris_only_total} of the ${R.dropped_total} dropped papers are in this index only because a RIS file was imported into it`,
    );
  });

  it("lists papers the index doesn't hold without a link, and the records it left out", async () => {
    await draw();
    await compareWith();
    const gaps = await screen.findByRole("region", {
      name: `${R.not_in_index_total} paper not in the index`,
    });
    fireEvent.click(within(gaps).getByRole("button", { name: /^List the/ }));
    const item = gaps.querySelector("ol li") as HTMLElement;
    expect(within(item).queryByRole("link")).toBeNull();
    expect(item.textContent).toContain(R.not_in_index[0]?.title);
    expect(item.textContent).toContain("no record with this title in that venue and year");
    // what is to be decided is named (UX-S4), and the match line is not said twice (USAB-N3)
    expect(item.textContent).toContain("to check: is it in the index under another title, venue or year?");
    expect(item.textContent).not.toContain("no forum id, proceedings id");
    const out = screen.getByRole("region", { name: `Not compared, ${R.not_compared_total} record` });
    fireEvent.click(within(out).getByRole("button", { name: /^List the/ }));
    expect(within(out).getByRole("listitem").textContent).toContain("its venue is not NeurIPS, ICLR or ICML");
  });

  it("saves each list as the server's own text", async () => {
    await draw();
    await compareWith();
    const added = await screen.findByRole("region", { name: `${R.added_total} added papers` });
    fireEvent.click(
      within(added).getByRole("button", { name: `Download RIS of the ${R.added_total} added papers` }),
    );
    fireEvent.click(
      within(added).getByRole("button", { name: `Download CSV of the ${R.added_total} added papers` }),
    );
    const dropped = screen.getByRole("region", { name: `${R.dropped_total} dropped papers` });
    fireEvent.click(within(dropped).getByRole("button", { name: /^Download CSV/ }));
    expect(within(dropped).queryByRole("button", { name: /^Download RIS/ })).toBeNull(); // RIS is the added list's
    const hash = R.query.canonical_hash.slice(0, 12);
    expect(saved.map((s) => s.name)).toEqual([
      `openproceedings-${R.index_version}-${hash}-added.ris`,
      `openproceedings-${R.index_version}-${hash}-added.csv`,
      `openproceedings-${R.index_version}-${hash}-dropped.csv`,
    ]);
    // `Blob.text()` drops a leading BOM when it decodes, so compare the bytes: the BOM is saved as sent
    const bytes = async (b: Blob) => [...new Uint8Array(await b.arrayBuffer())];
    const utf8 = (text: string) => [...new TextEncoder().encode(text)];
    expect(await bytes(saved[0]?.blob as Blob)).toEqual(utf8(R.added_ris));
    expect(await bytes(saved[1]?.blob as Blob)).toEqual(utf8(R.csv.added));
    expect(await bytes(saved[2]?.blob as Blob)).toEqual(utf8(R.csv.dropped));
    expect(R.csv.added.charCodeAt(0)).toBe(0xfeff);
  });

  it("draws a long list a hundred rows at a time", async () => {
    const many = Array.from({ length: ROWS_SHOWN * 2 + 5 }, (_, i) => ({
      ...(R.added[0] as (typeof R.added)[number]),
      id: `op:iclr:2021:X${i}`,
      title: `paper ${i}`,
    }));
    const big = { ...R, added: many, added_total: many.length, total: R.kept_total + many.length };
    await draw(
      serve(() => json(big)),
      { total: big.total },
    );
    await compareWith();
    const added = await screen.findByRole("region", { name: `${many.length} added papers` });
    fireEvent.click(within(added).getByRole("button", { name: /^List the/ }));
    const rows = () => added.querySelectorAll("ol > li");
    expect(rows()).toHaveLength(ROWS_SHOWN);
    fireEvent.click(within(added).getByRole("button", { name: `Show more (100 of ${many.length} shown)` }));
    expect(rows()).toHaveLength(ROWS_SHOWN * 2);
    await waitFor(() => expect(document.activeElement).toBe(rows()[ROWS_SHOWN])); // the first row it drew
    fireEvent.click(within(added).getByRole("button", { name: /^Show more/ }));
    expect(rows()).toHaveLength(many.length);
    await waitFor(() => expect(document.activeElement).toBe(rows()[ROWS_SHOWN * 2]));
    expect(within(added).queryByRole("button", { name: /^Show more/ })).toBeNull();
  });

  it("refuses a file over the instance's cap without sending it", async () => {
    const { calls } = await draw(serve(), {});
    const big = ris("big.ris");
    Object.defineProperty(big, "size", { value: LIMITS.max_body_bytes + 1 });
    await compareWith(big);
    expect(screen.getByRole("alert").textContent).toMatch(
      /^This file is 16\.0 MB; this instance compares files up to/,
    );
    expect(calls.filter((c) => c.path === "/api/v1/compare")).toEqual([]);
    expect(screen.getByLabelText("RIS file").getAttribute("aria-invalid")).toBe("true");
  });

  it("shows the server's refusal of a file, and asks for another file instead of a Retry", async () => {
    await draw(serve(() => json(fixture.invalid, 422)));
    await compareWith();
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("API_RIS_INVALID");
    expect(alert.textContent).toContain(fixture.invalid.error.message);
    // the same file would be refused again (USAB-N1)
    expect(within(alert).queryByRole("button", { name: "Retry" })).toBeNull();
    const panel = screen.getByRole("region", { name: "Compare with your records" });
    expect(panel.textContent).toContain("The comparison didn't run. Nothing was compared.");
    expect(panel.textContent).toContain("Choose another file, then Compare.");
    expect(screen.getByLabelText("RIS file").getAttribute("aria-invalid")).toBe("true");
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("retries a busy server by itself when its Retry-After is up", async () => {
    let asked = 0;
    const busy = {
      error: {
        code: "API_BUSY",
        message:
          "This index was loaded a moment ago and its comparison table is still being prepared. Try again in 0 s.",
      },
    };
    await draw(
      serve(() => {
        asked += 1;
        return asked === 1 ? json(busy, 503, { "Retry-After": "0" }) : json(R);
      }),
    );
    await compareWith();
    await screen.findByRole("table", { name: /What this search does/ }); // no button pressed (USAB-S8)
    expect(asked).toBe(2);
  });

  it("announces a busy wait once, politely, and never says it didn't run while a retry is to come", async () => {
    let asked = 0;
    const busy = {
      error: {
        code: "API_BUSY",
        message: "This instance is running as many comparisons as it can. Try again in 1 s.",
      },
    };
    await draw(
      serve(() => {
        asked += 1;
        return asked === 1 ? json(busy, 503, { "Retry-After": "1" }) : json(R);
      }),
    );
    await compareWith();
    const panel = screen.getByRole("region", { name: "Compare with your records" });
    await waitFor(() => expect(announced().textContent).toBe("Busy; retrying by itself in 1 s."));
    expect(screen.queryByRole("alert")).toBeNull(); // no alert per busy cycle (A11Y-R2-2)
    expect(within(panel).queryAllByRole("status")).toEqual([]); // and no second live region in the panel
    expect(panel.textContent).toContain("Busy; retrying by itself in 1 s");
    expect(panel.textContent).toContain("as many comparisons as it can.");
    expect(panel.textContent).not.toContain("Try again in"); // the countdown says when, once
    expect(panel.textContent).not.toContain("didn't run");
    const heard: string[] = [];
    const watcher = new MutationObserver(() => heard.push(announced().textContent ?? ""));
    watcher.observe(announced(), { childList: true, characterData: true, subtree: true });
    await screen.findByRole("table", { name: /What this search does/ }, { timeout: 3000 });
    watcher.disconnect();
    expect(asked).toBe(2);
    expect(heard.filter((x) => x.startsWith("Comparing"))).toEqual([]); // the retry isn't "Comparing…" again
  });

  it("announces a press of Retry after a deadline, as any comparison it starts", async () => {
    let asked = 0;
    const deadline = {
      error: { code: "API_BUSY", message: "This comparison ran past the 60 s this instance gives one." },
    };
    await draw(
      serve(() => {
        asked += 1;
        return asked === 1 ? json(deadline, 503) : json(R); // no Retry-After: nothing retries it by itself
      }),
    );
    await compareWith();
    const alert = await screen.findByRole("alert");
    await waitFor(() => expect(announced().textContent).toBe("The comparison didn't run."));
    const heard: string[] = [];
    const watcher = new MutationObserver(() => heard.push(announced().textContent ?? ""));
    watcher.observe(announced(), { childList: true, characterData: true, subtree: true });
    fireEvent.click(within(alert).getByRole("button", { name: "Retry" }));
    await screen.findByRole("table", { name: /What this search does/ });
    watcher.disconnect();
    expect(asked).toBe(2);
    expect(heard).toContain("Comparing my-records.ris with this search.");
  });

  it("keeps the count of retries by itself across a press of Retry, neither using one up nor starting over", async () => {
    let asked = 0;
    const busy = { error: { code: "API_BUSY", message: "Busy. Try again in 0 s." } };
    const deadline = { error: { code: "API_BUSY", message: "This comparison ran past its time." } };
    await draw(
      serve(() => {
        asked += 1;
        // a busy answer (one retry by itself), a deadline that asks for a press, then busy from then on
        return asked === 2 ? json(deadline, 503) : json(busy, 503, { "Retry-After": "0" });
      }),
    );
    await compareWith();
    const alert = await screen.findByRole("alert");
    expect(asked).toBe(2);
    fireEvent.click(within(alert).getByRole("button", { name: "Retry" }));
    // 1 retry by itself was used before the press, so 2 are left after it: asked 3 (the press), 4 and 5
    await waitFor(() => expect(announced().textContent).toBe("The comparison didn't run."), {
      timeout: 3000,
    });
    // no retry by itself is left pending, so no sixth request can follow
    expect(screen.queryByText(/retrying by itself/i)).toBeNull();
    expect(asked).toBe(5);
  });

  it("leaves focus where the reader went while a retry by itself was pending", async () => {
    let asked = 0;
    const busy = { error: { code: "API_BUSY", message: "Busy. Try again in 1 s." } };
    await draw(
      serve(() => {
        asked += 1;
        return asked === 1 ? json(busy, 503, { "Retry-After": "1" }) : json(R);
      }),
    );
    await compareWith();
    await waitFor(() => expect(announced().textContent).toContain("retrying by itself"));
    const input = screen.getByLabelText("RIS file");
    input.focus(); // the reader moved on while it waited (A11Y-R2-1)
    await screen.findByRole("table", { name: /What this search does/ }, { timeout: 3000 });
    expect(document.activeElement).toBe(input);
  });

  it("sends nothing from Compare during the pause, though a click lands on it", async () => {
    const { calls } = await draw(serve(() => json({ ...R, next_comparison_seconds: 54 })));
    await compareWith();
    await screen.findByRole("table", { name: /What this search does/ });
    const before = calls.filter((c) => c.path === "/api/v1/compare").length;
    const compare = screen.getByRole("button", { name: "Compare" });
    fireEvent.click(compare); // aria-disabled, not disabled: the click still reaches it (USAB-R2-2)
    fireEvent.keyDown(compare, { key: "Enter" });
    expect(screen.getByRole("region", { name: "Compare with your records" }).textContent).not.toContain(
      "Comparing my-records.ris",
    );
    await new Promise((resolve) => setTimeout(resolve, 50)); // the file is read before it is sent
    expect(calls.filter((c) => c.path === "/api/v1/compare").length).toBe(before);
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("counts down a rate limit's Retry-After, then compares again on Retry", async () => {
    let asked = 0;
    const limited = {
      error: { code: "API_RATE_LIMITED", message: "Too many requests; try again in 1 s." },
    };
    await draw(
      serve(() => {
        asked += 1;
        return asked === 1 ? json(limited, 429, { "Retry-After": "0" }) : json(R);
      }),
    );
    await compareWith();
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Too many requests");
    fireEvent.click(within(alert).getByRole("button", { name: "Retry" }));
    await screen.findByRole("table", { name: /What this search does/ });
    expect(asked).toBe(2);
  });

  it("labels an earlier answer as the earlier file's when a new comparison is refused", async () => {
    let asked = 0;
    const busy = {
      error: {
        code: "API_BUSY",
        message: "This instance is running as many comparisons as it can. Try again in 5 s.",
      },
    };
    await draw(
      serve(() => {
        asked += 1;
        return asked === 1 ? json(R) : json(busy, 503, { "Retry-After": "5" });
      }),
    );
    await compareWith(ris("first.ris"));
    await screen.findByRole("table", { name: /What this search does/ });
    fireEvent.change(screen.getByLabelText("RIS file"), { target: { files: [ris("second.ris")] } });
    fireEvent.click(screen.getByRole("button", { name: "Compare" }));
    const panel = screen.getByRole("region", { name: "Compare with your records" });
    await waitFor(() =>
      expect(panel.textContent).toContain(
        "The new comparison hasn't run yet: this instance is busy; this page will try again by itself. The " +
          "results below are from the earlier comparison with first.ris.",
      ),
    );
    expect(panel.textContent).not.toContain("Nothing was compared");
    // the earlier answer is still there, under its own file's name
    expect(screen.getByRole("heading", { name: "Comparison with first.ris" })).toBeTruthy();
    expect(screen.getByRole("table", { name: /What this search does/ })).toBeTruthy();
  });

  it("says how long a cooling-down network waits, and that searching still works", async () => {
    const cooling = {
      error: {
        code: "API_RATE_LIMITED",
        message:
          "One comparison at a time from this network, with a pause after each in proportion to how long it ran (searching is not affected); try again in 54 s.",
      },
    };
    await draw(serve(() => json(cooling, 429, { "Retry-After": "54" })));
    await compareWith();
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("try again in 54 s.");
    expect(alert.textContent).toContain("Retry in 54 s");
    expect(within(alert).getByRole("button", { name: "Retry" }).getAttribute("aria-disabled")).toBe("true");
    // the server's message says searching is not affected; the panel adds no claim of its own (UX-S1)
    const panel = screen.getByRole("region", { name: "Compare with your records" });
    expect(panel.textContent).not.toContain("you can keep searching while you wait");
  });

  it("says when the next comparison may start, beside Compare", async () => {
    await draw(serve(() => json({ ...R, next_comparison_seconds: 54 })));
    await compareWith();
    await screen.findByRole("table", { name: /What this search does/ });
    const compare = screen.getByRole("button", { name: "Compare" });
    expect(compare.getAttribute("aria-disabled")).toBe("true");
    expect(document.getElementById(compare.getAttribute("aria-describedby") ?? "")?.textContent).toMatch(
      /^Next comparison in 5[34] s: this instance pauses between one network's comparisons\.$/,
    );
  });

  it("has no pause to show when the instance has none", async () => {
    await draw(serve(() => json({ ...R, next_comparison_seconds: 0 })));
    await compareWith();
    await screen.findByRole("table", { name: /What this search does/ });
    expect(screen.getByRole("button", { name: "Compare" }).getAttribute("aria-disabled")).toBeNull();
  });

  /** The citable sentence's figure (named by its figcaption) and its read-only text box. */
  async function citable() {
    const caption = await screen.findByText(/^This comparison in one sentence, to cite/);
    const figure = caption.closest("figure");
    if (figure === null) throw new Error("the sentence's caption is not in a figure");
    expect(figure.hasAttribute("aria-labelledby")).toBe(false); // the figcaption names it
    const box = within(figure).getByRole("textbox", { name: /This comparison in one sentence, to cite/ });
    if (!(box instanceof HTMLTextAreaElement)) throw new Error("the sentence is not in a textarea");
    return { figure, box };
  }

  it("gives the comparison as one citable sentence, shown and copied, with the file's sha256", async () => {
    const writeText = vi.fn(() => Promise.resolve());
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    const bytes = new TextEncoder().encode(fixture.file);
    const sha = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)), (b) =>
      b.toString(16).padStart(2, "0"),
    ).join("");
    const { calls } = await draw();
    await compareWith();
    await screen.findByRole("table", { name: /What this search does/ });
    const { figure, box } = await citable();
    const shown = box.value;
    expect(box.readOnly).toBe(true);
    expect(box.tabIndex).toBe(0); // reachable from the keyboard, so the text can be selected there (WCAG 2.1.1)
    expect(shown).toContain(`RIS file my-records.ris (sha256 \`${sha}\`;`);
    expect(shown).toContain(`(index \`${R.index_version}\`)`);
    expect(shown).toContain(`(canonical_hash \`${R.query.canonical_hash}\`)`);
    expect(shown).toMatch(
      /^As a search-development check \(not a PRISMA flow-diagram count\), on \d{4}-\d{2}-\d{2} \(UTC\)/,
    );
    // the digest is this browser's: the request is the file and the query, nothing about its hash
    const sent = calls.find((c) => c.path === "/api/v1/compare");
    expect(sent?.body).toBe(fixture.file);
    expect([...(sent?.query.keys() ?? [])].sort()).toEqual(["mode", "q"]);
    // a native button, reached and pressed from the keyboard like any other, and announced
    const copy = within(figure).getByRole("button", { name: "Copy this comparison as one sentence" });
    copy.focus();
    expect(document.activeElement).toBe(copy);
    fireEvent.click(copy);
    expect(writeText).toHaveBeenCalledWith(shown);
    await waitFor(() => expect(within(figure).getByRole("status").textContent).toBe("Copied"));
  });

  it.each([
    ["there is no Clipboard API", undefined],
    ["the clipboard refuses the write", { writeText: () => Promise.reject(new Error("denied")) }],
  ])("selects the sentence for the keyboard where %s", async (_, value) => {
    Object.defineProperty(navigator, "clipboard", { value, configurable: true });
    await draw();
    await compareWith();
    const { figure, box } = await citable();
    fireEvent.click(within(figure).getByRole("button", { name: "Copy this comparison as one sentence" }));
    await waitFor(() => expect(document.activeElement).toBe(box));
    expect([box.selectionStart, box.selectionEnd]).toEqual([0, box.value.length]);
    await waitFor(() =>
      expect(within(figure).getByRole("status").textContent).toBe(
        "Couldn't copy: the text is selected; copy it with Ctrl+C (⌘C on a Mac)",
      ),
    );
  });

  it("is off, with the reason, while the results shown aren't the searched query's", async () => {
    const reason =
      "The results shown are from an earlier query — search again or restore it before exporting.";
    const { calls } = await draw(serve(), { disabledReason: reason });
    await compareWith();
    const compare = screen.getByRole("button", { name: "Compare" });
    expect(compare.getAttribute("aria-disabled")).toBe("true");
    expect(document.getElementById(compare.getAttribute("aria-describedby") ?? "")?.textContent).toBe(reason);
    expect(calls.filter((c) => c.path === "/api/v1/compare")).toEqual([]);
  });

  it("never shows a comparison of another query as the current one", async () => {
    const { rerender } = await draw();
    await compareWith();
    await screen.findByRole("table", { name: /What this search does/ });
    rerender(
      <div>
        <CompareRecords {...PROPS} q="another query" />
      </div>,
    );
    expect(screen.queryByRole("table")).toBeNull();
    expect(screen.getByRole("region", { name: "Compare with your records" }).textContent).toContain(
      "The search changed since the last comparison",
    );
    // the file is still chosen: one click compares the new query with it
    expect(screen.getByRole("button", { name: "Compare" }).getAttribute("aria-disabled")).toBeNull();
  });

  it("does not show numbers from another index, or a total that isn't the search's", async () => {
    await draw(serve(() => json({ ...R, index_version: "ffffffffffff" })));
    await compareWith();
    const moved = await screen.findByRole("alert");
    expect(moved.textContent).toContain("The index changed after this search");
    expect(within(moved).queryByRole("button", { name: "Search again" })).toBeNull(); // none offered here
    expect(screen.queryByRole("table")).toBeNull();
    cleanup();
    const onSearchAgain = vi.fn();
    await draw(
      serve(() => json({ ...R, index_version: "ffffffffffff" })),
      { onSearchAgain },
    );
    await compareWith();
    fireEvent.click(within(await screen.findByRole("alert")).getByRole("button", { name: "Search again" }));
    expect(onSearchAgain).toHaveBeenCalledOnce(); // as the export's notice offers (UX-S5)
    cleanup();
    await draw(serve(() => json({ ...R, total: R.total + 1 })));
    await compareWith();
    const bug = await screen.findByRole("alert");
    expect(bug.textContent).toContain("it is a bug in openproceedings");
    expect(within(bug).getByRole("link", { name: /Report it/ })).toBeTruthy();
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("can be cancelled while it runs", async () => {
    let release: (r: Response) => void = () => {};
    await draw(serve(() => new Promise<Response>((resolve) => (release = resolve))));
    await compareWith();
    const panel = screen.getByRole("region", { name: "Compare with your records" });
    await waitFor(() => expect(panel.textContent).toContain("Comparing my-records.ris"));
    expect(panel.textContent).toContain("can take up to 60 s.");
    expect(panel.textContent).toMatch(/\d+ s so far\./); // a counter, not a static sentence (USAB-S8)
    fireEvent.click(within(panel).getByRole("button", { name: "Cancel" }));
    release(json(R));
    await waitFor(() => expect(announced().textContent).toBe("Comparison cancelled."));
    expect(screen.queryByRole("table")).toBeNull();
    expect(panel.textContent).not.toContain("didn't run");
  });
});
