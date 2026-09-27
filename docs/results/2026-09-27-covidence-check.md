# Covidence import check for the RIS export (task-004 AC#1): pending

**Status: not yet run.** Only a person can do this import. When it's done:
1. Fill in the Result columns and the Outcome section, including the fixture's sha256.
2. Tick TASK-004 AC#1 (`backlog task edit TASK-004 --check-ac 1`).

Once the sha256 is recorded, or AC#1 is ticked, `test_the_hand_imported_fixture_is_the_pinned_one` in
`backend/tests/unit/test_covidence_fixture.py` checks that the file you imported is the one pinned in the
repo.

## What this checks
The RIS export writes `TY  - CPAPER` for every record (spec 04 §Exports). This check answers two questions:
- Does Covidence import `CPAPER` records with every field a screener needs?
- How does Covidence deduplicate them against copies of the same paper from other databases?

The files:
- `docs/results/2026-09-27-covidence-fixture.ris`: seven invented records (decision-004). The file is byte
  for byte what the RIS writer produces today. `backend/tests/unit/test_covidence_fixture.py` fails if the
  writer changes, and then this check has to be redone.
- `docs/results/2026-09-27-covidence-dedup-probe.ris`: three copies of fixture papers, each changed in one
  way, so any dedup result can be put down to that change (all three pinned by the same test):
  - **Probe 1** is the NeurIPS 2023 fixture record plus `VL  - 36`, and nothing else.
  - **Probe 2** is the ICML 2023 paper as a `CONF` with the PMLR volume title in `T2`, no volume, and only
    TY/TI/AU/PY/T2.
  - **Probe 3** is the NeurIPS 2024 paper as a `JOUR` with `T2` "Advances in Neural Information Processing
    Systems" and `VL  - 37`, the way another database might export it.

## Steps
1. **Create a throwaway Covidence review for this and never use the live one.** Never vote or screen
   anything in it, and delete it when you're done. Covidence keeps the first imported copy of a reference,
   and an import can't be undone once anyone votes (ris-format skill; Trust-Evals review 827224).
2. In the throwaway review, choose **Import references**:
   - **Import into:** **Screen** (the *Title and abstract screening* stage).
   - **Source:** `openproceedings fixture`.
   - **File:** `2026-09-27-covidence-fixture.ris`.

   Covidence should report **7 references imported, 0 duplicates**.
3. Open each of the seven references in *Title and abstract screening*, without voting, and fill in the
   per-record table below.
4. Import `2026-09-27-covidence-fixture.ris` again (Screen, source `openproceedings fixture again`).
   Expected: **0 imported, 7 duplicates**.
5. Import `2026-09-27-covidence-dedup-probe.ris` (Screen, source `openproceedings dedup probe`). Note which
   of the three probe records Covidence marks as duplicates. Covidence matches on title, year, volume and
   authors ([Covidence FAQ](https://support.covidence.org/help/how-does-covidence-detect-duplicates)). The FAQ
   doesn't say what an empty volume does, so this step finds out.
6. Delete the throwaway review.

## Per-record checks (step 3)
For every record, check each of these on screen:
- **Title:** exact, with every character shown (not `?` or boxes).
- **Abstract:** the full text as one paragraph, never cut.
- **Authors:** every author, in file order, with diacritics intact.
- **Year:** the year in the table, with no `///`. **Note any year that differs from the table**, since
  Covidence deduplicates on the exact year.
- **Journal/source:** the `T2` string. If Covidence shows nothing there for `CPAPER`, note which field (if
  any) holds it.
- **URL:** the first `UR`.
- **Notes:** the `N1` provenance line `openproceedings fixture0000a · query 000… · 2026-09-27`, with `·`
  intact.
- **Keywords:** the track, then `status:<status>`.

Write "ok" in the Result column, or what differed.

| # | Record (`ID`) | What to look for | Result |
|---|---|---|---|
| 1 | `op:iclr:2024:Wd8nJ3cV5r`: ICLR 2024, **rejected** | Keywords show `status:rejected`. Year 2024. Source `International Conference on Learning Representations (ICLR 2024)` | |
| 2 | `op:iclr:2024:Xq7Lm2Pz9A`: ICLR 2024 | Title shows `𝒪(log n)` and `𝔽` (outside the BMP). **No abstract**: nothing shown, not an empty quote or garbage. Year 2024 | |
| 3 | `op:iclr:2025:bT4kR8sW1n`: ICLR 2025 | Full abstract. 3 authors. Year 2025 | |
| 4 | `op:icml:2023:pmlr-v202-okafor23a`: ICML 2023, PMLR only | LaTeX in the abstract (`$\epsilon$`) kept as written. URL is the PMLR PDF. Year 2023. Source `International Conference on Machine Learning (ICML 2023)` | |
| 5 | `op:neurips:2017:nips-3f9a…`: NeurIPS 2017, proceedings only | Source says **NIPS 2017**: `Conference on Neural Information Processing Systems (NIPS 2017)`. URL is the proceedings page. Year 2017 | |
| 6 | `op:neurips:2023:Hn3vQ6eYt0`: NeurIPS 2023 | **7 authors in order**, from `Şahin, Elif` to `Kowalczyk, Łukasz`, with `Nguyễn, Thị Hương` intact. Year 2023 | |
| 7 | `op:neurips:2024:Rk2wP5dLx8`: NeurIPS 2024, datasets and benchmarks | DOI `10.5555/trustbench.2024.001`. Keywords `datasets_benchmarks`, `status:accepted`. Year 2024 | |

Also record once: the reference type Covidence shows for a `CPAPER`, and whether the `op:…` id shows
anywhere (not required).

## Dedup checks (steps 4 and 5)
| Import | Expected | Result |
|---|---|---|
| Fixture again | 7 duplicates, 0 new | |
| Probe 1: NeurIPS 2023, identical but for `VL  - 36` | A duplicate only if Covidence ignores a volume that is empty on one side | |
| Probe 2: ICML 2023 as `CONF`, PMLR title, no `VL` | A duplicate: title, year and authors match, and neither record has a volume | |
| Probe 3: NeurIPS 2024 as `JOUR` + `VL  - 37` | The same result as probe 1, unless the type or source also matters | |

## If `CPAPER` fails: the `JOUR` fallback
Make a `JOUR` copy and repeat steps 1–3 in a **new** throwaway review:

```sh
sed 's/^TY  - CPAPER$/TY  - JOUR/' docs/results/2026-09-27-covidence-fixture.ris > /tmp/covidence-fixture-jour.ris
```

Record the result below. The export only changes to `JOUR` through a spec 04 change.

## Outcome (fill in)
- Fixture sha256 imported: ``
  (`shasum -a 256 docs/results/2026-09-27-covidence-fixture.ris`, run on the file you imported. Paste the
  64 hex characters between the backticks.)
- `CPAPER` imports cleanly, with every field above shown: yes / no. If no, what broke, and whether the `JOUR`
  fallback fixes it.
- Any year shown differently from the table: none / which.
- Empty `VL` against `VL  - 36` (probe 1): matched / not matched. If not matched, TASK-081 decides whether the
  export writes `VL`.
- Date, reviewer role, and that the throwaway review was deleted.
