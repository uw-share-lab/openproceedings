---
name: ris-format
description: The openproceedings RIS export standard — the spec 04 field mapping, the Covidence-safe choices (one AU per line, full single-line AB, T2 venue string, N1 provenance line, UTF-8), what scholarmend's RIS parser (`scholarmend.parse.parse_ris`, pinned from PyPI) tolerates and silently drops, the known Covidence import behaviours, and the round-trip test. Use when writing or reviewing backend/src/openproceedings/api/exporters/ RIS code, `op export --format ris`, or an RIS fixture.
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
| `TY` | `CPAPER` for every record | Chosen over `JOUR` (spec 04 §Exports, task-004): Zotero imports it as `conferencePaper` with `T2` as `conferenceName`, EndNote as *Conference Paper*. EndNote's default duplicate check stays within one reference type, so another database's `JOUR`/`CONF` copy of a paper is only caught with Reference Type unticked. The Covidence hand import is `docs/results/2026-09-27-covidence-check.md` (**pending**). |
| `TI` | full title | One line. No trailing period added. |
| `AU` | one author per line, `Last, First` | Full names from the record. Never initials only, never an `...` sentinel line. |
| `PY` | year | The file known to import cleanly (Trust-Evals `mended.ris`) used `2025///`. Plain `2025` is also valid RIS. The writer writes plain `2025`; the Covidence check confirms it shows as the year. |
| `T2` | venue string: `<conference name> (<acronym that year> <year>)` | `export.venue_name()`, table `CONFERENCES` (spec 04 §Exports cites the sources). `Conference on Neural Information Processing Systems (NIPS 2017)`, `… (NeurIPS 2018)` on; `International Conference on Learning Representations (ICLR 2025)`; `International Conference on Machine Learning (ICML 2023)`. One string per venue-year whatever the track or status. It is the conference's name, never a proceedings title, because workshop, rejected and ICLR papers are in no proceedings. A year before the venue was held is refused. |
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
`mended.ris`, which imported cleanly, started with a BOM. The reference parser reads with `utf-8-sig`, so either
choice parses. Match the known-good file unless the Covidence fixture shows otherwise.

## What the reference RIS parser does (`scholarmend.parse.parse_ris`, from the pinned `scholarmend` PyPI package)
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
(`scholarmend.parse.parse_ris`, not our writer's code), and assert:
1. the record count equals `X-Total` and `/search` `total`;
2. the set of ids equals `match_ids` for the query;
3. `TI`, `AB`, the ordered `AU` list, `PY` and `T2` equal the stored record field for field;
4. every record has exactly one `N1`, and it names the served `index_version` and `canonical_hash`;
5. no value contains `\n`, `…` or `\r`.
Freeze the clock so the `N1` date is fixed and the file can be byte-compared to a golden fixture.
Cover records with no abstract, no DOI, no PDF URL, a non-ASCII author and a title with LaTeX. One
fixture is also imported into Covidence by hand: `docs/results/2026-09-27-covidence-fixture.ris`, with the
checklist and results in `docs/results/2026-09-27-covidence-check.md` (pending, task-004 AC#1).
`backend/tests/unit/test_covidence_fixture.py` pins that file byte for byte to the writer, so a writer change
fails it, and the hand import has to be redone before the fixture is regenerated.
