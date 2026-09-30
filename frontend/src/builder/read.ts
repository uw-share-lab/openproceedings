/**
 * The fit rule (docs/design/2026-09-27-concept-group-builder.md §The shape the builder edits): the builder
 * walks the **server's** `ast` (it never parses text). The query fits when its top node is an `And` (nested
 * `And`s flatten into more groups) or a single group, whose children are each a group (a leaf, or an `Or` of
 * leaves; nested `Or`s flatten), a limit (a filter, an `Or` of filters, or a `NOT` of one), or at most one
 * `Not` of a group (the Exclude row). Anything else names the first construct that doesn't fit, in source
 * order, with its span.
 *
 * `backend/tests/contract/test_frontend_builder_golden.py` holds a second, independent implementation of this
 * rule and writes its reading of 300+ queries into `builder-read-golden.json`; `read.test.ts` requires this
 * one to agree span for span.
 */
import { codePointSpanToUtf16 } from "@/api/spans";
import { lexemes } from "@/editor/lang/lex";
import type { AstNode, Blocker, BlockerKind, BuilderGroup, BuilderModel, CodePoints, Scope } from "./model";
import { newId } from "./model";
import { leafTermText } from "./terms";

type Leaf = Extract<AstNode, { kind: "term" | "wildcard" | "phrase" }>;

/** The reading as spans: what the golden compares. */
export interface Shape {
  readonly groups: readonly (readonly Leaf[])[];
  readonly exclude: readonly Leaf[] | null;
  readonly excludeAt: number;
  readonly limits: readonly AstNode[];
}

export type Reading =
  { readonly kind: "fits"; readonly shape: Shape } | { readonly kind: "blocked"; readonly blocker: Blocker };

class Blocked {
  constructor(
    readonly kind: BlockerKind,
    readonly span: CodePoints,
  ) {}
}

const isLeaf = (n: AstNode): n is Leaf => n.kind === "term" || n.kind === "wildcard" || n.kind === "phrase";

function flat(n: AstNode, kind: "and" | "or"): AstNode[] {
  return n.kind === kind ? n.children.flatMap((c) => flat(c, kind)) : [n];
}

function onlyFilters(n: AstNode): boolean {
  return n.kind === "filter" || (n.kind === "or" && n.children.every(onlyFilters));
}

const spanOf = (n: AstNode): CodePoints => [n.span[0] ?? 0, n.span[1] ?? 0];

/** A group's leaves, or the construct that blocks it (for AND, a limit or NOT inside it: the group itself). */
function group(n: AstNode): Leaf[] {
  const items = flat(n, "or");
  const leaves: Leaf[] = [];
  for (const item of items) {
    if (isLeaf(item)) leaves.push(item);
    else if (item.kind === "near") throw new Blocked("proximity", spanOf(item));
    else if (item.kind === "filter") throw new Blocked("a limit inside OR", spanOf(n));
    else if (item.kind === "not") throw new Blocked("NOT inside OR", spanOf(n));
    else throw new Blocked("AND inside OR", spanOf(n));
  }
  return leaves;
}

/**
 * Every top-level part of `ast`, read one by one: the ones that fit make the shape, and each one that doesn't
 * is a blocker, in source order.
 */
function readParts(ast: AstNode): { shape: Shape; blockers: Blocker[] } {
  const groups: Leaf[][] = [];
  let exclude: Leaf[] | null = null;
  let excludeAt = 0;
  const limits: AstNode[] = [];
  const blockers: Blocker[] = [];
  for (const child of flat(ast, "and")) {
    try {
      if (onlyFilters(child) || (child.kind === "not" && onlyFilters(child.child))) {
        limits.push(child);
      } else if (child.kind === "not") {
        const inner = child.child;
        if (exclude !== null) throw new Blocked("a second NOT", spanOf(child));
        if (inner.kind === "near") throw new Blocked("proximity", spanOf(inner));
        if (inner.kind === "and" || inner.kind === "not")
          throw new Blocked("NOT of a combination", spanOf(child));
        exclude = group(inner);
        excludeAt = groups.length;
      } else if (child.kind === "near") {
        throw new Blocked("proximity", spanOf(child));
      } else {
        groups.push(group(child));
      }
    } catch (e) {
      if (!(e instanceof Blocked)) throw e;
      blockers.push({ kind: e.kind, span: e.span });
    }
  }
  return {
    shape: { groups, exclude, excludeAt: exclude === null ? groups.length : excludeAt, limits },
    blockers,
  };
}

export function readAst(ast: AstNode): Reading {
  const { shape, blockers } = readParts(ast);
  const first = blockers[0];
  return first === undefined ? { kind: "fits", shape } : { kind: "blocked", blocker: first };
}

/**
 * The parts of a query that fit, whether or not the rest does: what the read-only builder shows dimmed under
 * its notice (design B2). For a query that fits it is `readAst`'s shape.
 */
export function readFitting(ast: AstNode): Shape {
  return readParts(ast).shape;
}

/** `q`'s text at a code-point span. */
export function sliceOf(q: string, span: CodePoints): string {
  const [from, to] = codePointSpanToUtf16(q, span);
  return q.slice(from, to);
}

function termsOf(q: string, leaves: readonly Leaf[]): BuilderGroup {
  return {
    id: newId(),
    terms: leaves.map((leaf) => ({
      id: newId(),
      text: leafTermText(sliceOf(q, spanOf(leaf)), leaf),
      scope: (leaf.field ?? "any") satisfies Scope,
      phrased: false,
    })),
  };
}

/**
 * A limit as written, parenthesised when it is an `OR` the query didn't parenthesise (`venue:ICLR OR
 * venue:ICML` as the whole query), so it keeps its meaning next to `AND`.
 */
function limitText(q: string, node: AstNode): string {
  const text = sliceOf(q, spanOf(node)).trim();
  // (a NOT binds tighter than AND, so a negated OR is always already parenthesised)
  return node.kind === "or" && !enclosed(text) ? `(${text})` : text;
}

/** Whether `text` is one parenthesised group: its first lexeme's `(` closes at its last lexeme. */
function enclosed(text: string): boolean {
  const lx = lexemes(text);
  if (lx[0]?.[0] !== "LPAREN") return false;
  let depth = 0;
  for (const [k, [kind]] of lx.entries()) {
    if (kind === "LPAREN") depth += 1;
    if (kind === "RPAREN") depth -= 1;
    if (depth === 0) return k === lx.length - 1;
  }
  return false;
}

/** The builder model of a query that fits. */
export function modelOf(q: string, shape: Shape): BuilderModel {
  return {
    groups: shape.groups.map((g) => termsOf(q, g)),
    exclude: shape.exclude === null ? null : termsOf(q, shape.exclude),
    excludeAt: shape.excludeAt,
    limits: shape.limits.map((n) => limitText(q, n)),
  };
}

/** Where each term of a model read from `shape` is in the query it was read from (per-term diagnostics). */
export function sourceSpans(model: BuilderModel, shape: Shape): Map<number, CodePoints> {
  const spans = new Map<number, CodePoints>();
  const pair = (group: BuilderGroup | null, leaves: readonly Leaf[] | null) =>
    group?.terms.forEach((t, k) => {
      const leaf = leaves?.[k];
      if (leaf !== undefined) spans.set(t.id, spanOf(leaf));
    });
  model.groups.forEach((g, i) => pair(g, shape.groups[i] ?? null));
  pair(model.exclude, shape.exclude);
  return spans;
}

/** The construct's text for the read-only notice (BD-7), clipped to 40 characters like server messages. */
export function constructText(q: string, blocker: Blocker): string {
  const text = sliceOf(q, blocker.span).replace(/\s+/gu, " ").trim();
  const cps = Array.from(text);
  return cps.length > 40 ? `${cps.slice(0, 39).join("")}…` : text;
}
