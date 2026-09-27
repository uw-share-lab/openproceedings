/**
 * The builder's model as a query string (docs/design/2026-09-27-concept-group-builder.md §The shape): groups
 * of two or more terms in parentheses joined by `OR`, a group of one bare, the groups joined by `AND`, the
 * Exclude row as `NOT …` where the model puts it, and the limits last, as written. Always fully
 * parenthesised with uppercase operators, so the server never has to apply precedence (no
 * `WARN_MIXED_AND_OR`) in either Syntax mode.
 *
 * Every term is one lexeme on its own (`terms.ts`); here the whole string is lexed again (with `lex.ts`, the
 * server lexer's mirror) to check that each term and limit is still exactly its own lexemes next to its
 * neighbours. A term that isn't (a LaTeX `$` pairing with a later one, say) is left out and reported, never
 * written to be read another way. The backend checks what this writes with the real parser
 * (`test_frontend_builder_golden.py`).
 */
import { lexemes } from "@/editor/lang/lex";
import type { BuilderGroup, BuilderModel, CodePoints } from "./model";
import { termWritten } from "./model";
import type { Reading } from "./read";

export interface WrittenTerm {
  /** The group's index in `model.groups`, or `"exclude"`. */
  readonly group: number | "exclude";
  readonly termId: number;
  /** Where the term (with its field prefix) is in `q`, in code points. */
  readonly span: CodePoints;
}

export interface Written {
  readonly q: string;
  readonly terms: readonly WrittenTerm[];
  /** Where each limit is in `q`, in `model.limits` order. */
  readonly limitSpans: readonly CodePoints[];
  /** Terms left out because they wouldn't stay one term next to the others. */
  readonly unsafe: readonly number[];
  /** A limit wouldn't keep its lexemes in the rewritten query (the builder then doesn't write). */
  readonly limitsUnsafe: boolean;
}

const cpLength = (s: string) => Array.from(s).length;

interface Unit {
  readonly text: string;
  readonly start: number;
  readonly termId: number | null;
}

function compose(model: BuilderModel, skip: ReadonlySet<number>) {
  let q = "";
  let at = 0;
  const terms: WrittenTerm[] = [];
  const units: Unit[] = [];
  const limitSpans: CodePoints[] = [];
  const emit = (s: string) => {
    q += s;
    at += cpLength(s);
  };
  const conjuncts: { group: number | "exclude"; g: BuilderGroup }[] = [];
  const excludeAt = Math.min(model.excludeAt, model.groups.length);
  model.groups.forEach((g, i) => {
    if (model.exclude !== null && excludeAt === i) conjuncts.push({ group: "exclude", g: model.exclude });
    conjuncts.push({ group: i, g });
  });
  if (model.exclude !== null && excludeAt === model.groups.length) {
    conjuncts.push({ group: "exclude", g: model.exclude });
  }
  let first = true;
  const sep = () => {
    if (!first) emit(" AND ");
    first = false;
  };
  for (const { group, g } of conjuncts) {
    const written = g.terms.filter((t) => t.text !== "" && !skip.has(t.id));
    if (written.length === 0) continue;
    sep();
    if (group === "exclude") emit("NOT ");
    if (written.length > 1) emit("(");
    written.forEach((t, k) => {
      if (k > 0) emit(" OR ");
      const text = termWritten(t);
      terms.push({ group, termId: t.id, span: [at, at + cpLength(text)] });
      units.push({ text, start: at, termId: t.id });
      emit(text);
    });
    if (written.length > 1) emit(")");
  }
  for (const limit of model.limits) {
    sep();
    limitSpans.push([at, at + cpLength(limit)]);
    units.push({ text: limit, start: at, termId: null });
    emit(limit);
  }
  return { q, terms, units, limitSpans };
}

/** The units whose lexemes in `q` aren't exactly their own lexemes, shifted to where they were written. */
function misread(q: string, units: readonly Unit[]): Unit[] {
  const all = lexemes(q);
  return units.filter((u) => {
    const end = u.start + cpLength(u.text);
    const inside = all.filter(([, s, e]) => s < end && e > u.start);
    const own = lexemes(u.text).map(([k, s, e]) => [k, s + u.start, e + u.start] as const);
    return (
      inside.length !== own.length ||
      inside.some(([k, s, e], i) => k !== own[i]?.[0] || s !== own[i]?.[1] || e !== own[i]?.[2])
    );
  });
}

/**
 * Whether the server read the written query as the builder meant it: it fits, and its leaves are exactly the
 * written terms, each at the span it was written, in the group it was written in, with the term's scope.
 * The goldens make a mismatch impossible for every case they hold; the builder still checks each answer.
 */
export function readsAsWritten(model: BuilderModel, written: Written, reading: Reading): boolean {
  if (reading.kind !== "fits") return false;
  const scopes = new Map<number, string>();
  for (const g of [...model.groups, ...(model.exclude === null ? [] : [model.exclude])]) {
    for (const t of g.terms) scopes.set(t.id, t.scope);
  }
  // the server numbers the groups it reads in text order; so does this
  const order: (number | "exclude")[] = [];
  for (const t of written.terms) if (t.group !== "exclude" && !order.includes(t.group)) order.push(t.group);
  const key = (group: number | "exclude", span: readonly number[], scope: string) =>
    `${group === "exclude" ? "exclude" : order.indexOf(group)}:${span[0]}-${span[1]}:${scope}`;
  const want = written.terms.map((t) => key(t.group, t.span, scopes.get(t.termId) ?? ""));
  const got = [
    ...reading.shape.groups.flatMap((g, i) =>
      g.map((l) => `${i}:${l.span[0]}-${l.span[1]}:${l.field ?? "any"}`),
    ),
    ...(reading.shape.exclude ?? []).map((l) => `exclude:${l.span[0]}-${l.span[1]}:${l.field ?? "any"}`),
  ];
  return JSON.stringify(want.sort()) === JSON.stringify(got.sort());
}

export function writeModel(model: BuilderModel): Written {
  const skip = new Set<number>();
  for (;;) {
    const { q, terms, units, limitSpans } = compose(model, skip);
    const bad = misread(q, units);
    const badTerms = bad.flatMap((u) => (u.termId === null ? [] : [u.termId]));
    if (badTerms.length === 0) {
      return { q, terms, limitSpans, unsafe: [...skip], limitsUnsafe: bad.length > 0 };
    }
    // Leave out the first misread term and try again: a pairing `$` misreads both of its terms, and
    // dropping one may be enough.
    skip.add(badTerms[0] ?? -1);
  }
}
