/**
 * The query language for CodeMirror: highlighting only (spec 05 §Components 1; codemirror-lezer skill).
 * Colours come from the `--syn-*` tokens in globals.css (both themes, contrast-checked by tokens.test.ts), and
 * nothing is shown by colour alone: operators are bold, wildcards underlined, phrases italic, fields bold.
 */
import { HighlightStyle, LanguageSupport, LRLanguage, syntaxHighlighting } from "@codemirror/language";
import { styleTags, tags as t } from "@lezer/highlight";
import { parser } from "./parser";

export const queryLanguage = LRLanguage.define({
  name: "openproceedings-query",
  parser: parser.configure({
    props: [
      styleTags({
        "And Or Not Near Pipe Minus": t.logicOperator,
        Field: t.propertyName,
        Phrase: t.string,
        Wildcard: t.special(t.variableName),
        Range: t.number,
        "LParen RParen": t.paren,
        // Word, UnknownField and BadNear are left plain: the server's diagnostic says what is wrong with them.
      }),
    ],
  }),
});

export const queryHighlightStyle = HighlightStyle.define([
  { tag: t.logicOperator, color: "var(--syn-operator)", fontWeight: "700" },
  { tag: t.propertyName, color: "var(--syn-field)", fontWeight: "600" },
  { tag: t.string, color: "var(--syn-phrase)", fontStyle: "italic" },
  {
    tag: t.special(t.variableName),
    color: "var(--syn-wildcard)",
    textDecoration: "underline dotted",
    textUnderlineOffset: "3px",
  },
  { tag: t.number, color: "var(--syn-number)" },
  { tag: t.paren, fontWeight: "700" },
]);

export function query(): LanguageSupport {
  return new LanguageSupport(queryLanguage, [syntaxHighlighting(queryHighlightStyle)]);
}
