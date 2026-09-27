import { describe, expect, it } from "vitest";
import { createApi } from "@/api/client";
import { json, parsed, stubFetch, type Handler } from "@/test/api-stub";
import { isErrorEnvelope, postParse } from "./parse";

const call = (handler: Handler, signal?: AbortSignal) => {
  const { fetch, calls } = stubFetch(handler);
  return { run: postParse(createApi("http://api.test", fetch), "trust*", "scholar", signal), calls };
};

describe("postParse", () => {
  it("POSTs {q, mode} and keys the answer by them", async () => {
    const { run, calls } = call(() => json(parsed("trust*")));
    const outcome = await run;
    expect(calls[0]?.method).toBe("POST");
    expect(calls[0]?.path).toBe("/api/v1/parse");
    expect(calls[0]?.body).toEqual({ q: "trust*", mode: "scholar" });
    expect(outcome).toMatchObject({ kind: "parsed", q: "trust*", mode: "scholar" });
  });

  it("413 API_BODY_TOO_LARGE is too_large, with the server's message", async () => {
    const message = "The request body is over 65,536 bytes; a query fits in far less.";
    const outcome = await call(() => json({ error: { code: "API_BODY_TOO_LARGE", message } }, 413)).run;
    expect(outcome).toEqual({ q: "trust*", mode: "scholar", kind: "too_large", message });
  });

  it("429 carries its envelope and Retry-After", async () => {
    const error = { code: "API_RATE_LIMITED", message: "Too many requests; try again in 12 s." };
    const outcome = await call(() => json({ error }, 429, { "Retry-After": "12" })).run;
    expect(outcome).toEqual({
      q: "trust*",
      mode: "scholar",
      kind: "refused",
      status: 429,
      error,
      retryAfter: 12,
    });
  });

  it("503 API_BUSY without a usable Retry-After has none", async () => {
    const error = { code: "API_BUSY", message: "busy" };
    const outcome = await call(() => json({ error }, 503, { "Retry-After": "soon" })).run;
    expect(outcome).toMatchObject({ kind: "refused", status: 503, retryAfter: null });
  });

  it("a body that isn't JSON (a proxy's 502, uvicorn's plain 503) is no_answer, with the status", async () => {
    const outcome = await call(() => new Response("Service Unavailable", { status: 503 })).run;
    expect(outcome).toEqual({ q: "trust*", mode: "scholar", kind: "no_answer", status: 503 });
  });

  it("JSON that isn't the envelope is no_answer too", async () => {
    const outcome = await call(() => json({ detail: "Not Found" }, 404)).run;
    expect(outcome).toMatchObject({ kind: "no_answer", status: 404 });
  });

  it("a fetch that rejects is unreachable", async () => {
    const outcome = await call(() => Promise.reject(new TypeError("Failed to fetch"))).run;
    expect(outcome).toEqual({ q: "trust*", mode: "scholar", kind: "unreachable" });
  });

  it("an aborted request is thrown, so no outcome is stored for a draft that moved on", async () => {
    const controller = new AbortController();
    const { run } = call(() => new Promise<Response>(() => {}), controller.signal);
    controller.abort();
    await expect(run).rejects.toThrow();
  });
});

describe("isErrorEnvelope", () => {
  it.each([
    [{ error: { code: "X", message: "m" } }, true],
    [{ error: { code: "X" } }, false],
    [{ error: "x" }, false],
    ["<html>", false],
    [null, false],
  ])("%j → %s", (body, ok) => {
    expect(isErrorEnvelope(body)).toBe(ok);
  });
});
