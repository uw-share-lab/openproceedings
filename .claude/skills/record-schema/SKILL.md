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
| `title` | Raw, whitespace-collapsed. **No** search normalization here (spec 03 owns it). Capped by the snapshot build at 8 combining marks per run (the ingest caps, below); the model doesn't check it. |
| `abstract` | Raw text or `null` (never an empty or whitespace-only string). Reject a value that starts or ends with `…`: that's a Scholar snippet. An ellipsis inside a real abstract (`x₁, …, x_n`) is allowed. HTML stripped, LaTeX kept verbatim. Capped by the snapshot build at 20,000 characters and 8 combining marks per run (the ingest caps, below); the model doesn't check it. |
| `authors` | Display order, as the source gives them. |
| `venue` | `NeurIPS` \| `ICLR` \| `ICML` (enum; extensible later). |
| `year` | Conference year. Never the arXiv or PDF year. Required: a record with no year is not a valid `PaperRecord`, nor is one for a year its venue was not held under its name (NeurIPS before 1987, ICLR before 2013, ICML before 1988; `vocab.CONFERENCES`, spec 04 §Exports). |
| `track` | `.claude/skills/track-taxonomy/SKILL.md`. No default value in the model. |
| `status` | `accepted` \| `rejected` \| `withdrawn` \| `desk_rejected` \| `unknown`. No default. |
| `presentation` | `oral` \| `spotlight` \| `poster` \| `null`, only when a source states it: a v1 decision note or venue string (`openreview_v1._PRESENTATION`); a v2 accepted, non-workshop note's `content.venue`, matched exactly per venue-year in `classify.V2_PRESENTATION` (an unlisted string is `null` and counted as `presentation_unmapped`; spec 01 §Presentation). Its claim's evidence is `content.venue=<string>`. `dedup.resolve` keeps it only when the resolved `status` is `accepted` (a reconcile-demoted `unknown` shows `null`; the claim stays). Never a track, never hashed. |
| `venue_id_raw` | OpenReview `content.venueid` verbatim, else `null`. |
| `urls` | `{forum, pdf, proceedings, doi}`, each optional. |
| `keywords` | Stored and shown, **never indexed as text** (guarantee 2). |
| `provenance` | `list[Claim]`, see below. |
| `content_hash` | See below. |
| `venue_name` | **Derived, never stored** (TASK-112): `vocab.venue_name(venue, year)`, a computed field. Sent with the record (`GET /papers/{id}`); `record.DERIVED` names it, and `snapshot.record_line` and `model_copy` dump with `exclude={*DERIVED}` (a set: mypy's `IncEx` refuses the frozenset itself). Stored data naming it is refused (`extra="forbid"`), so a dump you validate again must exclude it too. |

## Native ids
| Source | `native` |
|---|---|
| OpenReview (v1 or v2) | forum id, as-is (case-sensitive) |
| PMLR only | `pmlr-v<N>-<key>` (ICML volumes only, `ingest/volumes.py`) |
| NeurIPS proceedings only | `nips-<hash>`, the 32-hex hash from the paper_files path; on the 2021 D&B host `nips-<hash>-round1`/`-round2` (its hash is md5 of a per-round paper number, so rounds and the main track reuse hashes; a D&B link without a round gets no id). One function, `urls.proceedings_native`, makes it for the miner, the RIS importer and dedup |
| ICLR proceedings / archive | `iclr-<hash>` from a proceedings path; for the official 2014–2016 archive, an OpenReview target keeps its forum id and any other target is `iclr-<sha256(canonical-target)[:32]>` |
| RIS import | a venueid plus its forum id → the forum id; else the proceedings or PMLR form above, from scholarmend's `proceedings_url` / `pmlr_url` claim (`ingest/urls.py`). A record with neither is skipped and counted (`unresolved` / `no_id`), never given a minted id. |

A forum id and a PMLR `pmlr-v<N>-<key>` name one paper in every venue and year; a `nips-` or `iclr-` hash names
one only within its venue-year (TASK-067, measured: a NeurIPS hash is md5 of a per-year paper number, and
1,281 name two to five papers each in the 2026-09-29 snapshot; ICLR proceedings hashes collided across years
in the 2026-09-23 one; the 2014–2016 archive's sha256 ids share the form, so they are treated the same). Only
the first two link two ids by their native part (`takedowns.global_native`: the rekey rule of
`snapshot.withhold` and `snapshot.diff`, and the takedown list's `same_paper`).

When records merge (`.claude/skills/dedup-rules/SKILL.md`), the surviving id uses the OpenReview forum id
if either side has one. A proceedings record's `urls.forum` claim (PMLR v235's link) is identity evidence
too: dedup joins it to the note with that forum id (the forum link), so the claim must name exactly the
forum the page links.

## Provenance claims
One `Claim` per (field, source): `field`, `value`, `source` (`openreview_v2`, `openreview_v1`,
`iclr_archive`, `neurips_proceedings`, `pmlr`, `ris`), `url`, `fetched_at` (**from the cache entry**, never `now()` at
build time), `evidence` (for example `venueid=ICLR.cc/2024/Conference`, or a decision note id). Evidence starting
`not listed:` is **reserved** for reconcile's absence claims (`dedup.is_absence`, decision-005): no miner or
importer may write it, or its claim would stop counting as a listing. Claims are
frozen, with scalar fields only, so they are hashable and set-comparable. That shape follows scholarmend,
where a mutable claim caused a blocking defect.

Resolution is a **precedence table held as data** (scholarmend's ledger pattern). A source listed for a
field may answer it, best first. A source not listed may never answer it. Decided in decision-005
(title, abstract and authors: OpenReview first, proceedings where OpenReview lacks the paper):

| Field | Precedence |
|---|---|
| `status` | the official proceedings where the venue-year's are published and crawled (listed → `accepted`; OpenReview-accepted but not listed → `unknown` + `conflicts.csv`), otherwise `openreview_v2` via `content.venueid`, `openreview_v1` via its year's adapter (`content.venue`, `content.decision`, the decision note or the withdrawn / desk-rejected invitation; never the v1 venueid); `ris` only through claims |
| `track` | `openreview_v2` via `content.venueid`, `openreview_v1` via its year's adapter (the status evidence when it names a track, else the listing invitation the note was submitted under, checked against the venueid); proceedings only where OpenReview doesn't hold the venue-year's track (per track, decision-005, 2026-09-29): a record with an OpenReview track claim takes it; a record with no OpenReview track claim (the track isn't on OpenReview, or the paper's note didn't merge) takes its listing's |
| `title`, `abstract`, `authors` | `openreview_v2`, `openreview_v1`, then `iclr_archive`, `neurips_proceedings`, `pmlr` (papers or years not on OpenReview), then `ris` |
| `year`, `venue` | the source that defined the crawl scope and agrees with the venueid; a disagreement is a conflict |

All claims are kept, including the losing ones. Two same-rank sources that disagree produce a
`conflicts.csv` row.

**RIS-imported records** (spec 01 §Sources, `ingest/ris.py`): every claim has `source = "ris"`, with
its origin in `evidence` (`scholarmend:openreview_api venueid=…`, `mended.ris:TI`). `status` comes from a
claim only: an OpenReview venueid claim → its status (in a v1 venue-year, none: there scholarmend's
`venue_string` claim, OpenReview's `content.venue`, decides through `classify_v1_venue` when every such
claim's evidence names the record's venueid and the string names the venueid's venue, year and track,
evidence `scholarmend:openreview_api venueid=… venue_string=…`; else `unknown`, the evidence saying why;
TASK-098. ICLR 2013/2017's lower-case `conference` venueid names no track, so there the string gives the
track too, with the same evidence, when it names the venueid's venue and year; TASK-142; its claims don't name the
note's submission invitation, so it reads a 2017 workshop copy's `Submitted to ICLR 2017` as `main`/`rejected`,
which the crawl's `workshop`/`unknown` outranks once merged in a snapshot with the ICLR 2017 v1 crawl, TASK-152); a proceedings listing (NeurIPS/ICLR proceedings URL, or a PMLR URL in an ICML volume) → `accepted`, overriding a venueid that agrees on venue, year and track
(one that disagrees is a `conflict` and the record is skipped). A record with neither is never imported,
so a RIS record is never `unknown` for lack of a claim. It is **never** inferred from the paper appearing
in Scholar. The abstract is never Scholar's (`null` instead).

## Versions
`RECORD_SCHEMA_VERSION` (`record.py`) names this shape: the fields, native-id forms and content_hash
rule. It is `3` since TASK-118 added the round-qualified `nips-<hash>-round1`/`-round2` form (it was `2` from
TASK-096, which added the `iclr_archive` provenance source). Change any of them and bump it;
every snapshot manifest records it. A derived field (`DERIVED`, never in `records.jsonl`) is not part of the
stored shape: adding `venue_name` bumped nothing (TASK-112).

## content_hash
`sha256` of the canonical JSON of the **searchable and filterable** fields: `title`, `abstract`,
`venue`, `year`, `track`, `status`. Spec 02's `FIELD` list also names `source`, but `source:` is a Scholar
alias that the parser rewrites to `venue:` (`query/compat.py`); it is not a record field and isn't hashed. Canonical JSON means
`json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)` encoded as UTF-8, with no
floats and no extra Unicode normalization.

It **excludes** `provenance`, `urls`, `keywords`, `presentation`, `authors` and `venue_id_raw`. A re-crawl
that only refreshes fetch times must not change the hash. `op snapshot diff` uses it to tell a real change
from a display-only or provenance-only change.

`PaperRecord.build` computes the hash, `model_copy(update=...)` re-validates and recomputes it (both
ask for that through the validation context, which stored data can't reach), and loading a record
re-checks it. Never use `model_construct` on a record: it skips every check. Load stored records with
`model_validate_json` (the strict claims take tuples and datetimes from JSON, not from a Python dict of
lists and strings).

Every string field (title, abstract, authors, keywords, venue_id_raw, urls, and a claim's value, url and
evidence) must be valid Unicode (no lone surrogates), so a snapshot can always be written. A title has
no control characters; an abstract has no leading or trailing whitespace (importers strip it, and it is
hashed). A claim's value must fit its field: `year` an int, `authors`/`keywords` a tuple, every other
field a string. A forum-id native is 4–64 of `[A-Za-z0-9_-]` with at least one letter or digit.

**The ingest caps** (`ingest/caps.py`, decision-026, TASK-155; spec 01 §Pipeline 2). They exist because NFKC's
canonical reordering is superlinear in a long run of marks with alternating combining classes.
- **Marks.** A title or abstract keeps at most 8 combining marks in a run, and the extras are dropped.
  - A mark is a character whose NFKD form starts with a non-zero combining class.
  - A run ends only at a base: a letter or digit that is not a mark, and that the tokenizer keeps
    (`normalize.latex_mask`).
  - The tokenizer joins a word across the invisible characters it drops (ZWJ, soft hyphen, variation selectors)
    and across LaTeX markup (`\-`, the letter of an accent macro such as `\H{…}`). So none of those may reset
    the count.
  - A run is counted in NFKD non-starters, the base's own included.
  - A run over the cap is rewritten in its NFKD form, with its marks in canonical order, then keeps its first 8.
    So every Unicode form of the same text trims alike, and dedup title keys stay equal.
  - This keeps every token's run of non-starters within 8.
- **Length.** An abstract keeps at most 20,000 code points. A cut one is stripped of trailing whitespace and
  `…`.
- **Where.** The caps run once, in `snapshot.load_sources`, before dedup, on the record's field and on every
  claim of it alike.
- **Flagged.** Never silent: a trimmed claim's `evidence` carries `trimmed at ingest (decision-026): <what>`,
  the marks dropped and the length cut from and to.
  - With no source evidence, the note is the whole evidence.
  - Otherwise it follows the source's evidence in parentheses, so an RIS route and url stay first for
    `dedup.attribution`.
  - `caps.is_trimmed` matches only that form at the end.
  - The manifest's `trimmed` lists the records with any trimmed title or abstract claim.
- **Model.** The caps belong to the build, not the model: `PaperRecord` doesn't refuse text over them.
- **Unchanged otherwise.** Text within both caps comes back unchanged, so the caps change no record of a corpus
  within them.
