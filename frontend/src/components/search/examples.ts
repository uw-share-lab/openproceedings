import type { Mode } from "@/lib/search-state";

export interface Example {
  readonly q: string;
  readonly mode: Mode;
}

/**
 * The Trust-Evals review's main search string, `main-7-most-updated` in
 * `backend/tests/fixtures/queries/trust-evals.txt`, verbatim, in Google Scholar syntax (design W1, pre-pass
 * S11). `transparency.test.tsx` checks it against that file, so it can't be retyped with a difference.
 */
export const REVIEW_EXAMPLE: Example = {
  q:
    '("foundation model" OR "large language model" OR LLM OR "generative AI") AND (trustworthiness OR ' +
    'trustworthy OR "trust" OR "trustworthy AI") AND (benchmark OR leaderboard OR "evaluation framework") AND ' +
    '(source:"ICLR" OR source:"international conference on learning representations" OR source:ICML OR ' +
    'source:"international conference on machine learning" OR source:PMLR OR ' +
    'source:"proceedings of machine learning research" OR source:NeurIPS OR ' +
    'source:"neural information processing systems" OR source:"advances in neural information processing systems")',
  mode: "scholar",
};

/** Plain examples in native syntax (ED-3 "More examples (native syntax):"). */
export const MORE_EXAMPLES: readonly Example[] = [
  { q: "trust* NEAR/5 calibrat*", mode: "native" },
  { q: '"large language model$" AND (benchmark OR leaderboard) year:2023..2026', mode: "native" },
];
