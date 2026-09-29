/**
 * Tests only: `record-fixture.json`, the API's own answers (backend/tests/contract/record_fixture.py;
 * test_frontend_record_fixture.py keeps it current), typed. Every count a record, save or export test expects
 * is read from here, never typed by hand.
 */
import type { MethodResponse } from "openapi-fetch";
import type { Api } from "@/api/client";
import fixture from "@/components/record/record-fixture.json";
import type { ParseResponse } from "@/editor/parse";
import type { RecordResponse } from "@/lib/methods-text";

export type RecordCreated = MethodResponse<Api, "post", "/api/v1/records">;
export type SearchResponse = MethodResponse<Api, "get", "/api/v1/search">;

export interface RecordCase {
  readonly q: string;
  readonly mode: "native" | "scholar";
  readonly created: RecordCreated;
  /** `GET /records/{id}?replay=false`. */
  readonly stored: RecordResponse;
  /** `GET /records/{id}`: reproduced. */
  readonly replayed: RecordResponse;
  readonly parse_canonical: ParseResponse;
  readonly parse_identification: ParseResponse;
}

export interface SearchCase {
  readonly q: string;
  readonly mode: "native" | "scholar";
  readonly search: SearchResponse;
  readonly parse: ParseResponse;
}

type RecordName = "limits" | "defaults_only" | "all_negative" | "one_default" | "scholar";
type SearchName = "accepted" | "statuses" | "negated_status" | "workshop";

const typed = fixture as unknown as {
  records: Record<RecordName, RecordCase>;
  searches: Record<SearchName, SearchCase>;
};

export const RECORDS = typed.records;
export const SEARCHES = typed.searches;

/** A deep copy, so a test's overrides never leak into another's. */
export function copy<T>(value: T): T {
  return structuredClone(value);
}
