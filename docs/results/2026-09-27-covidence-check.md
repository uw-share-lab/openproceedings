# Covidence import check for the RIS export (task-004 AC#1): pending

**Status: not yet run.** Only a person can do this import. When it's done, fill in the Result column and the
Outcome section, then tick TASK-004 AC#1 (`backlog task edit TASK-004 --check-ac 1`).

## What this checks
The RIS export writes `TY  - CPAPER` (spec 04 §Exports). The question is whether Covidence imports
`CPAPER` records with every field a screener needs, and how it deduplicates them against copies of the same
paper from other databases. The files:

- `docs/results/2026-09-27-covidence-fixture.ris`: six invented records (decision-004), byte for byte what
  the RIS writer produces today. `backend/tests/unit/test_covidence_fixture.py` fails if the writer changes,
  and then this check has to be redone. The records:
  - ICLR 2024 with an astral-plane title (`𝒪`, `𝔽`) and **no abstract**
  - ICLR 2025
  - ICML 2023, PMLR only (no forum URL), with LaTeX in the abstract
  - NeurIPS 2017, proceedings only: its `T2` says **NIPS 2017**
  - NeurIPS 2023 with **seven authors**, most with non-ASCII names (`Şahin`, `Nguyễn, Thị Hương`,
    `Kowalczyk, Łukasz`)
  - NeurIPS 2024 datasets and benchmarks track, with a DOI
- `docs/results/2026-09-27-covidence-dedup-probe.ris`: two of those papers written as another database
  might export them. The NeurIPS 2023 paper is a `JOUR` with `T2` "Advances in Neural Information
  Processing Systems" and `VL  - 36`. The ICML 2023 paper is a `CONF` with the PMLR volume title and no `VL`.
  Title, authors and year are identical to the fixture's.

## Steps
1. **Use a throwaway Covidence review, never the live one.** Covidence keeps the first imported copy of a
   reference, and an import can't be undone once anyone votes (ris-format skill; Trust-Evals review 827224).
2. Import `2026-09-27-covidence-fixture.ris` (Import references → RIS). Covidence should report
   **6 references imported, 0 duplicates**.
3. Open each of the six references and fill in the table below.
4. Import `2026-09-27-covidence-fixture.ris` again. Expected: **0 imported, 6 duplicates**.
5. Import `2026-09-27-covidence-dedup-probe.ris`. Note which of the two probe records Covidence marks as
   duplicates. Covidence matches on title, year, volume and authors
   ([Covidence FAQ](https://support.covidence.org/help/how-does-covidence-detect-duplicates)). The FAQ
   doesn't say what an empty volume does, so this probe finds out.

## Per-record checks (step 3)
| Field on screen | Expected | Result |
|---|---|---|
| Title | exact, including `𝒪(log n)` and `𝔽` shown as characters, not `?` or boxes | |
| Abstract | the full text on one paragraph, never cut. The ICLR 2024 record shows no abstract, not an empty quote or garbage | |
| Authors | every author, **in file order**, diacritics intact. The NeurIPS 2023 record lists 7, `Şahin, Elif` first and `Kowalczyk, Łukasz` last | |
| Year | 2024, 2025, 2023, 2017, 2023, 2024: the `PY`, with no `///` | |
| Journal / source | the `T2` string, e.g. `Conference on Neural Information Processing Systems (NIPS 2017)`. If Covidence shows nothing there for `CPAPER`, note which field (if any) holds it | |
| Reference type | what Covidence calls a `CPAPER` (conference paper?) | |
| URL | the forum URL (OpenReview records) or the PMLR PDF / NeurIPS proceedings page | |
| DOI | only the NeurIPS 2024 record: `10.5555/trustbench.2024.001` | |
| Notes | the `N1` provenance line `openproceedings fixture0000a · query 000… · 2026-09-27`, with `·` intact | |
| Keywords | the track (`main`, `datasets_benchmarks`) | |
| ID | whether `op:…` shows anywhere (not required, but record it) | |

## Dedup checks (steps 4 and 5)
| Import | Expected | Result |
|---|---|---|
| Fixture again | 6 duplicates, 0 new | |
| Probe: NeurIPS 2023 as `JOUR` + `VL 36` | ? (a duplicate only if Covidence ignores an empty volume on one side) | |
| Probe: ICML 2023 as `CONF`, no `VL` | a duplicate (title, year and authors match, and neither record has a volume) | |

## Outcome (fill in)
- `CPAPER` imports cleanly, with every field above shown: yes / no. If no, what broke and whether `JOUR`
  fixes it (re-export with `TY  - JOUR` and repeat steps 2–3 in a fresh throwaway review).
- An empty `VL` against `VL 36`: matched / not matched. If not matched, the export should write `VL` (NeurIPS
  volume = year − 1987; the PMLR volume for ICML) so copies from other databases are caught. That's a spec
  change to decide then.
- Date, reviewer role, Covidence review id (throwaway).
