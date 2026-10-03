"use client";

import { useCallback, useEffect, useState } from "react";
import { createApi, type Api, type Schemas } from "@/api/client";
import { settle, type ApiResult } from "@/lib/api-result";
import { CoverageReport } from "./coverage-report";
import { LoadFailure } from "./load-failure";

type State = { kind: "loading" } | ApiResult<Schemas["CoverageResponse"]>;

/** Skeleton of the header lines while loading: bars, never made-up numbers (design §States). */
function Loading() {
  return (
    <div aria-busy="true" className="space-y-2">
      <p className="sr-only" role="status">
        Loading coverage
      </p>
      {[18, 26, 22, 30].map((w) => (
        <div key={w} className="h-4 rounded-sm bg-muted" style={{ width: `${w}rem`, maxWidth: "100%" }} />
      ))}
    </div>
  );
}

/** `/coverage`'s data: `GET /api/v1/coverage` on each visit (the index can hot-swap), retried only on request. */
export function CoverageView({ api }: { api?: Api }) {
  const [client] = useState(() => api ?? createApi());
  const [state, setState] = useState<State>({ kind: "loading" });
  const fetchCoverage = useCallback(() => settle(() => client.GET("/api/v1/coverage")), [client]);
  useEffect(() => {
    let live = true;
    void fetchCoverage().then((result) => {
      if (live) setState(result);
    });
    return () => {
      live = false;
    };
  }, [fetchCoverage]);
  const retry = () => {
    setState({ kind: "loading" });
    void fetchCoverage().then(setState);
  };
  if (state.kind === "loading") return <Loading />;
  if (state.kind !== "ok") return <LoadFailure failure={state} onRetry={retry} />;
  return <CoverageReport coverage={state.data} />;
}
