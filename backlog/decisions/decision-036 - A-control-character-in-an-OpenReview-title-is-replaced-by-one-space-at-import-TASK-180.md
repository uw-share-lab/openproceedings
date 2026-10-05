---
id: decision-036
title: >-
  A control character in an OpenReview title is replaced by one space at import
  (TASK-180)
date: '2026-10-05 07:20'
status: accepted
---
## Context

A record's title holds no control character (Unicode category `Cc`: C0, DEL, C1); `PaperRecord` refuses one. Sources leave them in: a PDF's soft line break pasted as U+0002 (`A SPEC␂TRUM FROM …`), a trailing NUL. The 2026 crawl (TASK-178) skipped ICLR 2026 `xHMNX3l8rx`, an accepted workshop paper, as `invalid` for two U+0002 in its title, and NeurIPS 2026 `KlvYZ17FPi` for a trailing NUL. Two earlier crawls had lost a paper the same way (ICLR 2024 `PqjQmLNuJt`, ICLR 2023 `6l46OaYQvu3`). A real paper was missing from the corpus over invisible characters. In the RIS importer the same character would have raised out of the import and failed the build, and in a proceedings importer it would have dropped the listing, after which reconcile would turn that paper's OpenReview acceptance into `unknown`.

Options considered:
1. Keep refusing the record. The paper stays missing.
2. Delete the control character. `SPEC␂TRUM` becomes `SPECTRUM`, which is right for that title. But U+0002 stands for a line-break hyphen in some texts (`modal␂ity`) and a real hyphen in others (`state␂of-the-art`, `decision␂making`, `3D␂MoLM`, all in crawled abstracts), so deletion fuses two words about as often as it mends one. It also changes the tokens: the tokenizer reads a control character as a separator (`spec`, `trum`).
3. Replace it with a space. The stored title's tokens are exactly the raw title's, and nothing is fused. The cost is readability and recall for a mended word: the title reads `SPEC TRUM`, and a search for `spectrum` does not find it.
4. Relax the record model and store the character. Every export and every display would then have to handle it.

## Decision

Every importer replaces each control character in a title with one space and then collapses whitespace (`record.title_text`); the title is otherwise the source's. The owner chose the space and rejected deletion (2026-10-05). The title claim's evidence states how many were replaced (`record.title_evidence`). Abstracts, authors and keywords are not changed.

## Consequences

- Applies to the OpenReview API v1 and v2 crawlers, the RIS importer and the NeurIPS, PMLR and ICLR-archive listings, through the one function. The record model still refuses a control character in a title.
- Tokenization is unchanged in meaning: the tokenizer already split on control characters, so `normalize(stored) == normalize(raw)`. The one exception is a control character just inside `$…$`, where a space stops the span reading as math; a test pins it, and no real title has it.
- No version changes. Only records that were refused before are affected: a rebuild of the 2026-10-05 cache adds four records (`op:iclr:2026:xHMNX3l8rx`, `op:neurips:2026:KlvYZ17FPi`, `op:iclr:2024:PqjQmLNuJt`, `op:iclr:2023:6l46OaYQvu3`) and changes the content of no other. `TOKENIZER_VERSION`, `SCHEMA_VERSION` and the record schema version stay; existing search records are unaffected until a new snapshot is indexed, and then drift only by the added papers.
- Whitespace controls (tab, line breaks, U+000B, U+001C–U+001F, U+0085) always became a space when whitespace was collapsed; they are not counted, so those titles' claims are byte-identical.
- Abstracts keep their control characters (dozens of crawled abstracts hold U+0002, and the tokenizer splits on it, so `modal␂ity` indexes as `modal`, `ity`). Cleaning them would change stored bytes and content hashes of existing records; it is a separate decision.
- Stated in spec 01 §Pipeline 2 and the `record-schema` and `openreview-api` skills. Tests: `test_record.py` (the table, the token property, the math exception), and one per importer (`test_openreview_v2.py`, `test_openreview_v1.py`, `test_ris.py`, `test_neurips.py`, `test_pmlr.py`, `test_iclr.py`).
- Revisit if the tokenizer ever stops treating a control character as a separator, or if a source appears whose control characters are reliably one thing (then deletion or a hyphen could be right for that source).

