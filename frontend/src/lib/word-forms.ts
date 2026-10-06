/**
 * "Add `$`" on the Scholar-mode no-stemming notice (TASK-175; spec 05 §Components 1, spec 02 §Word forms).
 *
 * `POST /parse` reports where a `$` can go (`word_forms`: a code-point offset `at` and the text `insert`), and
 * the server has parsed the query with every one inserted. This file only splices them into the draft: it
 * never finds a term, reads a message or decides what a `$` is valid on. The cases
 * (`word-forms-golden.json`) are generated from the server's own `wordforms.apply`, so the two write the same
 * string.
 */
import type { Schemas } from "@/api/client";
import { codePointSpanToUtf16 } from "@/api/spans";

export type WordForm = Schemas["WordForm"];
/** A term the notice names that `/parse` offers no `$` for, and why (`word_forms_skipped`, TASK-192). */
export type SkippedTerm = Schemas["SkippedTerm"];

/**
 * `text` with each of `forms` inserted (any subset of one `/parse` answer's, in any order), or `null` when an
 * offset doesn't fit `text`: the forms were reported for another text.
 */
export function withWordForms(text: string, forms: readonly WordForm[]): string | null {
  let out = text;
  try {
    // from the end, so an insert never moves an offset still to come
    for (const form of [...forms].sort((a, b) => b.at - a.at)) {
      const [at] = codePointSpanToUtf16(text, [form.at, form.at]);
      out = out.slice(0, at) + form.insert + out.slice(at);
    }
  } catch {
    return null;
  }
  return out;
}

/** The forms of one term, written in one or more places. */
export interface TermForms {
  readonly term: string;
  readonly forms: readonly WordForm[];
}

/** `forms` grouped by term, each term where it is first written: adding `$` to a term adds it in every place. */
export function byTerm(forms: readonly WordForm[]): TermForms[] {
  const terms = new Map<string, WordForm[]>();
  for (const form of forms) {
    const group = terms.get(form.term);
    if (group === undefined) terms.set(form.term, [form]);
    else group.push(form);
  }
  return [...terms].map(([term, group]) => ({ term, forms: group }));
}

/** The skipped terms of one reason. */
export interface ReasonTerms {
  readonly reason: string;
  readonly terms: readonly string[];
}

/** `skipped` grouped by the server's reason, each reason where it first appears (an open set: kept as sent). */
export function byReason(skipped: readonly SkippedTerm[]): ReasonTerms[] {
  const reasons = new Map<string, string[]>();
  for (const { term, reason } of skipped) {
    const group = reasons.get(reason);
    if (group === undefined) reasons.set(reason, [term]);
    else group.push(term);
  }
  return [...reasons].map(([reason, terms]) => ({ reason, terms }));
}
