# Scholar comparison, 2026-10-05

- Index: `index_version` `5ec5231adae2`, `tokenizer_version` `3`
- Snapshot: `2026-10-05-47d4e190ca81`, `snapshot_hash` `47d4e190ca816d89ff22bc88206e5e730929c14efbaa5a5213e5b36afde8a866` (133,632 records)
- Scholar set: `mended.ris`, sha256 `ec0b1367acb6d3764780db0eb00b11868d1fe14ebe437b106aa4215ae7476a7b` (1,834 records)
- Scope, both sides: ICLR, ICML, NeurIPS; 2020–2026
- Queries: `main-7-most-updated`, `main-7-dollar`, `main-2-pop`
- Query file: `trust-evals.txt`, sha256 `16afdaff80f1c4767ea7e92d3854620ff73ed5beec192995743a03d97ee8e47c`
- Query file: `scholar-comparison-strings.txt`, sha256 `bc55c6e2dddb7300fea1608a0eaf6fb2f6bff2735babf95d777343fe1d81e56b`
- Notes: `scholar-comparison-notes.md`, sha256 `97bd327517201fcf52ac0d63dff8cec637f426c9331ca5d5645e7af816387908`
- Command: `op eval scholar --ris mended.ris --query-file trust-evals.txt --query-file scholar-comparison-strings.txt --name main-7-most-updated --name main-7-dollar --name main-2-pop --years 2020..2026 --answers main-7-most-updated --notes scholar-comparison-notes.md --index 5ec5231adae2 --date 2026-10-05`
- Review rows: `2026-10-05-scholar-comparison-review.csv` (589 rows, 51 unresolved)

**`our_bug`: 0** across 3 queries.

**What the matches rest on.** Of the 1,815 in-scope papers of the Scholar set, 1,807 match an index record: 1,800 a record with an independent source (a crawl), 7 a record whose only source is an imported RIS set. A match of the second kind is the set matching its own import, and says nothing about coverage (see Matching).

| query | Scholar set in scope | openproceedings in scope | both | only Scholar | only openproceedings | `full_text` | of them RIS-only | `stemming` | unresolved |
|---|---|---|---|---|---|---|---|---|---|
| `main-7-most-updated` | 1,815 | 33 | 21 | 1,794 | 12 | 1,753 (96.6%) | 6 | 32 (1.8%) | 21 |
| `main-7-dollar` † | 1,815 | 101 | 51 | 1,764 | 50 | 1,753 (96.6%) | 6 | 2 (0.1%) | 21 |
| `main-2-pop` † | 1,815 | 114 | 65 | 1,750 | 49 | 1,709 (94.2%) | 6 | 32 (1.8%) | 9 |

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

Matched to a record with an independent source (a crawl of OpenReview or the proceedings): **1,800**. Matched to a record whose only source is an imported RIS set (RIS-only): **7**.

A RIS-only record is in the index because a Scholar set was imported into it. When the set compared here is that set, such a match is the set matching itself: it shows nothing about coverage, and the title and abstract the classes are judged on are the ones the import carried. Counts below are given for both kinds.

| venue | year | matched papers | crawled record | RIS-only record | crawled records the index holds |
|---|---|---|---|---|---|
| ICLR | 2024 | 51 | 50 | 1 | 8,522 |
| ICLR | 2025 | 208 | 205 | 3 | 13,746 |
| ICLR | 2026 | 415 | 412 | 3 | 22,825 |
| ICML | 2022 | 1 | 1 | 0 | 1,233 |
| ICML | 2023 | 2 | 2 | 0 | 2,826 |
| ICML | 2024 | 11 | 11 | 0 | 4,124 |
| ICML | 2025 | 13 | 13 | 0 | 5,083 |
| ICML | 2026 | 111 | 111 | 0 | 11,078 |
| NeurIPS | 2023 | 27 | 27 | 0 | 5,961 |
| NeurIPS | 2024 | 336 | 336 | 0 | 7,561 |
| NeurIPS | 2025 | 632 | 632 | 0 | 10,687 |

Abstract source of the matched records: `openreview_v2` 1,798; `ris:proceedings_page` 7; `neurips_proceedings` 1; `pmlr` 1. `ris:` is text the import carried (what scholarmend read from the proceedings page or the OpenReview API), not a crawl of this project.

1 papers matched a RIS-only record whose title key another index record has too (1 in the same venue and year: one paper under two ids, so the set can count it twice; the others in another venue or year: the import's venue or year may be wrong). The match is kept, and each such row that is a disagreement is `unsettled`, for a person.

Scholar searches in the set (Publish or Perish query dates): 16; the largest holds 631 records. Google Scholar returns at most 1,000 per search; a search at the cap makes every record only in openproceedings from its venues and years `scholar_cap`. No search in this set reached it.

## Query `main-7-most-updated`

Run in `mode=scholar`, exactly as written (`canonical_hash` `742f2e8263fd5d79c6e7f624b97841e26aa09514ff5ce939ebcd5427285b37e8`):

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
| openproceedings `total` (default filters; every venue and year) | 33 |
| openproceedings, in scope | 33 |
| in both | 21 (21 crawled records, 0 RIS-only) |
| in both, matched to a RIS-only record whose title another index record has | 0 |
| only in the Scholar set | 1,794 |
| only in openproceedings | 12 |

### Only in the Scholar set

| class | records | of these | of the Scholar set | crawled record | RIS-only record | meaning |
|---|---|---|---|---|---|---|
| `our_bug` | 0 | 0.0% | 0.0% | 0 | 0 | the oracle and the served engine disagree (must be 0) |
| `coverage_gap` | 3 | 0.2% | 0.2% | 0 | 0 | no record in the snapshot by forum id, proceedings id or title+venue+year |
| `stemming` | 32 | 1.8% | 1.8% | 32 | 0 | matches title or abstract only with an inflected form added |
| `full_text` | 1,753 | 97.7% | 96.6% | 1,747 | 6 | in the corpus with an abstract; no reading matches its title or abstract, inflected forms included |
| `unsettled` | 6 | 0.3% | 0.3% | 0 | 1 | the automation can't tell (see the row's evidence) |
| total | 1,794 | 100.0% | 98.8% | 1,779 | 7 | |

`crawled record` and `RIS-only record` say what the row's index record rests on (a row with no index record is in neither).

### Only in openproceedings

| class | records | of these | of the result | crawled record | RIS-only record | meaning |
|---|---|---|---|---|---|---|
| `our_bug` | 0 | 0.0% | 0.0% | 0 | 0 | the oracle and the served engine disagree (must be 0) |
| `scholar_missed` | 12 | 100.0% | 36.4% | 12 | 0 | an exact title or abstract match that the Scholar set lacks |
| total | 12 | 100.0% | 36.4% | 12 | 0 | |

`our_bug`: **0**. Rows for a person in `review.csv`: 21 unresolved, 179 spot check.

### Concept groups, over the 1,807 Scholar papers the index holds

How many of them hold each top-level group of the string in title or abstract, whatever their track and status:

| group | as run | with inflected forms |
|---|---|---|
| 1. `("foundation model" OR "large language model" OR llm OR "generative ai")` | 551 | 1,013 |
| 2. `(trustworthiness OR trustworthy OR trust OR "trustworthy ai")` | 191 | 197 |
| 3. `(benchmark OR leaderboard OR "evaluation framework")` | 480 | 800 |

Inflected forms added for the `stemming` test (the forms the compared records hold): `benchmark` → benchmarked, benchmarking, benchmarks; `evaluation` → evaluations; `foundation` → foundations; `framework` → frameworks; `language` → languages; `leaderboard` → leaderboards; `llm` → llms; `model` → modeled, modeling, models; `trust` → trusted, trusting.

### Scholar-only records listed

| record | title | venue | year | class | evidence |
|---|---|---|---|---|---|
| `op:iclr:2024:iclr-c3eb94d149aea08c28505d1e5234a21a` | Less is more: One-shot subgraph reasoning on large-scale knowledge graphs | ICLR | 2024 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:iclr:2024:QHROe7Mfcb (ICLR 2024): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 1, 2, inflected forms included) |
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
| `op:iclr:2026:7dTqUaY2Kl` | JailNewsBench: Multi-Lingual and Regional Benchmark for Fake News Generation under Jailbreak Attacks | ICLR | 2026 | `scholar_missed` | exact match on group 1: llm (abstract); group 2: trust (abstract); group 3: benchmark (title+abstract) |
| `op:iclr:2026:ZTAvANYFL5` | NurValues: Real-World Nursing Values Evaluation for Large Language Models in Clinical Context | ICLR | 2026 | `scholar_missed` | exact match on group 1: llm (abstract); group 2: trust (abstract); group 3: benchmark (abstract) |
| `op:iclr:2026:kVaE2kYjtV` | Unpacking Human Preference for LLMs: Demographically Aware Evaluation with the HUMAINE Framework | ICLR | 2026 | `scholar_missed` | exact match on group 1: llm (abstract); group 2: trust (abstract); group 3: leaderboard (abstract) |
| `op:icml:2025:V61nluxFlR` | Aligning with Logic: Measuring, Evaluating and Improving Logical Preference Consistency in Large Language Models | ICML | 2025 | `scholar_missed` | exact match on group 1: llm (abstract); group 2: trustworthy (abstract); group 3: "evaluation framework" (abstract) |
| `op:icml:2025:j3totqf8xW` | Position: Beyond Assistance – Reimagining LLMs as Ethical and Adaptive Co-Creators in Mental Health Care | ICML | 2025 | `scholar_missed` | exact match on group 1: llm (abstract); group 2: trustworthiness (abstract); group 3: "evaluation framework" (abstract) |
| `op:icml:2026:PW8YVqhI6K` | OpenDeception: Learning Deception and Trust in Human–AI Interaction via Multi-Agent Simulation | ICML | 2026 | `scholar_missed` | exact match on group 1: llm (abstract); group 2: trust (title+abstract); group 3: benchmark (abstract) |
| `op:icml:2026:PmAKKeZj7O` | Who can we trust? LLM-as-a-jury for Comparative Assessment | ICML | 2026 | `scholar_missed` | exact match on group 1: llm (title+abstract); group 2: trust (title); group 3: benchmark (abstract) |
| `op:icml:2026:W85McJPVMI` | ASyMOB: Algebraic Symbolic Mathematical Operations Benchmark | ICML | 2026 | `scholar_missed` | exact match on group 1: llm (abstract); group 2: trustworthy (abstract), "trustworthy ai" (abstract); group 3: benchmark (title) |
| `op:neurips:2025:XwqawBglmv` | LC-Opt: Benchmarking Reinforcement Learning and Agentic AI for End-to-End Liquid Cooling Optimization in Data Centers | NeurIPS | 2025 | `scholar_missed` | exact match on group 1: llm (abstract); group 2: trust (abstract); group 3: benchmark (abstract) |

**Finding.** Of the 1,815 in-scope papers of the Scholar set, 1,753 (96.6%) match this string nowhere in title or abstract, inflected forms included (`full_text`), and 32 (1.8%) match only through an inflected form (`stemming`). 21 (1.2%) are in the exact result.

- Of the 1,753 `full_text` papers, 1,747 rest on a crawled record and 6 on a RIS-only record, whose title and abstract are the import's own.
- 2 of them also fail the default track or status filters.
- **Sensitivity to the stemmer.** The `stemming` class uses an inflection-only stand-in (see Method); which stemmer stands for Scholar's is an open decision for the project owner. With every searched word replaced by its inflection stem read as a prefix (`benchmarks` → `benchmark*`, `evaluating` → `evaluat*`), 0 of the 1,753 (0.0%) `full_text` papers would match title or abstract. That is all this figure measures: it is not a stemmer, and one that strips derivational endings (`evaluation` to `evaluat`) or rewrites the stem could move more.

## Query `main-7-dollar`

The Scholar set is Google Scholar's answer to `main-7-most-updated`, not to this string. The numbers below are what this string keeps, drops and adds against that set; they say nothing about what Scholar would return for it.

Run in `mode=scholar`, exactly as written (`canonical_hash` `4cab505eec4e62899b541a212453bccf03fdae876baf5540205ed58117a94299`):

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
| openproceedings `total` (default filters; every venue and year) | 101 |
| openproceedings, in scope | 101 |
| in both | 51 (51 crawled records, 0 RIS-only) |
| in both, matched to a RIS-only record whose title another index record has | 0 |
| only in the Scholar set | 1,764 |
| only in openproceedings | 50 |

### Only in the Scholar set

| class | records | of these | of the Scholar set | crawled record | RIS-only record | meaning |
|---|---|---|---|---|---|---|
| `our_bug` | 0 | 0.0% | 0.0% | 0 | 0 | the oracle and the served engine disagree (must be 0) |
| `coverage_gap` | 3 | 0.2% | 0.2% | 0 | 0 | no record in the snapshot by forum id, proceedings id or title+venue+year |
| `stemming` | 2 | 0.1% | 0.1% | 2 | 0 | matches title or abstract only with an inflected form added |
| `full_text` | 1,753 | 99.4% | 96.6% | 1,747 | 6 | in the corpus with an abstract; no reading matches its title or abstract, inflected forms included |
| `unsettled` | 6 | 0.3% | 0.3% | 0 | 1 | the automation can't tell (see the row's evidence) |
| total | 1,764 | 100.0% | 97.2% | 1,749 | 7 | |

`crawled record` and `RIS-only record` say what the row's index record rests on (a row with no index record is in neither).

### Only in openproceedings

| class | records | of these | of the result | crawled record | RIS-only record | meaning |
|---|---|---|---|---|---|---|
| `our_bug` | 0 | 0.0% | 0.0% | 0 | 0 | the oracle and the served engine disagree (must be 0) |
| `compat_reading` | 38 | 76.0% | 37.6% | 38 | 0 | decided by how Scholar mode read the string (decision-002 phrases, `$`), not by the corpus |
| `scholar_missed` | 12 | 24.0% | 11.9% | 12 | 0 | an exact title or abstract match that the Scholar set lacks |
| total | 50 | 100.0% | 49.5% | 50 | 0 | |

`our_bug`: **0**. Rows for a person in `review.csv`: 21 unresolved, 180 spot check.

### Concept groups, over the 1,807 Scholar papers the index holds

How many of them hold each top-level group of the string in title or abstract, whatever their track and status:

| group | as run | with inflected forms |
|---|---|---|
| 1. `("foundation model$" OR "large language model$" OR llm$ OR "generative ai")` | 1,013 | 1,013 |
| 2. `(trustworthiness OR trustworthy OR trust OR "trustworthy ai")` | 191 | 197 |
| 3. `(benchmark$ OR leaderboard$ OR "evaluation framework$")` | 790 | 800 |

Inflected forms added for the `stemming` test (the forms the compared records hold): `benchmark` → benchmarked, benchmarking, benchmarks; `evaluation` → evaluations; `foundation` → foundations; `framework` → frameworks; `language` → languages; `leaderboard` → leaderboards; `llm` → llms; `model` → modeled, modeling, models; `trust` → trusted, trusting.

### Scholar-only records listed

| record | title | venue | year | class | evidence |
|---|---|---|---|---|---|
| `op:iclr:2024:iclr-c3eb94d149aea08c28505d1e5234a21a` | Less is more: One-shot subgraph reasoning on large-scale knowledge graphs | ICLR | 2024 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:iclr:2024:QHROe7Mfcb (ICLR 2024): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 1, 2, inflected forms included) |
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
| `op:iclr:2026:5RATVAQGPx` | Jackpot: Align Actor-Policy Distribution for scalable and stable RL for LLM | ICLR | 2026 | `compat_reading` | `$`: a zero-or-one wildcard here, no wildcard in Scholar |
| `op:iclr:2026:7dTqUaY2Kl` | JailNewsBench: Multi-Lingual and Regional Benchmark for Fake News Generation under Jailbreak Attacks | ICLR | 2026 | `scholar_missed` | exact match on group 1: "large language model$" (abstract), llm$ (abstract); group 2: trust (abstract); group 3: benchmark$ (title+abstract) |
| `op:iclr:2026:AhvApZghHf` | MARS-Sep: Multimodal-Aligned Reinforced Sound Separation | ICLR | 2026 | `compat_reading` | `$`: a zero-or-one wildcard here, no wildcard in Scholar |
| `op:iclr:2026:BYtqk6AVuL` | MedLesionVQA: A Multimodal Benchmark Emulating Clinical Visual Diagnosis for Body Surface Health | ICLR | 2026 | `compat_reading` | `$`: a zero-or-one wildcard here, no wildcard in Scholar |
| `op:iclr:2026:GODFBZhFcX` | From Assumptions to Actions: Turning LLM Reasoning into Uncertainty-Aware Planning for Embodied Agents | ICLR | 2026 | `compat_reading` | `$`: a zero-or-one wildcard here, no wildcard in Scholar |
| `op:iclr:2026:IIgl5MWelz` | Prosperity before Collapse: How Far Can Off-Policy RL Reach with Stale Data on LLMs? | ICLR | 2026 | `compat_reading` | `$`: a zero-or-one wildcard here, no wildcard in Scholar |
| `op:iclr:2026:Xa6QRrXrKX` | DUET: Distilled LLM Unlearning from an Efficiently Contextualized Teacher | ICLR | 2026 | `compat_reading` | `$`: a zero-or-one wildcard here, no wildcard in Scholar |
| `op:iclr:2026:ZTAvANYFL5` | NurValues: Real-World Nursing Values Evaluation for Large Language Models in Clinical Context | ICLR | 2026 | `scholar_missed` | exact match on group 1: "large language model$" (title), llm$ (abstract); group 2: trust (abstract); group 3: benchmark$ (abstract) |
| `op:iclr:2026:kVaE2kYjtV` | Unpacking Human Preference for LLMs: Demographically Aware Evaluation with the HUMAINE Framework | ICLR | 2026 | `scholar_missed` | exact match on group 1: "large language model$" (abstract), llm$ (title+abstract); group 2: trust (abstract); group 3: benchmark$ (abstract), leaderboard$ (abstract) |
| `op:iclr:2026:nJgS06sX3O` | DefensiveKV: Taming the Fragility of KV Cache Eviction in LLM Inference | ICLR | 2026 | `compat_reading` | `$`: a zero-or-one wildcard here, no wildcard in Scholar |
| `op:iclr:2026:oXlSEcxD6N` | Trust-Region Adaptive Policy Optimization | ICLR | 2026 | `compat_reading` | `$`: a zero-or-one wildcard here, no wildcard in Scholar |
| `op:iclr:2026:vfbeleLBWv` | Trust The Typical | ICLR | 2026 | `compat_reading` | `$`: a zero-or-one wildcard here, no wildcard in Scholar |
| `op:iclr:2026:wb05ver1k8` | Grounding Generative Planners in Verifiable Logic: A Hybrid Architecture for Trustworthy Embodied AI | ICLR | 2026 | `compat_reading` | `$`: a zero-or-one wildcard here, no wildcard in Scholar |
| `op:icml:2024:bWUU0LwwMp` | Position: TrustLLM: Trustworthiness in Large Language Models | ICML | 2024 | `compat_reading` | `$`: a zero-or-one wildcard here, no wildcard in Scholar |
| `op:icml:2025:V61nluxFlR` | Aligning with Logic: Measuring, Evaluating and Improving Logical Preference Consistency in Large Language Models | ICML | 2025 | `scholar_missed` | exact match on group 1: "large language model$" (title+abstract), llm$ (abstract); group 2: trustworthy (abstract); group 3: "evaluation framework$" (abstract) |
| `op:icml:2025:j3totqf8xW` | Position: Beyond Assistance – Reimagining LLMs as Ethical and Adaptive Co-Creators in Mental Health Care | ICML | 2025 | `scholar_missed` | exact match on group 1: "large language model$" (abstract), llm$ (title+abstract); group 2: trustworthiness (abstract); group 3: "evaluation framework$" (abstract) |
| `op:icml:2025:zvZTIXkzDe` | DAMA: Data- and Model-aware Alignment of Multi-modal LLMs | ICML | 2025 | `compat_reading` | `$`: a zero-or-one wildcard here, no wildcard in Scholar |
| `op:icml:2026:0RBMhFule7` | Reinforcement-aware Knowledge Distillation for LLM Reasoning | ICML | 2026 | `compat_reading` | `$`: a zero-or-one wildcard here, no wildcard in Scholar |
| `op:icml:2026:0tdnyH7uXp` | Language Bias in LVLMs: From In-Depth Analysis to Simple and Effective Mitigation | ICML | 2026 | `compat_reading` | `$`: a zero-or-one wildcard here, no wildcard in Scholar |
| `op:icml:2026:2OSFz8cteI` | Trust It or Not: Evidential Uncertainty for Feed-Forward 3D Reconstruction with Trust3R | ICML | 2026 | `compat_reading` | `$`: a zero-or-one wildcard here, no wildcard in Scholar |
| `op:icml:2026:51WmDaMOtd` | CORE: Conflict-Oriented Reasoning for General Multimodal Manipulation Detection | ICML | 2026 | `compat_reading` | `$`: a zero-or-one wildcard here, no wildcard in Scholar |
| `op:icml:2026:98XhDbtB21` | QUATRO: Query-Adaptive Trust Region Policy Optimization for LLM Fine-tuning | ICML | 2026 | `compat_reading` | `$`: a zero-or-one wildcard here, no wildcard in Scholar |
| `op:icml:2026:AprtLFCirb` | FactGuard: Agentic Video Misinformation Detection via Reinforcement Learning | ICML | 2026 | `compat_reading` | `$`: a zero-or-one wildcard here, no wildcard in Scholar |
| `op:icml:2026:I0RgZXTO53` | Bridging the Knowledge-Prediction Gap in LLMs on Multiple-Choice Questions | ICML | 2026 | `compat_reading` | `$`: a zero-or-one wildcard here, no wildcard in Scholar |
| `op:icml:2026:Kb2m543agS` | Causal Detection of Multi-Step LLM Agent Attacks | ICML | 2026 | `compat_reading` | `$`: a zero-or-one wildcard here, no wildcard in Scholar |
| `op:icml:2026:NT4Cz09S4w` | Ratio-Variance Regularized Policy Optimization | ICML | 2026 | `compat_reading` | `$`: a zero-or-one wildcard here, no wildcard in Scholar |
| `op:icml:2026:PW8YVqhI6K` | OpenDeception: Learning Deception and Trust in Human–AI Interaction via Multi-Agent Simulation | ICML | 2026 | `scholar_missed` | exact match on group 1: "large language model$" (abstract), llm$ (abstract); group 2: trust (title+abstract); group 3: benchmark$ (abstract) |
| `op:icml:2026:PmAKKeZj7O` | Who can we trust? LLM-as-a-jury for Comparative Assessment | ICML | 2026 | `scholar_missed` | exact match on group 1: "large language model$" (abstract), llm$ (title+abstract); group 2: trust (title); group 3: benchmark$ (abstract) |
| `op:icml:2026:UbzajT84Nd` | Domain-Shift-Aware Conformal Prediction for Large Language Models | ICML | 2026 | `compat_reading` | `$`: a zero-or-one wildcard here, no wildcard in Scholar |
| `op:icml:2026:VsaxovdJDA` | Learning from Comparison: Constrained Projection Policy Optimization for Pareto-Front Improvement | ICML | 2026 | `compat_reading` | `$`: a zero-or-one wildcard here, no wildcard in Scholar |
| `op:icml:2026:W2eEMPjzIQ` | Position: Time-Series Foundation Models Require Explicit Domain-Level Benchmarks | ICML | 2026 | `compat_reading` | `$`: a zero-or-one wildcard here, no wildcard in Scholar |
| `op:icml:2026:W85McJPVMI` | ASyMOB: Algebraic Symbolic Mathematical Operations Benchmark | ICML | 2026 | `scholar_missed` | exact match on group 1: "large language model$" (abstract), llm$ (abstract); group 2: trustworthy (abstract), "trustworthy ai" (abstract); group 3: benchmark$ (title+abstract) |
| `op:icml:2026:ZQSRsyk5Jc` | DecepChain: Inducing Deceptive Reasoning in Large Language Models | ICML | 2026 | `compat_reading` | `$`: a zero-or-one wildcard here, no wildcard in Scholar |
| `op:icml:2026:ZeZi4SerW0` | Immuno-VLM: Immunizing Large Vision-Language Models via Generative Semantic Antibodies for Open-World Trustworthiness | ICML | 2026 | `compat_reading` | `$`: a zero-or-one wildcard here, no wildcard in Scholar |
| `op:icml:2026:aBosytnQ6f` | CaliDist: Calibrating Large Language Models via Behavioral Robustness to Distraction | ICML | 2026 | `compat_reading` | `$`: a zero-or-one wildcard here, no wildcard in Scholar |
| `op:icml:2026:bHYAWawd4A` | Faults in Our Formal Benchmarking: Dataset Defects and Evaluation Failures in Lean Theorem Proving | ICML | 2026 | `compat_reading` | `$`: a zero-or-one wildcard here, no wildcard in Scholar |
| `op:icml:2026:l8RBjihPFk` | Does AI Reviewer See the Full Picture? Attacking and Defending Multimodal Peer Review | ICML | 2026 | `compat_reading` | `$`: a zero-or-one wildcard here, no wildcard in Scholar |
| `op:icml:2026:t4Jc7C9bTx` | Clipping Low-Probability Tokens in SFT Yields a Generalizable Initialization for RL | ICML | 2026 | `compat_reading` | `$`: a zero-or-one wildcard here, no wildcard in Scholar |
| `op:neurips:2023:kaHpo8OZw2` | DecodingTrust: A Comprehensive Assessment of Trustworthiness in GPT Models | NeurIPS | 2023 | `compat_reading` | `$`: a zero-or-one wildcard here, no wildcard in Scholar |
| `op:neurips:2024:5c1hh8AeHv` | MultiTrust: A Comprehensive Benchmark Towards Trustworthy Multimodal Large Language Models | NeurIPS | 2024 | `compat_reading` | `$`: a zero-or-one wildcard here, no wildcard in Scholar |
| `op:neurips:2025:Lm8HcblPCJ` | VMDT: Decoding the Trustworthiness of Video Foundation Models | NeurIPS | 2025 | `compat_reading` | `$`: a zero-or-one wildcard here, no wildcard in Scholar |
| `op:neurips:2025:QQhQIqons0` | SEC-bench: Automated Benchmarking of LLM Agents on Real-World Software Security Tasks | NeurIPS | 2025 | `compat_reading` | `$`: a zero-or-one wildcard here, no wildcard in Scholar |
| `op:neurips:2025:R5EBtNE2Y9` | HeavyWater and SimplexWater: Distortion-free LLM Watermarks for Low-Entropy Distributions | NeurIPS | 2025 | `compat_reading` | `$`: a zero-or-one wildcard here, no wildcard in Scholar |
| `op:neurips:2025:XwqawBglmv` | LC-Opt: Benchmarking Reinforcement Learning and Agentic AI for End-to-End Liquid Cooling Optimization in Data Centers | NeurIPS | 2025 | `scholar_missed` | exact match on group 1: llm$ (abstract); group 2: trust (abstract); group 3: benchmark$ (abstract) |
| `op:neurips:2025:eafIjoZAHm` | GnnXemplar: Exemplars to Explanations - Natural Language Rules for Global GNN Interpretability | NeurIPS | 2025 | `compat_reading` | `$`: a zero-or-one wildcard here, no wildcard in Scholar |
| `op:neurips:2025:gA3fFAEXNT` | Trust, But Verify: A Self-Verification Approach to Reinforcement Learning with Verifiable Rewards | NeurIPS | 2025 | `compat_reading` | `$`: a zero-or-one wildcard here, no wildcard in Scholar |

**Finding.** Of the 1,815 in-scope papers of the Scholar set, 1,753 (96.6%) match this string nowhere in title or abstract, inflected forms included (`full_text`), and 2 (0.1%) match only through an inflected form (`stemming`). 51 (2.8%) are in the exact result.

- Of the 1,753 `full_text` papers, 1,747 rest on a crawled record and 6 on a RIS-only record, whose title and abstract are the import's own.
- 2 of them also fail the default track or status filters.
- **Sensitivity to the stemmer.** The `stemming` class uses an inflection-only stand-in (see Method); which stemmer stands for Scholar's is an open decision for the project owner. With every searched word replaced by its inflection stem read as a prefix (`benchmarks` → `benchmark*`, `evaluating` → `evaluat*`), 0 of the 1,753 (0.0%) `full_text` papers would match title or abstract. That is all this figure measures: it is not a stemmer, and one that strips derivational endings (`evaluation` to `evaluat`) or rewrites the stem could move more.

## Query `main-2-pop`

The Scholar set is Google Scholar's answer to `main-7-most-updated`, not to this string. The numbers below are what this string keeps, drops and adds against that set; they say nothing about what Scholar would return for it.

Run in `mode=scholar`, exactly as written (`canonical_hash` `b92c9c32052a50b6306212b11628a99102a57ee94ff9bf429f0cca5752b7197b`):

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
| openproceedings `total` (default filters; every venue and year) | 114 |
| openproceedings, in scope | 114 |
| in both | 65 (65 crawled records, 0 RIS-only) |
| in both, matched to a RIS-only record whose title another index record has | 0 |
| only in the Scholar set | 1,750 |
| only in openproceedings | 49 |

### Only in the Scholar set

| class | records | of these | of the Scholar set | crawled record | RIS-only record | meaning |
|---|---|---|---|---|---|---|
| `our_bug` | 0 | 0.0% | 0.0% | 0 | 0 | the oracle and the served engine disagree (must be 0) |
| `coverage_gap` | 3 | 0.2% | 0.2% | 0 | 0 | no record in the snapshot by forum id, proceedings id or title+venue+year |
| `stemming` | 32 | 1.8% | 1.8% | 32 | 0 | matches title or abstract only with an inflected form added |
| `full_text` | 1,709 | 97.7% | 94.2% | 1,703 | 6 | in the corpus with an abstract; no reading matches its title or abstract, inflected forms included |
| `unsettled` | 6 | 0.3% | 0.3% | 0 | 1 | the automation can't tell (see the row's evidence) |
| total | 1,750 | 100.0% | 96.4% | 1,735 | 7 | |

`crawled record` and `RIS-only record` say what the row's index record rests on (a row with no index record is in neither).

### Only in openproceedings

| class | records | of these | of the result | crawled record | RIS-only record | meaning |
|---|---|---|---|---|---|---|
| `our_bug` | 0 | 0.0% | 0.0% | 0 | 0 | the oracle and the served engine disagree (must be 0) |
| `compat_reading` | 49 | 100.0% | 43.0% | 49 | 0 | decided by how Scholar mode read the string (decision-002 phrases, `$`), not by the corpus |
| total | 49 | 100.0% | 43.0% | 49 | 0 | |

`our_bug`: **0**. Rows for a person in `review.csv`: 9 unresolved, 179 spot check.

### Concept groups, over the 1,807 Scholar papers the index holds

How many of them hold each top-level group of the string in title or abstract, whatever their track and status:

| group | as run | with inflected forms |
|---|---|---|
| 1. `("large language model$" OR llm OR "foundation model$" OR "generative ai$" OR "vision language model$" OR vlm OR "multimodal model$" OR "ai agent$" OR "text to image model$")` | 1,116 | 1,160 |
| 2. `(trust OR trustworthy OR trustworthiness OR "trustworthy ai$")` | 191 | 197 |
| 3. `(benchmark OR dataset OR evaluation OR leaderboard OR "evaluation framework$" OR "test suite$")` | 794 | 1,257 |

Inflected forms added for the `stemming` test (the forms the compared records hold): `agent` → agents; `benchmark` → benchmarked, benchmarking, benchmarks; `dataset` → datasets; `evaluation` → evaluations; `foundation` → foundations; `framework` → frameworks; `image` → images, imaging; `language` → languages; `leaderboard` → leaderboards; `llm` → llms; `model` → modeled, modeling, models; `suite` → suit, suited, suites; `test` → tested, testing, tests; `text` → texts; `trust` → trusted, trusting; `vlm` → vlms.

### Scholar-only records listed

| record | title | venue | year | class | evidence |
|---|---|---|---|---|---|
| `op:iclr:2024:iclr-c3eb94d149aea08c28505d1e5234a21a` | Less is more: One-shot subgraph reasoning on large-scale knowledge graphs | ICLR | 2024 | `unsettled` | matched by proceedings id to a record only the imported set holds, whose title is also on op:iclr:2024:QHROe7Mfcb (ICLR 2024): possibly one paper under two ids; otherwise `full_text` (no title or abstract match for group 1, 2, inflected forms included) |
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
| `op:iclr:2026:6cEPDGaShH` | Invisible Safety Threat: Malicious Finetuning for LLM via Steganography | ICLR | 2026 | `compat_reading` | decision-002: the unquoted `\|` items are phrases here, neighbouring words ORed in Scholar |
| `op:iclr:2026:7dTqUaY2Kl` | JailNewsBench: Multi-Lingual and Regional Benchmark for Fake News Generation under Jailbreak Attacks | ICLR | 2026 | `compat_reading` | decision-002: the unquoted `\|` items are phrases here, neighbouring words ORed in Scholar |
| `op:iclr:2026:9jYpHmI8ot` | Bridging Explainability and Embeddings: BEE Aware of Spuriousness | ICLR | 2026 | `compat_reading` | decision-002: the unquoted `\|` items are phrases here, neighbouring words ORed in Scholar; `$`: a zero-or-one wildcard here, no wildcard in Scholar |
| `op:iclr:2026:BYtqk6AVuL` | MedLesionVQA: A Multimodal Benchmark Emulating Clinical Visual Diagnosis for Body Surface Health | ICLR | 2026 | `compat_reading` | decision-002: the unquoted `\|` items are phrases here, neighbouring words ORed in Scholar; `$`: a zero-or-one wildcard here, no wildcard in Scholar |
| `op:iclr:2026:IIgl5MWelz` | Prosperity before Collapse: How Far Can Off-Policy RL Reach with Stale Data on LLMs? | ICLR | 2026 | `compat_reading` | decision-002: the unquoted `\|` items are phrases here, neighbouring words ORed in Scholar |
| `op:iclr:2026:Xa6QRrXrKX` | DUET: Distilled LLM Unlearning from an Efficiently Contextualized Teacher | ICLR | 2026 | `compat_reading` | decision-002: the unquoted `\|` items are phrases here, neighbouring words ORed in Scholar |
| `op:iclr:2026:ZTAvANYFL5` | NurValues: Real-World Nursing Values Evaluation for Large Language Models in Clinical Context | ICLR | 2026 | `compat_reading` | decision-002: the unquoted `\|` items are phrases here, neighbouring words ORed in Scholar |
| `op:iclr:2026:ggycXmhrrG` | AFTER: Mitigating the Object Hallucination of LVLM via Adaptive Factual-Guided Activation Editing | ICLR | 2026 | `compat_reading` | decision-002: the unquoted `\|` items are phrases here, neighbouring words ORed in Scholar; `$`: a zero-or-one wildcard here, no wildcard in Scholar |
| `op:iclr:2026:kVaE2kYjtV` | Unpacking Human Preference for LLMs: Demographically Aware Evaluation with the HUMAINE Framework | ICLR | 2026 | `compat_reading` | decision-002: the unquoted `\|` items are phrases here, neighbouring words ORed in Scholar |
| `op:iclr:2026:vfbeleLBWv` | Trust The Typical | ICLR | 2026 | `compat_reading` | decision-002: the unquoted `\|` items are phrases here, neighbouring words ORed in Scholar |
| `op:iclr:2026:zfVICPB5Sv` | Silent Leaks: Implicit Knowledge Extraction Attack on RAG Systems | ICLR | 2026 | `compat_reading` | decision-002: the unquoted `\|` items are phrases here, neighbouring words ORed in Scholar; `$`: a zero-or-one wildcard here, no wildcard in Scholar |
| `op:icml:2024:3tJDnEszco` | CHEMREASONER: Heuristic Search over a Large Language Model’s Knowledge Space using Quantum-Chemical Feedback | ICML | 2024 | `compat_reading` | decision-002: the unquoted `\|` items are phrases here, neighbouring words ORed in Scholar |
| `op:icml:2024:Cw6Xl0g8a5` | Probabilistic Conceptual Explainers: Trustworthy Conceptual Explanations for Vision Foundation Models | ICML | 2024 | `compat_reading` | decision-002: the unquoted `\|` items are phrases here, neighbouring words ORed in Scholar; `$`: a zero-or-one wildcard here, no wildcard in Scholar |
| `op:icml:2024:DKKg5EFAFr` | Evaluating Quantized Large Language Models | ICML | 2024 | `compat_reading` | decision-002: the unquoted `\|` items are phrases here, neighbouring words ORed in Scholar; `$`: a zero-or-one wildcard here, no wildcard in Scholar |
| `op:icml:2024:Fzp1DRzCIN` | Implicit meta-learning may lead language models to trust more reliable sources | ICML | 2024 | `compat_reading` | decision-002: the unquoted `\|` items are phrases here, neighbouring words ORed in Scholar; `$`: a zero-or-one wildcard here, no wildcard in Scholar |
| `op:icml:2024:b1YQ5WKY3w` | Is In-Context Learning in Large Language Models Bayesian? A Martingale Perspective | ICML | 2024 | `compat_reading` | decision-002: the unquoted `\|` items are phrases here, neighbouring words ORed in Scholar |
| `op:icml:2024:bWUU0LwwMp` | Position: TrustLLM: Trustworthiness in Large Language Models | ICML | 2024 | `compat_reading` | decision-002: the unquoted `\|` items are phrases here, neighbouring words ORed in Scholar; `$`: a zero-or-one wildcard here, no wildcard in Scholar |
| `op:icml:2024:e3Dpq3WdMv` | Decoding Compressed Trust: Scrutinizing the Trustworthiness of Efficient LLMs Under Compression | ICML | 2024 | `compat_reading` | decision-002: the unquoted `\|` items are phrases here, neighbouring words ORed in Scholar; `$`: a zero-or-one wildcard here, no wildcard in Scholar |
| `op:icml:2025:V61nluxFlR` | Aligning with Logic: Measuring, Evaluating and Improving Logical Preference Consistency in Large Language Models | ICML | 2025 | `compat_reading` | decision-002: the unquoted `\|` items are phrases here, neighbouring words ORed in Scholar |
| `op:icml:2025:j3totqf8xW` | Position: Beyond Assistance – Reimagining LLMs as Ethical and Adaptive Co-Creators in Mental Health Care | ICML | 2025 | `compat_reading` | decision-002: the unquoted `\|` items are phrases here, neighbouring words ORed in Scholar |
| `op:icml:2026:6aFU1bnUnv` | Reward Auditor: Inference on Reward Modeling Suitability in Real-World Perturbed Scenarios | ICML | 2026 | `compat_reading` | decision-002: the unquoted `\|` items are phrases here, neighbouring words ORed in Scholar |
| `op:icml:2026:BGcw0KWStP` | PRPO: Paragraph-level Policy Optimization for Vision-Language Deepfake Detection | ICML | 2026 | `compat_reading` | decision-002: the unquoted `\|` items are phrases here, neighbouring words ORed in Scholar |
| `op:icml:2026:E5SVowO13b` | Unlearning Isn't Deletion: Investigating Reversibility of Machine Unlearning in LLMs | ICML | 2026 | `compat_reading` | decision-002: the unquoted `\|` items are phrases here, neighbouring words ORed in Scholar; `$`: a zero-or-one wildcard here, no wildcard in Scholar |
| `op:icml:2026:EB8MHApOav` | AutoQRA: Joint Optimization of Mixed-Precision Quantization and Low-rank Adapters for Efficient LLM Fine-Tuning | ICML | 2026 | `compat_reading` | decision-002: the unquoted `\|` items are phrases here, neighbouring words ORed in Scholar |
| `op:icml:2026:Kb2m543agS` | Causal Detection of Multi-Step LLM Agent Attacks | ICML | 2026 | `compat_reading` | decision-002: the unquoted `\|` items are phrases here, neighbouring words ORed in Scholar |
| `op:icml:2026:PW8YVqhI6K` | OpenDeception: Learning Deception and Trust in Human–AI Interaction via Multi-Agent Simulation | ICML | 2026 | `compat_reading` | decision-002: the unquoted `\|` items are phrases here, neighbouring words ORed in Scholar |
| `op:icml:2026:PmAKKeZj7O` | Who can we trust? LLM-as-a-jury for Comparative Assessment | ICML | 2026 | `compat_reading` | decision-002: the unquoted `\|` items are phrases here, neighbouring words ORed in Scholar |
| `op:icml:2026:UbzajT84Nd` | Domain-Shift-Aware Conformal Prediction for Large Language Models | ICML | 2026 | `compat_reading` | decision-002: the unquoted `\|` items are phrases here, neighbouring words ORed in Scholar; `$`: a zero-or-one wildcard here, no wildcard in Scholar |
| `op:icml:2026:W2eEMPjzIQ` | Position: Time-Series Foundation Models Require Explicit Domain-Level Benchmarks | ICML | 2026 | `compat_reading` | decision-002: the unquoted `\|` items are phrases here, neighbouring words ORed in Scholar; `$`: a zero-or-one wildcard here, no wildcard in Scholar |
| `op:icml:2026:W85McJPVMI` | ASyMOB: Algebraic Symbolic Mathematical Operations Benchmark | ICML | 2026 | `compat_reading` | decision-002: the unquoted `\|` items are phrases here, neighbouring words ORed in Scholar |
| `op:icml:2026:Ygg3KJPeT6` | DocVAL: Validated Chain-of-Thought Distillation for Grounded Document VQA | ICML | 2026 | `compat_reading` | decision-002: the unquoted `\|` items are phrases here, neighbouring words ORed in Scholar |
| `op:icml:2026:ZQSRsyk5Jc` | DecepChain: Inducing Deceptive Reasoning in Large Language Models | ICML | 2026 | `compat_reading` | decision-002: the unquoted `\|` items are phrases here, neighbouring words ORed in Scholar |
| `op:icml:2026:bHYAWawd4A` | Faults in Our Formal Benchmarking: Dataset Defects and Evaluation Failures in Lean Theorem Proving | ICML | 2026 | `compat_reading` | decision-002: the unquoted `\|` items are phrases here, neighbouring words ORed in Scholar |
| `op:icml:2026:c2dM89gjRi` | Position: Reasoning is a Learnable Rule-Based Process | ICML | 2026 | `compat_reading` | decision-002: the unquoted `\|` items are phrases here, neighbouring words ORed in Scholar |
| `op:icml:2026:l8RBjihPFk` | Does AI Reviewer See the Full Picture? Attacking and Defending Multimodal Peer Review | ICML | 2026 | `compat_reading` | decision-002: the unquoted `\|` items are phrases here, neighbouring words ORed in Scholar; `$`: a zero-or-one wildcard here, no wildcard in Scholar |
| `op:neurips:2021:bB-l0cnS3E` | Evaluation of Human-AI Teams for Learned and Rule-Based Agents in Hanabi | NeurIPS | 2021 | `compat_reading` | decision-002: the unquoted `\|` items are phrases here, neighbouring words ORed in Scholar; `$`: a zero-or-one wildcard here, no wildcard in Scholar |
| `op:neurips:2023:kaHpo8OZw2` | DecodingTrust: A Comprehensive Assessment of Trustworthiness in GPT Models | NeurIPS | 2023 | `compat_reading` | decision-002: the unquoted `\|` items are phrases here, neighbouring words ORed in Scholar; `$`: a zero-or-one wildcard here, no wildcard in Scholar |
| `op:neurips:2024:5c1hh8AeHv` | MultiTrust: A Comprehensive Benchmark Towards Trustworthy Multimodal Large Language Models | NeurIPS | 2024 | `compat_reading` | decision-002: the unquoted `\|` items are phrases here, neighbouring words ORed in Scholar; `$`: a zero-or-one wildcard here, no wildcard in Scholar |
| `op:neurips:2025:Lm8HcblPCJ` | VMDT: Decoding the Trustworthiness of Video Foundation Models | NeurIPS | 2025 | `compat_reading` | decision-002: the unquoted `\|` items are phrases here, neighbouring words ORed in Scholar; `$`: a zero-or-one wildcard here, no wildcard in Scholar |
| `op:neurips:2025:QQhQIqons0` | SEC-bench: Automated Benchmarking of LLM Agents on Real-World Software Security Tasks | NeurIPS | 2025 | `compat_reading` | decision-002: the unquoted `\|` items are phrases here, neighbouring words ORed in Scholar |
| `op:neurips:2025:XwqawBglmv` | LC-Opt: Benchmarking Reinforcement Learning and Agentic AI for End-to-End Liquid Cooling Optimization in Data Centers | NeurIPS | 2025 | `compat_reading` | decision-002: the unquoted `\|` items are phrases here, neighbouring words ORed in Scholar |
| `op:neurips:2025:zPKeJAEo27` | What is Your Data Worth to GPT? LLM-Scale Data Valuation with Influence Functions | NeurIPS | 2025 | `compat_reading` | decision-002: the unquoted `\|` items are phrases here, neighbouring words ORed in Scholar |

**Finding.** Of the 1,815 in-scope papers of the Scholar set, 1,709 (94.2%) match this string nowhere in title or abstract, inflected forms included (`full_text`), and 32 (1.8%) match only through an inflected form (`stemming`). 65 (3.6%) are in the exact result.

- Of the 1,709 `full_text` papers, 1,703 rest on a crawled record and 6 on a RIS-only record, whose title and abstract are the import's own.
- 2 of them also fail the default track or status filters.
- **Sensitivity to the stemmer.** The `stemming` class uses an inflection-only stand-in (see Method); which stemmer stands for Scholar's is an open decision for the project owner. With every searched word replaced by its inflection stem read as a prefix (`benchmarks` → `benchmark*`, `evaluating` → `evaluat*`), 2 of the 1,709 (0.1%) `full_text` papers would match title or abstract. That is all this figure measures: it is not a stemmer, and one that strips derivational endings (`evaluation` to `evaluat`) or rewrites the stem could move more.

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
- **Earlier counts.** On index `05a0541717f6` (snapshot `2026-09-29-d552baa07aed`, no 2026 crawl) the
  2026-09-30 runs gave 27 records for the literal string and 67 for the `$` string, 51 of them among the
  review's records and 16 not; `docs/results/2026-10-04-scholar-comparison.md` reproduces all four on that
  index (`main-7-most-updated` limited to 2020–2026 is the literal string). An index built after the 2026 crawl
  holds more records, so its counts are larger.
- **The set is in the index.** Every snapshot so far was built with the set imported as its `ris` source
  (1,805 of the set's records, their ids from scholarmend's claims). Where a crawl holds the paper too, the two
  are merged and the record has an independent source; where none does, the index record is the import alone.
  On the 2026-09-29 snapshot that was 530 of the matched papers, nearly all of them 2026, which no crawl had
  reached. The 2026 OpenReview crawl (snapshot `2026-10-05-47d4e190ca81`, TASK-178) merged almost all of them
  into crawled records. "What the matches rest on" counts the two kinds apart for the index a report ran on.
- **Matching.** This report matches the set by URL and title, as it would any RIS file, not by the import's
  ids.
