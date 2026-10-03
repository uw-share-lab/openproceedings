/**
 * Builder edits as pure functions over the model (design §Interaction spec). The UI calls these; the write
 * golden (`write.test.ts`) drives the same functions with seeded random edits, so what it checks against the
 * server's parser is exactly what the UI produces.
 */
import type { BuilderGroup, BuilderModel, BuilderTerm, Scope } from "./model";
import { emptyGroup, emptyTerm, newId } from "./model";
import { phraseOf, termFromInput } from "./terms";

/** A group by its index in `model.groups`, or the Exclude row. */
export type GroupKey = number | "exclude";

export function groupAt(model: BuilderModel, key: GroupKey): BuilderGroup | null {
  return key === "exclude" ? model.exclude : (model.groups[key] ?? null);
}

function withGroup(model: BuilderModel, key: GroupKey, f: (g: BuilderGroup) => BuilderGroup): BuilderModel {
  if (key === "exclude") return model.exclude === null ? model : { ...model, exclude: f(model.exclude) };
  return { ...model, groups: model.groups.map((g, i) => (i === key ? f(g) : g)) };
}

const mapTerms = (g: BuilderGroup, f: (terms: readonly BuilderTerm[]) => readonly BuilderTerm[]) => ({
  ...g,
  terms: f(g.terms),
});

export type CommitResult =
  | { readonly kind: "ok"; readonly model: BuilderModel }
  | { readonly kind: "removed"; readonly model: BuilderModel }
  | { readonly kind: "unwritable" };

/**
 * Set a term's text from what the reader typed (`terms.ts`); an empty box removes the term. `"phrase"`: the
 * reader chose "Keep as one phrase" for a pasted list.
 */
export function commitTerm(
  model: BuilderModel,
  key: GroupKey,
  termId: number,
  input: string,
  as: "typed" | "phrase" = "typed",
): CommitResult {
  const read = as === "phrase" ? phraseOf(input) : termFromInput(input);
  if (read.kind === "unwritable") return { kind: "unwritable" };
  if (read.kind === "empty") return { kind: "removed", model: removeTerm(model, key, termId) };
  return {
    kind: "ok",
    model: withGroup(model, key, (g) =>
      mapTerms(g, (ts) =>
        ts.map((t) =>
          t.id === termId
            ? { ...t, text: read.text, phrased: read.phrased, scope: read.scope ?? t.scope }
            : t,
        ),
      ),
    ),
  };
}

/**
 * Replace a term with one term per pasted item (BD-5a "Split into n terms"). Items no phrase can hold are
 * dropped; the ids of the new terms are returned in order.
 */
export function splitTerm(
  model: BuilderModel,
  key: GroupKey,
  termId: number,
  items: readonly string[],
): { model: BuilderModel; ids: number[] } {
  const target = groupAt(model, key)?.terms.find((t) => t.id === termId);
  const made: BuilderTerm[] = [];
  for (const item of items) {
    const read = termFromInput(item);
    if (read.kind !== "term") continue;
    made.push({
      id: newId(),
      text: read.text,
      phrased: read.phrased,
      scope: read.scope ?? target?.scope ?? "any",
    });
  }
  const next = withGroup(model, key, (g) =>
    mapTerms(g, (ts) => ts.flatMap((t) => (t.id === termId ? made : [t]))),
  );
  return { model: next, ids: made.map((t) => t.id) };
}

export function removeTerm(model: BuilderModel, key: GroupKey, termId: number): BuilderModel {
  return withGroup(model, key, (g) => mapTerms(g, (ts) => ts.filter((t) => t.id !== termId)));
}

export function setScope(model: BuilderModel, key: GroupKey, termId: number, scope: Scope): BuilderModel {
  return withGroup(model, key, (g) =>
    mapTerms(g, (ts) => ts.map((t) => (t.id === termId ? { ...t, scope } : t))),
  );
}

/** An empty term at the end of the group (or after `afterId`); its id, to focus its box. */
export function addTerm(
  model: BuilderModel,
  key: GroupKey,
  afterId?: number,
): { model: BuilderModel; id: number } {
  const term = emptyTerm();
  const next = withGroup(model, key, (g) =>
    mapTerms(g, (ts) => {
      const at = afterId === undefined ? -1 : ts.findIndex((t) => t.id === afterId);
      return at < 0 ? [...ts, term] : [...ts.slice(0, at + 1), term, ...ts.slice(at + 1)];
    }),
  );
  return { model: next, id: term.id };
}

/** A new group with one empty term, last (after the Exclude row too, when that was last). */
export function addGroup(model: BuilderModel): BuilderModel {
  const last = model.excludeAt >= model.groups.length;
  return {
    ...model,
    groups: [...model.groups, emptyGroup()],
    excludeAt: last ? model.groups.length + 1 : model.excludeAt,
  };
}

export function removeGroup(model: BuilderModel, index: number): BuilderModel {
  return {
    ...model,
    groups: model.groups.filter((_, i) => i !== index),
    excludeAt: index < model.excludeAt ? model.excludeAt - 1 : model.excludeAt,
  };
}

/** Swap group `index` with its neighbour (`-1` up, `+1` down); the order changes the text, never the set. */
export function moveGroup(model: BuilderModel, index: number, by: -1 | 1): BuilderModel {
  const to = index + by;
  const a = model.groups[index];
  const b = model.groups[to];
  if (a === undefined || b === undefined) return model;
  const groups = [...model.groups];
  groups[index] = b;
  groups[to] = a;
  return { ...model, groups };
}

/** The Exclude row, with one empty term, written last. */
export function addExclude(model: BuilderModel): BuilderModel {
  if (model.exclude !== null) return model;
  return { ...model, exclude: emptyGroup(), excludeAt: model.groups.length };
}

export function removeExclude(model: BuilderModel): BuilderModel {
  return { ...model, exclude: null, excludeAt: model.groups.length };
}
