"use client";

/**
 * Client-side providers: the typed API client and TanStack Query (spec 05 §Stack; nextjs-conventions
 * §TanStack Query). Nothing is retried silently (spec 05 §Error handling) and nothing refetches on focus: an
 * answer changes only when the reader acts. Tests pass their own `api` (a stubbed fetch) and `queryClient`.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createContext, useContext, useState, type ReactNode } from "react";
import { createApi, type Api } from "@/api/client";

const ApiContext = createContext<Api | null>(null);

export function newQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false, refetchOnReconnect: false } },
  });
}

export function Providers({
  children,
  api,
  queryClient,
}: {
  children: ReactNode;
  api?: Api;
  queryClient?: QueryClient;
}) {
  const [client] = useState(() => queryClient ?? newQueryClient());
  const [value] = useState(() => api ?? createApi());
  return (
    <ApiContext.Provider value={value}>
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    </ApiContext.Provider>
  );
}

export function useApi(): Api {
  const api = useContext(ApiContext);
  if (api === null) throw new Error("useApi() needs <Providers> above it (src/components/providers.tsx)");
  return api;
}
