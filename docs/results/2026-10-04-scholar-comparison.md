# Scholar comparison, 2026-10-04

- Index: `index_version` `05a0541717f6`, `tokenizer_version` `2`
- Snapshot: `2026-09-29-d552baa07aed`, `snapshot_hash` `d552baa07aed6bd754720c7ef17bc7d9ef7a645531fb95d6bc4174c2eacf91b8` (95,877 records)
- Scholar set: `mended.ris`, sha256 `ec0b1367acb6d3764780db0eb00b11868d1fe14ebe437b106aa4215ae7476a7b` (1,834 records)
- Scope, both sides: ICLR, ICML, NeurIPS; 2020–2026
- Queries: `main-7-most-updated`, `main-7-dollar`, `main-2-pop`
- Query file: `trust-evals.txt`, sha256 `16afdaff80f1c4767ea7e92d3854620ff73ed5beec192995743a03d97ee8e47c`
- Query file: `scholar-comparison-strings.txt`, sha256 `bc55c6e2dddb7300fea1608a0eaf6fb2f6bff2735babf95d777343fe1d81e56b`
- Notes: `scholar-comparison-notes.md`, sha256 `94bd9ead029c017b4da93d66f1d8555f05e71c82162ed4153169f3d87634b323`
- Command: `op eval scholar --ris mended.ris --query-file trust-evals.txt --query-file scholar-comparison-strings.txt --name main-7-most-updated --name main-7-dollar --name main-2-pop --years 2020..2026 --index 05a0541717f6 --date 2026-10-04`
- Review rows: `2026-10-04-scholar-comparison-review.csv` (569 rows, 39 unresolved)

**`our_bug`: 0** across 3 queries.

| query | Scholar set in scope | openproceedings in scope | both | only Scholar | only openproceedings | `full_text` | `stemming` | unresolved |
|---|---|---|---|---|---|---|---|---|
| `main-7-most-updated` | 1,810 | 27 | 21 | 1,789 | 6 | 1,748 (96.6%) | 32 (1.8%) | 15 |
| `main-7-dollar` | 1,810 | 67 | 51 | 1,759 | 16 | 1,748 (96.6%) | 2 (0.1%) | 15 |
| `main-2-pop` | 1,810 | 88 | 65 | 1,745 | 23 | 1,704 (94.1%) | 32 (1.8%) | 9 |

## Matching the Scholar set to the index

Each Scholar record is matched by spec 01's merge rules, in their order: the OpenReview forum id its URL names, else the proceedings paper its URL names (the native id within that venue and year), else the dedup title key within the same venue and year. A title alone never matches. A matched record is scoped by its index record's venue and year, an unmatched one by its own; records outside the scope are dropped before comparing.

| | records |
|---|---|
| read | 1,834 |
| outside the scope (ICLR, ICML, NeurIPS; 2020–2026) | 24 |
| in scope | 1,810 |
| repeats of a paper already counted | 0 |
| **papers in scope** | **1,810** |

| matched by | papers |
|---|---|
| proceedings id | 1,636 |
| forum id | 169 |
| no match (not found) | 3 |
| title venue year | 2 |

Outside the scope: 24 venue unrecognised. `venue unrecognised` means the record's venue string is not exactly one of Scholar mode's source names (Scholar cuts long venue names with `…`) and no URL of it names an indexed paper. Venue strings: (no venue) (4); International Conference on Machine … (2); International Conference … (2); 2025 International Conference on Machine Learning, Computational Intelligence and Pattern Recognition (MLCIPR) (1); Advances in Neural … (1); Advances in neural information processing … (1); Conference on … (1); ICBINB (1); International Conference on Artificial Intelligence and Statistics (1); Machine learning for healthcare … (1); Proceedings of Machine … (1); arXiv.org (1); … Information Processing … (1); … International Conference on … (1); … Representations (1); … Systems (NeurIPS 2025), San Diego … (1); … of Machine Learning Research … (1); … of Machine Learning … (1); … processing systems (1).

7 of them share a title key with an in-scope index record. That is never a match (no venue to check it against); a person may want to look:

| Scholar record | title | venue string | year | index record with that title |
|---|---|---|---|---|
| `mended.ris#3` | Building a stable classifier with the inflated argmax | — | 2024 | `op:neurips:2024:M7zNXntzsp` (NeurIPS 2024) |
| `mended.ris#4` | Selective Explanations | — | 2024 | `op:neurips:2024:gHCFduRo7o` (NeurIPS 2024) |
| `mended.ris#5` | Self-evaluation improves selective generation in large language models | ICBINB | 2023 | `op:neurips:2023:OptKBWmreP` (NeurIPS 2023) |
| `mended.ris#6` | Quantifying uncertainty in natural language explanations of large language models | International Conference on Artificial Intelligence and Statistics | 2024 | `op:neurips:2023:Yd2S8flZKm` (NeurIPS 2023) |
| `mended.ris#143` | Crafting interpretable embeddings for language neuroscience by asking LLMs questions | … processing systems | 2024 | `op:neurips:2024:mxMvWwyBWe` (NeurIPS 2024) |
| `mended.ris#441` | Decodingtrust: A comprehensive assessment of trustworthiness in {GPT} models | — | 2023 | `op:neurips:2023:kaHpo8OZw2` (NeurIPS 2023) |
| `mended.ris#1072` | AugGen: Synthetic Augmentation using Diffusion Models Can Improve Recognition | Advances in Neural … | 2025 | `op:neurips:2025:LuKlBH8DAT` (NeurIPS 2025) |

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
| Scholar set, in scope | 1,810 |
| openproceedings `total` (default filters; every venue and year) | 27 |
| openproceedings, in scope | 27 |
| in both | 21 |
| only in the Scholar set | 1,789 |
| only in openproceedings | 6 |

### Only in the Scholar set

| class | records | of these | of the Scholar set | meaning |
|---|---|---|---|---|
| `our_bug` | 0 | 0.0% | 0.0% | the oracle and the served engine disagree (must be 0) |
| `coverage_gap` | 3 | 0.2% | 0.2% | no record in the snapshot by forum id, proceedings id or title+venue+year |
| `stemming` | 32 | 1.8% | 1.8% | matches title or abstract only with an inflected form added |
| `full_text` | 1,748 | 97.7% | 96.6% | in the corpus; no reading matches its title or abstract, inflected forms included |
| `unsettled` | 6 | 0.3% | 0.3% | the automation can't tell (see the row's evidence) |
| total | 1,789 | 100.0% | 98.8% | |

### Only in openproceedings

| class | records | of these | of the result | meaning |
|---|---|---|---|---|
| `our_bug` | 0 | 0.0% | 0.0% | the oracle and the served engine disagree (must be 0) |
| `scholar_missed` | 6 | 100.0% | 22.2% | an exact title or abstract match that the Scholar set lacks |
| total | 6 | 100.0% | 22.2% | |

`our_bug`: **0**. Rows for a person in `review.csv`: 15 unresolved, 178 spot check.

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
| `op:icml:2026:JoJUWsQBp0` | Can LLM Agents Stick to the Script? Modeling Commitment in Interactive Narratives | ICML | 2026 | `unsettled` | no title match, and the corpus has no abstract for it |
| `op:icml:2026:5Qpy3uTD05` | Domain Restriction via SAE Multi-Layer Transitions | ICML | 2026 | `unsettled` | no title match, and the corpus has no abstract for it |
| `op:icml:2026:dzcDbh8ewp` | LECTOR: Joint Learning of Scientific Reasoning Graphs and Introduction Generation | ICML | 2026 | `unsettled` | no title match, and the corpus has no abstract for it |
| `op:icml:2026:goUAT3UcR4` | * MemPot*: Defend Against Memory Extraction Attack with Optimized Honeypots | ICML | 2026 | `unsettled` | no title match, and the corpus has no abstract for it |
| `op:icml:2026:IBLJ5MNcgy` | Bridging the Grounding Gap in VideoQA via Typed Memory for Language-based Belief-State Reasoning | ICML | 2026 | `unsettled` | no title match, and the corpus has no abstract for it |
| `op:icml:2026:LD9mlgF5WU` | VR-Thinker: Boosting Multimodal Reward Models through Think with Image Reasoning | ICML | 2026 | `unsettled` | no title match, and the corpus has no abstract for it |
| `mended.ris#437` | Loss function with memory for trustworthiness threshold learning: Case of face and facial expression recognition | ICML | 2022 | `coverage_gap` | no forum id, proceedings id or title+venue+year match in the snapshot; its links are on link.springer.com, www.researchgate.net |
| `mended.ris#442` | Foundational Robustness of Foundation Models | NeurIPS | 2022 | `coverage_gap` | no forum id, proceedings id or title+venue+year match in the snapshot; its links are on neurips.cc |
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

**Finding.** Of the 1,810 in-scope papers of the Scholar set, 1,748 (96.6%) match this string nowhere in title or abstract, inflected forms included (`full_text`), and 32 (1.8%) match only through an inflected form (`stemming`). 21 (1.2%) are in the exact result.

## Query `main-7-dollar`

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
| Scholar set, in scope | 1,810 |
| openproceedings `total` (default filters; every venue and year) | 67 |
| openproceedings, in scope | 67 |
| in both | 51 |
| only in the Scholar set | 1,759 |
| only in openproceedings | 16 |

### Only in the Scholar set

| class | records | of these | of the Scholar set | meaning |
|---|---|---|---|---|
| `our_bug` | 0 | 0.0% | 0.0% | the oracle and the served engine disagree (must be 0) |
| `coverage_gap` | 3 | 0.2% | 0.2% | no record in the snapshot by forum id, proceedings id or title+venue+year |
| `stemming` | 2 | 0.1% | 0.1% | matches title or abstract only with an inflected form added |
| `full_text` | 1,748 | 99.4% | 96.6% | in the corpus; no reading matches its title or abstract, inflected forms included |
| `unsettled` | 6 | 0.3% | 0.3% | the automation can't tell (see the row's evidence) |
| total | 1,759 | 100.0% | 97.2% | |

### Only in openproceedings

| class | records | of these | of the result | meaning |
|---|---|---|---|---|
| `our_bug` | 0 | 0.0% | 0.0% | the oracle and the served engine disagree (must be 0) |
| `compat_reading` | 10 | 62.5% | 14.9% | decided by how Scholar mode read the string (decision-002 phrases, `$`), not by the corpus |
| `scholar_missed` | 6 | 37.5% | 9.0% | an exact title or abstract match that the Scholar set lacks |
| total | 16 | 100.0% | 23.9% | |

`our_bug`: **0**. Rows for a person in `review.csv`: 15 unresolved, 176 spot check.

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
| `op:icml:2026:JoJUWsQBp0` | Can LLM Agents Stick to the Script? Modeling Commitment in Interactive Narratives | ICML | 2026 | `unsettled` | no title match, and the corpus has no abstract for it |
| `op:icml:2026:5Qpy3uTD05` | Domain Restriction via SAE Multi-Layer Transitions | ICML | 2026 | `unsettled` | no title match, and the corpus has no abstract for it |
| `op:icml:2026:dzcDbh8ewp` | LECTOR: Joint Learning of Scientific Reasoning Graphs and Introduction Generation | ICML | 2026 | `unsettled` | no title match, and the corpus has no abstract for it |
| `op:icml:2026:goUAT3UcR4` | * MemPot*: Defend Against Memory Extraction Attack with Optimized Honeypots | ICML | 2026 | `unsettled` | no title match, and the corpus has no abstract for it |
| `op:icml:2026:IBLJ5MNcgy` | Bridging the Grounding Gap in VideoQA via Typed Memory for Language-based Belief-State Reasoning | ICML | 2026 | `unsettled` | no title match, and the corpus has no abstract for it |
| `op:icml:2026:LD9mlgF5WU` | VR-Thinker: Boosting Multimodal Reward Models through Think with Image Reasoning | ICML | 2026 | `unsettled` | no title match, and the corpus has no abstract for it |
| `mended.ris#437` | Loss function with memory for trustworthiness threshold learning: Case of face and facial expression recognition | ICML | 2022 | `coverage_gap` | no forum id, proceedings id or title+venue+year match in the snapshot; its links are on link.springer.com, www.researchgate.net |
| `mended.ris#442` | Foundational Robustness of Foundation Models | NeurIPS | 2022 | `coverage_gap` | no forum id, proceedings id or title+venue+year match in the snapshot; its links are on neurips.cc |
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

**Finding.** Of the 1,810 in-scope papers of the Scholar set, 1,748 (96.6%) match this string nowhere in title or abstract, inflected forms included (`full_text`), and 2 (0.1%) match only through an inflected form (`stemming`). 51 (2.8%) are in the exact result.

## Query `main-2-pop`

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
| Scholar set, in scope | 1,810 |
| openproceedings `total` (default filters; every venue and year) | 88 |
| openproceedings, in scope | 88 |
| in both | 65 |
| only in the Scholar set | 1,745 |
| only in openproceedings | 23 |

### Only in the Scholar set

| class | records | of these | of the Scholar set | meaning |
|---|---|---|---|---|
| `our_bug` | 0 | 0.0% | 0.0% | the oracle and the served engine disagree (must be 0) |
| `coverage_gap` | 3 | 0.2% | 0.2% | no record in the snapshot by forum id, proceedings id or title+venue+year |
| `stemming` | 32 | 1.8% | 1.8% | matches title or abstract only with an inflected form added |
| `full_text` | 1,704 | 97.7% | 94.1% | in the corpus; no reading matches its title or abstract, inflected forms included |
| `unsettled` | 6 | 0.3% | 0.3% | the automation can't tell (see the row's evidence) |
| total | 1,745 | 100.0% | 96.4% | |

### Only in openproceedings

| class | records | of these | of the result | meaning |
|---|---|---|---|---|
| `our_bug` | 0 | 0.0% | 0.0% | the oracle and the served engine disagree (must be 0) |
| `compat_reading` | 23 | 100.0% | 26.1% | decided by how Scholar mode read the string (decision-002 phrases, `$`), not by the corpus |
| total | 23 | 100.0% | 26.1% | |

`our_bug`: **0**. Rows for a person in `review.csv`: 9 unresolved, 176 spot check.

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
| `op:icml:2026:JoJUWsQBp0` | Can LLM Agents Stick to the Script? Modeling Commitment in Interactive Narratives | ICML | 2026 | `unsettled` | no title match, and the corpus has no abstract for it |
| `op:icml:2026:5Qpy3uTD05` | Domain Restriction via SAE Multi-Layer Transitions | ICML | 2026 | `unsettled` | no title match, and the corpus has no abstract for it |
| `op:icml:2026:dzcDbh8ewp` | LECTOR: Joint Learning of Scientific Reasoning Graphs and Introduction Generation | ICML | 2026 | `unsettled` | no title match, and the corpus has no abstract for it |
| `op:icml:2026:goUAT3UcR4` | * MemPot*: Defend Against Memory Extraction Attack with Optimized Honeypots | ICML | 2026 | `unsettled` | no title match, and the corpus has no abstract for it |
| `op:icml:2026:IBLJ5MNcgy` | Bridging the Grounding Gap in VideoQA via Typed Memory for Language-based Belief-State Reasoning | ICML | 2026 | `unsettled` | no title match, and the corpus has no abstract for it |
| `op:icml:2026:LD9mlgF5WU` | VR-Thinker: Boosting Multimodal Reward Models through Think with Image Reasoning | ICML | 2026 | `unsettled` | no title match, and the corpus has no abstract for it |
| `mended.ris#437` | Loss function with memory for trustworthiness threshold learning: Case of face and facial expression recognition | ICML | 2022 | `coverage_gap` | no forum id, proceedings id or title+venue+year match in the snapshot; its links are on link.springer.com, www.researchgate.net |
| `mended.ris#442` | Foundational Robustness of Foundation Models | NeurIPS | 2022 | `coverage_gap` | no forum id, proceedings id or title+venue+year match in the snapshot; its links are on neurips.cc |
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

**Finding.** Of the 1,810 in-scope papers of the Scholar set, 1,704 (94.1%) match this string nowhere in title or abstract, inflected forms included (`full_text`), and 32 (1.8%) match only through an inflected form (`stemming`). 65 (3.6%) are in the exact result.

## Method

- **Order of the tests** (scholar-comparison-protocol). Only in the Scholar set: `our_bug`, `filtered`,
  `compat_reading`, `coverage_gap`, `stemming`, then `full_text`. Only in openproceedings: `our_bug`, `scholar_cap`,
  `compat_reading`, then `scholar_missed`. A record gets the first class whose test it passes; a second cause is
  named in its evidence (`also filtered`).
- **Oracle.** Every class rests on `ReferenceEngine`, built over the compared records: each matched paper of the
  Scholar set and each in-scope match of the served index. `our_bug` counts every compared record on which the
  oracle and the served index disagree about the query as run.
- **`compat_reading`.** The string is rewritten as Google Scholar reads it (`$` is no wildcard; an unquoted
  multi-word `|` item is separate words, with `|` binding tighter than juxtaposition) and run again. The evidence
  names the rewrite that decides the record.
- **`stemming`.** Each searched word also matches its other English inflections found in the compared records:
  plural or third-person `s`/`es`/`ies`, `ed`, `ing` (`eval.scholar_compare.inflection_stem`). Inflection only: no
  derivation (`trustworthy` is not a form of `trust`). Google Scholar's stemmer is undocumented, so this is a
  stated stand-in; it errs towards `stemming` (it pairs `suite` with `suit`), which keeps `full_text` a lower
  bound. Quoted words get forms too, for the same reason.
- **`full_text`** is the residue: the record is in the corpus with an abstract, and the oracle confirms that no
  reading above matches its title or abstract. A record the corpus holds without an abstract is `unsettled`.
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
- **Matched papers.** 1,805 of the set's records were imported into the snapshot as its `ris` source (their ids
  come from scholarmend's claims). This report matches the set by URL and title instead, as it would any RIS
  file, and finds those 1,805 and 2 more, by title, venue and year.
