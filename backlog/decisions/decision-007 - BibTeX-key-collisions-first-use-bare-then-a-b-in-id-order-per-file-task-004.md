---
id: decision-007
title: >-
  BibTeX key collisions: first use bare, then a, b in id order, per file
  (task-004)
date: '2026-09-27 07:45'
status: accepted
---
## Context

Spec 04 keys BibTeX entries `<firstauthorlast><year><firsttitleword>` and de-duplicates them "with a/b",
but left open whether the first paper with a colliding key stays bare (`smith2024deep`, `smith2024deepa`,
`smith2024deepb`) or also takes a letter (`smith2024deepa`, `smith2024deepb`, `smith2024deepc`). The
bibtex-format skill asked for the choice to be pinned. task-030 built the first form: a repeat key takes the
next unused suffix, so a suffixed key never meets a real one (`smith2024deepa` from a title starting
"Deepa" moves on to `smith2024deepaa`). Found while pinning the export details in task-004.

What other tools do (checked 2026-09-27):
- **Better BibTeX for Zotero** (retorque.re/zotero-better-bibtex/citing/): on a clash it appends a letter
  postfix (a, b, c, …; Zotero-style numbers optional). The first item keeps the bare key. It keeps keys stable
  by taking every other key in the library into account "regardless of what part of your library you
  export", and by letting users pin keys.
- **JabRef** (docs.jabref.org/setup/citationkeypatterns): a key that isn't unique "is made unique by adding
  one of the letters a-z until a unique key is found". The existing key stays bare (`Yared1998`, then
  `Yared1998a`).

Options considered:
1. **First use bare, later ones a, b, … in the export's id order** (as built). This matches BBT and JabRef.
   It streams with a set of issued keys and needs no pre-pass. A paper that collides with nothing keeps its
   bare key in every export.
2. **Every colliding paper suffixed, from `a`** (biblatex's `2024a`/`2024b` labels look like this). It needs a
   pre-pass over the whole set before the first entry is written, which breaks streaming (spec 04: exports
   stream, not held whole). It is also less stable: a paper exported alone as `smith2024deep` becomes
   `smith2024deepa` as soon as any colliding paper joins a later export.
3. **A suffix derived from the paper's id** (`smith2024deep-iilhN2`). Stable in every export, but unreadable,
   and not the spec's a/b scheme or what any reference manager does.
4. **Index-wide assignment** (BBT's approach, with the index as the library): number every collision
   group over the whole index at build time, so every export from one `index_version` gives a paper the same
   key whatever the query. That needs a key table built with the index (`engine/`) and passed to the
   exporter. It is more work than the need justifies today, because keys are documented as per-file and
   the id lives in `openproceedings_id`.

## Decision

We keep option 1. The first paper with a key keeps it bare; each later paper with the same key, in the
export's stable order (ascending openproceedings id), takes the next suffix that hasn't been issued in that
file: a, b, … z, aa, ab, …. Keys are unique within one file and are not identifiers.

## Consequences

- Deterministic: the same set from the same index gives byte-identical keys. Pinned by
  `test_three_colliding_keys_the_first_bare_then_a_then_b` and `test_bibtex_keys` in
  `backend/tests/unit/test_export.py`, which also parse the result with the pinned refaudit.
- Superset stability, pinned by `test_a_superset_keeps_keys_unless_an_added_paper_sorts_first`: an
  export of a superset keeps every earlier key when the added colliding papers sort after the ones already
  there. An added paper that sorts first takes the bare key and shifts the rest by one letter. So does an
  added paper whose real key equals a suffix issued before it. Users who cite from successive exports should
  merge on `openproceedings_id` (or DOI), not on the key. Spec 04 §Exports and the bibtex-format skill say so.
- No code change: task-030's `_bibtex` already implements this. Spec 04 §Exports and
  `.claude/skills/bibtex-format/SKILL.md` now state the rule as decided.
- Revisit (option 4) if users ask for keys that survive re-exports, for example to keep a LaTeX manuscript's
  `\cite` keys valid across searches. Keys would then depend on `index_version`, as membership does.