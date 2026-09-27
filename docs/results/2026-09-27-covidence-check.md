# Covidence import check for the RIS export (task-004 AC#1): pending

**Status: not yet run.** Only a person can do this import. When it's done:
1. Fill in the Result columns and the Outcome section, including the fixture's sha256.
2. Tick TASK-004 AC#1 (`backlog task edit TASK-004 --check-ac 1`) and TASK-036 AC#1
   (`backlog task edit TASK-036 --check-ac 1`: the API's RIS body is byte for byte `op export`'s).
3. Add a final summary to each and complete both: `backlog task complete TASK-004`, then
   `backlog task complete TASK-036` (every other AC of both is already ticked).

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
- `docs/results/2026-09-27-covidence-dedup-probe.ris`: five copies of fixture papers, each changed in one
  way, so any dedup result can be put down to that change (all five pinned by the same test):
  - **Probe 1** is the NeurIPS 2023 fixture record plus `VL  - 36`, and nothing else.
  - **Probe 2** is the ICML 2023 paper as a `CONF` with the PMLR volume title in `T2`, no volume, and only
    TY/TI/AU/PY/T2.
  - **Probe 3** is the NeurIPS 2024 paper as a `JOUR` with `T2` "Advances in Neural Information Processing
    Systems" and `VL  - 37`, the way another database might export it.
  - **Probe 4** is fixture record 3 (ICLR 2025, `op:iclr:2025:bT4kR8sW1n`) with `PY  - 2024`, one year
    earlier, and nothing else (its `T2` still says ICLR 2025). Another database may date a paper by its
    OpenReview posting or preprint year.
  - **Probe 5** is fixture record 6 (NeurIPS 2023, `op:neurips:2023:Hn3vQ6eYt0`) with every author as
    initials only (`Şahin, E.`, `Nguyễn, T. H.`, …, `Kowalczyk, Ł.`), and nothing else. Probe 1 is the same
    paper, so if probe 1 was imported as new, probe 5 may match either copy; a match still means Covidence
    tolerates initials.

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
   of the five probe records Covidence marks as duplicates. Covidence matches on title, year, volume and
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
- **Notes:** the `N1` provenance line `openproceedings fixture0000a · query 000… · exported 2026-09-27`,
  with `·` intact. Record 1 (rejected) has a second note before it: `Submitted to International Conference
  on Learning Representations (ICLR 2024); status: rejected (not in its proceedings).` Check both show, in
  that order.
- **Keywords:** the track, then `status:<status>`.

Write "ok" in the Result column, or what differed.

| # | Record (`ID`) | What to look for | Result |
|---|---|---|---|
| 1 | `op:iclr:2024:Wd8nJ3cV5r`: ICLR 2024, **rejected** | Keywords show `status:rejected` (where, if at all, a screener sees them). Notes show `Submitted to … (ICLR 2024); status: rejected (not in its proceedings).` then the provenance line. Year 2024. Source `International Conference on Learning Representations (ICLR 2024)` | |
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
| Probe 4: ICLR 2025 record with `PY  - 2024` | Not a duplicate if Covidence matches the exact year (its FAQ says it compares year) | |
| Probe 5: NeurIPS 2023 record with initials-only authors | Unknown: a duplicate only if Covidence normalises author names to initials | |

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
- KW (status) visible to screeners in *Title and abstract screening*: yes / no. If no, the status reaches
  them only through the first `N1` note (record 1's "Submitted to …; status: rejected (not in its
  proceedings)."): check that note is visible to screeners instead. If neither is, a rejected paper can't be
  told apart while screening: say so here, and the review must exclude by status before import (export
  with the default `status:accepted` filter, or filter the CSV's `status` column).
- Year one earlier (probe 4): matched / not matched. Initials-only authors (probe 5): matched / not matched.
- **What must be deduplicated by hand:** list each probe Covidence did *not* mark as a duplicate (for
  example "probe 4: a copy dated a year earlier elsewhere"): those are the cross-database copies screeners
  must merge by hand in Covidence's duplicate review.
- Where the duplicates Covidence finds are reported: in the PRISMA flow diagram's **duplicates removed**
  box (the review's own deduplication across databases). openproceedings' dedup statement (the search
  record's `dedup` counts, PRISMA-S item 16) covers only merges inside openproceedings at ingest; never add
  Covidence's count to it, or its count to Covidence's.
- Date, reviewer role, and that the throwaway review was deleted.
