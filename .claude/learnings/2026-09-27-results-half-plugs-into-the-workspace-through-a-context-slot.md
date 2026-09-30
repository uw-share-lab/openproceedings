# The results half plugs into the search workspace through one context slot, and the React compiler lint rejects a render-prop that closes over refs

**Key lesson:** Give a component drawn inside another's area what it needs through a context provided around a `ReactNode` slot (`results` + `useWorkspaceSlot()`), not a render prop called during render, because eslint's `react-hooks/refs` rejects passing ref-reading callbacks to a function called in render; and keep the host's diff to a prop, a provider and one effect so parallel branches merge.

- **Date:** 2026-09-27 · **Task:** task-042 · **Area:** frontend
- **Artifacts:** `frontend/src/components/search/{search-view.tsx,workspace-slot.ts,controls.ts,exclusions.ts,filter-sidebar.tsx}`, `frontend/src/components/paper/paper-view.tsx`, `frontend/src/lib/excerpt.ts`

## What we set out to do
Build `/search`'s results, exclusion banner, filter sidebar (year included), paging and error states, and
`/paper/[id]`, while TASK-043 edits the editor area of the same `SearchWorkspace` in parallel.

## What we learned
- **A render prop that closes over refs fails lint.** `results?.({ select: () => editor.current?.select() })`
  is "Cannot access refs during render" (react-hooks/refs), and so is reading any field of a props object
  that holds a ref (`p.searching` next to `p.heading`); destructuring the props fixed the second. A context
  provider around a `ReactNode` slot passes the same callbacks without the error, and the host's diff is 26
  lines (evidence: `git diff feat/m3b-ui -- frontend/src/components/search/search-workspace.tsx`).
- **"Select after the draft changes" needs no timer.** Child effects run before the parent's, so the
  editor's value effect has already replaced the document when the workspace's effect applies a pending
  selection (`draftAndSelect`; test "Edit year: with no year clause…").
- **`/parse`'s report has to be kept across q changes, or STALE_CLAUSE never happens.** A new URL's parse is
  briefly missing; keeping the previous report lets `whyBlocked` refuse it as stale with the reducer's own
  wording. With no report at all, the same wording comes from probing the reducer with a clause read from
  another string (`controls.ts::staleOf`), so the message isn't restated.
- **Accessible names concatenate inline text without spaces.** `workshop<span sr-only>,</span><span>205</span>`
  is "workshop,205"; `{" "}` between the spans gives "workshop, 205 papers" (and `Track (default)`).
- **openapi-fetch percent-encodes path params**: `/papers/op%3Aiclr%3A…`; the API decodes it; the page
  decodes `params.id` defensively.
- **Smoke test against `op serve` on the local index** (production build, headless Chromium): toggling
  workshop pushed `(trust*) AND track:(datasets_benchmarks OR main OR position OR workshop)`, the banner
  moved track to "your limit applies", the live region said "Track: workshop included. 198 papers.",
  a year untick wrote `year:(1000..2022 OR 2024..9999)`, Next replaced the URL and focused "Results, page 2
  of 4", the paper page lit 17 spans; no console errors; no sideways scroll at 320 px.

## Dead ends — don't repeat these
- Calling the slot as a function (`results(slot)`), then as a props object `p.*`: both fail the compiler
  lint; don't try to silence it.
- The local corpus is pre-filtered (1,805 accepted papers), so every banner reads `excluded: none` there;
  include buttons and adds-0 wording are only exercised by the unit tests.

## Decisions (and what would change them)
- One DOM order for both widths: header, banner and Limits before the sidebar (the design's order had the
  sidebar first). Reverse if TASK-046's keyboard walkthrough or TASK-047 finds it confusing.
- The paper status line says `ICLR 2024`, not the conference's full name, which only the backend knows.
  Reverse when the API sends a venue name. **Reversed by TASK-112** (2026-09-30): the API sends
  `PaperRecord.venue_name` and the line names the conference in full.

## Follow-ups
- [x] TASK-112: `PaperRecord.venue_name` (derived, never stored); the status line reads the full venue string.
- [ ] No separate copy task: review the new strings in TASK-047: "Type a four-digit year in both boxes, the
  earlier first.", "Page N is past the last page…", "No papers on page N…", "Admits …"/"Every year.",
  "Loading the paper…", "No provenance recorded."

## Propagated to
- Skill / agent / CLAUDE.md updated? — `.claude/skills/nextjs-conventions/SKILL.md` (layout, keys, stub `query`), `CLAUDE.md`, spec 05, the two design docs
- Test or hook added? — `frontend/src/components/search/search-view.test.tsx`, `exclusions.test.ts`, `frontend/src/components/paper/paper-view.test.tsx`, `frontend/src/lib/excerpt.test.ts`
