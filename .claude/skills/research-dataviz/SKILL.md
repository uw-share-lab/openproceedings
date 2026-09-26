---
name: research-dataviz
description: Data-display standard for openproceedings — which form to use for coverage (venue × year × track), facet counts, PRISMA flow, exclusion breakdowns and drift diffs; tables before charts when precision matters; colour-blind-safe palettes (Okabe–Ito) in both themes; never colour alone; count axes start at zero; every display shows n, index_version and its source; numbers come from the API, never hard-coded. Use when building or reviewing any table, chart, count display, flow diagram or figure in frontend/ or docs/results.
---

# Research data visualization

## Rules that always apply
1. **Numbers come from the API or from an `op eval` output**, bound to a named field. No literal in JSX, no
   client recount. Allowed transforms are formatting (thousands separators, one-decimal `delta_pct`) and
   derived shares shown next to both operands.
2. **Tables before charts when the reader will cite a number.** A chart is added *next to* the table for
   pattern-finding, and never replaces it.
3. **Every display carries provenance:** n (or `total`), `index_version`, snapshot date where relevant,
   the source (`GET /coverage`, `coverage-sources.md` revision). A figure without its `index_version` is
   uncitable.
4. **Honest scales:** axes for counts start at 0. No truncated bars, no dual axes, no 3-D, no pies for
   more than two parts. Deltas are centred on 0. Log scales are labelled "log" and never used for counts
   a reviewer compares linearly.
5. **Exact values reachable:** every mark has a text value (label, tooltip *and* table). Charts have a
   keyboard-reachable data table and an accessible name that states the takeaway.
6. **Missing is not zero:** `no source`, `unknown` and `missing_abstract` get their own glyph or label.

## Form per display
| Display | Primary form | Optional chart | Notes |
|---|---|---|---|
| Coverage (`/coverage`, 07 §C) | Table per venue: year × track, indexed / official / `delta_pct` / gate ✓✗ / source | Dot plot of `delta_pct` per main-track cell with a shaded ±1% band | ✗ cells sorted first in a "failing" filter. `no source` is a fail, and is labelled |
| Facet counts (sidebar) | Count as text in the label (`workshop, 212`), `tabular-nums`, right-aligned | Thin inline bar, zero-based, scale shared within one facet | Disjunctive counts (04). Say so in the facet's help text |
| Exclusion breakdown | Inline text banner (`ui-design-system`) | none | Itemized buckets sum to `Σ excluded` exactly, overlap counted once (`prisma-reporting`) |
| PRISMA flow (record page, pending spec) | Box diagram (SVG, or Mermaid `flowchart TD` in docs) with n per box | — | Boxes and labels exactly per `prisma-reporting`. Near-misses never in "identified from databases" |
| Drift diff (`/records/{id}/diff`) | Summary `+added / −removed` then two lists with titles and ids | Small paired bar of the two counts, zero-based | Name both index versions. `mismatch` is an error panel, not a chart |
| Year trend of matches | Table, then a line or column chart of counts by year | — | Show the default filters in the caption, since they change the series |

## Palette (Okabe–Ito, colour-blind safe)
| Role | Hex | Pair with |
|---|---|---|
| primary series | `#0072B2` blue | — |
| comparison / official | `#E69F00` orange | dashed stroke or hollow marker |
| pass / within gate | `#009E73` green | ✓ glyph |
| fail / outside gate | `#D55E00` vermillion | ✗ glyph |
| accent | `#CC79A7` purple, `#56B4E9` sky | — |
| avoid for text | `#F0E442` yellow | only as fill with a dark outline |
Define these as CSS variables in both themes (`ui-design-system` tokens). Check contrast against both
backgrounds (≥3:1 for marks, ≥4.5:1 for text). Green/red meaning always also carries a glyph or label.
Categorical series ≤ 6. Beyond that, use a table or small multiples.

## Typography and layout
Numbers `tabular-nums`, right-aligned in tables. Units in headers, not cells. One decimal for
percentages, integers for counts, thousands separators. Titles state the finding ("3 of 18 main-track
cells miss the ±1% gate"), and the caption states n, `index_version` and the source.

## Testing
Vitest over a recorded API fixture. Playwright compares rendered values with a live API fetch, in
both themes at 360 px, and runs axe on chart pages. A snapshot of the chart's data table catches
silent rebinding.
