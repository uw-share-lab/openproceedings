---
name: record-schema
description: The PaperRecord contract from spec 01 — every field with its type and rules, the op:<venue>:<year>:<native> id scheme, provenance claims and the source-precedence table, and exactly which fields content_hash covers and how the canonical JSON is serialised. Use when writing or reviewing backend/src/openproceedings/ingest/ models, any source adapter's normalize step, the RIS importer, or anything that reads records.jsonl.
---

# Record schema (spec 01 §Record schema)

`PaperRecord` is a pydantic v2 model (`extra="forbid"`, frozen). It is the only thing the index build
(spec 03) reads.

## Fields
| Field | Rule |
|---|---|
| `id` | `op:<venue>:<year>:<native>`, with venue lower-cased: `op:iclr:2024:iilhN2MycO`. Never changes once a snapshot has shipped it. |
| `title` | Raw, whitespace-collapsed. **No** search normalization here (spec 03 owns it). |
| `abstract` | Raw text or `null`. Reject any value containing `…`, because that's a Scholar snippet. HTML stripped, LaTeX kept verbatim. |
| `authors` | Display order, as the source gives them. |
| `venue` | `NeurIPS` \| `ICLR` \| `ICML` (enum; extensible later). |
| `year` | Conference year. Never the arXiv or PDF year. Required: a record with no year is not a valid `PaperRecord`. |
| `track` | `.claude/skills/track-taxonomy/SKILL.md`. No default value in the model. |
| `status` | `accepted` \| `rejected` \| `withdrawn` \| `desk_rejected` \| `unknown`. No default. |
| `presentation` | `oral` \| `spotlight` \| `poster` \| `null`, only when a source states it. |
| `venue_id_raw` | OpenReview `content.venueid` verbatim, else `null`. |
| `urls` | `{forum, pdf, proceedings, doi}`, each optional. |
| `keywords` | Stored and shown, **never indexed as text** (guarantee 2). |
| `provenance` | `list[Claim]`, see below. |
| `content_hash` | See below. |

## Native ids
| Source | `native` |
|---|---|
| OpenReview (v1 or v2) | forum id, as-is (case-sensitive) |
| PMLR only | `pmlr-v<N>-<key>` |
| NeurIPS proceedings only | `nips-<sha>` from the paper_files path |
| RIS import | the forum id if the record carries an OpenReview URL, else the proceedings form above. If neither exists, it can't be ingested: report it, never mint a random id. |

When records merge (`.claude/skills/dedup-rules/SKILL.md`), the surviving id uses the OpenReview forum id
if either side has one.

## Provenance claims
One `Claim` per (field, source): `field`, `value`, `source` (`openreview_v2`, `openreview_v1`,
`neurips_proceedings`, `pmlr`, `ris`), `url`, `fetched_at` (**from the cache entry**, never `now()` at
build time), `evidence` (for example `venueid=ICLR.cc/2024/Conference`, or a decision note id). Claims are
frozen, with scalar fields only, so they are hashable and set-comparable. That shape follows scholarmend,
where a mutable claim caused a blocking defect.

Resolution is a **precedence table held as data** (scholarmend's ledger pattern). A source listed for a
field may answer it, best first. A source not listed may never answer it. Proposed (confirm in a decision
record before M4):

| Field | Precedence |
|---|---|
| `track`, `status` | `openreview_v2`, `openreview_v1`, then proceedings (`neurips_proceedings`, `pmlr`) only for venue-years not on OpenReview, then `ris` |
| `abstract` | `neurips_proceedings`, `pmlr` (the published text), `openreview_*`, `ris` |
| `year`, `venue` | the source that defined the crawl scope and agrees with the venueid; a disagreement is a conflict |

All claims are kept, including the losing ones. Two same-rank sources that disagree produce a
`conflicts.csv` row.

## content_hash
`sha256` of the canonical JSON of the **searchable and filterable** fields: `title`, `abstract`,
`venue`, `year`, `track`, `status`, plus any further field spec 02's `FIELD` list makes filterable (it
names `source`; verify how `source` is derived at implementation time). Canonical JSON means
`json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)` encoded as UTF-8, with no
floats and no extra Unicode normalization.

It **excludes** `provenance`, `urls`, `keywords` and `presentation`. A re-crawl that only refreshes fetch
times must not change the hash. `op snapshot diff` uses it to tell a real change from a provenance-only
change.
