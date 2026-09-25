---
name: ui-design-system
description: The openproceedings visual standard — Tailwind + shadcn/ui tokens for light and dark, the /search layout from spec 05, venue/year/track badges, the exclusion banner, expansion chips, diagnostics row, highlight styling, and the research-tool tone (dense, precise, numbers first, no marketing). Use when building or reviewing any frontend component or page, choosing a colour or copy string, or judging whether a warning, exclusion or expansion is visible enough.
---

# UI design system

## Tone
A research instrument. Dense, precise, quiet. No hero sections, no illustrations, no "Discover
papers!" copy, no emoji. Numbers are the content: `tabular-nums`, exact counts (never "400+"), units
named. Query strings, canonical strings, `index_version` and hashes are **monospace** and copyable.

## Tokens (CSS variables on `:root` and `.dark`, shadcn naming)
Base shadcn set: `--background --foreground --muted --muted-foreground --border --ring --primary
--destructive --popover --card`. Project semantic tokens (define both themes, check contrast ≥4.5:1 for
text, ≥3:1 for borders/icons):
| Token | Use |
|---|---|
| `--hl-bg`, `--hl-fg` | query-term highlights (plus bold, never colour alone) |
| `--warn-*` | parse warnings, translations notices |
| `--excluded-*` | exclusion banner |
| `--default-clause` | default filters shown grey in the tree ("made explicit") |
| `--track-workshop` | the workshop badge, visibly distinct from main |
Theme via class on `<html>` (`next-themes` or equivalent); no flash on load; both themes are
first-class and both are in visual regression.

## `/search` layout (spec 05)
Top to bottom, left to right: `[Text | Builder]` toggle, `mode` select, `Search` → editor → diagnostics
row → expansion chips → (sidebar | results). Sidebar: Venue, Year range, Track, Status, each option with
its **facet count**; workshop unchecked by default. Results header: `412 papers · index a1b2c3 ·`
exclusion banner · `[Export ▾]` `[Save search record]`. At <768 px the sidebar collapses behind a
"Filters (n active)" button above the results; nothing is hidden without a count.

## Transparency components (guarantee 6 — each is always rendered)
- **Diagnostics row:** every warning and translation from the response, server wording verbatim, with
  `[show tree]` for mixed AND/OR. Zero warnings → row absent, not "No warnings".
- **Expansion chips:** one chip per wildcard: `trustworth* → trustworthy, trustworthiness`. Long lists
  show the first ~8 plus `+N more` which expands inline to the full list. Never truncate without `+N`.
- **Exclusion banner:** `excluded: 212 workshop · 4 competition · 88 rejected`, each with `[include ▸]`
  that rewrites `q`. Shown even when every count is 0 (`excluded: none`), because "nothing excluded" is
  also a reportable fact. An info disclosure explains the PRISMA mapping ("removed before screening").
- **"How we read your query":** collapsible AST tree; default clauses in `--default-clause` with a
  `default` label (text, not only grey).

## Badges (shadcn `Badge`, outline variant)
`ICML` `2024` `main` `poster` in that order. Track badge text is the taxonomy value from `/meta`
(`datasets_benchmarks` displayed as `D&B` with the full name in `title`/accessible name). Status badge
only when not `accepted`.

## Result item
Title (link to `/paper/[id]`) with highlights → badges → abstract excerpt with highlights → links
(OpenReview · PDF · proceedings). Highlights are `<mark>` with bold + `--hl-*`; spans come from the API.

## Copy rules
Say what happened, with the number: "412 papers match". Errors quote the server message and hint. Methods
text follows spec 05 §8 exactly; don't paraphrase it.
