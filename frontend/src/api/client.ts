/**
 * The one typed API client (nextjs-conventions §Layout). Paths, parameters, bodies and responses all come
 * from the generated `schema.ts` (regenerate with `make openapi`); nothing here restates an API type.
 *
 *   const api = createApi();
 *   const { data, error } = await api.GET("/api/v1/search", { params: { query: { q } } });
 *
 * `error` is the spec 04 envelope (`ErrorEnvelope`): every non-2xx answer, a 422 included, is data to
 * render, not an exception. Spans stay in code points until `hitHighlightsUtf16` converts them, once.
 */
import createClient from "openapi-fetch";
import type { components, paths } from "./schema";
import { codePointSpanToUtf16, type Utf16Span } from "./spans";

export type Schemas = components["schemas"];

/**
 * `baseUrl` defaults to `NEXT_PUBLIC_API_BASE_URL`, else "" (same origin: the reverse proxy serves
 * `/api/v1`). `no-store` always: the index can hot-swap, so a cached response could show a stale
 * `index_version`.
 */
export function createApi(
  baseUrl: string = process.env.NEXT_PUBLIC_API_BASE_URL ?? "",
  fetchImpl: typeof globalThis.fetch = globalThis.fetch,
) {
  return createClient<paths>({ baseUrl, fetch: fetchImpl, cache: "no-store" });
}

export type Api = ReturnType<typeof createApi>;

/** A hit's highlight spans as UTF-16 ranges into its own `title` and `abstract` (spans.ts is the only converter). */
export function hitHighlightsUtf16(hit: Pick<Schemas["Hit"], "title" | "abstract" | "highlights">): {
  title: Utf16Span[];
  abstract: Utf16Span[];
} {
  const abstract = hit.abstract ?? "";
  return {
    title: hit.highlights.title.map((span) => codePointSpanToUtf16(hit.title, span)),
    abstract: hit.highlights.abstract.map((span) => codePointSpanToUtf16(abstract, span)),
  };
}
