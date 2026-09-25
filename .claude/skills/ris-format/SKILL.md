---
name: ris-format
description: The openproceedings RIS export standard — the spec 04 field mapping, the Covidence-safe choices (one AU per line, full single-line AB, T2 venue string, N1 provenance line, UTF-8), what venuetriage's RIS parser tolerates and silently drops, the known Covidence import behaviours, and the round-trip test. Use when writing or reviewing backend/src/openproceedings/api/exporters/ RIS code, `op export --format ris`, or an RIS fixture.
---

# RIS export (spec 04 §Exports)

The RIS file exists to be imported into Covidence for screening. A wrong field there reaches the
screeners, and Covidence cannot fix it after the fact (see the gotchas below).

## Line grammar
`TAG  - value`: a two-letter tag, **two spaces**, a hyphen, one space, the value. Every record begins with
`TY  - ` and ends with `ER  - `, followed by a blank line. Pick one line ending (LF) and pin it in the
fixtures. The reference parser strips values, so it reads either ending.

## Field mapping
| Tag | Value | Notes |
|---|---|---|
| `TY` | `CPAPER` for proceedings papers | Spec allows `JOUR`/`CPAPER`. Confirm what Covidence shows for `CPAPER` in the hand-imported fixture. |
| `TI` | full title | One line. No trailing period added. |
| `AU` | one author per line, `Last, First` | Full names from the record. Never initials only, never an `...` sentinel line. |
| `PY` | year | The file known to import cleanly (Trust-Evals `mended.ris`) used `2025///`. Plain `2025` is also valid RIS. Pin one with the fixture. |
| `T2` | venue string | e.g. `International Conference on Learning Representations (ICLR 2025)`. The NeurIPS and ICML strings are pinned from the venue table; verify the wording at implementation time. |
| `AB` | the **full** abstract on **one line** | Replace internal newlines with a space. Never truncate, never use `…`. |
| `UR` | forum URL, then PDF URL | Two `UR` lines in that order. Skip an absent URL, never write an empty one. |
| `DO` | DOI, only if present | |
| `ID` | the openproceedings paper `id` | So exports round-trip (spec 04 §Exports). Exactly one line. |
| `KW` | `track` value (`main`, `datasets_benchmarks`, …) | From `.claude/skills/track-taxonomy/SKILL.md`. |
| `N1` | `openproceedings <index_version> · query <canonical_hash> · <UTC date>` | Exactly one provenance line. `·` is U+00B7. The date is `YYYY-MM-DD` UTC. |
| `ER` | empty | |

**Id carrier:** the round-trip test reads the openproceedings `id` back from the `ID` tag, for every
record including PMLR-only ones. Never overload `N1` or recover ids from `UR`.

## Encoding
UTF-8. Keep diacritics and non-Latin names as they are (`Şahin`); never ASCII-fold them in RIS.
`mended.ris`, which imported cleanly, started with a BOM. venuetriage reads with `utf-8-sig`, so either
choice parses. Match the known-good file unless the Covidence fixture shows otherwise.

## What venuetriage's parser does (`Trust-Evals-LitReview/src/venuetriage/parse.py`, read-only)
- Records start at the regex `^TY  - `. Any non-blank text before the first `TY` raises `ValueError`, so
  write no header comment.
- Fields match `^([A-Z][A-Z0-9])  - (.*)$`. **Continuation lines are dropped silently.** A multi-line `AB`
  loses everything after its first line with no error. That is why `AB` must be a single line.
- Repeated tags (`AU`, `UR`, `KW`) keep every value, in order.

## Covidence behaviours to design around (from the Trust-Evals import, review 827224)
- Covidence keeps the **first** imported copy of a reference and matches duplicates on an exact year.
  A corrected file cannot be layered over an earlier import. Once any vote is cast, the only fix is a
  new review. Get `PY`, `TI` and `AU` right the first time.
- Scholar's snippet `AB` (fragments joined by `…`) looked like an abstract to screeners. That is the
  failure this export exists to prevent.

## Round-trip test (spec 04 §Testing)
`backend/tests/contract/`: export the fixture query, parse the result with an independent RIS reader
(the same rules as venuetriage, not our writer's code), and assert:
1. the record count equals `X-Total` and `/search` `total`;
2. the set of ids equals `match_ids` for the query;
3. `TI`, `AB`, the ordered `AU` list, `PY` and `T2` equal the stored record field for field;
4. every record has exactly one `N1`, and it names the served `index_version` and `canonical_hash`;
5. no value contains `\n`, `…` or `\r`.
Freeze the clock so the `N1` date is fixed and the file can be byte-compared to a golden fixture.
Cover records with no abstract, no DOI, no PDF URL, a non-ASCII author and a title with LaTeX. One
fixture is also imported into Covidence by hand, and the result is recorded in `docs/results/`.
