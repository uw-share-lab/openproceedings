/**
 * The concept-group builder's model (spec 05 §Components 3; docs/design/2026-09-27-concept-group-builder.md).
 *
 * `q := group₁ AND group₂ AND … [AND NOT exclude-group] [AND limits…]`, where a group is an OR of terms and
 * each term is one word, phrase or wildcard with its own field scope. **The text is canonical**: the model is
 * only ever read from the server's `ast` of a query (`read.ts`) and written back to a query string
 * (`write.ts`); it is never stored anywhere else.
 */
import type { ParseResponse } from "@/editor/parse";

/** A node of the server's AST (`/parse` `ast`), spans in code points. */
export type AstNode = NonNullable<ParseResponse["ast"]>;
export type CodePoints = readonly [start: number, end: number];

/** Where a term searches: both text fields (no prefix), or one of them (`title:` / `abstract:`). */
export type Scope = "any" | "title" | "abstract";

export interface BuilderTerm {
  /** Stable within a builder session (React keys and focus targets); never written anywhere. */
  readonly id: number;
  /**
   * What the term writes, without its field prefix: exactly one word, wildcard or phrase lexeme (`terms.ts`),
   * or `""` for a box left empty (left out of the query).
   */
  readonly text: string;
  readonly scope: Scope;
  /** The builder put the quotes on (the reader typed several words): the chip says "searched as one phrase". */
  readonly phrased: boolean;
}

export interface BuilderGroup {
  readonly id: number;
  readonly terms: readonly BuilderTerm[];
}

export interface BuilderModel {
  readonly groups: readonly BuilderGroup[];
  /** The Exclude row ("Leave out papers with any of:"), shown last. */
  readonly exclude: BuilderGroup | null;
  /**
   * How many groups precede the Exclude row **in the text**. The reader keeps where the query had its `NOT`
   * (so an unedited rewrite keeps the canonical query, whose text conjuncts keep their written order); a new
   * Exclude row goes last.
   */
  readonly excludeAt: number;
  /** The top-level filter clauses, each as written (read-only here: Filters or Text edit them). */
  readonly limits: readonly string[];
}

/** The design's names for what doesn't fit (copy deck BD-7), plus two the fit table implies. */
export type BlockerKind =
  | "proximity"
  | "AND inside OR"
  | "a limit inside OR"
  | "NOT of a combination"
  | "NOT inside OR"
  | "a second NOT";

export interface Blocker {
  readonly kind: BlockerKind;
  /** The construct's span in the query (code points). */
  readonly span: CodePoints;
}

let nextId = 1;
/** A fresh id for a term or group. */
export function newId(): number {
  return nextId++;
}

export function emptyTerm(): BuilderTerm {
  return { id: newId(), text: "", scope: "any", phrased: false };
}

export function emptyGroup(): BuilderGroup {
  return { id: newId(), terms: [emptyTerm()] };
}

/** The Empty state: one empty group with one empty term. */
export function emptyModel(): BuilderModel {
  return { groups: [emptyGroup()], exclude: null, excludeAt: 1, limits: [] };
}

export const SCOPE_LABELS: Readonly<Record<Scope, string>> = {
  any: "title or abstract",
  title: "title only",
  abstract: "abstract only",
};

/** The term as its chip shows it and the query holds it: `title:LLM`, `"foundation model"`. */
export function termWritten(term: BuilderTerm): string {
  return term.scope === "any" ? term.text : `${term.scope}:${term.text}`;
}
