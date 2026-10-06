/**
 * Tests only: `compare-fixture.json`, the API's own `POST /compare` answers
 * (backend/tests/contract/compare_fixture.py; test_frontend_compare_fixture.py keeps it current), typed. Every
 * count and title a comparison test expects is read from here, never typed by hand.
 */
import type { Schemas } from "@/api/client";
import fixture from "@/components/compare/compare-fixture.json";
import type { CompareLimits, Comparison } from "@/lib/compare";

const typed = fixture as unknown as {
  /** The query the file was compared with. */
  readonly q: string;
  readonly mode: "native" | "scholar";
  /** The RIS file's text. */
  readonly file: string;
  /** `GET /meta`'s `limits` on the instance that answered (comparisons on). */
  readonly limits: Schemas["Limits"] & { readonly compare: CompareLimits };
  /** `/search`'s `total` for `q`. */
  readonly search_total: number;
  readonly response: Comparison;
  /** A refusal's envelope (422 `API_RIS_INVALID`). */
  readonly invalid: Schemas["ErrorEnvelope"];
  /** The same file against `q` with a year limit of its own, which leaves papers out (`query_limit`, TASK-185). */
  readonly limited: { readonly q: string; readonly response: Comparison };
};

export const COMPARE = typed;
