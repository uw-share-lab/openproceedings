import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import {
  addExclude,
  addGroup,
  addTerm,
  commitTerm,
  moveGroup,
  removeGroup,
  removeTerm,
  setScope,
  splitTerm,
  type GroupKey,
} from "./edits";
import { readGolden, WRITE_GOLDEN_PATH, type ReadCase } from "./golden";
import { emptyModel, termWritten, type BuilderModel, type Scope } from "./model";
import { modelOf, readAst } from "./read";
import { listItems } from "./terms";
import { readsAsWritten, writeModel, type Written } from "./write";

/** A small seeded PRNG (mulberry32): the golden must be the same on every run. */
function prng(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** What a reader might type into a term box, including every awkward kind the writer must handle. */
const INPUTS = [
  "trust",
  "leaderboard",
  "LLM",
  "trustworth*",
  "model$",
  "gpt-4*",
  '"foundation model"',
  "“curly phrase”",
  "foundation model",
  "Trust AND safety",
  "trust OR reliance",
  "bias, fairness; equity",
  "a | b",
  "title:LLM",
  'abstract:"trust calibration"',
  "venue:ICLR",
  "foo:bar",
  "and",
  "OR",
  "NOT",
  "NEAR/3",
  "-bias",
  "(x)",
  "x)",
  "C++",
  ".NET",
  'G\\"odel',
  "a\\",
  "\\",
  '"',
  "$x$",
  "$x",
  "y$",
  "𝐱",
  "ＬＬＭ",
  "ＯＲ",
  "é",
  "2024",
  "2020..2026",
  "human-AI trust",
  "vision-language",
  "trust*ed",
];
const SCOPES: Scope[] = ["any", "title", "abstract"];

function pick<T>(rand: () => number, xs: readonly T[]): T {
  const x = xs[Math.floor(rand() * xs.length)];
  if (x === undefined) throw new Error("empty choice");
  return x;
}

function keys(model: BuilderModel): GroupKey[] {
  return [...model.groups.map((_, i) => i), ...(model.exclude === null ? [] : ["exclude" as const])];
}

/**
 * Type `input` into a new term of group `key`, as the UI does: Enter splits a list, else commits; `keep`
 * chooses "Keep as one phrase" for a list instead.
 */
function type(model: BuilderModel, key: GroupKey, input: string, keep = false): BuilderModel {
  const added = addTerm(model, key);
  const items = listItems(input);
  if (items !== null && !keep) return splitTerm(added.model, key, added.id, items).model;
  const done = commitTerm(added.model, key, added.id, input, items !== null ? "phrase" : "typed");
  return done.kind === "unwritable" ? removeTerm(added.model, key, added.id) : done.model;
}

function edit(model: BuilderModel, rand: () => number): BuilderModel {
  if (model.groups.length === 0) return type(addGroup(model), 0, pick(rand, INPUTS));
  const ks = keys(model);
  const key = pick(rand, ks);
  const terms = (key === "exclude" ? model.exclude?.terms : model.groups[key]?.terms) ?? [];
  switch (Math.floor(rand() * 8)) {
    case 0:
      return type(model, key, pick(rand, INPUTS));
    case 1:
      return type(model, key, pick(rand, INPUTS), true);
    case 2:
      return terms.length > 0 ? removeTerm(model, key, pick(rand, terms).id) : model;
    case 3:
      return terms.length > 0 ? setScope(model, key, pick(rand, terms).id, pick(rand, SCOPES)) : model;
    case 4:
      return model.groups.length > 1
        ? moveGroup(model, Math.floor(rand() * model.groups.length), rand() < 0.5 ? -1 : 1)
        : model;
    case 5:
      return model.groups.length > 1 ? removeGroup(model, Math.floor(rand() * model.groups.length)) : model;
    case 6: {
      const grown = addGroup(model);
      return type(
        type(grown, grown.groups.length - 1, pick(rand, INPUTS)),
        grown.groups.length - 1,
        pick(rand, INPUTS),
      );
    }
    default: {
      const withExclude = addExclude(model);
      return type(withExclude, "exclude", pick(rand, INPUTS));
    }
  }
}

/** The groups as the written query holds them: chips as written, empty and left-out terms omitted. */
function chipsOf(model: BuilderModel, written: Written) {
  const writtenIds = new Set(written.terms.map((t) => t.termId));
  const chips = (terms: BuilderModel["groups"][number]["terms"]) =>
    terms.filter((t) => writtenIds.has(t.id)).map(termWritten);
  const groups = model.groups.map((g) => chips(g.terms)).filter((g) => g.length > 0);
  const exclude = model.exclude === null ? [] : chips(model.exclude.terms);
  const firstExclude = written.terms.findIndex((t) => t.group === "exclude");
  const before = new Set(written.terms.slice(0, Math.max(firstExclude, 0)).map((t) => t.group));
  return {
    chips: groups,
    exclude: exclude.length > 0 ? exclude : null,
    exclude_at: exclude.length > 0 ? before.size : groups.length,
    limits: [...model.limits],
  };
}

function fittingModel(c: ReadCase): BuilderModel | null {
  if (c.ast === null) return null;
  const reading = readAst(c.ast);
  return reading.kind === "fits" ? modelOf(c.q, reading.shape) : null;
}

function buildWriteGolden() {
  const out: object[] = [];
  const fits = readGolden().flatMap((c) => {
    const model = fittingModel(c);
    return model === null ? [] : [{ c, model }];
  });
  for (const { c, model } of fits) out.push({ mode: c.mode, from: c.q, written: writeModel(model).q });
  const rand = prng(43);
  for (const { c, model } of fits) {
    let m = model;
    const n = 1 + Math.floor(rand() * 4);
    for (let k = 0; k < n; k++) m = edit(m, rand);
    const written = writeModel(m);
    if (written.q === "" || written.limitsUnsafe) continue;
    out.push({ mode: c.mode, written: written.q, ...chipsOf(m, written) });
  }
  // From an empty builder: every input alone, in each scope, and in a group with a neighbour
  for (const [i, input] of INPUTS.entries()) {
    for (const mode of ["native", "scholar"] as const) {
      let m = type(emptyModel(), 0, input);
      const first = m.groups[0]?.terms.find((t) => t.text !== "");
      if (first !== undefined) m = setScope(m, 0, first.id, pick(prng(i), SCOPES));
      m = type(m, 0, pick(prng(i + 1), INPUTS));
      const written = writeModel(m);
      if (written.q !== "") out.push({ mode, written: written.q, ...chipsOf(m, written) });
    }
  }
  return out;
}

function render(cases: object[]): string {
  const lines = cases.map((c) => JSON.stringify(c)).join(",\n");
  return (
    '{"_generated": "by UPDATE_BUILDER_GOLDEN=1 npm test --workspace frontend -- builder; checked by ' +
    'backend/tests/contract/test_frontend_builder_golden.py; do not edit",\n"cases": [\n' +
    `${lines}\n]}\n`
  );
}

describe("builder-write-golden.json", () => {
  it("is current (regenerate with UPDATE_BUILDER_GOLDEN=1, then run the backend test)", () => {
    const text = render(buildWriteGolden());
    if (process.env.UPDATE_BUILDER_GOLDEN === "1") writeFileSync(WRITE_GOLDEN_PATH, text, "utf8");
    expect(existsSync(WRITE_GOLDEN_PATH)).toBe(true);
    expect(readFileSync(WRITE_GOLDEN_PATH, "utf8") === text).toBe(true);
  });
});

function modelFor(groups: string[][], limits: string[] = []): BuilderModel {
  let m: BuilderModel = { groups: [], exclude: null, excludeAt: 0, limits };
  for (const g of groups) {
    m = addGroup(m);
    const index = m.groups.length - 1;
    m = removeTerm(m, index, m.groups[index]?.terms[0]?.id ?? -1);
    for (const input of g) m = type(m, index, input);
  }
  return m;
}

describe("writeModel", () => {
  it("writes the design's example and its edit", () => {
    const m = modelFor(
      [['"foundation model"', "LLM"], ["trustworth*", "trust"], ["benchmark"]],
      ["venue:ICLR"],
    );
    expect(writeModel(m).q).toBe(
      '("foundation model" OR LLM) AND (trustworth* OR trust) AND benchmark AND venue:ICLR',
    );
    expect(writeModel(type(m, 2, "leaderboard")).q).toBe(
      '("foundation model" OR LLM) AND (trustworth* OR trust) AND (benchmark OR leaderboard) AND venue:ICLR',
    );
  });

  it("leaves empty terms and empty groups out; all empty is the empty query", () => {
    expect(writeModel(emptyModel()).q).toBe("");
    const m = addGroup(modelFor([["trust"]]));
    expect(writeModel(m).q).toBe("trust");
  });

  it("quotes several words as one phrase, and says it did", () => {
    const m = modelFor([["foundation model", "Trust AND safety"]]);
    expect(writeModel(m).q).toBe('("foundation model" OR "Trust AND safety")');
    expect(m.groups[0]?.terms.map((t) => t.phrased)).toEqual([true, true]);
  });

  it("never writes an operator: uppercase ones become phrases, lowercase ones are quoted words", () => {
    expect(writeModel(modelFor([["x", "OR", "NOT", "and", "-bias", "(x)"]])).q).toBe(
      '(x OR "OR" OR "NOT" OR "and" OR "-bias" OR "(x)")',
    );
  });

  it("takes a typed title:/abstract: prefix as the chip's scope", () => {
    const m = modelFor([["title:LLM", 'abstract:"trust calibration"']]);
    expect(m.groups[0]?.terms.map((t) => [t.scope, t.text])).toEqual([
      ["title", "LLM"],
      ["abstract", '"trust calibration"'],
    ]);
    expect(writeModel(setScope(m, 0, m.groups[0]?.terms[0]?.id ?? -1, "any")).q).toBe(
      '(LLM OR abstract:"trust calibration")',
    );
  });

  it("writes the Exclude row where the model puts it", () => {
    let m = addExclude(modelFor([["trust"], ["benchmark"]]));
    m = type(m, "exclude", "bias, fairness");
    expect(writeModel(m).q).toBe("trust AND benchmark AND NOT (bias OR fairness)");
    expect(writeModel({ ...m, excludeAt: 0 }).q).toBe("NOT (bias OR fairness) AND trust AND benchmark");
  });

  it("reports where each term is written, in code points", () => {
    const written = writeModel(modelFor([["𝐱", "title:y"]]));
    expect(written.q).toBe("(𝐱 OR title:y)");
    expect(written.terms.map((t) => t.span)).toEqual([
      [1, 2],
      [6, 13],
    ]);
  });

  it("leaves out a term that wouldn't stay one term next to its neighbours (a pairing LaTeX $)", () => {
    const m = modelFor([["$x", "y$"]]);
    expect(m.groups[0]?.terms.map((t) => t.text)).toEqual(["$x", "y$"]);
    const written = writeModel(m);
    expect(written.unsafe).toHaveLength(1);
    expect(written.q).toBe("y$");
  });
});

describe("readsAsWritten (the builder's check of each server answer)", () => {
  const same = readGolden().flatMap((c) => {
    const model = fittingModel(c);
    return model !== null && c.ast !== null && writeModel(model).q === c.q ? [{ c, model, ast: c.ast }] : [];
  });

  it("accepts the server's reading of every golden query the builder writes unchanged", () => {
    expect(same.length).toBeGreaterThan(20);
    for (const { model, ast } of same)
      expect(readsAsWritten(model, writeModel(model), readAst(ast))).toBe(true);
  });

  it("rejects a reading with another scope, another grouping, or one that doesn't fit", () => {
    const found = same.find(({ c }) => c.q === "(trust OR reliance) AND benchmark");
    if (found === undefined) throw new Error("missing golden case");
    const { model, ast } = found;
    const written = writeModel(model);
    const trust = model.groups[0]?.terms[0]?.id ?? -1;
    expect(readsAsWritten(setScope(model, 0, trust, "title"), written, readAst(ast))).toBe(false);
    const reading = readAst(ast);
    if (reading.kind !== "fits") throw new Error("fits");
    const [g1 = [], g2 = []] = reading.shape.groups;
    // the same leaves at the same spans, but `reliance` read in the second group
    const regrouped = { ...reading.shape, groups: [g1.slice(0, 1), [...g1.slice(1), ...g2]] };
    expect(readsAsWritten(model, written, { kind: "fits", shape: regrouped })).toBe(false);
    expect(
      readsAsWritten(model, written, { kind: "blocked", blocker: { kind: "proximity", span: [0, 1] } }),
    ).toBe(false);
  });
});

describe("terms that can't be written", () => {
  it("drops a box holding nothing a phrase can keep", () => {
    const added = addTerm(modelFor([["trust"]]), 0);
    expect(commitTerm(added.model, 0, added.id, '"').kind).toBe("unwritable");
    expect(commitTerm(added.model, 0, added.id, "  ").kind).toBe("removed");
  });
});
