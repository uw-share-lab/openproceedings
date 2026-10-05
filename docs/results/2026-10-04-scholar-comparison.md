# Scholar comparison, 2026-10-04

- Index: `index_version` `05a0541717f6`, `tokenizer_version` `2`
- Snapshot: `2026-09-29-d552baa07aed`, `snapshot_hash` `d552baa07aed6bd754720c7ef17bc7d9ef7a645531fb95d6bc4174c2eacf91b8` (95,877 records)
- Scholar set: `mended.ris`, sha256 `ec0b1367acb6d3764780db0eb00b11868d1fe14ebe437b106aa4215ae7476a7b` (1,834 records)
- Scope, both sides: ICLR, ICML, NeurIPS; 2020–2026
- Queries: `main-7-most-updated`, `main-7-dollar`, `main-2-pop`
- Query file: `trust-evals.txt`, sha256 `16afdaff80f1c4767ea7e92d3854620ff73ed5beec192995743a03d97ee8e47c`
- Query file: `scholar-comparison-strings.txt`, sha256 `bc55c6e2dddb7300fea1608a0eaf6fb2f6bff2735babf95d777343fe1d81e56b`
- Notes: `scholar-comparison-notes.md`, sha256 `09ae6e3e7019217ffa66d1382296ac0abd576cd141b6303d67bea8098446d436`
- Command: `op eval scholar --ris mended.ris --query-file trust-evals.txt --query-file scholar-comparison-strings.txt --name main-7-most-updated --name main-7-dollar --name main-2-pop --years 2020..2026 --answers main-7-most-updated --notes scholar-comparison-notes.md --index 05a0541717f6 --date 2026-10-04`
- Review rows: `2026-10-04-scholar-comparison-review.csv` (683 rows, 162 unresolved)

**`our_bug`: 0** across 3 queries.

**What the matches rest on.** Of the 1,815 in-scope papers of the Scholar set, 1,807 match an index record: 1,277 a record with an independent source (a crawl), 530 a record whose only source is an imported RIS set. A match of the second kind is the set matching its own import, and says nothing about coverage (see Matching).

| query | Scholar set in scope | openproceedings in scope | both | only Scholar | only openproceedings | `full_text` | of them RIS-only | `stemming` | unresolved |
|---|---|---|---|---|---|---|---|---|---|
| `main-7-most-updated` | 1,815 | 27 | 21 | 1,794 | 6 | 1,713 (94.4%) | 466 | 30 (1.7%) | 57 |
| `main-7-dollar` † | 1,815 | 67 | 51 | 1,764 | 16 | 1,713 (94.4%) | 466 | 2 (0.1%) | 55 |
| `main-2-pop` † | 1,815 | 88 | 65 | 1,750 | 23 | 1,669 (92.0%) | 451 | 31 (1.7%) | 50 |

† The Scholar set is Google Scholar's answer to `main-7-most-updated` only. For `main-7-dollar`, `main-2-pop` the columns are what the string keeps, drops and adds against that same set, not a comparison with what Scholar returns for it.

## Matching the Scholar set to the index

Each Scholar record is matched by spec 01's merge rules, in their order: the OpenReview forum id its URL names, else the proceedings paper its URL names (the native id within that venue and year), else the dedup title key within the same venue and year. A title alone never matches. A matched record is scoped by its index record's venue and year, an unmatched one by its own; records outside the scope are dropped before comparing.

| | records |
|---|---|
| read | 1,834 |
| outside the scope (ICLR, ICML, NeurIPS; 2020–2026) | 19 |
| in scope | 1,815 |
| repeats of a paper already counted | 0 |
| **papers in scope** (the denominator of every percentage of the Scholar set) | **1,815** |

| matched by | papers |
|---|---|
| proceedings id | 1,636 |
| forum id | 169 |
| no match (no venue) | 5 |
| no match (not found) | 3 |
| title venue year | 2 |

`no match (no venue)`: 5 records whose venue string is empty or cut by Scholar (`…`) and whose URLs name no indexed paper, but whose title key an in-scope index record of the same year has. A title alone is never a match, so they are counted in scope and listed as `unsettled` for a person, with that record named.

Outside the scope: 19 venue unrecognised. `venue unrecognised` means the record's venue string is not exactly one of Scholar mode's source names and no URL of it names an indexed paper: it names another venue in full, or it is empty or cut (`…`) and no in-scope index record of its year has its title. Venue strings: International Conference on Machine … (2); International Conference … (2); (no venue) (1); 2025 International Conference on Machine Learning, Computational Intelligence and Pattern Recognition (MLCIPR) (1); Advances in neural information processing … (1); Conference on … (1); ICBINB (1); International Conference on Artificial Intelligence and Statistics (1); Machine learning for healthcare … (1); Proceedings of Machine … (1); arXiv.org (1); … Information Processing … (1); … International Conference on … (1); … Representations (1); … Systems (NeurIPS 2025), San Diego … (1); … of Machine Learning Research … (1); … of Machine Learning … (1).

### What the matches rest on

Matched to a record with an independent source (a crawl of OpenReview or the proceedings): **1,277**. Matched to a record whose only source is an imported RIS set (RIS-only): **530**.

A RIS-only record is in the index because a Scholar set was imported into it. When the set compared here is that set, such a match is the set matching itself: it shows nothing about coverage, and the title and abstract the classes are judged on are the ones the import carried. Counts below are given for both kinds.

| venue | year | matched papers | crawled record | RIS-only record | crawled records the index holds |
|---|---|---|---|---|---|
| ICLR | 2024 | 51 | 50 | 1 | 8,522 |
| ICLR | 2025 | 208 | 205 | 3 | 13,746 |
| ICLR | 2026 | 415 | 0 | 415 | 0 |
| ICML | 2022 | 1 | 1 | 0 | 1,233 |
| ICML | 2023 | 2 | 2 | 0 | 2,826 |
| ICML | 2024 | 11 | 11 | 0 | 4,124 |
| ICML | 2025 | 13 | 13 | 0 | 5,083 |
| ICML | 2026 | 111 | 0 | 111 | 0 |
| NeurIPS | 2023 | 27 | 27 | 0 | 5,961 |
| NeurIPS | 2024 | 336 | 336 | 0 | 7,561 |
| NeurIPS | 2025 | 632 | 632 | 0 | 10,687 |

Abstract source of the matched records: `openreview_v2` 1,275; `ris:proceedings_page` 385; `ris:openreview_api` 139; `none` 6; `neurips_proceedings` 1; `pmlr` 1. `ris:` is text the import carried (what scholarmend read from the proceedings page or the OpenReview API), not a crawl of this project.

The index holds **no crawled record** for ICLR 2026, ICML 2026, NeurIPS 2026. There, every match is to a RIS-only record, and no record can be only in openproceedings: that side of the comparison is empty by construction, not by agreement.

37 papers matched a RIS-only record whose title key another index record has too (1 in the same venue and year: one paper under two ids, so the set can count it twice; the others in another venue or year: the import's venue or year may be wrong). The match is kept, and each such row that is a disagreement is `unsettled`, for a person.

Scholar searches in the set (Publish or Perish query dates): 16; the largest holds 631 records. Google Scholar returns at most 1,000 per search; a search at the cap makes every record only in openproceedings from its venues and years `scholar_cap`. No search in this set reached it.

## Query `main-7-most-updated`

Run in `mode=scholar`, exactly as written (`canonical_hash` `7db5a89c5f78230fd8c4ce33fdf18100147f514e7e45d84c653bf699d8fc2e9d`):

```
("foundation model" OR "large language model" OR LLM OR "generative AI") AND (trustworthiness OR trustworthy OR "trust" OR "trustworthy AI") AND (benchmark OR leaderboard OR "evaluation framework") AND (source:"ICLR" OR source:"international conference on learning representations" OR source:ICML OR source:"international conference on machine learning" OR source:PMLR OR source:"proceedings of machine learning research" OR source:NeurIPS OR source:"neural information processing systems" OR source:"advances in neural information processing systems")
```

Canonical form, as run:

```
(("foundation model" OR "large language model" OR llm OR "generative ai") AND (trustworthiness OR trustworthy OR trust OR "trustworthy ai") AND (benchmark OR leaderboard OR "evaluation framework") AND venue:(ICLR OR ICML OR NeurIPS) AND track:(datasets_benchmarks OR main OR position) AND status:accepted)
```

Notices: `COMPAT_NO_STEMMING` × 1, `COMPAT_SOURCE_ALIAS` × 9, `WARN_SOURCE_PARTIAL` × 2.

| | records |
|---|---|
| Scholar set, in scope | 1,815 |
| openproceedings `total` (default filters; every venue and year) | 27 |
| openproceedings, in scope | 27 |
| in both | 21 (15 crawled records, 6 RIS-only) |
| in both, matched to a RIS-only record whose title another index record has | 0 |
| only in the Scholar set | 1,794 |
| only in openproceedings | 6 |

### Only in the Scholar set

| class | records | of these | of the Scholar set | crawled record | RIS-only record | meaning |
|---|---|---|---|---|---|---|
| `our_bug` | 0 | 0.0% | 0.0% | 0 | 0 | the oracle and the served engine disagree (must be 0) |
| `coverage_gap` | 3 | 0.2% | 0.2% | 0 | 0 | no record in the snapshot by forum id, proceedings id or title+venue+year |
| `stemming` | 30 | 1.7% | 1.7% | 15 | 15 | matches title or abstract only with an inflected form added |
| `full_text` | 1,713 | 95.5% | 94.4% | 1,247 | 466 | in the corpus with an abstract; no reading matches its title or abstract, inflected forms included |
| `unsettled` | 48 | 2.7% | 2.6% | 0 | 43 | the automation can't tell (see the row's evidence) |
| total | 1,794 | 100.0% | 98.8% | 1,262 | 524 | |

`crawled record` and `RIS-only record` say what the row's index record rests on (a row with no index record is in neither).

### Only in openproceedings

| class | records | of these | of the result | crawled record | RIS-only record | meaning |
|---|---|---|---|---|---|---|
| `our_bug` | 0 | 0.0% | 0.0% | 0 | 0 | the oracle and the served engine disagree (must be 0) |
| `scholar_missed` | 6 | 100.0% | 22.2% | 6 | 0 | an exact title or abstract match that the Scholar set lacks |
| total | 6 | 100.0% | 22.2% | 6 | 0 | |

`our_bug`: **0**. Rows for a person in `review.csv`: 57 unresolved, 175 spot check.

### Concept groups, over the 1,807 Scholar papers the index holds

How many of them hold each top-level group of the string in title or abstract, whatever their track and status:

| group | as run | with inflected forms |
|---|---|---|
| 1. `("foundation model" OR "large language model" OR llm OR "generative ai")` | 549 | 1,011 |
| 2. `(trustworthiness OR trustworthy OR trust OR "trustworthy ai")` | 191 | 197 |
| 3. `(benchmark OR leaderboard OR "evaluation framework")` | 477 | 794 |

Inflected forms added for the `stemming` test (the forms the compared records hold): `benchmark` → benchmarked, benchmarking, benchmarks; `evaluation` → evaluations; `foundation` → foundations; `framework` → frameworks; `language` → languages; `leaderboard` → leaderboards; `llm` → llms; `model` → modeled, modeling, models; `trust` → trusted, trusting.

### Scholar-only records listed

| record | title | venue | year | class | evidence |
|---|---|---|---|---|---|
| `op:iclr:2024:iclr-c3eb94d149aea08c28505d1e5234a21a` | Less is more: One-shot subgraph reasoning on large-scale knowledge graphs | ICLR | 2024 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:iclr:2024:QHROe7Mfcb (ICLR 2024): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 1, 2, inflected forms included) |
| `op:iclr:2026:iclr-2aa212d6f40c1cb19b777e83db00ec6a` | Audiotrust: Benchmarking the multifaceted trustworthiness of audio large language models | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:neurips:2025:3CyLAUi3cO (NeurIPS 2025): possibly one paper under two ids; otherwise `stemming` (matches with models) |
| `op:iclr:2026:iclr-c6c29e590e3c62e37e6b39cdd6baf2e8` | St-webagentbench: A benchmark for evaluating safety and trustworthiness in web agents | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:iclr:2025:IIzehISTBe (ICLR 2025); op:icml:2025:fAmhr96SUw (ICML 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 1, inflected forms included) |
| `op:iclr:2026:iclr-bb3a308fd06c7f88ba5a81af60e8977a` | In agents we trust, but who do agents trust? latent source preferences steer LLM generations | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:icml:2025:oZMisPPggL (ICML 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 3, inflected forms included) |
| `op:iclr:2026:iclr-2fb00c27ddcb782ae41066b2b037630f` | Get RICH or Die Scaling: Profitably Trading Inference Compute for Robustness | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:neurips:2025:dZRCZUvKPj (NeurIPS 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 2, 3, inflected forms included) |
| `op:iclr:2026:iclr-9334fd3a5170dbfe74eae4755f6c5f89` | Steering evaluation-aware language models to act like they are deployed | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:neurips:2025:RCjtIoy7zh (NeurIPS 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 2, 3, inflected forms included) |
| `op:iclr:2026:iclr-1a96349bbc03432c5ec8c6c502d102e7` | Do large language models know what they are capable of? | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:neurips:2025:IPGR4uXxvg (NeurIPS 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 2, 3, inflected forms included) |
| `op:iclr:2026:iclr-92d777fb721936613b6444b07c4ffc18` | Dropping just a handful of preferences can change top large language model rankings | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:icml:2025:b9r1snfxIH (ICML 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 2, 3, inflected forms included) |
| `op:iclr:2026:iclr-fd1eff9dd295df50a41f2521942fa31d` | Evaluating memory in llm agents via incremental multi-turn interactions | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:icml:2025:ZgQ0t3zYTQ (ICML 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 2, inflected forms included) |
| `op:iclr:2026:iclr-6297baf3f5c98146b62dd3a1bffe068e` | Preference leakage: A contamination problem in llm-as-a-judge | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:icml:2025:gW6NT2IuME (ICML 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 2, inflected forms included) |
| `op:iclr:2026:iclr-a24cd16bc361afa78e57d31d34f3d936` | Your agent may misevolve: Emergent risks in self-evolving llm agents | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:neurips:2025:lS1gWUHbfx (NeurIPS 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 3, inflected forms included) |
| `op:iclr:2026:iclr-eaa3d3f05ae14240b7a6a250ce6ddcd7` | Dragon: Guard llm unlearning in context via negative detection and reasoning | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:icml:2025:ET24oKP23c (ICML 2025); op:neurips:2025:FNuul0hlin (NeurIPS 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 2, 3, inflected forms included) |
| `op:iclr:2026:iclr-0fb49ffa040d13a491c7164c5912cf7d` | Sophiavl-r1: Reinforcing mllms reasoning with thinking reward | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:neurips:2025:iJ4i5HE5ER (NeurIPS 2025): possibly one paper under two ids; otherwise `stemming` (matches with benchmarks, models) |
| `op:iclr:2026:iclr-4444eb0b68174180d2a46841c951e7f3` | Benchmarking overton pluralism in llms | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:neurips:2025:Mq3QUs7FAp (NeurIPS 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 2, inflected forms included) |
| `op:iclr:2026:iclr-5fc8b3bdfbb9167b5144df5d3fae4616` | Mem1: Learning to synergize memory and reasoning for efficient long-horizon agents | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:neurips:2025:jJ6F1sDn9i (NeurIPS 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 2, 3, inflected forms included) |
| `op:iclr:2026:iclr-799b39274bdfeea24be0a3ccf304107e` | ZeroTuning: Unlocking the Initial Token's Power to Enhance Large Language Models Without Training | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:icml:2025:THSbsRWy9v (ICML 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 2, 3, inflected forms included) |
| `op:iclr:2026:iclr-b51362de8ffda06bcdf0bc538a1a0fc1` | Unlearning Isn't Invisible: Detecting Unlearning Traces in LLMs from Model Outputs | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:icml:2025:qvZhRdQ0QE (ICML 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 2, 3, inflected forms included) |
| `op:iclr:2026:iclr-c9d780d1e2d57d4b70e807608a72501b` | Arms: Adaptive red-teaming agent against multimodal models with plug-and-play attacks | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:neurips:2025:5jOqGe6CxS (NeurIPS 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 1, 2, inflected forms included) |
| `op:iclr:2026:iclr-5b288823575bb29654b0953a251e933b` | Diffuguard: How intrinsic safety is lost and found in diffusion large language models | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:neurips:2025:r3cDmnicYh (NeurIPS 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 2, 3, inflected forms included) |
| `op:iclr:2026:iclr-3bf80b34f731313b8292f4578e820c90` | Deep ignorance: Filtering pretraining data builds tamper-resistant safeguards into open-weight llms | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:neurips:2025:lZGgc845Uz (NeurIPS 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 2, 3, inflected forms included) |
| `op:iclr:2026:iclr-033f2b82bf0f35add31a88d76f041f58` | Detecting data contamination in llms via in-context learning | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:neurips:2025:eWObAa0Uaw (NeurIPS 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 2, inflected forms included) |
| `op:iclr:2026:iclr-b77b5f1a2878fedd4705bfeafd24ca35` | Aside: Architectural separation of instructions and data in language models | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:iclr:2025:GlmqRQsCaI (ICLR 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 2, inflected forms included) |
| `op:iclr:2026:iclr-fd8872fcba4ba87312cdfe5ebba91ca9` | BA-loRA: Bias-alleviating low-rank adaptation to mitigate catastrophic inheritance in large language models | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:iclr:2025:d465apqCqc (ICLR 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 2, 3, inflected forms included) |
| `op:iclr:2026:iclr-9bf12308ece130daa083fb21f7faf1b6` | Customizing visual emotion evaluation for mllms: An open-vocabulary, multifaceted, and scalable approach | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:neurips:2025:O8Hu5u0v1A (NeurIPS 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 2, inflected forms included) |
| `op:iclr:2026:iclr-a7060588538c3ca1ef2fb071db9e5630` | Medical thinking with multiple images | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:neurips:2025:dynv2pD1cN (NeurIPS 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 2, inflected forms included) |
| `op:iclr:2026:iclr-524ff06d5375d76e93d8490e654a81bf` | Simpletom: Exposing the gap between explicit tom inference and implicit tom application in llms | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:iclr:2025:ZzATfnskP1 (ICLR 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 2, inflected forms included) |
| `op:iclr:2026:iclr-b0832cc57899cfd2d3fedeb3f330ba80` | Omni-reward: Towards generalist omni-modal reward modeling with free-form preferences | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:neurips:2025:FEixSLhANJ (NeurIPS 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 1, 2, inflected forms included) |
| `op:iclr:2026:iclr-02c1d1d33dbfbaf03b3971bb542e72e2` | JailbreakloRA: Your downloaded loRA from sharing platforms might be unsafe | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:icml:2025:RjaeiNswGh (ICML 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 2, 3, inflected forms included) |
| `op:iclr:2026:iclr-bbd35a35873e1e447b14b0932af87af0` | Beyond magic words: Sharpness-aware prompt evolving for robust large language models with tare | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:neurips:2025:3yhOA0BZsK (NeurIPS 2025); op:neurips:2025:lyIhSyyaU4 (NeurIPS 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 2, 3, inflected forms included) |
| `op:iclr:2026:iclr-ed67dff7cb96e7e86c4d91c0d5db49bb` | Attributing response to context: A jensen–shannon divergence driven mechanistic study of context attribution in retrieval-augmented generation | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:neurips:2025:UyXjYlJij3 (NeurIPS 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 2, inflected forms included) |
| `op:iclr:2026:iclr-f5846131aa6a72d1df3bd6d43a4a960b` | LUMINA: Detecting hallucinations in RAG system with context–knowledge signals | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:neurips:2025:fRUW4qbET3 (NeurIPS 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 2, inflected forms included) |
| `op:iclr:2026:iclr-607864303db1f2bea942b4a9d462920c` | Weak-to-strong diffusion with reflection | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:iclr:2025:wllm64LuJN (ICLR 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 1, 2, inflected forms included) |
| `op:iclr:2026:iclr-5810666374031717089033d95f9973ea` | Adaptive Logit Adjustment for Debiasing Multimodal Language Models | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:neurips:2025:hMlUGoMsEK (NeurIPS 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 1, 2, 3, inflected forms included) |
| `op:iclr:2026:iclr-23b9ed90f5eed45cdf12a9abb31308be` | MaskInversion: Localized embeddings via optimization of explainability maps | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:iclr:2025:DhlbK7tAjz (ICLR 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 2, 3, inflected forms included) |
| `op:iclr:2026:iclr-08a362bd4ae1934e099ce025f06039fe` | Rote learning considered useful: generalizing over memorized data in LLMs | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:icml:2025:vNOA396J3q (ICML 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 2, 3, inflected forms included) |
| `op:iclr:2026:iclr-b2f56a345fe0ce337df3bdfb31e2b350` | Towards Better Branching Policies: Leveraging the Sequential Nature of Branch-and-Bound Tree | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:neurips:2025:fwJ1rRHT91 (NeurIPS 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 1, 2, 3, inflected forms included) |
| `op:iclr:2026:iclr-3327377ee37b8c87c43a7d6a4ea3d279` | Decoupling the class label and the target concept in machine unlearning | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:iclr:2025:OHOmpkGiYK (ICLR 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 1, 2, 3, inflected forms included) |
| `op:icml:2026:JoJUWsQBp0` | Can LLM Agents Stick to the Script? Modeling Commitment in Interactive Narratives | ICML | 2026 | `unsettled` | no title match, and the corpus has no abstract for it |
| `op:icml:2026:5Qpy3uTD05` | Domain Restriction via SAE Multi-Layer Transitions | ICML | 2026 | `unsettled` | no title match, and the corpus has no abstract for it |
| `op:icml:2026:dzcDbh8ewp` | LECTOR: Joint Learning of Scientific Reasoning Graphs and Introduction Generation | ICML | 2026 | `unsettled` | no title match, and the corpus has no abstract for it |
| `op:icml:2026:goUAT3UcR4` | * MemPot*: Defend Against Memory Extraction Attack with Optimized Honeypots | ICML | 2026 | `unsettled` | no title match, and the corpus has no abstract for it |
| `op:icml:2026:IBLJ5MNcgy` | Bridging the Grounding Gap in VideoQA via Typed Memory for Language-based Belief-State Reasoning | ICML | 2026 | `unsettled` | no title match, and the corpus has no abstract for it |
| `op:icml:2026:LD9mlgF5WU` | VR-Thinker: Boosting Multimodal Reward Models through Think with Image Reasoning | ICML | 2026 | `unsettled` | no title match, and the corpus has no abstract for it |
| `mended.ris#3` | Building a stable classifier with the inflated argmax |  | 2024 | `unsettled` | its venue string is no venue, so no title match is made; same title: op:neurips:2024:M7zNXntzsp (NeurIPS 2024) |
| `mended.ris#4` | Selective Explanations |  | 2024 | `unsettled` | its venue string is no venue, so no title match is made; same title: op:neurips:2024:gHCFduRo7o (NeurIPS 2024) |
| `mended.ris#143` | Crafting interpretable embeddings for language neuroscience by asking LLMs questions | … processing systems | 2024 | `unsettled` | its venue string is no venue, so no title match is made; same title: op:neurips:2024:mxMvWwyBWe (NeurIPS 2024) |
| `mended.ris#437` | Loss function with memory for trustworthiness threshold learning: Case of face and facial expression recognition | ICML | 2022 | `coverage_gap` | no forum id, proceedings id or title+venue+year match in the snapshot; its links are on link.springer.com, www.researchgate.net |
| `mended.ris#441` | Decodingtrust: A comprehensive assessment of trustworthiness in {GPT} models |  | 2023 | `unsettled` | its venue string is no venue, so no title match is made; same title: op:neurips:2023:kaHpo8OZw2 (NeurIPS 2023) |
| `mended.ris#442` | Foundational Robustness of Foundation Models | NeurIPS | 2022 | `coverage_gap` | no forum id, proceedings id or title+venue+year match in the snapshot; its links are on neurips.cc |
| `mended.ris#1072` | AugGen: Synthetic Augmentation using Diffusion Models Can Improve Recognition | Advances in Neural … | 2025 | `unsettled` | its venue string is no venue, so no title match is made; same title: op:neurips:2025:LuKlBH8DAT (NeurIPS 2025) |
| `mended.ris#1790` | Fusing Large Language Models and LDA for Attribute Mining in Online Reviews | ICML | 2025 | `coverage_gap` | no forum id, proceedings id or title+venue+year match in the snapshot; its links are on ieeexplore.ieee.org |

### Records only in openproceedings

| record | title | venue | year | class | evidence |
|---|---|---|---|---|---|
| `op:iclr:2024:UMfcdRIotC` | Faithful Explanations of Black-box NLP Models Using LLM-generated Counterfactuals | ICLR | 2024 | `scholar_missed` | exact match on group 1: "large language model" (abstract), llm (title+abstract); group 2: trust (abstract); group 3: benchmark (abstract) |
| `op:iclr:2024:fsW7wJGLBd` | Tensor Trust: Interpretable Prompt Injection Attacks from an Online Game | ICLR | 2024 | `scholar_missed` | exact match on group 1: llm (abstract); group 2: trust (title+abstract); group 3: benchmark (abstract) |
| `op:iclr:2025:UHPnqSTBPO` | Trust or Escalate: LLM Judges with Provable Guarantees for Human Agreement | ICLR | 2025 | `scholar_missed` | exact match on group 1: llm (title+abstract); group 2: trust (title+abstract); group 3: "evaluation framework" (abstract) |
| `op:icml:2025:V61nluxFlR` | Aligning with Logic: Measuring, Evaluating and Improving Logical Preference Consistency in Large Language Models | ICML | 2025 | `scholar_missed` | exact match on group 1: llm (abstract); group 2: trustworthy (abstract); group 3: "evaluation framework" (abstract) |
| `op:icml:2025:j3totqf8xW` | Position: Beyond Assistance – Reimagining LLMs as Ethical and Adaptive Co-Creators in Mental Health Care | ICML | 2025 | `scholar_missed` | exact match on group 1: llm (abstract); group 2: trustworthiness (abstract); group 3: "evaluation framework" (abstract) |
| `op:neurips:2025:XwqawBglmv` | LC-Opt: Benchmarking Reinforcement Learning and Agentic AI for End-to-End Liquid Cooling Optimization in Data Centers | NeurIPS | 2025 | `scholar_missed` | exact match on group 1: llm (abstract); group 2: trust (abstract); group 3: benchmark (abstract) |

**Finding.** Of the 1,815 in-scope papers of the Scholar set, 1,713 (94.4%) match this string nowhere in title or abstract, inflected forms included (`full_text`), and 30 (1.7%) match only through an inflected form (`stemming`). 21 (1.2%) are in the exact result.

- Of the 1,713 `full_text` papers, 1,247 rest on a crawled record and 466 on a RIS-only record, whose title and abstract are the import's own.
- 2 of them also fail the default track or status filters.
- **Sensitivity to the stemmer.** The `stemming` class uses an inflection-only stand-in (see Method); which stemmer stands for Scholar's is an open decision for the project owner. With every searched word replaced by its inflection stem read as a prefix (`benchmarks` → `benchmark*`, `evaluating` → `evaluat*`), 0 of the 1,713 (0.0%) `full_text` papers would match title or abstract. That is all this figure measures: it is not a stemmer, and one that strips derivational endings (`evaluation` to `evaluat`) or rewrites the stem could move more.

## Query `main-7-dollar`

The Scholar set is Google Scholar's answer to `main-7-most-updated`, not to this string. The numbers below are what this string keeps, drops and adds against that set; they say nothing about what Scholar would return for it.

Run in `mode=scholar`, exactly as written (`canonical_hash` `69733056ecf7c223925f2b885e9a074ca641db6f36a4b67277c634f88961350c`):

```
("foundation model$" OR "large language model$" OR LLM$ OR "generative AI") AND (trustworthiness OR trustworthy OR "trust" OR "trustworthy AI") AND (benchmark$ OR leaderboard$ OR "evaluation framework$") AND (source:"ICLR" OR source:"international conference on learning representations" OR source:ICML OR source:"international conference on machine learning" OR source:PMLR OR source:"proceedings of machine learning research" OR source:NeurIPS OR source:"neural information processing systems" OR source:"advances in neural information processing systems") AND year:2020..2026
```

Canonical form, as run:

```
(("foundation model$" OR "large language model$" OR llm$ OR "generative ai") AND (trustworthiness OR trustworthy OR trust OR "trustworthy ai") AND (benchmark$ OR leaderboard$ OR "evaluation framework$") AND venue:(ICLR OR ICML OR NeurIPS) AND year:2020..2026 AND track:(datasets_benchmarks OR main OR position) AND status:accepted)
```

Notices: `COMPAT_NO_STEMMING` × 1, `COMPAT_POP_DOLLAR` × 6, `COMPAT_SOURCE_ALIAS` × 9, `WARN_SOURCE_PARTIAL` × 2.

Google Scholar reads this string differently from Scholar mode. Scholar's reading, written natively:

```
(("foundation model" OR "large language model" OR llm OR "generative ai") AND (trustworthiness OR trustworthy OR trust OR "trustworthy ai") AND (benchmark OR leaderboard OR "evaluation framework") AND venue:(ICLR OR ICML OR NeurIPS) AND year:2020..2026 AND track:(datasets_benchmarks OR main OR position) AND status:accepted)
```

| | records |
|---|---|
| Scholar set, in scope | 1,815 |
| openproceedings `total` (default filters; every venue and year) | 67 |
| openproceedings, in scope | 67 |
| in both | 51 (30 crawled records, 21 RIS-only) |
| in both, matched to a RIS-only record whose title another index record has | 2 |
| only in the Scholar set | 1,764 |
| only in openproceedings | 16 |

### Only in the Scholar set

| class | records | of these | of the Scholar set | crawled record | RIS-only record | meaning |
|---|---|---|---|---|---|---|
| `our_bug` | 0 | 0.0% | 0.0% | 0 | 0 | the oracle and the served engine disagree (must be 0) |
| `coverage_gap` | 3 | 0.2% | 0.2% | 0 | 0 | no record in the snapshot by forum id, proceedings id or title+venue+year |
| `stemming` | 2 | 0.1% | 0.1% | 0 | 2 | matches title or abstract only with an inflected form added |
| `full_text` | 1,713 | 97.1% | 94.4% | 1,247 | 466 | in the corpus with an abstract; no reading matches its title or abstract, inflected forms included |
| `unsettled` | 46 | 2.6% | 2.5% | 0 | 41 | the automation can't tell (see the row's evidence) |
| total | 1,764 | 100.0% | 97.2% | 1,247 | 509 | |

`crawled record` and `RIS-only record` say what the row's index record rests on (a row with no index record is in neither).

### Only in openproceedings

| class | records | of these | of the result | crawled record | RIS-only record | meaning |
|---|---|---|---|---|---|---|
| `our_bug` | 0 | 0.0% | 0.0% | 0 | 0 | the oracle and the served engine disagree (must be 0) |
| `compat_reading` | 10 | 62.5% | 14.9% | 10 | 0 | decided by how Scholar mode read the string (decision-002 phrases, `$`), not by the corpus |
| `scholar_missed` | 6 | 37.5% | 9.0% | 6 | 0 | an exact title or abstract match that the Scholar set lacks |
| total | 16 | 100.0% | 23.9% | 16 | 0 | |

`our_bug`: **0**. Rows for a person in `review.csv`: 55 unresolved, 173 spot check.

### Concept groups, over the 1,807 Scholar papers the index holds

How many of them hold each top-level group of the string in title or abstract, whatever their track and status:

| group | as run | with inflected forms |
|---|---|---|
| 1. `("foundation model$" OR "large language model$" OR llm$ OR "generative ai")` | 1,011 | 1,011 |
| 2. `(trustworthiness OR trustworthy OR trust OR "trustworthy ai")` | 191 | 197 |
| 3. `(benchmark$ OR leaderboard$ OR "evaluation framework$")` | 784 | 794 |

Inflected forms added for the `stemming` test (the forms the compared records hold): `benchmark` → benchmarked, benchmarking, benchmarks; `evaluation` → evaluations; `foundation` → foundations; `framework` → frameworks; `language` → languages; `leaderboard` → leaderboards; `llm` → llms; `model` → modeled, modeling, models; `trust` → trusted, trusting.

### Scholar-only records listed

| record | title | venue | year | class | evidence |
|---|---|---|---|---|---|
| `op:iclr:2024:iclr-c3eb94d149aea08c28505d1e5234a21a` | Less is more: One-shot subgraph reasoning on large-scale knowledge graphs | ICLR | 2024 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:iclr:2024:QHROe7Mfcb (ICLR 2024): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 1, 2, inflected forms included) |
| `op:iclr:2026:iclr-c6c29e590e3c62e37e6b39cdd6baf2e8` | St-webagentbench: A benchmark for evaluating safety and trustworthiness in web agents | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:iclr:2025:IIzehISTBe (ICLR 2025); op:icml:2025:fAmhr96SUw (ICML 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 1, inflected forms included) |
| `op:iclr:2026:iclr-bb3a308fd06c7f88ba5a81af60e8977a` | In agents we trust, but who do agents trust? latent source preferences steer LLM generations | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:icml:2025:oZMisPPggL (ICML 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 3, inflected forms included) |
| `op:iclr:2026:iclr-2fb00c27ddcb782ae41066b2b037630f` | Get RICH or Die Scaling: Profitably Trading Inference Compute for Robustness | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:neurips:2025:dZRCZUvKPj (NeurIPS 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 2, 3, inflected forms included) |
| `op:iclr:2026:iclr-9334fd3a5170dbfe74eae4755f6c5f89` | Steering evaluation-aware language models to act like they are deployed | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:neurips:2025:RCjtIoy7zh (NeurIPS 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 2, 3, inflected forms included) |
| `op:iclr:2026:iclr-1a96349bbc03432c5ec8c6c502d102e7` | Do large language models know what they are capable of? | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:neurips:2025:IPGR4uXxvg (NeurIPS 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 2, 3, inflected forms included) |
| `op:iclr:2026:iclr-92d777fb721936613b6444b07c4ffc18` | Dropping just a handful of preferences can change top large language model rankings | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:icml:2025:b9r1snfxIH (ICML 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 2, 3, inflected forms included) |
| `op:iclr:2026:iclr-fd1eff9dd295df50a41f2521942fa31d` | Evaluating memory in llm agents via incremental multi-turn interactions | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:icml:2025:ZgQ0t3zYTQ (ICML 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 2, inflected forms included) |
| `op:iclr:2026:iclr-6297baf3f5c98146b62dd3a1bffe068e` | Preference leakage: A contamination problem in llm-as-a-judge | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:icml:2025:gW6NT2IuME (ICML 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 2, inflected forms included) |
| `op:iclr:2026:iclr-a24cd16bc361afa78e57d31d34f3d936` | Your agent may misevolve: Emergent risks in self-evolving llm agents | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:neurips:2025:lS1gWUHbfx (NeurIPS 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 3, inflected forms included) |
| `op:iclr:2026:iclr-eaa3d3f05ae14240b7a6a250ce6ddcd7` | Dragon: Guard llm unlearning in context via negative detection and reasoning | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:icml:2025:ET24oKP23c (ICML 2025); op:neurips:2025:FNuul0hlin (NeurIPS 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 2, 3, inflected forms included) |
| `op:iclr:2026:iclr-4444eb0b68174180d2a46841c951e7f3` | Benchmarking overton pluralism in llms | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:neurips:2025:Mq3QUs7FAp (NeurIPS 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 2, inflected forms included) |
| `op:iclr:2026:iclr-5fc8b3bdfbb9167b5144df5d3fae4616` | Mem1: Learning to synergize memory and reasoning for efficient long-horizon agents | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:neurips:2025:jJ6F1sDn9i (NeurIPS 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 2, 3, inflected forms included) |
| `op:iclr:2026:iclr-799b39274bdfeea24be0a3ccf304107e` | ZeroTuning: Unlocking the Initial Token's Power to Enhance Large Language Models Without Training | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:icml:2025:THSbsRWy9v (ICML 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 2, 3, inflected forms included) |
| `op:iclr:2026:iclr-b51362de8ffda06bcdf0bc538a1a0fc1` | Unlearning Isn't Invisible: Detecting Unlearning Traces in LLMs from Model Outputs | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:icml:2025:qvZhRdQ0QE (ICML 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 2, 3, inflected forms included) |
| `op:iclr:2026:iclr-c9d780d1e2d57d4b70e807608a72501b` | Arms: Adaptive red-teaming agent against multimodal models with plug-and-play attacks | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:neurips:2025:5jOqGe6CxS (NeurIPS 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 1, 2, inflected forms included) |
| `op:iclr:2026:iclr-5b288823575bb29654b0953a251e933b` | Diffuguard: How intrinsic safety is lost and found in diffusion large language models | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:neurips:2025:r3cDmnicYh (NeurIPS 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 2, 3, inflected forms included) |
| `op:iclr:2026:iclr-3bf80b34f731313b8292f4578e820c90` | Deep ignorance: Filtering pretraining data builds tamper-resistant safeguards into open-weight llms | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:neurips:2025:lZGgc845Uz (NeurIPS 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 2, 3, inflected forms included) |
| `op:iclr:2026:iclr-033f2b82bf0f35add31a88d76f041f58` | Detecting data contamination in llms via in-context learning | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:neurips:2025:eWObAa0Uaw (NeurIPS 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 2, inflected forms included) |
| `op:iclr:2026:iclr-b77b5f1a2878fedd4705bfeafd24ca35` | Aside: Architectural separation of instructions and data in language models | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:iclr:2025:GlmqRQsCaI (ICLR 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 2, inflected forms included) |
| `op:iclr:2026:iclr-fd8872fcba4ba87312cdfe5ebba91ca9` | BA-loRA: Bias-alleviating low-rank adaptation to mitigate catastrophic inheritance in large language models | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:iclr:2025:d465apqCqc (ICLR 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 2, 3, inflected forms included) |
| `op:iclr:2026:iclr-9bf12308ece130daa083fb21f7faf1b6` | Customizing visual emotion evaluation for mllms: An open-vocabulary, multifaceted, and scalable approach | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:neurips:2025:O8Hu5u0v1A (NeurIPS 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 2, inflected forms included) |
| `op:iclr:2026:iclr-a7060588538c3ca1ef2fb071db9e5630` | Medical thinking with multiple images | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:neurips:2025:dynv2pD1cN (NeurIPS 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 2, inflected forms included) |
| `op:iclr:2026:iclr-524ff06d5375d76e93d8490e654a81bf` | Simpletom: Exposing the gap between explicit tom inference and implicit tom application in llms | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:iclr:2025:ZzATfnskP1 (ICLR 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 2, inflected forms included) |
| `op:iclr:2026:iclr-b0832cc57899cfd2d3fedeb3f330ba80` | Omni-reward: Towards generalist omni-modal reward modeling with free-form preferences | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:neurips:2025:FEixSLhANJ (NeurIPS 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 1, 2, inflected forms included) |
| `op:iclr:2026:iclr-02c1d1d33dbfbaf03b3971bb542e72e2` | JailbreakloRA: Your downloaded loRA from sharing platforms might be unsafe | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:icml:2025:RjaeiNswGh (ICML 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 2, 3, inflected forms included) |
| `op:iclr:2026:iclr-bbd35a35873e1e447b14b0932af87af0` | Beyond magic words: Sharpness-aware prompt evolving for robust large language models with tare | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:neurips:2025:3yhOA0BZsK (NeurIPS 2025); op:neurips:2025:lyIhSyyaU4 (NeurIPS 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 2, 3, inflected forms included) |
| `op:iclr:2026:iclr-ed67dff7cb96e7e86c4d91c0d5db49bb` | Attributing response to context: A jensen–shannon divergence driven mechanistic study of context attribution in retrieval-augmented generation | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:neurips:2025:UyXjYlJij3 (NeurIPS 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 2, inflected forms included) |
| `op:iclr:2026:iclr-f5846131aa6a72d1df3bd6d43a4a960b` | LUMINA: Detecting hallucinations in RAG system with context–knowledge signals | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:neurips:2025:fRUW4qbET3 (NeurIPS 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 2, inflected forms included) |
| `op:iclr:2026:iclr-607864303db1f2bea942b4a9d462920c` | Weak-to-strong diffusion with reflection | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:iclr:2025:wllm64LuJN (ICLR 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 1, 2, inflected forms included) |
| `op:iclr:2026:iclr-5810666374031717089033d95f9973ea` | Adaptive Logit Adjustment for Debiasing Multimodal Language Models | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:neurips:2025:hMlUGoMsEK (NeurIPS 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 1, 2, 3, inflected forms included) |
| `op:iclr:2026:iclr-23b9ed90f5eed45cdf12a9abb31308be` | MaskInversion: Localized embeddings via optimization of explainability maps | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:iclr:2025:DhlbK7tAjz (ICLR 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 2, 3, inflected forms included) |
| `op:iclr:2026:iclr-08a362bd4ae1934e099ce025f06039fe` | Rote learning considered useful: generalizing over memorized data in LLMs | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:icml:2025:vNOA396J3q (ICML 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 2, 3, inflected forms included) |
| `op:iclr:2026:iclr-b2f56a345fe0ce337df3bdfb31e2b350` | Towards Better Branching Policies: Leveraging the Sequential Nature of Branch-and-Bound Tree | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:neurips:2025:fwJ1rRHT91 (NeurIPS 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 1, 2, 3, inflected forms included) |
| `op:iclr:2026:iclr-3327377ee37b8c87c43a7d6a4ea3d279` | Decoupling the class label and the target concept in machine unlearning | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:iclr:2025:OHOmpkGiYK (ICLR 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 1, 2, 3, inflected forms included) |
| `op:icml:2026:JoJUWsQBp0` | Can LLM Agents Stick to the Script? Modeling Commitment in Interactive Narratives | ICML | 2026 | `unsettled` | no title match, and the corpus has no abstract for it |
| `op:icml:2026:5Qpy3uTD05` | Domain Restriction via SAE Multi-Layer Transitions | ICML | 2026 | `unsettled` | no title match, and the corpus has no abstract for it |
| `op:icml:2026:dzcDbh8ewp` | LECTOR: Joint Learning of Scientific Reasoning Graphs and Introduction Generation | ICML | 2026 | `unsettled` | no title match, and the corpus has no abstract for it |
| `op:icml:2026:goUAT3UcR4` | * MemPot*: Defend Against Memory Extraction Attack with Optimized Honeypots | ICML | 2026 | `unsettled` | no title match, and the corpus has no abstract for it |
| `op:icml:2026:IBLJ5MNcgy` | Bridging the Grounding Gap in VideoQA via Typed Memory for Language-based Belief-State Reasoning | ICML | 2026 | `unsettled` | no title match, and the corpus has no abstract for it |
| `op:icml:2026:LD9mlgF5WU` | VR-Thinker: Boosting Multimodal Reward Models through Think with Image Reasoning | ICML | 2026 | `unsettled` | no title match, and the corpus has no abstract for it |
| `mended.ris#3` | Building a stable classifier with the inflated argmax |  | 2024 | `unsettled` | its venue string is no venue, so no title match is made; same title: op:neurips:2024:M7zNXntzsp (NeurIPS 2024) |
| `mended.ris#4` | Selective Explanations |  | 2024 | `unsettled` | its venue string is no venue, so no title match is made; same title: op:neurips:2024:gHCFduRo7o (NeurIPS 2024) |
| `mended.ris#143` | Crafting interpretable embeddings for language neuroscience by asking LLMs questions | … processing systems | 2024 | `unsettled` | its venue string is no venue, so no title match is made; same title: op:neurips:2024:mxMvWwyBWe (NeurIPS 2024) |
| `mended.ris#437` | Loss function with memory for trustworthiness threshold learning: Case of face and facial expression recognition | ICML | 2022 | `coverage_gap` | no forum id, proceedings id or title+venue+year match in the snapshot; its links are on link.springer.com, www.researchgate.net |
| `mended.ris#441` | Decodingtrust: A comprehensive assessment of trustworthiness in {GPT} models |  | 2023 | `unsettled` | its venue string is no venue, so no title match is made; same title: op:neurips:2023:kaHpo8OZw2 (NeurIPS 2023) |
| `mended.ris#442` | Foundational Robustness of Foundation Models | NeurIPS | 2022 | `coverage_gap` | no forum id, proceedings id or title+venue+year match in the snapshot; its links are on neurips.cc |
| `mended.ris#1072` | AugGen: Synthetic Augmentation using Diffusion Models Can Improve Recognition | Advances in Neural … | 2025 | `unsettled` | its venue string is no venue, so no title match is made; same title: op:neurips:2025:LuKlBH8DAT (NeurIPS 2025) |
| `mended.ris#1790` | Fusing Large Language Models and LDA for Attribute Mining in Online Reviews | ICML | 2025 | `coverage_gap` | no forum id, proceedings id or title+venue+year match in the snapshot; its links are on ieeexplore.ieee.org |

### Records only in openproceedings

| record | title | venue | year | class | evidence |
|---|---|---|---|---|---|
| `op:iclr:2023:WE_vluYUL-X` | ReAct: Synergizing Reasoning and Acting in Language Models | ICLR | 2023 | `compat_reading` | `$`: a zero-or-one wildcard here, no wildcard in Scholar |
| `op:iclr:2024:UMfcdRIotC` | Faithful Explanations of Black-box NLP Models Using LLM-generated Counterfactuals | ICLR | 2024 | `scholar_missed` | exact match on group 1: "large language model$" (abstract), llm$ (title+abstract); group 2: trust (abstract); group 3: benchmark$ (abstract) |
| `op:iclr:2024:fsW7wJGLBd` | Tensor Trust: Interpretable Prompt Injection Attacks from an Online Game | ICLR | 2024 | `scholar_missed` | exact match on group 1: "large language model$" (abstract), llm$ (abstract); group 2: trust (title+abstract); group 3: benchmark$ (abstract) |
| `op:iclr:2025:UHPnqSTBPO` | Trust or Escalate: LLM Judges with Provable Guarantees for Human Agreement | ICLR | 2025 | `scholar_missed` | exact match on group 1: llm$ (title+abstract); group 2: trust (title+abstract); group 3: "evaluation framework$" (abstract) |
| `op:icml:2024:bWUU0LwwMp` | Position: TrustLLM: Trustworthiness in Large Language Models | ICML | 2024 | `compat_reading` | `$`: a zero-or-one wildcard here, no wildcard in Scholar |
| `op:icml:2025:V61nluxFlR` | Aligning with Logic: Measuring, Evaluating and Improving Logical Preference Consistency in Large Language Models | ICML | 2025 | `scholar_missed` | exact match on group 1: "large language model$" (title+abstract), llm$ (abstract); group 2: trustworthy (abstract); group 3: "evaluation framework$" (abstract) |
| `op:icml:2025:j3totqf8xW` | Position: Beyond Assistance – Reimagining LLMs as Ethical and Adaptive Co-Creators in Mental Health Care | ICML | 2025 | `scholar_missed` | exact match on group 1: "large language model$" (abstract), llm$ (title+abstract); group 2: trustworthiness (abstract); group 3: "evaluation framework$" (abstract) |
| `op:icml:2025:zvZTIXkzDe` | DAMA: Data- and Model-aware Alignment of Multi-modal LLMs | ICML | 2025 | `compat_reading` | `$`: a zero-or-one wildcard here, no wildcard in Scholar |
| `op:neurips:2023:kaHpo8OZw2` | DecodingTrust: A Comprehensive Assessment of Trustworthiness in GPT Models | NeurIPS | 2023 | `compat_reading` | `$`: a zero-or-one wildcard here, no wildcard in Scholar |
| `op:neurips:2024:5c1hh8AeHv` | MultiTrust: A Comprehensive Benchmark Towards Trustworthy Multimodal Large Language Models | NeurIPS | 2024 | `compat_reading` | `$`: a zero-or-one wildcard here, no wildcard in Scholar |
| `op:neurips:2025:Lm8HcblPCJ` | VMDT: Decoding the Trustworthiness of Video Foundation Models | NeurIPS | 2025 | `compat_reading` | `$`: a zero-or-one wildcard here, no wildcard in Scholar |
| `op:neurips:2025:QQhQIqons0` | SEC-bench: Automated Benchmarking of LLM Agents on Real-World Software Security Tasks | NeurIPS | 2025 | `compat_reading` | `$`: a zero-or-one wildcard here, no wildcard in Scholar |
| `op:neurips:2025:R5EBtNE2Y9` | HeavyWater and SimplexWater: Distortion-free LLM Watermarks for Low-Entropy Distributions | NeurIPS | 2025 | `compat_reading` | `$`: a zero-or-one wildcard here, no wildcard in Scholar |
| `op:neurips:2025:XwqawBglmv` | LC-Opt: Benchmarking Reinforcement Learning and Agentic AI for End-to-End Liquid Cooling Optimization in Data Centers | NeurIPS | 2025 | `scholar_missed` | exact match on group 1: llm$ (abstract); group 2: trust (abstract); group 3: benchmark$ (abstract) |
| `op:neurips:2025:eafIjoZAHm` | GnnXemplar: Exemplars to Explanations - Natural Language Rules for Global GNN Interpretability | NeurIPS | 2025 | `compat_reading` | `$`: a zero-or-one wildcard here, no wildcard in Scholar |
| `op:neurips:2025:gA3fFAEXNT` | Trust, But Verify: A Self-Verification Approach to Reinforcement Learning with Verifiable Rewards | NeurIPS | 2025 | `compat_reading` | `$`: a zero-or-one wildcard here, no wildcard in Scholar |

**Finding.** Of the 1,815 in-scope papers of the Scholar set, 1,713 (94.4%) match this string nowhere in title or abstract, inflected forms included (`full_text`), and 2 (0.1%) match only through an inflected form (`stemming`). 51 (2.8%) are in the exact result.

- Of the 1,713 `full_text` papers, 1,247 rest on a crawled record and 466 on a RIS-only record, whose title and abstract are the import's own.
- 2 of them also fail the default track or status filters.
- **Sensitivity to the stemmer.** The `stemming` class uses an inflection-only stand-in (see Method); which stemmer stands for Scholar's is an open decision for the project owner. With every searched word replaced by its inflection stem read as a prefix (`benchmarks` → `benchmark*`, `evaluating` → `evaluat*`), 0 of the 1,713 (0.0%) `full_text` papers would match title or abstract. That is all this figure measures: it is not a stemmer, and one that strips derivational endings (`evaluation` to `evaluat`) or rewrites the stem could move more.

## Query `main-2-pop`

The Scholar set is Google Scholar's answer to `main-7-most-updated`, not to this string. The numbers below are what this string keeps, drops and adds against that set; they say nothing about what Scholar would return for it.

Run in `mode=scholar`, exactly as written (`canonical_hash` `bad35af2385b39312e99ebf02c77eb84b7407fcbd6f7d8f46193b48482d4199a`):

```
(large language model$ | LLM | foundation model$ | generative AI$ | vision-language model$ | VLM | multimodal model$ | AI agent$ | text-to-image model$) (trust | trustworthy | trustworthiness | trustworthy AI$)  (benchmark | dataset | evaluation | leaderboard | evaluation framework$ | test suite$)
```

Canonical form, as run:

```
(("large language model$" OR llm OR "foundation model$" OR "generative ai$" OR "vision language model$" OR vlm OR "multimodal model$" OR "ai agent$" OR "text to image model$") AND (trust OR trustworthy OR trustworthiness OR "trustworthy ai$") AND (benchmark OR dataset OR evaluation OR leaderboard OR "evaluation framework$" OR "test suite$") AND track:(datasets_benchmarks OR main OR position) AND status:accepted)
```

Notices: `COMPAT_NO_STEMMING` × 1, `COMPAT_POP_DOLLAR` × 10, `COMPAT_POP_PHRASE` × 10.

Google Scholar reads this string differently from Scholar mode. Scholar's reading, written natively:

```
(large AND language AND (model OR llm OR foundation) AND (model OR generative) AND (ai OR vision) AND (model OR vlm OR multimodal) AND (model OR ai) AND (agent OR text) AND to AND image AND model AND (trust OR trustworthy OR trustworthiness) AND ai AND (benchmark OR dataset OR evaluation OR leaderboard) AND (framework OR test) AND suite AND track:(datasets_benchmarks OR main OR position) AND status:accepted)
```

**Decision-002.** This string has 10 unquoted multi-word `|` items. Scholar mode reads each as a phrase, which is what the review meant; Google Scholar itself ORs only the neighbouring words. Every difference that comes from that reading is classed `compat_reading`: it is not a record either side missed.

| | records |
|---|---|
| Scholar set, in scope | 1,815 |
| openproceedings `total` (default filters; every venue and year) | 88 |
| openproceedings, in scope | 88 |
| in both | 65 (44 crawled records, 21 RIS-only) |
| in both, matched to a RIS-only record whose title another index record has | 1 |
| only in the Scholar set | 1,750 |
| only in openproceedings | 23 |

### Only in the Scholar set

| class | records | of these | of the Scholar set | crawled record | RIS-only record | meaning |
|---|---|---|---|---|---|---|
| `our_bug` | 0 | 0.0% | 0.0% | 0 | 0 | the oracle and the served engine disagree (must be 0) |
| `coverage_gap` | 3 | 0.2% | 0.2% | 0 | 0 | no record in the snapshot by forum id, proceedings id or title+venue+year |
| `stemming` | 31 | 1.8% | 1.7% | 15 | 16 | matches title or abstract only with an inflected form added |
| `full_text` | 1,669 | 95.4% | 92.0% | 1,218 | 451 | in the corpus with an abstract; no reading matches its title or abstract, inflected forms included |
| `unsettled` | 47 | 2.7% | 2.6% | 0 | 42 | the automation can't tell (see the row's evidence) |
| total | 1,750 | 100.0% | 96.4% | 1,233 | 509 | |

`crawled record` and `RIS-only record` say what the row's index record rests on (a row with no index record is in neither).

### Only in openproceedings

| class | records | of these | of the result | crawled record | RIS-only record | meaning |
|---|---|---|---|---|---|---|
| `our_bug` | 0 | 0.0% | 0.0% | 0 | 0 | the oracle and the served engine disagree (must be 0) |
| `compat_reading` | 23 | 100.0% | 26.1% | 23 | 0 | decided by how Scholar mode read the string (decision-002 phrases, `$`), not by the corpus |
| total | 23 | 100.0% | 26.1% | 23 | 0 | |

`our_bug`: **0**. Rows for a person in `review.csv`: 50 unresolved, 173 spot check.

### Concept groups, over the 1,807 Scholar papers the index holds

How many of them hold each top-level group of the string in title or abstract, whatever their track and status:

| group | as run | with inflected forms |
|---|---|---|
| 1. `("large language model$" OR llm OR "foundation model$" OR "generative ai$" OR "vision language model$" OR vlm OR "multimodal model$" OR "ai agent$" OR "text to image model$")` | 1,114 | 1,158 |
| 2. `(trust OR trustworthy OR trustworthiness OR "trustworthy ai$")` | 191 | 197 |
| 3. `(benchmark OR dataset OR evaluation OR leaderboard OR "evaluation framework$" OR "test suite$")` | 791 | 1,251 |

Inflected forms added for the `stemming` test (the forms the compared records hold): `agent` → agents; `benchmark` → benchmarked, benchmarking, benchmarks; `dataset` → datasets; `evaluation` → evaluations; `foundation` → foundations; `framework` → frameworks; `image` → images, imaging; `language` → languages; `leaderboard` → leaderboards; `llm` → llms; `model` → modeled, modeling, models; `suite` → suit, suited, suites; `test` → tested, testing, tests; `text` → texts; `trust` → trusted, trusting; `vlm` → vlms.

### Scholar-only records listed

| record | title | venue | year | class | evidence |
|---|---|---|---|---|---|
| `op:iclr:2024:iclr-c3eb94d149aea08c28505d1e5234a21a` | Less is more: One-shot subgraph reasoning on large-scale knowledge graphs | ICLR | 2024 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:iclr:2024:QHROe7Mfcb (ICLR 2024): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 1, 2, inflected forms included) |
| `op:iclr:2026:iclr-c6c29e590e3c62e37e6b39cdd6baf2e8` | St-webagentbench: A benchmark for evaluating safety and trustworthiness in web agents | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:iclr:2025:IIzehISTBe (ICLR 2025); op:icml:2025:fAmhr96SUw (ICML 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 1, inflected forms included) |
| `op:iclr:2026:iclr-bb3a308fd06c7f88ba5a81af60e8977a` | In agents we trust, but who do agents trust? latent source preferences steer LLM generations | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:icml:2025:oZMisPPggL (ICML 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 3, inflected forms included) |
| `op:iclr:2026:iclr-2fb00c27ddcb782ae41066b2b037630f` | Get RICH or Die Scaling: Profitably Trading Inference Compute for Robustness | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:neurips:2025:dZRCZUvKPj (NeurIPS 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 2, 3, inflected forms included) |
| `op:iclr:2026:iclr-9334fd3a5170dbfe74eae4755f6c5f89` | Steering evaluation-aware language models to act like they are deployed | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:neurips:2025:RCjtIoy7zh (NeurIPS 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 2, inflected forms included) |
| `op:iclr:2026:iclr-1a96349bbc03432c5ec8c6c502d102e7` | Do large language models know what they are capable of? | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:neurips:2025:IPGR4uXxvg (NeurIPS 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 2, 3, inflected forms included) |
| `op:iclr:2026:iclr-92d777fb721936613b6444b07c4ffc18` | Dropping just a handful of preferences can change top large language model rankings | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:icml:2025:b9r1snfxIH (ICML 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 2, inflected forms included) |
| `op:iclr:2026:iclr-fd1eff9dd295df50a41f2521942fa31d` | Evaluating memory in llm agents via incremental multi-turn interactions | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:icml:2025:ZgQ0t3zYTQ (ICML 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 2, inflected forms included) |
| `op:iclr:2026:iclr-6297baf3f5c98146b62dd3a1bffe068e` | Preference leakage: A contamination problem in llm-as-a-judge | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:icml:2025:gW6NT2IuME (ICML 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 2, inflected forms included) |
| `op:iclr:2026:iclr-a24cd16bc361afa78e57d31d34f3d936` | Your agent may misevolve: Emergent risks in self-evolving llm agents | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:neurips:2025:lS1gWUHbfx (NeurIPS 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 3, inflected forms included) |
| `op:iclr:2026:iclr-eaa3d3f05ae14240b7a6a250ce6ddcd7` | Dragon: Guard llm unlearning in context via negative detection and reasoning | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:icml:2025:ET24oKP23c (ICML 2025); op:neurips:2025:FNuul0hlin (NeurIPS 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 2, 3, inflected forms included) |
| `op:iclr:2026:iclr-0fb49ffa040d13a491c7164c5912cf7d` | Sophiavl-r1: Reinforcing mllms reasoning with thinking reward | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:neurips:2025:iJ4i5HE5ER (NeurIPS 2025): possibly one paper under two ids; otherwise `stemming` (matches with benchmarks, datasets) |
| `op:iclr:2026:iclr-4444eb0b68174180d2a46841c951e7f3` | Benchmarking overton pluralism in llms | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:neurips:2025:Mq3QUs7FAp (NeurIPS 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 2, inflected forms included) |
| `op:iclr:2026:iclr-5fc8b3bdfbb9167b5144df5d3fae4616` | Mem1: Learning to synergize memory and reasoning for efficient long-horizon agents | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:neurips:2025:jJ6F1sDn9i (NeurIPS 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 2, inflected forms included) |
| `op:iclr:2026:iclr-799b39274bdfeea24be0a3ccf304107e` | ZeroTuning: Unlocking the Initial Token's Power to Enhance Large Language Models Without Training | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:icml:2025:THSbsRWy9v (ICML 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 2, inflected forms included) |
| `op:iclr:2026:iclr-b51362de8ffda06bcdf0bc538a1a0fc1` | Unlearning Isn't Invisible: Detecting Unlearning Traces in LLMs from Model Outputs | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:icml:2025:qvZhRdQ0QE (ICML 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 2, 3, inflected forms included) |
| `op:iclr:2026:iclr-c9d780d1e2d57d4b70e807608a72501b` | Arms: Adaptive red-teaming agent against multimodal models with plug-and-play attacks | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:neurips:2025:5jOqGe6CxS (NeurIPS 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 2, inflected forms included) |
| `op:iclr:2026:iclr-5b288823575bb29654b0953a251e933b` | Diffuguard: How intrinsic safety is lost and found in diffusion large language models | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:neurips:2025:r3cDmnicYh (NeurIPS 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 2, 3, inflected forms included) |
| `op:iclr:2026:iclr-3bf80b34f731313b8292f4578e820c90` | Deep ignorance: Filtering pretraining data builds tamper-resistant safeguards into open-weight llms | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:neurips:2025:lZGgc845Uz (NeurIPS 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 2, 3, inflected forms included) |
| `op:iclr:2026:iclr-033f2b82bf0f35add31a88d76f041f58` | Detecting data contamination in llms via in-context learning | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:neurips:2025:eWObAa0Uaw (NeurIPS 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 2, inflected forms included) |
| `op:iclr:2026:iclr-b77b5f1a2878fedd4705bfeafd24ca35` | Aside: Architectural separation of instructions and data in language models | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:iclr:2025:GlmqRQsCaI (ICLR 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 2, inflected forms included) |
| `op:iclr:2026:iclr-fd8872fcba4ba87312cdfe5ebba91ca9` | BA-loRA: Bias-alleviating low-rank adaptation to mitigate catastrophic inheritance in large language models | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:iclr:2025:d465apqCqc (ICLR 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 2, inflected forms included) |
| `op:iclr:2026:iclr-9bf12308ece130daa083fb21f7faf1b6` | Customizing visual emotion evaluation for mllms: An open-vocabulary, multifaceted, and scalable approach | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:neurips:2025:O8Hu5u0v1A (NeurIPS 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 2, inflected forms included) |
| `op:iclr:2026:iclr-a7060588538c3ca1ef2fb071db9e5630` | Medical thinking with multiple images | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:neurips:2025:dynv2pD1cN (NeurIPS 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 2, inflected forms included) |
| `op:iclr:2026:iclr-524ff06d5375d76e93d8490e654a81bf` | Simpletom: Exposing the gap between explicit tom inference and implicit tom application in llms | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:iclr:2025:ZzATfnskP1 (ICLR 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 2, inflected forms included) |
| `op:iclr:2026:iclr-b0832cc57899cfd2d3fedeb3f330ba80` | Omni-reward: Towards generalist omni-modal reward modeling with free-form preferences | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:neurips:2025:FEixSLhANJ (NeurIPS 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 1, 2, inflected forms included) |
| `op:iclr:2026:iclr-02c1d1d33dbfbaf03b3971bb542e72e2` | JailbreakloRA: Your downloaded loRA from sharing platforms might be unsafe | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:icml:2025:RjaeiNswGh (ICML 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 2, 3, inflected forms included) |
| `op:iclr:2026:iclr-bbd35a35873e1e447b14b0932af87af0` | Beyond magic words: Sharpness-aware prompt evolving for robust large language models with tare | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:neurips:2025:3yhOA0BZsK (NeurIPS 2025); op:neurips:2025:lyIhSyyaU4 (NeurIPS 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 2, 3, inflected forms included) |
| `op:iclr:2026:iclr-ed67dff7cb96e7e86c4d91c0d5db49bb` | Attributing response to context: A jensen–shannon divergence driven mechanistic study of context attribution in retrieval-augmented generation | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:neurips:2025:UyXjYlJij3 (NeurIPS 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 2, inflected forms included) |
| `op:iclr:2026:iclr-f5846131aa6a72d1df3bd6d43a4a960b` | LUMINA: Detecting hallucinations in RAG system with context–knowledge signals | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:neurips:2025:fRUW4qbET3 (NeurIPS 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 2, inflected forms included) |
| `op:iclr:2026:iclr-607864303db1f2bea942b4a9d462920c` | Weak-to-strong diffusion with reflection | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:iclr:2025:wllm64LuJN (ICLR 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 1, 2, inflected forms included) |
| `op:iclr:2026:iclr-5810666374031717089033d95f9973ea` | Adaptive Logit Adjustment for Debiasing Multimodal Language Models | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:neurips:2025:hMlUGoMsEK (NeurIPS 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 2, 3, inflected forms included) |
| `op:iclr:2026:iclr-23b9ed90f5eed45cdf12a9abb31308be` | MaskInversion: Localized embeddings via optimization of explainability maps | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:iclr:2025:DhlbK7tAjz (ICLR 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 2, inflected forms included) |
| `op:iclr:2026:iclr-08a362bd4ae1934e099ce025f06039fe` | Rote learning considered useful: generalizing over memorized data in LLMs | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:icml:2025:vNOA396J3q (ICML 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 2, 3, inflected forms included) |
| `op:iclr:2026:iclr-b2f56a345fe0ce337df3bdfb31e2b350` | Towards Better Branching Policies: Leveraging the Sequential Nature of Branch-and-Bound Tree | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:neurips:2025:fwJ1rRHT91 (NeurIPS 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 1, 2, 3, inflected forms included) |
| `op:iclr:2026:iclr-3327377ee37b8c87c43a7d6a4ea3d279` | Decoupling the class label and the target concept in machine unlearning | ICLR | 2026 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:iclr:2025:OHOmpkGiYK (ICLR 2025): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 1, 2, 3, inflected forms included) |
| `op:icml:2026:JoJUWsQBp0` | Can LLM Agents Stick to the Script? Modeling Commitment in Interactive Narratives | ICML | 2026 | `unsettled` | no title match, and the corpus has no abstract for it |
| `op:icml:2026:5Qpy3uTD05` | Domain Restriction via SAE Multi-Layer Transitions | ICML | 2026 | `unsettled` | no title match, and the corpus has no abstract for it |
| `op:icml:2026:dzcDbh8ewp` | LECTOR: Joint Learning of Scientific Reasoning Graphs and Introduction Generation | ICML | 2026 | `unsettled` | no title match, and the corpus has no abstract for it |
| `op:icml:2026:goUAT3UcR4` | * MemPot*: Defend Against Memory Extraction Attack with Optimized Honeypots | ICML | 2026 | `unsettled` | no title match, and the corpus has no abstract for it |
| `op:icml:2026:IBLJ5MNcgy` | Bridging the Grounding Gap in VideoQA via Typed Memory for Language-based Belief-State Reasoning | ICML | 2026 | `unsettled` | no title match, and the corpus has no abstract for it |
| `op:icml:2026:LD9mlgF5WU` | VR-Thinker: Boosting Multimodal Reward Models through Think with Image Reasoning | ICML | 2026 | `unsettled` | no title match, and the corpus has no abstract for it |
| `mended.ris#3` | Building a stable classifier with the inflated argmax |  | 2024 | `unsettled` | its venue string is no venue, so no title match is made; same title: op:neurips:2024:M7zNXntzsp (NeurIPS 2024) |
| `mended.ris#4` | Selective Explanations |  | 2024 | `unsettled` | its venue string is no venue, so no title match is made; same title: op:neurips:2024:gHCFduRo7o (NeurIPS 2024) |
| `mended.ris#143` | Crafting interpretable embeddings for language neuroscience by asking LLMs questions | … processing systems | 2024 | `unsettled` | its venue string is no venue, so no title match is made; same title: op:neurips:2024:mxMvWwyBWe (NeurIPS 2024) |
| `mended.ris#437` | Loss function with memory for trustworthiness threshold learning: Case of face and facial expression recognition | ICML | 2022 | `coverage_gap` | no forum id, proceedings id or title+venue+year match in the snapshot; its links are on link.springer.com, www.researchgate.net |
| `mended.ris#441` | Decodingtrust: A comprehensive assessment of trustworthiness in {GPT} models |  | 2023 | `unsettled` | its venue string is no venue, so no title match is made; same title: op:neurips:2023:kaHpo8OZw2 (NeurIPS 2023) |
| `mended.ris#442` | Foundational Robustness of Foundation Models | NeurIPS | 2022 | `coverage_gap` | no forum id, proceedings id or title+venue+year match in the snapshot; its links are on neurips.cc |
| `mended.ris#1072` | AugGen: Synthetic Augmentation using Diffusion Models Can Improve Recognition | Advances in Neural … | 2025 | `unsettled` | its venue string is no venue, so no title match is made; same title: op:neurips:2025:LuKlBH8DAT (NeurIPS 2025) |
| `mended.ris#1790` | Fusing Large Language Models and LDA for Attribute Mining in Online Reviews | ICML | 2025 | `coverage_gap` | no forum id, proceedings id or title+venue+year match in the snapshot; its links are on ieeexplore.ieee.org |

### Records only in openproceedings

| record | title | venue | year | class | evidence |
|---|---|---|---|---|---|
| `op:iclr:2023:3Pf3Wg6o-A4` | Selection-Inference: Exploiting Large Language Models for Interpretable Logical Reasoning | ICLR | 2023 | `compat_reading` | decision-002: the unquoted `\|` items are phrases here, neighbouring words ORed in Scholar |
| `op:iclr:2024:UMfcdRIotC` | Faithful Explanations of Black-box NLP Models Using LLM-generated Counterfactuals | ICLR | 2024 | `compat_reading` | decision-002: the unquoted `\|` items are phrases here, neighbouring words ORed in Scholar |
| `op:iclr:2024:fsW7wJGLBd` | Tensor Trust: Interpretable Prompt Injection Attacks from an Online Game | ICLR | 2024 | `compat_reading` | decision-002: the unquoted `\|` items are phrases here, neighbouring words ORed in Scholar |
| `op:iclr:2025:4ub9gpx9xw` | Walk the Talk? Measuring the Faithfulness of Large Language Model Explanations | ICLR | 2025 | `compat_reading` | decision-002: the unquoted `\|` items are phrases here, neighbouring words ORed in Scholar |
| `op:iclr:2025:RQPSPGpBOP` | Can a Large Language Model be a Gaslighter? | ICLR | 2025 | `compat_reading` | decision-002: the unquoted `\|` items are phrases here, neighbouring words ORed in Scholar |
| `op:iclr:2025:UHPnqSTBPO` | Trust or Escalate: LLM Judges with Provable Guarantees for Human Agreement | ICLR | 2025 | `compat_reading` | decision-002: the unquoted `\|` items are phrases here, neighbouring words ORed in Scholar |
| `op:iclr:2025:i8IwcQBi74` | Interpreting Language Reward Models via Contrastive Explanations | ICLR | 2025 | `compat_reading` | decision-002: the unquoted `\|` items are phrases here, neighbouring words ORed in Scholar |
| `op:icml:2024:3tJDnEszco` | CHEMREASONER: Heuristic Search over a Large Language Model’s Knowledge Space using Quantum-Chemical Feedback | ICML | 2024 | `compat_reading` | decision-002: the unquoted `\|` items are phrases here, neighbouring words ORed in Scholar |
| `op:icml:2024:Cw6Xl0g8a5` | Probabilistic Conceptual Explainers: Trustworthy Conceptual Explanations for Vision Foundation Models | ICML | 2024 | `compat_reading` | decision-002: the unquoted `\|` items are phrases here, neighbouring words ORed in Scholar; `$`: a zero-or-one wildcard here, no wildcard in Scholar |
| `op:icml:2024:DKKg5EFAFr` | Evaluating Quantized Large Language Models | ICML | 2024 | `compat_reading` | decision-002: the unquoted `\|` items are phrases here, neighbouring words ORed in Scholar; `$`: a zero-or-one wildcard here, no wildcard in Scholar |
| `op:icml:2024:Fzp1DRzCIN` | Implicit meta-learning may lead language models to trust more reliable sources | ICML | 2024 | `compat_reading` | decision-002: the unquoted `\|` items are phrases here, neighbouring words ORed in Scholar; `$`: a zero-or-one wildcard here, no wildcard in Scholar |
| `op:icml:2024:b1YQ5WKY3w` | Is In-Context Learning in Large Language Models Bayesian? A Martingale Perspective | ICML | 2024 | `compat_reading` | decision-002: the unquoted `\|` items are phrases here, neighbouring words ORed in Scholar |
| `op:icml:2024:bWUU0LwwMp` | Position: TrustLLM: Trustworthiness in Large Language Models | ICML | 2024 | `compat_reading` | decision-002: the unquoted `\|` items are phrases here, neighbouring words ORed in Scholar; `$`: a zero-or-one wildcard here, no wildcard in Scholar |
| `op:icml:2024:e3Dpq3WdMv` | Decoding Compressed Trust: Scrutinizing the Trustworthiness of Efficient LLMs Under Compression | ICML | 2024 | `compat_reading` | decision-002: the unquoted `\|` items are phrases here, neighbouring words ORed in Scholar; `$`: a zero-or-one wildcard here, no wildcard in Scholar |
| `op:icml:2025:V61nluxFlR` | Aligning with Logic: Measuring, Evaluating and Improving Logical Preference Consistency in Large Language Models | ICML | 2025 | `compat_reading` | decision-002: the unquoted `\|` items are phrases here, neighbouring words ORed in Scholar |
| `op:icml:2025:j3totqf8xW` | Position: Beyond Assistance – Reimagining LLMs as Ethical and Adaptive Co-Creators in Mental Health Care | ICML | 2025 | `compat_reading` | decision-002: the unquoted `\|` items are phrases here, neighbouring words ORed in Scholar |
| `op:neurips:2021:bB-l0cnS3E` | Evaluation of Human-AI Teams for Learned and Rule-Based Agents in Hanabi | NeurIPS | 2021 | `compat_reading` | decision-002: the unquoted `\|` items are phrases here, neighbouring words ORed in Scholar; `$`: a zero-or-one wildcard here, no wildcard in Scholar |
| `op:neurips:2023:kaHpo8OZw2` | DecodingTrust: A Comprehensive Assessment of Trustworthiness in GPT Models | NeurIPS | 2023 | `compat_reading` | decision-002: the unquoted `\|` items are phrases here, neighbouring words ORed in Scholar; `$`: a zero-or-one wildcard here, no wildcard in Scholar |
| `op:neurips:2024:5c1hh8AeHv` | MultiTrust: A Comprehensive Benchmark Towards Trustworthy Multimodal Large Language Models | NeurIPS | 2024 | `compat_reading` | decision-002: the unquoted `\|` items are phrases here, neighbouring words ORed in Scholar; `$`: a zero-or-one wildcard here, no wildcard in Scholar |
| `op:neurips:2025:Lm8HcblPCJ` | VMDT: Decoding the Trustworthiness of Video Foundation Models | NeurIPS | 2025 | `compat_reading` | decision-002: the unquoted `\|` items are phrases here, neighbouring words ORed in Scholar; `$`: a zero-or-one wildcard here, no wildcard in Scholar |
| `op:neurips:2025:QQhQIqons0` | SEC-bench: Automated Benchmarking of LLM Agents on Real-World Software Security Tasks | NeurIPS | 2025 | `compat_reading` | decision-002: the unquoted `\|` items are phrases here, neighbouring words ORed in Scholar |
| `op:neurips:2025:XwqawBglmv` | LC-Opt: Benchmarking Reinforcement Learning and Agentic AI for End-to-End Liquid Cooling Optimization in Data Centers | NeurIPS | 2025 | `compat_reading` | decision-002: the unquoted `\|` items are phrases here, neighbouring words ORed in Scholar |
| `op:neurips:2025:zPKeJAEo27` | What is Your Data Worth to GPT? LLM-Scale Data Valuation with Influence Functions | NeurIPS | 2025 | `compat_reading` | decision-002: the unquoted `\|` items are phrases here, neighbouring words ORed in Scholar |

**Finding.** Of the 1,815 in-scope papers of the Scholar set, 1,669 (92.0%) match this string nowhere in title or abstract, inflected forms included (`full_text`), and 31 (1.7%) match only through an inflected form (`stemming`). 65 (3.6%) are in the exact result.

- Of the 1,669 `full_text` papers, 1,218 rest on a crawled record and 451 on a RIS-only record, whose title and abstract are the import's own.
- 2 of them also fail the default track or status filters.
- **Sensitivity to the stemmer.** The `stemming` class uses an inflection-only stand-in (see Method); which stemmer stands for Scholar's is an open decision for the project owner. With every searched word replaced by its inflection stem read as a prefix (`benchmarks` → `benchmark*`, `evaluating` → `evaluat*`), 2 of the 1,669 (0.1%) `full_text` papers would match title or abstract. That is all this figure measures: it is not a stemmer, and one that strips derivational endings (`evaluation` to `evaluat`) or rewrites the stem could move more.

## Method

- **Order of the tests** (scholar-comparison-protocol). Only in the Scholar set: `our_bug`, `filtered`,
  `compat_reading`, `coverage_gap`, `stemming`, then `full_text`. Only in openproceedings: `our_bug`, `scholar_cap`,
  `compat_reading`, then `scholar_missed`. A record gets the first class whose test it passes, and a second cause
  is named in its evidence. The filters come before the text: a record that fails the default track or status
  filters and matches with them removed, as run, as Scholar reads the string or with an inflected form, is
  `filtered`, and its evidence says which (`also stemming`, `also compat_reading`).
- **Oracle.** Every class rests on `ReferenceEngine`, built over the compared records only: each matched paper of
  the Scholar set and each in-scope match of the served index. A wildcard (`$`, `*`) therefore expands over the
  compared records' vocabulary, not the snapshot's; for these records the matches are the same. `our_bug` counts
  every compared record on which the oracle and the served index disagree about the query as run. A record
  neither side holds is not compared, so a disagreement about one is outside this report (the differential suite
  covers it).
- **`compat_reading`.** The string is rewritten as Google Scholar reads it (`$` is no wildcard; an unquoted
  multi-word `|` item is separate words, with `|` binding tighter than juxtaposition) and run again. The evidence
  names the rewrite that decides the record.
- **`stemming`.** Each searched word also matches its other English inflections found in the compared records:
  plural or third-person `s`/`es`/`ies`, `ed`, `ing` (`eval.scholar_compare.inflection_stem`). Inflection only: no
  derivation (`trustworthy` is not a form of `trust`), and it over-pairs in places (`suite` with `suit`). Google
  Scholar's stemmer is undocumented, so this is a stated stand-in, not Scholar's rule; quoted words get forms too.
  A wider stemmer would move papers from `full_text` to `stemming`; each query's sensitivity line says how many
  would move if every word were replaced by its inflection stem read as a prefix, and nothing more than that.
- **`full_text`** is the residue: the record is in the corpus with an abstract, and the oracle confirms that no
  reading above matches its title or abstract. It may also fail the filters (counted under each finding). A
  record the corpus holds without an abstract is `unsettled`.
- **Provenance.** Each row says whether its index record has an independent source or only an imported RIS set
  (`crawled record`, `RIS-only record`), and `review.csv` carries it with the abstract's source.
- **`scholar_missed`** rows all go to `review.csv`: a person confirms the exact tokens are in the title or abstract.
- **`coverage_gap`** rows all go to `review.csv` too: a record the corpus lacks and a record Scholar filed under
  the wrong venue or year look the same to the matching, so a person checks each against the coverage report.
- **`review.csv`** also holds a spot check: a tenth of each query's settled disagreements, chosen by a hash of
  the row's ids. `human_class` is filled by a person, never by the analyst.

## Notes on these inputs

- **The Scholar set.** `mended.ris` is the Trust-Evals review's Scholar export after scholarmend: the 1,834 records of
  the review's `clean.ris` (sha256 `576c695db2361bdff68841d0f020f78b38647e9c8365c0bb5953f3c8aeb46f50`, which already
  holds the 443 records of the 2020–2024 delta), with the same titles, one for one. It is used in place of
  `clean.ris`, which spec 07 §B names, because scoping needs a year: `clean.ris` has no year on 99 records and gives
  1,059 the year 2026, Scholar's own guess. scholarmend replaced those with the year of the paper's proceedings
  or OpenReview page, and each truncated venue string with the venue's short name where a page settled it. It is a
  fixed export, dated by its Publish or Perish query dates (2026-09-19 and 2026-09-23); nothing was fetched from
  Scholar for this report.
- **Which string the set answers.** The review exported one file per `source:` value of `main-7-most-updated`, so
  the set is Scholar's answer to that string. `main-7-dollar` is the same string with `$` on six words and
  `year:2020..2026`, as it was run here on 2026-09-30; `main-2-pop` is the review's Publish or Perish variant. For
  those two the Scholar set is still `main-7-most-updated`'s: their sections show what each string keeps, drops
  and adds against the records the review already holds, not what Scholar returned for them.
- **Scholar's cap.** The review's 17 raw exports hold between 7 and 639 records each, all under Scholar's 1,000,
  so no search was cut at the cap. The set itself is de-duplicated across exports, which is why its largest
  query-date group is smaller.
- **Earlier counts.** On this index the 2026-09-30 runs gave 27 records for the literal string and 67 for the `$`
  string, 51 of them among the review's records and 16 not. This report reproduces all four numbers:
  `main-7-most-updated` limited to 2020–2026 is the literal string.
- **The set is in the index.** This index's snapshot was built with the set imported as its `ris` source
  (1,805 of the set's records, their ids from scholarmend's claims). Where a crawl holds the paper too, the two
  were merged and the record has an independent source. Where no crawl holds it, the index record is the import
  alone: above all in 2026, which no crawl had reached when the snapshot was built. "What the matches rest on"
  counts the two kinds apart. On an index built without the import, the RIS-only papers would be reported as not
  in the index, and their classes could not be judged at all.
- **Matching.** This report matches the set by URL and title, as it would any RIS file, not by the import's
  ids.
