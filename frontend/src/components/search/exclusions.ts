/**
 * What the exclusion banner and the "Limits you wrote" line say (spec 05 §5; design W5 banner, include
 * buttons and Limits line, pre-pass M1, M2, S5; copy BN-1–5, RH-4). Pure: every number is one the API sent
 * (`excluded`, `facets`), read, never added up (ux-design: the UI adds no numbers), and every clause is the
 * server's `/parse` report sliced from `q`, never a parse of `q`.
 */
import { codePointSpanToUtf16 } from "@/api/spans";
import { clip } from "@/lib/clip";
import type { ParsedFilters } from "@/lib/search-state";
import type { SearchResponse } from "./use-search";

type Excluded = SearchResponse["excluded"];
type Facets = SearchResponse["facets"];

/** The two fields a default filter can apply to, in the order buckets are counted (track, then status). */
export const DEFAULT_FIELDS = ["track", "status"] as const;
export type DefaultField = (typeof DEFAULT_FIELDS)[number];

/**
 * A clause as the query writes it, for a message `Coded` draws: `status:accepted`,
 * `track:(datasets_benchmarks OR main OR position)`. `field` is the client's own literal; each value is the
 * API's (`/parse`'s report, sliced from `q`), so it goes through `clip`: a backtick in it would shift every
 * later code span, and a control or bidi character would reach the page (TASK-160).
 */
export function clauseText(field: string, values: readonly string[]): string {
  const shown = values.map((v) => clip(v));
  return shown.length === 1 ? `${field}:${shown[0] ?? ""}` : `${field}:(${shown.join(" OR ")})`;
}

/**
 * The PRISMA disclosure's subject (BN-4): the default clauses, each between backticks, or the words alone when
 * `/parse` hasn't reported them. The clauses are `clauseText`s, so their values are already clipped.
 */
export function defaultsText(defaultClauses: readonly string[]): string {
  return defaultClauses.length === 0
    ? "The default filters"
    : `The default filters ${defaultClauses.map((c) => `\`${c}\``).join(" and ")}`;
}

/** A bucket's value as the banner names it: `unknown` says which map it is from. */
export function bucketName(field: DefaultField, value: string): string {
  return value === "unknown" ? `${field} unknown` : value;
}

export interface IncludeButton {
  readonly field: DefaultField;
  readonly value: string;
  /** The bucket's count (`excluded[field][value]`). */
  readonly bucket: number;
  /** What the click adds: the facet count (`facets[field][value]`), which is what the label shows. */
  readonly adds: number;
  /** The visible label, without the `▸`. */
  readonly label: string;
  /** The accessible name: the visible label's number, in a sentence (pre-pass M1). */
  readonly name: string;
  /** The description: what the click writes (BN-3). */
  readonly description: string;
}

export interface Banner {
  /** Line 1, the standing string: `excluded: 212 workshop · 4 competition · 88 rejected`, or `excluded: none`. */
  readonly excluded: string;
  /** Fields that are a limit the reader wrote, named on line 1 (pre-pass M2). */
  readonly limitFields: readonly DefaultField[];
  /** Line 2, or `null` when no map is under a default: `unclassified: 3 track unknown · 0 status unknown`. */
  readonly unclassified: string | null;
  readonly includes: readonly IncludeButton[];
  /** The default clauses as text, for the PRISMA disclosure (BN-4), from `/parse`'s report. */
  readonly defaultClauses: readonly string[];
}

/**
 * `defaults` is `/parse`'s list of fields whose default applied, or `null` when there is no report for this
 * query yet: then nothing is called a limit, and both maps are itemised as the API sent them.
 */
export function bannerOf(
  excluded: Excluded,
  facets: Facets,
  defaults: readonly string[] | null,
  filters: ParsedFilters | null,
): Banner {
  const underDefault = (f: DefaultField) => defaults === null || defaults.includes(f);
  const limitFields = DEFAULT_FIELDS.filter((f) => !underDefault(f));
  const defaultValues = (f: DefaultField): readonly string[] | null =>
    defaults?.includes(f) === true ? (filters?.[f].values ?? null) : null;

  const parts: string[] = [];
  for (const f of DEFAULT_FIELDS) {
    for (const [value, n] of Object.entries(excluded[f])) {
      if (value !== "unknown" && n > 0) parts.push(`${n.toLocaleString("en-US")} ${value}`);
    }
  }
  const limitParts = limitFields.map((f) => `${f}: your limit applies (see Limits you wrote)`);
  const line1 =
    parts.length === 0 && limitParts.length === 0
      ? "excluded: none"
      : `excluded: ${[...(parts.length === 0 ? ["none"] : parts), ...limitParts].join(" · ")}`;

  const kept = DEFAULT_FIELDS.filter(underDefault);
  const unclassified =
    kept.length === 0
      ? null
      : `unclassified: ${kept
          .map((f) => `${(excluded[f]["unknown"] ?? 0).toLocaleString("en-US")} ${f} unknown`)
          .join(" · ")}`;

  const includes: IncludeButton[] = [];
  for (const f of kept) {
    const other = DEFAULT_FIELDS.find((o) => o !== f) ?? f;
    const otherValues = defaultValues(other);
    for (const [value, bucket] of Object.entries(excluded[f])) {
      if (bucket <= 0) continue;
      const adds = facets[f][value] ?? 0;
      const name = bucketName(f, value);
      const shown = clip(value); // the API's bucket name, bare and in the clause, for `Coded` (TASK-160)
      const description =
        `Adds ${shown} to the ${f} filter, \`${f}:(… OR ${shown})\`; ` +
        `the ${f} filter then becomes a limit you wrote.`;
      if (adds === 0) {
        const fails = otherValues === null ? "another filter" : `\`${clauseText(other, otherValues)}\``;
        const label = `include ${name} (adds 0: all ${bucket.toLocaleString("en-US")} also fail ${fails.replaceAll("`", "")})`;
        includes.push({ field: f, value, bucket, adds, label, name: label, description });
      } else {
        const n = adds.toLocaleString("en-US");
        includes.push({
          field: f,
          value,
          bucket,
          adds,
          label: `include ${n} ${name}`,
          name: `Include ${n} ${name} papers`,
          description,
        });
      }
    }
  }

  const defaultClauses = DEFAULT_FIELDS.flatMap((f) => {
    const values = defaultValues(f);
    return values === null ? [] : [clauseText(f, values)];
  });
  return { excluded: line1, limitFields, unclassified, includes, defaultClauses };
}

/** The filter fields a reader can write, in the sidebar's order. */
export const FILTER_FIELDS = ["venue", "year", "track", "status"] as const;

export interface Limit {
  readonly field: (typeof FILTER_FIELDS)[number];
  /** The clause as written in `q`, or `null` when there is more than one (listed as several clauses). */
  readonly text: string | null;
  /** What it leaves out, from the facet counts: `[value, count]`, zeros omitted (never summed). */
  readonly leavesOut: readonly (readonly [string, number])[];
}

/**
 * The clauses of the searched `q` that are not defaults (design W5 "Limits line"): each field `/parse`
 * reports with a non-zero-width span, sliced from `q`, or with no single span (several clauses). For a single
 * venue, track or status clause, the values it leaves out come from `facets[field]` (exact: a field's facet
 * is counted without its own clause), for every value outside the clause, in vocabulary order.
 */
export function limitsOf(
  q: string,
  filters: ParsedFilters,
  defaults: readonly string[],
  facets: Facets,
  vocabulary: Readonly<Partial<Record<string, readonly string[]>>>,
): Limit[] {
  const out: Limit[] = [];
  for (const field of FILTER_FIELDS) {
    if (defaults.includes(field)) continue;
    const clause = filters[field];
    if (clause.span === null) {
      out.push({ field, text: null, leavesOut: [] });
      continue;
    }
    const [start, end] = clause.span;
    if (start === end) continue;
    let text: string;
    try {
      const [a, b] = codePointSpanToUtf16(q, [start, end]);
      text = q.slice(a, b);
    } catch {
      text = `${field}:…`;
    }
    const leavesOut: [string, number][] = [];
    if (field !== "year" && !clause.negated && "values" in clause && clause.values !== null) {
      const admitted = new Set(clause.values);
      const counts = facets[field];
      const values = [...(vocabulary[field] ?? []), ...Object.keys(counts)];
      for (const v of new Set(values)) {
        const n = counts[v] ?? 0;
        if (!admitted.has(v) && n > 0) leavesOut.push([v, n]);
      }
    }
    out.push({ field, text, leavesOut });
  }
  return out;
}
