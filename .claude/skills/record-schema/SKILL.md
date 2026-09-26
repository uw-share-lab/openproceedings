---
name: record-schema
description: The PaperRecord contract from spec 01 — every field with its type and rules, the op:<venue>:<year>:<native> id scheme, provenance claims and the source-precedence table, and exactly which fields content_hash covers and how the canonical JSON is serialised. Use when writing or reviewing backend/src/openproceedings/ingest/ models, any source adapter's normalize step, the RIS importer, or anything that reads records.jsonl.
---

# Record schema (spec 01 §Record schema)

`PaperRecord` is a pydantic v2 model (`extra="forbid"`, frozen) in
`backend/src/openproceedings/ingest/record.py`, with `Claim`, `Urls` and `content_hash`. It is the only
thing the index build (spec 03) reads. Build one with `PaperRecord.build(**fields)`, which computes the
hash; loading a record whose stored hash doesn't match its fields fails (a hash can never go stale).

## Fields
| Field | Rule |
|---|---|
| `id` | `op:<venue>:<year>:<native>`, with venue lower-cased: `op:iclr:2024:iilhN2MycO`. Never changes once a snapshot has shipped it. |
| `title` | Raw, whitespace-collapsed. **No** search normalization here (spec 03 owns it). |
| `abstract` | Raw text or `null` (never an empty or whitespace-only string). Reject a value that starts or ends with `…`: that's a Scholar snippet. An ellipsis inside a real abstract (`x₁, …, x_n`) is allowed. HTML stripped, LaTeX kept verbatim. |
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
| PMLR only | `pmlr-v<N>-<key>` (ICML volumes only, `ingest/volumes.py`) |
| NeurIPS proceedings only | `nips-<hash>`, the 32-hex hash from the paper_files path |
| ICLR proceedings only | `iclr-<hash>`, the 32-hex hash from the proceedings path |
| RIS import | a venueid plus its forum id → the forum id; else the proceedings or PMLR form above, from scholarmend's `proceedings_url` / `pmlr_url` claim (`ingest/urls.py`). A record with neither is skipped and counted (`unresolved` / `no_id`), never given a minted id. |

When records merge (`.claude/skills/dedup-rules/SKILL.md`), the surviving id uses the OpenReview forum id
if either side has one.

## Provenance claims
One `Claim` per (field, source): `field`, `value`, `source` (`openreview_v2`, `openreview_v1`,
`neurips_proceedings`, `pmlr`, `ris`), `url`, `fetched_at` (**from the cache entry**, never `now()` at
build time), `evidence` (for example `venueid=ICLR.cc/2024/Conference`, or a decision note id). Claims are
frozen, with scalar fields only, so they are hashable and set-comparable. That shape follows scholarmend,
where a mutable claim caused a blocking defect.

Resolution is a **precedence table held as data** (scholarmend's ledger pattern). A source listed for a
field may answer it, best first. A source not listed may never answer it. Decided in decision-005
(title, abstract and authors: OpenReview first, proceedings where OpenReview lacks the paper):

| Field | Precedence |
|---|---|
| `status` | the official proceedings where the venue-year's are published and crawled (listed → `accepted`; OpenReview-accepted but not listed → `unknown` + `conflicts.csv`), otherwise `openreview_v2`, `openreview_v1` via `content.venueid`; `ris` only through claims |
| `track` | `openreview_v2`, `openreview_v1` via `content.venueid`; proceedings only for venue-years not on OpenReview |
| `title`, `abstract`, `authors` | `openreview_v2`, `openreview_v1`, then `neurips_proceedings`, `pmlr` (papers or years not on OpenReview), then `ris` |
| `year`, `venue` | the source that defined the crawl scope and agrees with the venueid; a disagreement is a conflict |

All claims are kept, including the losing ones. Two same-rank sources that disagree produce a
`conflicts.csv` row.

**RIS-imported records** (spec 01 §Sources, `ingest/ris.py`): every claim has `source = "ris"`, with
its origin in `evidence` (`scholarmend:openreview_api venueid=…`, `mended.ris:TI`). `status` comes from a
claim only: an OpenReview venueid claim → its status; a proceedings listing (NeurIPS/ICLR proceedings URL,
or a PMLR URL in an ICML volume) → `accepted`, overriding a venueid that agrees on venue, year and track
(one that disagrees is a `conflict` and the record is skipped). A record with neither is never imported,
so a RIS record is never `unknown` for lack of a claim. It is **never** inferred from the paper appearing
in Scholar. The abstract is never Scholar's (`null` instead).

## content_hash
`sha256` of the canonical JSON of the **searchable and filterable** fields: `title`, `abstract`,
`venue`, `year`, `track`, `status`. Spec 02's `FIELD` list also names `source`, but `source:` is a Scholar
alias that the parser rewrites to `venue:` (`query/compat.py`); it is not a record field and isn't hashed. Canonical JSON means
`json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)` encoded as UTF-8, with no
floats and no extra Unicode normalization.

It **excludes** `provenance`, `urls`, `keywords`, `presentation`, `authors` and `venue_id_raw`. A re-crawl
that only refreshes fetch times must not change the hash. `op snapshot diff` uses it to tell a real change
from a display-only or provenance-only change.

`PaperRecord.build` computes the hash, `model_copy(update=...)` re-validates and recomputes it, and
loading a record re-checks it. Never use `model_construct` on a record: it skips every check.
