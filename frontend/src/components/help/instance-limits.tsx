"use client";

import { useEffect, useState } from "react";
import { createApi, type Api, type Schemas } from "@/api/client";
import { settle } from "@/lib/api-result";
import { count } from "@/components/coverage/format";

type Limits = Schemas["Limits"];
type Loaded = { kind: "loading" } | { kind: "served"; limits: Limits } | { kind: "defaults" };

/**
 * This instance's query limits from `GET /meta` (`limits`), read at request time so an instance run with other
 * limits shows its own (design §`/help/syntax`). If `/meta` doesn't answer, the defaults are shown and said to
 * be defaults (copy deck HS-2).
 */
export function InstanceLimits({ defaults, api }: { defaults: Limits; api?: Api }) {
  const [client] = useState(() => api ?? createApi());
  const [loaded, setLoaded] = useState<Loaded>({ kind: "loading" });
  useEffect(() => {
    let live = true;
    void settle(() => client.GET("/api/v1/meta")).then((result) => {
      if (live)
        setLoaded(
          result.kind === "ok" ? { kind: "served", limits: result.data.limits } : { kind: "defaults" },
        );
    });
    return () => {
      live = false;
    };
  }, [client]);
  if (loaded.kind === "loading") {
    return (
      <p role="status" className="text-muted-foreground">
        Loading this instance&apos;s limits
      </p>
    );
  }
  const limits = loaded.kind === "served" ? loaded.limits : defaults;
  return (
    <div className="space-y-1">
      {loaded.kind === "defaults" ? (
        <p className="text-warn-fg">
          This instance&apos;s limits couldn&apos;t be loaded; these are the defaults.
        </p>
      ) : null}
      <ul className="list-disc space-y-1 pl-5 tabular-nums">
        <li>
          At most {count(limits.max_query_length)} characters (Unicode code points) in a query, and in its
          canonical form, where the default filters are written out.
        </li>
        <li>Groups and NOTs nested at most {count(limits.max_query_depth)} deep.</li>
        <li>
          At most {count(limits.max_verified_clauses)} position-verified clauses (phrases with a wildcard,
          NEARs) in one query.
        </li>
        <li>
          At most {count(limits.max_verification_candidates)} candidate documents read by those clauses&apos;
          position checks, summed over each clause&apos;s fields.
        </li>
        <li>
          The builder&apos;s group counts are shown for a query of at most {count(limits.max_counted_groups)}{" "}
          groups whose counting reads at most {count(limits.max_counted_terms)} terms and{" "}
          {count(limits.max_counted_ids)} position-checked matches; a larger query is searched as usual,
          without the counts.
        </li>
      </ul>
    </div>
  );
}
