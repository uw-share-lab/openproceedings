// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createApi } from "@/api/client";
import { CoverageView } from "./coverage-view";
import fixture from "./coverage-fixture.json";

afterEach(cleanup);

function json(status: number, body: unknown, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...headers },
  });
}

function view(fetchImpl: typeof fetch) {
  render(<CoverageView api={createApi("http://api.test", fetchImpl)} />);
}

describe("/coverage's states", () => {
  it("shows a skeleton with no numbers while loading, then the API's report", async () => {
    let answer: (r: Response) => void = () => {};
    const fetchImpl = vi.fn(() => new Promise<Response>((resolve) => (answer = resolve)));
    view(fetchImpl as unknown as typeof fetch);
    expect(screen.getByRole("status").textContent).toBe("Loading coverage");
    expect(document.body.textContent).not.toMatch(/\d/);
    answer(json(200, fixture));
    expect(await screen.findByRole("region", { name: "Coverage table" })).toBeTruthy();
    const request = fetchImpl.mock.calls[0] as unknown as [Request];
    expect(new URL(request[0].url).pathname).toBe("/api/v1/coverage");
  });

  it("shows the API's message for an error envelope, and retries only when asked", async () => {
    const envelope = { error: { code: "API_INDEX_NOT_LOADED", message: "No index is loaded yet." } };
    const fetchImpl = vi
      .fn()
      .mockResolvedValueOnce(json(503, envelope, { "Retry-After": "5" }))
      .mockResolvedValueOnce(json(200, fixture));
    view(fetchImpl as unknown as typeof fetch);
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Search index loading");
    expect(alert.textContent).toContain("No index is loaded yet.");
    expect(alert.textContent).toContain("Retry in 5 s.");
    expect(fetchImpl).toHaveBeenCalledTimes(1); // no automatic retry
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("region", { name: "Coverage table" })).toBeTruthy();
    expect(fetchImpl).toHaveBeenCalledTimes(2);
  });

  it("says when something other than the API answered", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(new Response("<html>Bad gateway</html>", { status: 502 }));
    view(fetchImpl as unknown as typeof fetch);
    expect((await screen.findByRole("alert")).textContent).toContain(
      "The server is busy or restarting (HTTP 502, not from the search service).",
    );
  });

  it("says when the server couldn't be reached", async () => {
    const fetchImpl = vi.fn().mockRejectedValue(new TypeError("Failed to fetch"));
    view(fetchImpl as unknown as typeof fetch);
    expect((await screen.findByRole("alert")).textContent).toContain("Couldn't reach the server");
  });
});
