---
name: specter2-embeddings
description: The semantic-layer standard (spec 06, M5) — SPECTER2 base plus proximity adapter pinned by revision, semantic_version, one float16 .npy per snapshot with its metadata, deterministic brute-force cosine, the title-only flag, the query centroid, and the rule that embeddings never change membership and are disabled on any version mismatch. Use when working in backend/src/openproceedings/semantic/, on `op embed build`, sort=semantic or /near-misses, or reviewing anything that lets embeddings near a result set.
---

# SPECTER2 embeddings (spec 06)

## The rule (guarantee 5), which comes before everything else
Embeddings may **re-order** the lexical matched set and **suggest** unmatched papers in a separate
panel. They never add to or remove from the set. `total`, `excluded`, facets, exports, `ids_hash` and
search records are computed from the lexical set alone, and are byte-identical with the semantic layer
on or off. Nothing in `semantic/` may be imported by `engine/` or by the export and records code paths.

## Model pinning
- `allenai/specter2_base` plus the SPECTER2 **proximity** adapter, each pinned to an exact Hugging Face
  revision (a commit sha, never `main`) in config. Load the adapter the way the model card documents
  (the `adapters` library at the time of writing). Verify the loading API and the output pooling (CLS,
  per the model card) at implementation time.
- Input: `title + tokenizer.sep_token + abstract`, truncated at the model maximum (512 tokens).
- `semantic_version = sha256(model id, model revision, adapter id, adapter revision, input template,
  max_length, pooling, normalisation)[:12]`. Any change to these means a new `semantic_version` and a
  rebuild.

## Artifacts (`op embed build`)
- One float16 matrix, about 80k × 768 (about 120 MB), rows **L2-normalised before the cast**, row order =
  ids sorted as `str`. A sidecar metadata file records `ids` (the row order), `index_version`,
  `snapshot_hash`, `semantic_version`, a per-row `title_only` flag, a sha256 of the `.npy` bytes, and
  the torch and adapter library versions.
- Location (spec 06 §Model and storage): the matrix is the file
  `data/embeddings/<index_version>/<semantic_version>.npy`, with its sidecar metadata beside it as
  `<semantic_version>.json`. It lives beside the index rather than inside it, because
  `data/indexes/<v>/` is immutable and `protect-data-dir.sh` guards it.
- Records with no abstract are embedded from the title alone and get `title_only = true`. The near-miss
  response surfaces the flag so the UI can label the suggestion.
- A build is not bit-identical across hardware (GPU against CPU kernels). Reproducibility is pinned at
  query time: given the same `.npy`, results are deterministic.

## Load-time guard: disabled, never degraded
At startup and on every hot swap, compare the metadata's `index_version` and `snapshot_hash` with the
served engine, check the `.npy` hash, and check that `ids` equals the index's id set. On **any**
mismatch, or if the file is missing, the semantic layer is **off**. `sort=semantic` is rejected with a
clear error, `/near-misses` returns a visible "unavailable" notice, and `/meta` says why. It must never
run against a mismatched snapshot, and must never fall back to a stale file.

## Scoring (deterministic, brute force)
- Cosine = dot product of normalised vectors. Upcast to float32 for the product (all at once or in
  chunks, trading memory for speed). No ANN and no vector DB.
- **`sort=semantic`:** centroid = the mean of the top k = 20 BM25 hits' vectors (all hits if fewer),
  re-normalised. Order the matched set by cosine descending, then BM25 score descending, then `id`
  ascending. The set and `total` are unchanged, and the UI labels it "by similarity to your top results".
- **Near-miss centroid:** the top 200 matched by BM25. Candidates are **unmatched** papers that pass the
  query's own filters (venue/year/track/status, `.claude/skills/default-filters/SKILL.md`). Return the
  top `limit` (25).
- Tie-breaks must not depend on float noise. Round cosine to a fixed number of decimals before comparing
  (pin it). Run determinism tests with BLAS threads pinned to 1.

## Near-miss explanations
Missing-vocabulary terms are the suggestion's top tf-idf tokens that appear in no query clause.
Tokenise with `normalize()` only (`.claude/skills/token-contract/SKILL.md`), and count a wildcard's
expansion terms as present. Report per top-level concept group whether the paper matches it. Term chips
edit `q`, so the user makes every set change lexically.

## `semantic_version` in the audit trail
It goes in every `/near-misses` response, and in a search record created while the panel was visible
(`.claude/skills/search-records/SKILL.md`). It never enters `ids_hash`.
