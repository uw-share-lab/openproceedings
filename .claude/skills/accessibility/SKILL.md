---
name: accessibility
description: The WCAG 2.2 AA checklist tailored to openproceedings — keyboard-only flows through the CodeMirror editor, the concept-group builder and the results, focus management for the Text/Builder toggle, non-colour highlights, live announcements for diagnostics and counts, axe-core in Playwright, and the 320/360 px reflow requirement. Use when building or auditing any frontend component, writing Playwright a11y checks, or reviewing a frontend/** diff.
---

# Accessibility (WCAG 2.2 AA, spec 05 §Non-functional)

## Keyboard flows that must work end to end
1. **Editor:** Tab into CodeMirror, type, `Ctrl-Space` completion (arrow + Enter to pick, Esc to close),
   Enter submits. **Tab leaves the editor** — never bind `indentWithTab` (2.1.2 No Keyboard Trap).
   Editor has an accessible name ("Query") and `aria-describedby` pointing at the diagnostics row.
2. **Diagnostics:** the summary ("1 error, 2 warnings") is in a polite `aria-live` region, updated after
   the debounced `/parse`, not per keystroke. Each squiggle's message is reachable without a mouse
   (`@codemirror/lint` panel via `Mod-Shift-m`, and the diagnostics row as plain text).
3. **Text/Builder toggle:** a tab pattern (`role=tablist`, arrow keys) or a two-button toggle group with
   `aria-pressed`. On switch, focus moves to the first control of the new panel; if the builder is
   read-only ("too complex for the builder"), focus moves to that notice, which says why and how to go
   back. Switching never loses the query.
4. **Builder:** add/remove row and term, change field scope, reorder by buttons (no drag-only action —
   2.5.7 Dragging Movements). After removing a row, focus goes to the previous row, not to `<body>`.
5. **Sidebar and banner:** real checkboxes/inputs with labels that include the count ("workshop, 212").
   `[include ▸]` is a button whose name says what it includes. After a facet rewrites `q`, announce the
   new total in the live region.
6. **Results:** heading per hit (`h3`), links distinguishable, pagination/infinite scroll reachable by
   keyboard with a "Load more" button (no scroll-only loading).

## Checklist
| SC | Here |
|---|---|
| 1.4.1 Use of Color | highlights = `<mark>` + bold (or underline); operators bold; workshop badge has text |
| 1.4.3 / 1.4.11 Contrast | text ≥4.5:1, UI borders/focus/icons ≥3:1, **both themes**, incl. highlight + squiggles |
| 1.4.10 Reflow | no 2-D scroll at **320 CSS px** (WCAG) — spec 05 says 360; test both. Long canonical strings wrap (`break-all` in mono blocks) |
| 1.4.13 Content on Hover | PRISMA tooltip dismissible (Esc), hoverable, persistent; prefer a disclosure button |
| 2.4.3 / 2.4.7 Focus | logical order: toggle → mode → editor → Search → diagnostics → sidebar → results; visible ring |
| 2.4.11 Focus Not Obscured | sticky header/toolbar must not cover the focused hit |
| 2.5.8 Target Size | ≥24×24 px for chip, badge-link, checkbox, `+N more` |
| 3.3.1 / 3.3.3 Errors | server error + fix hint in text, tied to the editor |
| 4.1.2 / 4.1.3 | names/roles on custom controls; status messages via live region |
| 3.2.2 On Input | typing never navigates; only submit changes the URL |

## axe-core in Playwright
`@axe-core/playwright`: `new AxeBuilder({ page }).withTags(["wcag2a","wcag2aa","wcag21a","wcag21aa","wcag22aa"]).analyze()`
on `/`, `/search` (with results, with a parse error, builder open, read-only builder), `/paper/[id]`,
`/record/[id]`, `/coverage`, `/help/syntax`, in **both themes** and at 320 px. Zero violations; any
`exclude()` needs a written reason in the test. axe misses most keyboard and live-region issues, so the
keyboard flows above are separate Playwright tests using `page.keyboard` only.
