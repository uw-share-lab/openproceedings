import { describe, expect, it } from "vitest";
import { readGolden } from "./golden";
import { constructText, modelOf, readAst, type Shape } from "./read";

const spans = (nodes: readonly { span: readonly number[] }[]) => nodes.map((n) => [...n.span]);

function asGolden(shape: Shape) {
  return {
    groups: shape.groups.map(spans),
    exclude: shape.exclude === null ? null : spans(shape.exclude),
    exclude_at: shape.excludeAt,
    limits: spans(shape.limits),
  };
}

const cases = readGolden();

describe("the fit rule agrees with the backend's reference reading (builder-read-golden.json)", () => {
  it("has the cases the backend generated", () => {
    expect(cases.length).toBeGreaterThan(300);
  });

  it.each(cases.filter((c) => c.ast !== null).map((c) => [`${c.mode}: ${c.q}`, c] as const))("%s", (_, c) => {
    if (c.ast === null) throw new Error("filtered");
    const reading = readAst(c.ast);
    if (c.read === null) throw new Error("a parsed query always has a reading");
    if ("blocker" in c.read) {
      expect(reading).toEqual({ kind: "blocked", blocker: c.read.blocker });
    } else {
      expect(reading.kind).toBe("fits");
      if (reading.kind === "fits") expect(asGolden(reading.shape)).toEqual(c.read);
    }
  });
});

function fitting(q: string) {
  const c = cases.find((x) => x.q === q && x.mode === "native");
  if (c?.ast == null) throw new Error(`no native golden case ${q}`);
  const reading = readAst(c.ast);
  if (reading.kind !== "fits") throw new Error(`${q} doesn't fit`);
  return modelOf(q, reading.shape);
}

describe("modelOf", () => {
  it("reads the design's example: terms as typed, scopes on the chip, limits as written", () => {
    const model = fitting(
      '("foundation model" OR LLM) AND (trustworth* OR trust) AND benchmark AND venue:ICLR',
    );
    expect(model.groups.map((g) => g.terms.map((t) => t.text))).toEqual([
      ['"foundation model"', "LLM"],
      ["trustworth*", "trust"],
      ["benchmark"],
    ]);
    expect(model.limits).toEqual(["venue:ICLR"]);
    expect(model.exclude).toBeNull();
  });

  it("takes a leaf's own field prefix into its scope, and a field group's scope onto each leaf", () => {
    const own = fitting('Title:LLM OR abstract: "trust calibration"');
    expect(own.groups[0]?.terms.map((t) => [t.scope, t.text])).toEqual([
      ["title", "LLM"],
      ["abstract", '"trust calibration"'],
    ]);
    const shared = fitting("title:(a OR b) c");
    expect(shared.groups.map((g) => g.terms.map((t) => [t.scope, t.text]))).toEqual([
      [
        ["title", "a"],
        ["title", "b"],
      ],
      [["any", "c"]],
    ]);
  });

  it("reads a NOT as the Exclude row and keeps where it was written", () => {
    const model = fitting("NOT (bias OR fairness) trust");
    expect(model.exclude?.terms.map((t) => t.text)).toEqual(["bias", "fairness"]);
    expect(model.excludeAt).toBe(0);
    expect(fitting("trust -bias").excludeAt).toBe(1);
  });

  it("parenthesises an OR of limits the query left bare", () => {
    expect(fitting("venue:ICLR OR venue:ICML").limits).toEqual(["(venue:ICLR OR venue:ICML)"]);
    expect(fitting("venue:ICLR trust (venue:ICML OR venue:NeurIPS)").limits).toEqual([
      "venue:ICLR",
      "(venue:ICML OR venue:NeurIPS)",
    ]);
  });

  it("writes a Scholar unquoted phrase as a quoted one (decision-002)", () => {
    const c = cases.find((x) => x.q === "(large language model$ | LLM) source:ICLR");
    if (c?.ast == null) throw new Error("missing");
    const reading = readAst(c.ast);
    if (reading.kind !== "fits") throw new Error("doesn't fit");
    const model = modelOf(c.q, reading.shape);
    expect(model.groups[0]?.terms.map((t) => t.text)).toEqual(['"large language model$"', "LLM"]);
    expect(model.limits).toEqual(["source:ICLR"]);
  });

  it("reads main-7-most-updated in Scholar mode: three groups and its source limits as typed", () => {
    const c = cases.find(
      (x) => x.mode === "scholar" && x.q.startsWith('("foundation model"') && x.q.includes("PMLR"),
    );
    if (c?.ast == null) throw new Error("missing");
    const reading = readAst(c.ast);
    if (reading.kind !== "fits") throw new Error("doesn't fit");
    const model = modelOf(c.q, reading.shape);
    expect(model.groups).toHaveLength(3);
    expect(model.limits).toHaveLength(1);
    expect(model.limits[0]).toMatch(
      /^\(source:"ICLR" OR .* OR source:"advances in neural information processing systems"\)$/u,
    );
  });
});

describe("constructText", () => {
  it("names the blocking construct from the query text, clipped to 40 characters", () => {
    const q = "trust NEAR/5 calibrat*";
    expect(constructText(q, { kind: "proximity", span: [0, 22] })).toBe("trust NEAR/5 calibrat*");
    const long = `(${"a".repeat(50)} AND b) OR c`;
    const text = constructText(long, { kind: "AND inside OR", span: [0, Array.from(long).length] });
    expect(Array.from(text)).toHaveLength(40);
    expect(text.endsWith("…")).toBe(true);
  });
});
