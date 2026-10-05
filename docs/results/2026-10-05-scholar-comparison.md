# Scholar comparison, 2026-10-05

- Index: `index_version` `fd13d8d27535`, `tokenizer_version` `3`
- Snapshot: `2026-10-05-10b5a205a63f`, `snapshot_hash` `10b5a205a63f964496b9b572321785cf4c845c49fac4bf6cbdf5ab3dfe4cbe76` (133,629 records)
- Scholar set: `mended.ris`, sha256 `ec0b1367acb6d3764780db0eb00b11868d1fe14ebe437b106aa4215ae7476a7b` (1,834 records)
- Scope, both sides: ICLR, ICML, NeurIPS; 2020–2026
- Queries: `main-7-most-updated`, `main-7-dollar`, `main-2-pop`
- Query file: `trust-evals.txt`, sha256 `16afdaff80f1c4767ea7e92d3854620ff73ed5beec192995743a03d97ee8e47c`
- Query file: `scholar-comparison-strings.txt`, sha256 `bc55c6e2dddb7300fea1608a0eaf6fb2f6bff2735babf95d777343fe1d81e56b`
- Notes: `scholar-comparison-notes.md`, sha256 `66127116eec0caa947a75c9a4f9e458af5dc36ea4742a14cca2eb16ff4e94602`
- Command: `op eval scholar --ris mended.ris --query-file trust-evals.txt --query-file scholar-comparison-strings.txt --name main-7-most-updated --name main-7-dollar --name main-2-pop --years 2020..2026 --answers main-7-most-updated --notes scholar-comparison-notes.md --index fd13d8d27535 --date 2026-10-05`
- Review rows: `2026-10-05-scholar-comparison-review.csv` (586 rows; 48 left for a call, 48 called)

**`our_bug`: 0** across 3 queries.

**What the matches rest on.** Of the 1,813 in-scope papers of the Scholar set, 1,805 match an index record: 1,805 a record with an independent source (a crawl), 0 a record whose only source is an imported RIS set. A match of the second kind is the set matching its own import, and says nothing about coverage (see Matching).

| query | Scholar set in scope | openproceedings in scope | both | only Scholar | only openproceedings | `full_text` | of them RIS-only | `stemming` | unresolved |
|---|---|---|---|---|---|---|---|---|---|
| `main-7-most-updated` | 1,813 | 33 | 21 | 1,792 | 12 | 1,752 (96.6%) | 0 | 32 (1.8%) | 20 |
| `main-7-dollar` † | 1,813 | 101 | 51 | 1,762 | 50 | 1,752 (96.6%) | 0 | 2 (0.1%) | 20 |
| `main-2-pop` † | 1,813 | 114 | 65 | 1,748 | 49 | 1,708 (94.2%) | 0 | 32 (1.8%) | 8 |

† The Scholar set is Google Scholar's answer to `main-7-most-updated` only. For `main-7-dollar`, `main-2-pop` the columns are what the string keeps, drops and adds against that same set, not a comparison with what Scholar returns for it.

## Matching the Scholar set to the index

Each Scholar record is matched by spec 01's merge rules, in their order: the OpenReview forum id its URL names, else the proceedings paper its URL names (the native id within that venue and year), else the dedup title key within the same venue and year. A title alone never matches. A matched record is scoped by its index record's venue and year, an unmatched one by its own; records outside the scope are dropped before comparing.

| | records |
|---|---|
| read | 1,834 |
| outside the scope (ICLR, ICML, NeurIPS; 2020–2026) | 19 |
| in scope | 1,815 |
| repeats of a paper already counted | 2 |
| **papers in scope** (the denominator of every percentage of the Scholar set) | **1,813** |

| matched by | papers |
|---|---|
| proceedings id | 1,635 |
| forum id | 168 |
| no match (no venue) | 5 |
| no match (not found) | 3 |
| title venue year | 2 |

`no match (no venue)`: 5 records whose venue string is empty or cut by Scholar (`…`) and whose URLs name no indexed paper, but whose title key an in-scope index record of the same year has. A title alone is never a match, so they are counted in scope and listed as `unsettled` for a reviewer, with that record named.

Outside the scope: 19 venue unrecognised. `venue unrecognised` means the record's venue string is not exactly one of Scholar mode's source names and no URL of it names an indexed paper: it names another venue in full, or it is empty or cut (`…`) and no in-scope index record of its year has its title. Venue strings: International Conference on Machine … (2); International Conference … (2); (no venue) (1); 2025 International Conference on Machine Learning, Computational Intelligence and Pattern Recognition (MLCIPR) (1); Advances in neural information processing … (1); Conference on … (1); ICBINB (1); International Conference on Artificial Intelligence and Statistics (1); Machine learning for healthcare … (1); Proceedings of Machine … (1); arXiv.org (1); … Information Processing … (1); … International Conference on … (1); … Representations (1); … Systems (NeurIPS 2025), San Diego … (1); … of Machine Learning Research … (1); … of Machine Learning … (1).

### What the matches rest on

Matched to a record with an independent source (a crawl of OpenReview or the proceedings): **1,805**. Matched to a record whose only source is an imported RIS set (RIS-only): **0**.

A RIS-only record is in the index because a Scholar set was imported into it. When the set compared here is that set, such a match is the set matching itself: it shows nothing about coverage, and the title and abstract the classes are judged on are the ones the import carried. Counts below are given for both kinds.

| venue | year | matched papers | crawled record | RIS-only record | crawled records the index holds |
|---|---|---|---|---|---|
| ICLR | 2024 | 50 | 50 | 0 | 8,523 |
| ICLR | 2025 | 208 | 208 | 0 | 13,746 |
| ICLR | 2026 | 414 | 414 | 0 | 22,826 |
| ICML | 2022 | 1 | 1 | 0 | 1,233 |
| ICML | 2023 | 2 | 2 | 0 | 2,826 |
| ICML | 2024 | 11 | 11 | 0 | 4,124 |
| ICML | 2025 | 13 | 13 | 0 | 5,083 |
| ICML | 2026 | 111 | 111 | 0 | 11,078 |
| NeurIPS | 2023 | 27 | 27 | 0 | 5,961 |
| NeurIPS | 2024 | 336 | 336 | 0 | 7,561 |
| NeurIPS | 2025 | 632 | 632 | 0 | 10,687 |

Abstract source of the matched records: `openreview_v2` 1,803; `neurips_proceedings` 1; `pmlr` 1. `ris:` is text the import carried (what scholarmend read from the proceedings page or the OpenReview API), not a crawl of this project.

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
| Scholar set, in scope | 1,813 |
| openproceedings `total` (default filters; every venue and year) | 33 |
| openproceedings, in scope | 33 |
| in both | 21 (21 crawled records, 0 RIS-only) |
| in both, matched to a RIS-only record whose title another index record has | 0 |
| only in the Scholar set | 1,792 |
| only in openproceedings | 12 |

### Only in the Scholar set

| class | records | of these | of the Scholar set | crawled record | RIS-only record | meaning |
|---|---|---|---|---|---|---|
| `our_bug` | 0 | 0.0% | 0.0% | 0 | 0 | the oracle and the served engine disagree (must be 0) |
| `coverage_gap` | 3 | 0.2% | 0.2% | 0 | 0 | no record in the snapshot by forum id, proceedings id or title+venue+year |
| `stemming` | 32 | 1.8% | 1.8% | 32 | 0 | matches title or abstract only with an inflected form added |
| `full_text` | 1,752 | 97.8% | 96.6% | 1,752 | 0 | in the corpus with an abstract; no reading matches its title or abstract, inflected forms included |
| `unsettled` | 5 | 0.3% | 0.3% | 0 | 0 | the automation can't tell (see the row's evidence) |
| total | 1,792 | 100.0% | 98.8% | 1,784 | 0 | |

`crawled record` and `RIS-only record` say what the row's index record rests on (a row with no index record is in neither).

### Only in openproceedings

| class | records | of these | of the result | crawled record | RIS-only record | meaning |
|---|---|---|---|---|---|---|
| `our_bug` | 0 | 0.0% | 0.0% | 0 | 0 | the oracle and the served engine disagree (must be 0) |
| `scholar_missed` | 12 | 100.0% | 36.4% | 12 | 0 | an exact title or abstract match that the Scholar set lacks |
| total | 12 | 100.0% | 36.4% | 12 | 0 | |

`our_bug`: **0**. Rows of `review.csv`: 20 left for a call, 179 spot check.

### Concept groups, over the 1,805 Scholar papers the index holds

How many of them hold each top-level group of the string in title or abstract, whatever their track and status:

| group | as run | with inflected forms |
|---|---|---|
| 1. `("foundation model" OR "large language model" OR llm OR "generative ai")` | 550 | 1,012 |
| 2. `(trustworthiness OR trustworthy OR trust OR "trustworthy ai")` | 191 | 197 |
| 3. `(benchmark OR leaderboard OR "evaluation framework")` | 480 | 799 |

Inflected forms added for the `stemming` test (the forms the compared records hold): `benchmark` → benchmarked, benchmarking, benchmarks; `evaluation` → evaluations; `foundation` → foundations; `framework` → frameworks; `language` → languages; `leaderboard` → leaderboards; `llm` → llms; `model` → modeled, modeling, models; `trust` → trusted, trusting.

### Scholar-only records listed

| record | title | venue | year | class | evidence |
|---|---|---|---|---|---|
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

**Finding.** Of the 1,813 in-scope papers of the Scholar set, 1,752 (96.6%) match this string nowhere in title or abstract, inflected forms included (`full_text`), and 32 (1.8%) match only through an inflected form (`stemming`). 21 (1.2%) are in the exact result.

- Of the 1,752 `full_text` papers, 1,752 rest on a crawled record and 0 on a RIS-only record, whose title and abstract are the import's own.
- 2 of them also fail the default track or status filters.
- **Sensitivity to the stemmer.** The `stemming` class uses an inflection-only stand-in, kept by decision-038 (see Method); it is not Google Scholar's stemmer, which is undocumented. With every searched word replaced by its inflection stem read as a prefix (`benchmarks` → `benchmark*`, `evaluating` → `evaluat*`), 0 of the 1,752 (0.0%) `full_text` papers would match title or abstract. That is all this figure measures: it is not a stemmer, and one that strips derivational endings (`evaluation` to `evaluat`) or rewrites the stem could move more.
- **After the calls** (section Human calls, made as: `AI assistant acting at the project owner's direction; not an independent reviewer` (48 rows)): 1,756 of 1,810 (97.0%) `full_text`, 33 (1.8%) `stemming`, 21 (1.2%) in the exact result. The figures above this bullet are the automation's and are the ones to cite. Cite the after-calls figures only with those roles beside them, and as reviewed only if every role is an independent reviewer's.

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
| Scholar set, in scope | 1,813 |
| openproceedings `total` (default filters; every venue and year) | 101 |
| openproceedings, in scope | 101 |
| in both | 51 (51 crawled records, 0 RIS-only) |
| in both, matched to a RIS-only record whose title another index record has | 0 |
| only in the Scholar set | 1,762 |
| only in openproceedings | 50 |

### Only in the Scholar set

| class | records | of these | of the Scholar set | crawled record | RIS-only record | meaning |
|---|---|---|---|---|---|---|
| `our_bug` | 0 | 0.0% | 0.0% | 0 | 0 | the oracle and the served engine disagree (must be 0) |
| `coverage_gap` | 3 | 0.2% | 0.2% | 0 | 0 | no record in the snapshot by forum id, proceedings id or title+venue+year |
| `stemming` | 2 | 0.1% | 0.1% | 2 | 0 | matches title or abstract only with an inflected form added |
| `full_text` | 1,752 | 99.4% | 96.6% | 1,752 | 0 | in the corpus with an abstract; no reading matches its title or abstract, inflected forms included |
| `unsettled` | 5 | 0.3% | 0.3% | 0 | 0 | the automation can't tell (see the row's evidence) |
| total | 1,762 | 100.0% | 97.2% | 1,754 | 0 | |

`crawled record` and `RIS-only record` say what the row's index record rests on (a row with no index record is in neither).

### Only in openproceedings

| class | records | of these | of the result | crawled record | RIS-only record | meaning |
|---|---|---|---|---|---|---|
| `our_bug` | 0 | 0.0% | 0.0% | 0 | 0 | the oracle and the served engine disagree (must be 0) |
| `compat_reading` | 38 | 76.0% | 37.6% | 38 | 0 | decided by how Scholar mode read the string (decision-002 phrases, `$`), not by the corpus |
| `scholar_missed` | 12 | 24.0% | 11.9% | 12 | 0 | an exact title or abstract match that the Scholar set lacks |
| total | 50 | 100.0% | 49.5% | 50 | 0 | |

`our_bug`: **0**. Rows of `review.csv`: 20 left for a call, 180 spot check.

Read the table above with care. A `compat_reading` row decided by `$` matches only through a plural, the same forms the `stemming` class credits Google Scholar with, so it is no evidence that Scholar would not return the paper. `scholar_missed` counts exact matches only: it is a floor for what Scholar's set lacks, not the whole of it.

### Concept groups, over the 1,805 Scholar papers the index holds

How many of them hold each top-level group of the string in title or abstract, whatever their track and status:

| group | as run | with inflected forms |
|---|---|---|
| 1. `("foundation model$" OR "large language model$" OR llm$ OR "generative ai")` | 1,012 | 1,012 |
| 2. `(trustworthiness OR trustworthy OR trust OR "trustworthy ai")` | 191 | 197 |
| 3. `(benchmark$ OR leaderboard$ OR "evaluation framework$")` | 789 | 799 |

Inflected forms added for the `stemming` test (the forms the compared records hold): `benchmark` → benchmarked, benchmarking, benchmarks; `evaluation` → evaluations; `foundation` → foundations; `framework` → frameworks; `language` → languages; `leaderboard` → leaderboards; `llm` → llms; `model` → modeled, modeling, models; `trust` → trusted, trusting.

### Scholar-only records listed

| record | title | venue | year | class | evidence |
|---|---|---|---|---|---|
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

**Finding.** Of the 1,813 in-scope papers of the Scholar set, 1,752 (96.6%) match this string nowhere in title or abstract, inflected forms included (`full_text`), and 2 (0.1%) match only through an inflected form (`stemming`). 51 (2.8%) are in the exact result.

- Of the 1,752 `full_text` papers, 1,752 rest on a crawled record and 0 on a RIS-only record, whose title and abstract are the import's own.
- 2 of them also fail the default track or status filters.
- **Sensitivity to the stemmer.** The `stemming` class uses an inflection-only stand-in, kept by decision-038 (see Method); it is not Google Scholar's stemmer, which is undocumented. With every searched word replaced by its inflection stem read as a prefix (`benchmarks` → `benchmark*`, `evaluating` → `evaluat*`), 0 of the 1,752 (0.0%) `full_text` papers would match title or abstract. That is all this figure measures: it is not a stemmer, and one that strips derivational endings (`evaluation` to `evaluat`) or rewrites the stem could move more.
- **After the calls** (section Human calls, made as: `AI assistant acting at the project owner's direction; not an independent reviewer` (48 rows)): 1,756 of 1,810 (97.0%) `full_text`, 2 (0.1%) `stemming`, 52 (2.9%) in the exact result. The figures above this bullet are the automation's and are the ones to cite. Cite the after-calls figures only with those roles beside them, and as reviewed only if every role is an independent reviewer's.

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
| Scholar set, in scope | 1,813 |
| openproceedings `total` (default filters; every venue and year) | 114 |
| openproceedings, in scope | 114 |
| in both | 65 (65 crawled records, 0 RIS-only) |
| in both, matched to a RIS-only record whose title another index record has | 0 |
| only in the Scholar set | 1,748 |
| only in openproceedings | 49 |

### Only in the Scholar set

| class | records | of these | of the Scholar set | crawled record | RIS-only record | meaning |
|---|---|---|---|---|---|---|
| `our_bug` | 0 | 0.0% | 0.0% | 0 | 0 | the oracle and the served engine disagree (must be 0) |
| `coverage_gap` | 3 | 0.2% | 0.2% | 0 | 0 | no record in the snapshot by forum id, proceedings id or title+venue+year |
| `stemming` | 32 | 1.8% | 1.8% | 32 | 0 | matches title or abstract only with an inflected form added |
| `full_text` | 1,708 | 97.7% | 94.2% | 1,708 | 0 | in the corpus with an abstract; no reading matches its title or abstract, inflected forms included |
| `unsettled` | 5 | 0.3% | 0.3% | 0 | 0 | the automation can't tell (see the row's evidence) |
| total | 1,748 | 100.0% | 96.4% | 1,740 | 0 | |

`crawled record` and `RIS-only record` say what the row's index record rests on (a row with no index record is in neither).

### Only in openproceedings

| class | records | of these | of the result | crawled record | RIS-only record | meaning |
|---|---|---|---|---|---|---|
| `our_bug` | 0 | 0.0% | 0.0% | 0 | 0 | the oracle and the served engine disagree (must be 0) |
| `compat_reading` | 49 | 100.0% | 43.0% | 49 | 0 | decided by how Scholar mode read the string (decision-002 phrases, `$`), not by the corpus |
| total | 49 | 100.0% | 43.0% | 49 | 0 | |

`our_bug`: **0**. Rows of `review.csv`: 8 left for a call, 179 spot check.

Read the table above with care. A `compat_reading` row decided by `$` matches only through a plural, the same forms the `stemming` class credits Google Scholar with, so it is no evidence that Scholar would not return the paper. `scholar_missed` counts exact matches only: it is a floor for what Scholar's set lacks, not the whole of it.

### Concept groups, over the 1,805 Scholar papers the index holds

How many of them hold each top-level group of the string in title or abstract, whatever their track and status:

| group | as run | with inflected forms |
|---|---|---|
| 1. `("large language model$" OR llm OR "foundation model$" OR "generative ai$" OR "vision language model$" OR vlm OR "multimodal model$" OR "ai agent$" OR "text to image model$")` | 1,115 | 1,159 |
| 2. `(trust OR trustworthy OR trustworthiness OR "trustworthy ai$")` | 191 | 197 |
| 3. `(benchmark OR dataset OR evaluation OR leaderboard OR "evaluation framework$" OR "test suite$")` | 794 | 1,256 |

Inflected forms added for the `stemming` test (the forms the compared records hold): `agent` → agents; `benchmark` → benchmarked, benchmarking, benchmarks; `dataset` → datasets; `evaluation` → evaluations; `foundation` → foundations; `framework` → frameworks; `image` → images, imaging; `language` → languages; `leaderboard` → leaderboards; `llm` → llms; `model` → modeled, modeling, models; `suite` → suit, suited, suites; `test` → tested, testing, tests; `text` → texts; `trust` → trusted, trusting; `vlm` → vlms.

### Scholar-only records listed

| record | title | venue | year | class | evidence |
|---|---|---|---|---|---|
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

**Finding.** Of the 1,813 in-scope papers of the Scholar set, 1,708 (94.2%) match this string nowhere in title or abstract, inflected forms included (`full_text`), and 32 (1.8%) match only through an inflected form (`stemming`). 65 (3.6%) are in the exact result.

- Of the 1,708 `full_text` papers, 1,708 rest on a crawled record and 0 on a RIS-only record, whose title and abstract are the import's own.
- 2 of them also fail the default track or status filters.
- **Sensitivity to the stemmer.** The `stemming` class uses an inflection-only stand-in, kept by decision-038 (see Method); it is not Google Scholar's stemmer, which is undocumented. With every searched word replaced by its inflection stem read as a prefix (`benchmarks` → `benchmark*`, `evaluating` → `evaluat*`), 2 of the 1,708 (0.1%) `full_text` papers would match title or abstract. That is all this figure measures: it is not a stemmer, and one that strips derivational endings (`evaluation` to `evaluat`) or rewrites the stem could move more.
- **After the calls** (section Human calls, made as: `AI assistant acting at the project owner's direction; not an independent reviewer` (48 rows)): 1,712 of 1,810 (94.6%) `full_text`, 32 (1.8%) `stemming`, 66 (3.6%) in the exact result. The figures above this bullet are the automation's and are the ones to cite. Cite the after-calls figures only with those roles beside them, and as reviewed only if every role is an independent reviewer's.

## Human calls

Read from `2026-10-05-scholar-comparison-review.csv` (sha256 `80fcbd04e73686489e44c2227495fd1df5d6af1fe73f70dc66d0b90df7bf7e04`): 48 of its 586 rows have a call. **Who made them** (the file's `reviewer_role`, as written): `AI assistant acting at the project owner's direction; not an independent reviewer` (48 rows). Every figure in this section rests on those roles; the tables above this section are the automation's alone. `in_both` means the record is the same paper as one in the result; `out_of_scope` that it is no paper of the scope's venues and years.

| query | unresolved rows | called | spot-check rows | called | agree with the automated class |
|---|---|---|---|---|---|
| `main-7-most-updated` | 20 | 20 | 179 | none called | — |
| `main-7-dollar` | 20 | 20 | 180 | none called | — |
| `main-2-pop` | 8 | 8 | 179 | none called | — |

| query | automated class | human class | rows |
|---|---|---|---|
| `main-2-pop` | `coverage_gap` | `out_of_scope` | 3 |
| `main-2-pop` | `unsettled` | `full_text` | 4 |
| `main-2-pop` | `unsettled` | `in_both` | 1 |
| `main-7-dollar` | `coverage_gap` | `out_of_scope` | 3 |
| `main-7-dollar` | `scholar_missed` | `scholar_missed` | 12 |
| `main-7-dollar` | `unsettled` | `full_text` | 4 |
| `main-7-dollar` | `unsettled` | `in_both` | 1 |
| `main-7-most-updated` | `coverage_gap` | `out_of_scope` | 3 |
| `main-7-most-updated` | `scholar_missed` | `scholar_missed` | 12 |
| `main-7-most-updated` | `unsettled` | `full_text` | 4 |
| `main-7-most-updated` | `unsettled` | `stemming` | 1 |

### After the calls

Each call moves its row: a class puts the row in that class; `out_of_scope` takes the record out of the Scholar set, so out of the denominator; `in_both` moves it to "in both" and takes the index record it is paired with (the row's own record, or the one same-title record its evidence names) out of the rows only in openproceedings. Rows without a call keep the automation's class.

`main-7-most-updated`, the automation's counts and the counts after the calls:

| | automation | after the calls |
|---|---|---|
| Scholar set, in scope | 1,813 | 1,810 |
| in both | 21 | 21 |
| only in the Scholar set | 1,792 | 1,789 |
| only in the Scholar set: `coverage_gap` | 3 | 0 |
| only in the Scholar set: `stemming` | 32 | 33 |
| only in the Scholar set: `full_text` | 1,752 | 1,756 |
| only in the Scholar set: `unsettled` | 5 | 0 |
| only in openproceedings | 12 | 12 |
| only in openproceedings: `scholar_missed` | 12 | 12 |

`main-7-dollar`, the automation's counts and the counts after the calls:

| | automation | after the calls |
|---|---|---|
| Scholar set, in scope | 1,813 | 1,810 |
| in both | 51 | 52 |
| only in the Scholar set | 1,762 | 1,758 |
| only in the Scholar set: `coverage_gap` | 3 | 0 |
| only in the Scholar set: `stemming` | 2 | 2 |
| only in the Scholar set: `full_text` | 1,752 | 1,756 |
| only in the Scholar set: `unsettled` | 5 | 0 |
| only in openproceedings | 50 | 49 |
| only in openproceedings: `compat_reading` | 38 | 37 |
| only in openproceedings: `scholar_missed` | 12 | 12 |

`main-2-pop`, the automation's counts and the counts after the calls:

| | automation | after the calls |
|---|---|---|
| Scholar set, in scope | 1,813 | 1,810 |
| in both | 65 | 66 |
| only in the Scholar set | 1,748 | 1,744 |
| only in the Scholar set: `coverage_gap` | 3 | 0 |
| only in the Scholar set: `stemming` | 32 | 32 |
| only in the Scholar set: `full_text` | 1,708 | 1,712 |
| only in the Scholar set: `unsettled` | 5 | 0 |
| only in openproceedings | 49 | 48 |
| only in openproceedings: `compat_reading` | 49 | 48 |

**Every disagreement classified: yes, on the calls whose roles this line names.** `our_bug` by the automation: 0; by a call: 0; rows left for a call that have none yet: 0. The 48 calls were made as: `AI assistant acting at the project owner's direction; not an independent reviewer` (48 rows). A call weighs what its role does: unless every role is an independent reviewer's, this verdict is provisional and spec 07 §B's bar is not closed.

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
  Decision-038 keeps this stand-in and adopts no published stemmer, because that figure is at or near zero for
  the review's strings; the `stemming` and `full_text` counts are relative to the stand-in, and the decision is
  revisited for any string whose sensitivity is not near zero.
- **`full_text`** is the residue: the record is in the corpus with an abstract, and the oracle confirms that no
  reading above matches its title or abstract. It may also fail the filters (counted under each finding). A
  record the corpus holds without an abstract is `unsettled`.
- **Provenance.** Each row says whether its index record has an independent source or only an imported RIS set
  (`crawled record`, `RIS-only record`), and `review.csv` carries it with the abstract's source.
- **`scholar_missed`** rows all go to `review.csv`: a reviewer confirms the exact tokens are in the title or abstract.
- **`coverage_gap`** rows all go to `review.csv` too: a record the corpus lacks and a record Scholar filed under
  the wrong venue or year look the same to the matching, so a reviewer checks each against the coverage report.
- **`review.csv`** also holds a spot check: a tenth of each query's settled disagreements, chosen by a hash of
  the row's ids. The tool never fills `human_class`: whoever makes a call writes it with their role in
  `reviewer_role`, and the Human calls section prints those roles beside every figure that rests on them. A call
  made by anyone but an independent reviewer (the analyst, or software acting for the project) is recorded
  like any other and leaves the verdict provisional.

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
- **Scholar's cap.** The review's 17 raw Scholar exports hold between 7 and 639 records each, all under Scholar's
  1,000, so no search was cut at the cap. The set itself is de-duplicated across exports, which is why its largest
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
  reached (`docs/results/2026-10-04-scholar-comparison.md`). The 2026 OpenReview crawl (TASK-178) merged all but
  7, and the dedup fix of TASK-179 merged those. "What the matches rest on" counts the two kinds apart for the
  index a report ran on.
- **The superseded run of 2026-10-05.** A report of this date first ran on index `5ec5231adae2` (snapshot
  `2026-10-05-47d4e190ca81`, 133,632 records), the first build after the 2026 crawl. That snapshot still held 7
  imported records as unmerged second copies of crawled papers (ICLR 2024 ×1, 2025 ×3, 2026 ×3), and lacked 4
  papers refused for a control character in their title. TASK-179 and TASK-180 fixed both, the snapshot was
  rebuilt (`2026-10-05-10b5a205a63f`, 133,629 records), and that report was replaced by this one. On the
  superseded index 1,800 matched papers rested on a crawled record and 7 on the import alone; the class counts
  differed only by those 7.
- **Why the denominator moved.** The papers in scope were 1,810 in TASK-056's first run (index `05a0541717f6`);
  1,817 once a record with an empty or cut venue string was kept when an in-scope record of its year has its
  title; 1,815 once a record naming another venue in full was kept out again (the 2026-10-04 report). On index
  `fd13d8d27535` they are 1,813: 2 Scholar records that each matched an imported copy now match a crawled paper
  another record of the set already matched, and are counted as repeats ("repeats of a paper already counted").
  The 3 `out_of_scope` calls below take it to 1,810 in the counts after the calls only.
- **Matching.** This report matches the set by URL and title, as it would any RIS file, not by the import's
  ids.
- **Who made the calls.** The 48 calls in the review file of the 2026-10-05 run were made on 2026-10-05 by an AI
  assistant at the project owner's direction, not by an independent reviewer; the file's `reviewer_role` says so
  on each row, the report prints that role beside every figure that rests on the calls, and each `note` gives the
  evidence. Until TASK-193 repeats them with an independent reviewer, the calls and the counts after them are not
  cited, and spec 07 §B's bar is not closed. The checks behind them: for the 12 `scholar_missed` papers, no record
  with the title (exact, prefix or near match) in `mended.ris` or in the review's other Scholar files, its 17 raw
  Scholar exports and 3 pre-filter output files (21 files with `mended.ris`); for the 5 records with no venue
  string, the same title, year and authors as the named index record, then the class the tool gives once the
  venue is restored; for the 3 `coverage_gap` records, the venue named by Crossref or by the conference's own
  page (a Springer LNCS volume of another conference, an IEEE conference of another name, and a NeurIPS 2022
  tutorial). That a `scholar_missed` paper's title or abstract holds the exact tokens rests on the tool alone:
  each note restates the row's evidence; the abstracts were not read. That reading is the
  part of these calls TASK-193 must do first. No spot-check row has a call. A reviewer who repeats any of these
  calls should replace the role on that row.
