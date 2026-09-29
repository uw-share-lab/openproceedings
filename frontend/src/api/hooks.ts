"use client";

/**
 * Small read-only API queries shared by the search pages (nextjs-conventions §TanStack Query keys). A failed
 * answer is `null`: every caller has a way to show nothing rather than a placeholder (design W1).
 */
import { useQuery } from "@tanstack/react-query";
import { useApi } from "@/components/providers";
import type { Schemas } from "./client";

/** `GET /meta`: vocabularies for completion, `limits`, `index_version`. Long-lived (a swap is rare). */
export function useMeta(): Schemas["MetaResponse"] | null {
  const api = useApi();
  const query = useQuery({
    queryKey: ["meta"],
    queryFn: async ({ signal }) => (await api.GET("/api/v1/meta", { signal })).data ?? null,
    staleTime: 10 * 60 * 1000,
  });
  return query.data ?? null;
}

/** `GET /coverage`: the corpus totals for the home page's coverage line. */
export function useCoverage(): Schemas["CoverageResponse"] | null {
  const api = useApi();
  const query = useQuery({
    queryKey: ["coverage"],
    queryFn: async ({ signal }) => (await api.GET("/api/v1/coverage", { signal })).data ?? null,
    staleTime: 10 * 60 * 1000,
  });
  return query.data ?? null;
}
