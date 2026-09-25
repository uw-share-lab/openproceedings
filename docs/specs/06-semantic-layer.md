# 06 — Semantic layer (phase 2, M5)

Status: **draft for review** · depends on: 01, 03, 04 · consumed by: 05

## Purpose and the one rule

Use embeddings where they help a systematic review, and nowhere else. **The rule (guarantee 5):
embeddings never change which papers match.** They may (a) *re-order* the matched set, and (b) *suggest*
unmatched papers in a separate, clearly labelled panel. `total`, `excluded`, exports and search records are
computed from the lexical set only.

Why include them at all: the hardest part of a review search is *vocabulary you didn't think of*. The
Trust-Evals protocol went through six search-string revisions for that reason. The near-miss panel shows
papers that look like your hits but that your query missed, and tells you which of their words your query
lacks.

## Model and storage

- **SPECTER2** (`allenai/specter2_base` plus the proximity adapter) over `title [SEP] abstract`. The
  model's name and revision are pinned in config and folded into `semantic_version`.
- Embeddings are computed offline per snapshot (`op embed build`). They are about 80k × 768 float16, around
  120 MB. They are stored at `data/embeddings/<index_version>/<semantic_version>.npy`, beside the index rather than inside it (`data/indexes/` is immutable), and loaded into memory. Exact cosine search is done
  with numpy (a brute-force matrix product takes milliseconds at this scale). No vector database and no ANN
  are needed, so results are deterministic.
- Records with no abstract are embedded from the title alone and flagged.

## Features

### 1. `sort=semantic` (re-order within the set)
Order the matched set by cosine similarity to the **query centroid**: the mean embedding of the top-k
(k=20) BM25 hits. Ties are broken by BM25 and then by `id`. This is labelled in the UI as "by similarity to
your top results".

### 2. Near-miss panel (`GET /api/v1/near-misses?q=…&limit=25`)
1. Compute the centroid of the matched set, capped at the top 200 by BM25.
2. Rank every **unmatched** paper that passes the query's own filters (the same venue/year/track/status)
   by cosine similarity to that centroid.
3. For each suggestion, return the **missing-vocabulary terms**: its top tf-idf tokens that appear in no
   clause of the query. Also return, per concept group, which group it failed (for example, "matches AI and
   benchmark terms; misses the trust group").
4. The UI shows these as "Papers your query may have missed". Each term chip has a "+ add to group …"
   action that **edits `q`**, so any change to the set is still made by the user, lexically.

## Guardrails

- The API response for near-misses is a separate resource. It never merges into `/search`.
- `semantic_version` is included in every near-miss response and in search records that were created while
  it was visible (for the audit trail). It never goes into `ids_hash`.
- If embeddings are missing or out of date for the current `index_version`, the feature is **disabled**
  with a visible notice. It must never run against a mismatched snapshot.

## Evaluation (connects to 07)

- **Invariant test (CI gate):** for random queries, `/search` totals, IDs and exports are identical with the
  semantic layer on and off.
- **Usefulness:** use the review's Covidence **included** set as ground truth. For the review's query
  strings, measure how many included papers the lexical query missed, and how many of those the near-miss
  panel surfaced in its top 25 (recall@25 of near-misses). If this doesn't beat a BM25-on-OR-of-all-terms
  baseline, the feature doesn't ship.
