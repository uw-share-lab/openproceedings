/**
 * Completion (Ctrl-Space; spec 05 §Components 1): field names, and after `venue:`, `track:` or `status:`
 * (also inside `field:(… OR …`) that field's values. Every suggestion comes from `/meta` (`text_fields`,
 * `filter_fields`, `values`): nothing is suggested before `/meta` answers, and no value is ever made up here.
 * It never opens by itself (`activateOnTyping: false` in the editor), so Enter always searches.
 */
import type {
  Completion,
  CompletionContext,
  CompletionResult,
  CompletionSource,
} from "@codemirror/autocomplete";
import { syntaxTree } from "@codemirror/language";
import type { Schemas } from "@/api/client";

export type Meta = Pick<Schemas["MetaResponse"], "text_fields" | "filter_fields" | "values">;
type ValueField = keyof Schemas["Vocabularies"];

const isValueField = (name: string): name is ValueField =>
  name === "venue" || name === "track" || name === "status";

/** The value field whose clause the cursor at `pos` is in, from the highlighting tree's tokens before it. */
function valueFieldAt(context: CompletionContext, pos: number): ValueField | null {
  const tokens: { name: string; from: number; to: number }[] = [];
  syntaxTree(context.state).iterate({
    to: pos,
    enter: (node) => {
      if (node.name !== "Query" && node.to <= pos)
        tokens.push({ name: node.name, from: node.from, to: node.to });
    },
  });
  // Walk back over a value group's contents (`track:(main OR |`) to the field that opens it.
  let k = tokens.length - 1;
  let inGroup = false;
  while (k >= 0) {
    const name = tokens[k]?.name;
    if (name === "Word" || name === "Or" || name === "Pipe") {
      k -= 1;
      continue;
    }
    if (name === "LParen" && !inGroup) {
      inGroup = true;
      k -= 1;
      break;
    }
    break;
  }
  const field = tokens[inGroup ? k : tokens.length - 1];
  if (field === undefined || field.name !== "Field") return null;
  // after the colon (`track:|`, or `track: |`, which the server also reads), or inside its group (`track:(…|`)
  if (!inGroup && context.state.sliceDoc(field.to, pos).trim() !== "") return null;
  const name = context.state.sliceDoc(field.from, field.to - 1).toLowerCase();
  return isValueField(name) ? name : null;
}

export function queryCompletions(getMeta: () => Meta | null): CompletionSource {
  return (context: CompletionContext): CompletionResult | null => {
    const meta = getMeta();
    if (meta === null) return null;
    const word = context.matchBefore(/[\p{L}\p{N}_]*/u);
    if (word === null || (word.from === word.to && !context.explicit)) return null;
    const field = valueFieldAt(context, word.from);
    const options: Completion[] =
      field !== null
        ? meta.values[field].map((value) => ({ label: value, type: "enum", detail: field }))
        : [...meta.text_fields, ...meta.filter_fields].map((name) => ({
            label: `${name}:`,
            type: "property",
            detail: "field",
          }));
    return { from: word.from, options, validFor: /^[\p{L}\p{N}_]*$/u };
  };
}
