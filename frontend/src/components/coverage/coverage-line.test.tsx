// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { Schemas } from "@/api/client";
import { json, renderWithApi, type Handler } from "@/test/api-stub";
import { CoverageLine } from "./coverage-line";
import { CoverageReport } from "./coverage-report";
import fixture from "./coverage-fixture.json";

// The API's own answer (backend/tests/contract/coverage_fixture.py; test_frontend_coverage_fixture.py keeps it
// equal to what GET /coverage serves).
const COVERAGE = fixture as unknown as Schemas["CoverageResponse"];

afterEach(cleanup);

const serve =
  (body: unknown): Handler =>
  (call) =>
    call.path === "/api/v1/coverage"
      ? json(body)
      : json({ error: { code: "API_NOT_FOUND", message: "no" } }, 404);

async function line(handler: Handler): Promise<string> {
  renderWithApi(<CoverageLine />, handler);
  return (await screen.findByText(/records indexed/)).textContent ?? "";
}

describe("CoverageLine", () => {
  it("writes the fixture's GET /coverage answer", async () => {
    expect(await line(serve(COVERAGE))).toBe(
      `Index ${COVERAGE.index_version} · 39 records indexed · ICLR 2019–2026, ICML 2019–2026, NeurIPS 2019–2025 · ` +
        "Google Scholar searches run on 2026-09-26 (local time) · Coverage ▸",
    );
    expect(screen.getByRole("link", { name: "Coverage ▸" }).getAttribute("href")).toBe("/coverage");
  });

  it("uses the coverage page's window wording for the same answer", async () => {
    const home = await line(serve(COVERAGE));
    cleanup();
    const window = home.split(" · ")[3]!;
    render(<CoverageReport coverage={COVERAGE} />);
    expect(screen.getByText(/^Built /).textContent).toContain(` · ${window}`);
  });

  it("writes a window's ends in order and the served total, not a sum of venue-years", async () => {
    const data = structuredClone(COVERAGE);
    data.snapshot.crawl_dates["*"] = { from: "2026-09-20T08:14:03Z", to: "2026-09-26T23:59:00Z" };
    data.snapshot.crawl_dates_kind["*"] = "crawl";
    data.totals.records = 1805; // not what venue_years add up to: the line shows the field as served
    expect(await line(serve(data))).toBe(
      `Index ${data.index_version} · 1,805 records indexed · ICLR 2019–2026, ICML 2019–2026, NeurIPS 2019–2025 · ` +
        "Crawled 2026-09-20 to 2026-09-26 · Coverage ▸",
    );
  });

  it("leaves out a missing corpus window", async () => {
    const noWindow = structuredClone(COVERAGE);
    delete noWindow.snapshot.crawl_dates["*"];
    expect(await line(serve(noWindow))).toBe(
      `Index ${noWindow.index_version} · 39 records indexed · ICLR 2019–2026, ICML 2019–2026, NeurIPS 2019–2025 · Coverage ▸`,
    );
  });

  it("claims no numbers while loading", () => {
    const { container } = renderWithApi(<CoverageLine />, () => new Promise<Response>(() => {}));
    expect(container.textContent).toBe("");
  });

  it.each([
    ["a 502", () => new Response("no", { status: 502 })],
    ["a network failure", () => Promise.reject(new TypeError("Failed to fetch"))],
  ])("is left out after %s", async (_name, answer: () => Response | Promise<Response>) => {
    const { container, queryClient } = renderWithApi(<CoverageLine />, answer);
    // settled: the query has its answer (null for a non-2xx) or its error, and nothing is in flight
    await expect
      .poll(() => {
        const state = queryClient.getQueryState(["coverage"]);
        return state !== undefined && state.status !== "pending" && state.fetchStatus === "idle";
      })
      .toBe(true);
    expect(container.textContent).toBe("");
  });
});
