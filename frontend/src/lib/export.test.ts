import { describe, expect, it } from "vitest";
import { createApi } from "@/api/client";
import { json, stubFetch, type Call } from "@/test/api-stub";
import { SEARCHES } from "@/test/record-fixture";
import {
  DEFAULT_STATUSES,
  DEFAULT_TRACKS,
  fetchExport,
  fieldWarning,
  filenameOf,
  warningLine,
  warningText,
  type ExportSource,
} from "./export";
import type { ParsedFilters } from "./search-state";

const SEARCH: ExportSource = {
  kind: "search",
  q: "trust*",
  mode: "native",
  indexVersion: "a1b2c3d4e5f6",
  total: 412,
};
const RECORD: ExportSource = {
  kind: "record",
  recordId: "Ab3dE5fG7hJ9",
  indexVersion: "a1b2c3d4e5f6",
  total: 412,
};

function file(headers: Record<string, string>, body = "TY  - CPAPER\nER  - \n"): Response {
  return new Response(body, {
    status: 200,
    headers: { "Content-Type": "application/x-research-info-systems", ...headers },
  });
}

const good = {
  "X-Index-Version": "a1b2c3d4e5f6",
  "X-Total": "412",
  "Content-Disposition": 'attachment; filename="openproceedings-a1b2c3d4e5f6-0123456789ab.ris"',
};

function run(source: ExportSource, answer: (call: Call) => Response) {
  const { fetch, calls } = stubFetch(answer);
  return { result: fetchExport(createApi("http://api.test", fetch), source, "ris"), calls };
}

describe("fetchExport: pinned to what was shown (design E1)", () => {
  it("pins a search's export to its q, mode and shown index_version", async () => {
    const { result, calls } = run(SEARCH, () => file(good));
    const r = await result;
    expect(r.kind).toBe("ok");
    expect(calls[0]?.path).toBe("/api/v1/export");
    expect(Object.fromEntries(calls[0]?.query ?? [])).toEqual({
      format: "ris",
      q: "trust*",
      mode: "native",
      index_version: "a1b2c3d4e5f6",
    });
    if (r.kind === "ok") {
      expect(r.filename).toBe("openproceedings-a1b2c3d4e5f6-0123456789ab.ris");
      expect(await r.blob.text()).toBe("TY  - CPAPER\nER  - \n");
    }
  });

  it("downloads a file whose abstracts were withheld, and says so (decision-021)", async () => {
    const attributed = await run(SEARCH, () => file({ ...good, "X-Abstract-Source": "attributed" })).result;
    expect(attributed.kind === "ok" && attributed.abstractsWithheld).toBe(false);
    const withheld = await run(RECORD, () => file({ ...good, "X-Abstract-Source": "unavailable" })).result;
    expect(withheld.kind).toBe("ok");
    expect(withheld.kind === "ok" && withheld.abstractsWithheld).toBe(true);
  });

  it("exports a record by its record_id alone: never its q, never a re-run", async () => {
    const { result, calls } = run(RECORD, () => file(good));
    expect((await result).kind).toBe("ok");
    expect(Object.fromEntries(calls[0]?.query ?? [])).toEqual({ format: "ris", record_id: "Ab3dE5fG7hJ9" });
  });

  it("abandons the body when X-Index-Version isn't the shown index", async () => {
    let cancelled = false;
    const body = new ReadableStream({
      cancel() {
        cancelled = true;
      },
    });
    const { result } = run(
      SEARCH,
      () => new Response(body, { headers: { ...good, "X-Index-Version": "9f8e7d6c5b4a" } }),
    );
    expect(await result).toEqual({ kind: "index_changed", shown: "a1b2c3d4e5f6", got: "9f8e7d6c5b4a" });
    expect(cancelled).toBe(true);
  });

  it("calls another count on the same index a bug, not an index change (EX-E3b)", async () => {
    const { result } = run(SEARCH, () => file({ ...good, "X-Total": "411" }));
    expect(await result).toEqual({ kind: "total_differs", shown: 412, got: 411 });
    const missing = run(SEARCH, () => file({ "X-Index-Version": "a1b2c3d4e5f6" }));
    expect(await missing.result).toEqual({ kind: "total_differs", shown: 412, got: null });
  });

  it("reads 409 API_INDEX_VERSION_UNAVAILABLE as the pinned index being gone", async () => {
    const { result } = run(SEARCH, () =>
      json({ error: { code: "API_INDEX_VERSION_UNAVAILABLE", message: "not served" } }, 409),
    );
    expect(await result).toEqual({ kind: "index_unavailable", shown: "a1b2c3d4e5f6" });
  });

  it("keeps a 429's Retry-After, and says when nothing but a proxy answered", async () => {
    const limited = run(SEARCH, () =>
      json({ error: { code: "API_RATE_LIMITED", message: "slow down" } }, 429, { "Retry-After": "7" }),
    );
    expect(await limited.result).toMatchObject({ kind: "refused", status: 429, retryAfter: 7 });
    const proxy = run(SEARCH, () => new Response("<html>502</html>", { status: 502 }));
    expect(await proxy.result).toEqual({ kind: "no_answer", status: 502 });
  });

  it("names the file from Content-Disposition, else from the index", () => {
    expect(filenameOf(null, SEARCH, "bibtex")).toBe("openproceedings-a1b2c3d4e5f6.bib");
    expect(filenameOf('attachment; filename="../x.ris"', SEARCH, "ris")).toBe(
      "openproceedings-a1b2c3d4e5f6.ris",
    );
  });
});

describe("the status and track warnings (design E2; copy EX-E3, EX-E3a), from the API's own answers", () => {
  const filters = (name: keyof typeof SEARCHES) => SEARCHES[name].parse.filters as unknown as ParsedFilters;
  const warn = (name: keyof typeof SEARCHES, field: "status" | "track") =>
    fieldWarning(field, filters(name), SEARCHES[name].parse.defaults, SEARCHES[name].search.facets[field]);

  it("knows the defaults the backend applies", () => {
    expect(DEFAULT_STATUSES).toEqual(["accepted"]);
    expect(DEFAULT_TRACKS).toEqual(["datasets_benchmarks", "main", "position"]);
  });

  it("says nothing while the default filters apply", () => {
    expect(warn("accepted", "status")).toBeNull();
    expect(warn("accepted", "track")).toBeNull();
  });

  it("lists each non-accepted status the clause admits with its facet count, never summed", () => {
    const facets = SEARCHES.statuses.search.facets.status;
    const w = warn("statuses", "status");
    expect(w).toEqual({
      field: "status",
      counts: [
        ["rejected", facets["rejected"]],
        ["withdrawn", facets["withdrawn"]],
      ],
    });
    if (w === null) throw new Error("no warning");
    expect(warningText(w)).toBe(
      `This export includes papers that were not accepted: ${facets["rejected"]} rejected, ${facets["withdrawn"]} ` +
        "withdrawn. Covidence doesn't show a paper's status to screeners (no keywords or notes on the screening " +
        "card), so they can't be told apart there. To screen accepted papers only, keep the default status filter.",
    );
    expect(warningLine(w)).toBe(
      `Includes ${facets["rejected"]} rejected, ${facets["withdrawn"]} withdrawn papers`,
    );
  });

  it("warns without numbers for a negated status clause", () => {
    const w = warn("negated_status", "status");
    expect(w).toEqual({ field: "status", reason: "negated" });
    if (w === null) throw new Error("no warning");
    expect(warningText(w)).toMatch(
      /^This export may include papers that were not accepted \(the query's `status:` clause is negated\)\. /,
    );
  });

  it("lists the tracks outside the default a written track clause admits", () => {
    const facets = SEARCHES.workshop.search.facets.track;
    const w = warn("workshop", "track");
    expect(w).toEqual({ field: "track", counts: [["workshop", facets["workshop"]]] });
    if (w === null) throw new Error("no warning");
    expect(warningText(w)).toBe(
      `This export includes ${facets["workshop"]} workshop papers. Covidence doesn't show a paper's track to ` +
        "screeners, so they can't be told apart there. To screen main-track papers only, keep the default track filter.",
    );
    expect(warn("workshop", "status")).toBeNull(); // status is still the default there
  });

  it("leaves out a value the export holds none of", () => {
    const f = filters("statuses");
    expect(fieldWarning("status", f, ["track"], { accepted: 5, rejected: 0, withdrawn: 2 })).toEqual({
      field: "status",
      counts: [["withdrawn", 2]],
    });
    expect(fieldWarning("status", f, ["track"], { accepted: 5 })).toBeNull();
  });

  it("words a clause written more than once", () => {
    const f = filters("statuses");
    const several = {
      ...f,
      status: {
        ...f.status,
        span: null,
        values: null,
        toggleable: false,
        reason: "multiple_clauses" as const,
      },
    };
    expect(fieldWarning("status", several, [], {})).toEqual({
      field: "status",
      reason: "written more than once",
    });
  });
});
