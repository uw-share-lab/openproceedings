# Creative AI listings merge with their own OpenReview notes: 59 of 64 on the real crawl (TASK-137), 2026-09-30

Decided by the owner, 2026-09-30: a NeurIPS Creative AI listing merges with its own OpenReview note; other
`other` tracks still never merge (decision-005, amended). As built, dedup's track rule is per family: a merge
involving a listing holds only `PROCEEDINGS_TRACKS` records or only NeurIPS Creative AI records
(`dedup.is_creative_ai`: every source claiming the track says `other` and backs it with the
`NeurIPS.cc/<Y>/Creative_AI_Track` venueid or a `-Creative_AI_Track` proceedings URL of the record's year).
`other` stays out of `PROCEEDINGS_TRACKS`, so reconcile is unchanged.

## What was run
Two scratch data directories, each with the main checkout's `data/cache` symlinked read-only (the 2026-09-29
crawl). "Before" ran origin/dev `a48e453` from a detached worktree; "after" ran the TASK-137 branch. In each:
```
OP_DATA_DIR=<scratch> uv run --locked op snapshot build
OP_DATA_DIR=<scratch> uv run --locked op index build --snapshot <scratch>/snapshots/<snapshot>
OP_DATA_DIR=<scratch> uv run --locked op eval coverage --index <index> --out <scratch>/report --check
```

| | Before | After |
|---|---|---|
| Snapshot | `2026-09-29-c6c9a156fdf7` | `2026-09-29-78f5a0204501` |
| Index | `dd58cd19856e` | `375263be7993` |
| Records | 95,936 | 95,877 (−59) |
| Merges | 28,272 | 28,331 (+59, all `title_venue_year` NeurIPS 2025) |
| Conflicts | 7,815 | 7,815 (+59 `status` `precedence:neurips_proceedings`, −61 `title_key` `track_not_merged`, +2 `title_key` `ambiguous_not_merged`) |
| M4 gate | PASS (43 of 44, ICLR 2013 main accepted, decision-016) | PASS, identical |

## NeurIPS 2025 Creative AI (the only year with Creative AI listings)
- **59 of 64 listings merged** with their notes: 58 are now proceedings + OpenReview records, 1 proceedings +
  OpenReview + RIS. Each keeps track `other` (both sides say so) and takes `accepted` from the proceedings over
  OpenReview's bare-path `unknown` (the 59 new status rows).
- Two of the 59 merged past a same-title workshop note (`3yeBer3J5z` past AI4Music workshop `yL8BrlEqHQ`, and
  `tY3Jvs5jwN` past `3CGj0ANxaZ`), which stays a separate record with a `track_not_merged` row.
- **5 listings stay listing-only:**
  - `nips-1350a018b6442df34ef97648647a3e16` Artificial "Authentic" Intelligence: … "Cyber Subin" and Thai
    Traditional Dance (no note with this title)
  - `nips-3bd4e338b06d69dbc16b66be1a0cd4f8` Possible You: AI-Generated Digital Twins as Creative Mirrors for
    Future Self Modeling (no note)
  - `nips-57fd8c11123a66899dbb625c7318e986` "Artificial Spectator" Developing AI Audiences for Watching
    AI-Generated Films … (no note)
  - `nips-e7d712cef7adb2c0d3917b3b9c09cfcd` Text to Robotic Assembly of Multi Component Objects using 3D
    Generative AI and Vision Language Models (no note)
  - `nips-ddf6cdb31fbd9b23613e0c59aa339cea` LUMIA: A Handheld Vision-to-Music System for Real-Time, Embodied
    Composition: its title matches two Creative AI notes (`Trmj1dfNmO`, `l5OW2GmSvX`), so it is ambiguous
    (the 2 new `ambiguous_not_merged` rows)
- **Cells:** NeurIPS 2025 `other`/`unknown` 146 → 87 (the 59 absorbed notes; the 54 `Education_Program` notes
  and 33 unlisted Creative AI notes remain). `other`/`accepted` stays 64. **No other cell moved.**
- Every changed record is Creative AI, and the 59 ids that vanished are exactly the new `merged_id`s.
