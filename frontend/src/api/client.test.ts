import { describe, expect, it } from "vitest";
import { createApi, hitHighlightsUtf16, type Schemas } from "./client";

function answering(status: number, body: unknown, seen: Request[] = []): typeof fetch {
  return async (input) => {
    if (input instanceof Request) seen.push(input);
    return new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    });
  };
}

const health: Schemas["Health"] = {
  index_loaded: true,
  index_version: "abc123",
  tokenizer_version: "t1",
  query_version: "q1",
};

describe("createApi", () => {
  it("sends typed requests under the base URL, uncached", async () => {
    const seen: Request[] = [];
    const api = createApi("http://api.test", answering(200, {}, seen));
    await api.GET("/api/v1/search", { params: { query: { q: "trust AND calibration", limit: 10 } } });
    const url = new URL(seen[0]!.url);
    expect(url.origin + url.pathname).toBe("http://api.test/api/v1/search");
    expect(url.searchParams.get("q")).toBe("trust AND calibration");
    expect(url.searchParams.get("limit")).toBe("10");
    expect(seen[0]!.cache).toBe("no-store");
  });

  it("returns the response body as typed data", async () => {
    const api = createApi("http://api.test", answering(200, health));
    const { data, error } = await api.GET("/api/v1/healthz");
    expect(error).toBeUndefined();
    expect(data?.index_version).toBe("abc123");
  });

  it("returns the error envelope as data, a 422 included", async () => {
    const envelope: Schemas["ErrorEnvelope"] = {
      error: {
        code: "PARSE_UNBALANCED_PAREN",
        message: "unbalanced (",
        diagnostics: [
          { code: "PARSE_UNBALANCED_PAREN", message: "unbalanced (", span: [0, 1], reading: null },
        ],
      },
    };
    const api = createApi("http://api.test", answering(422, envelope));
    const { data, error, response } = await api.GET("/api/v1/search", { params: { query: { q: "(" } } });
    expect(data).toBeUndefined();
    expect(response.status).toBe(422);
    expect(error?.error.code).toBe("PARSE_UNBALANCED_PAREN");
    expect(error?.error.diagnostics?.[0]?.span).toEqual([0, 1]);
  });
});

describe("hitHighlightsUtf16", () => {
  it("converts both fields' code-point spans, past an astral character", () => {
    const hit = {
      title: "𝒜 trust model",
      abstract: "We study trust.",
      highlights: { title: [[2, 7]], abstract: [[9, 14]] },
    } satisfies Pick<Schemas["Hit"], "title" | "abstract" | "highlights">;
    const { title, abstract } = hitHighlightsUtf16(hit);
    expect(title).toEqual([[3, 8]]);
    expect(hit.title.slice(...title[0]!)).toBe("trust");
    expect(abstract).toEqual([[9, 14]]);
  });

  it("treats a missing abstract as empty text", () => {
    const hit = {
      title: "trust",
      abstract: null,
      highlights: { title: [[0, 5]], abstract: [] },
    } satisfies Pick<Schemas["Hit"], "title" | "abstract" | "highlights">;
    expect(hitHighlightsUtf16(hit)).toEqual({ title: [[0, 5]], abstract: [] });
  });
});
