# Overflow scrolling does not contain a wide table unless layout and browser baselines are pinned

**Key lesson:** At 320 px, put wide tables in named focusable overflow regions with layout containment, wait for populated client data before axe or screenshot assertions, and pin Playwright, Chromium, the CI OS and platform-specific snapshot paths so each renderer has an honest baseline.

- **Date:** 2026-09-28 · **Task:** TASK-046 · **Area:** frontend
- **Artifacts:** `frontend/src/components/coverage/coverage-report.tsx`, `frontend/src/components/help/syntax-help.tsx`, `frontend/e2e/accessibility.spec.ts`, `frontend/playwright.config.ts`, `.github/workflows/e2e.yml`

## What we set out to do
Add an end-to-end browser suite for the spec 05 review flow, keyboard use, WCAG 2.2 AA checks, 320 px
reflow and light/dark visual regression, then run it against the production frontend and a deterministic
5,000-record API fixture.

## What we learned
- `overflow-x-auto` on the coverage table did not keep Chromium's root layout at 320 px: the table's
  intrinsic width still made the document wider than the viewport. Adding `contain-layout` to the scroll
  region (and `min-w-0` to its content wrapper) kept horizontal movement inside the region; the Playwright
  reflow assertion now checks `document.documentElement.scrollWidth <= clientWidth` on `/`, `/search`,
  `/coverage` and `/help/syntax` (`frontend/e2e/accessibility.spec.ts`).
- A scrollable table is usable by keyboard and screen-reader users only when it is itself reachable and
  named. The coverage and syntax tables therefore use `role="region"`, a specific `aria-label` and
  `tabIndex={0}` in addition to horizontal overflow (`coverage-report.tsx`, `syntax-help.tsx`).
- An axe scan can pass the wrong page state if it runs while React is still showing a loading shell. The
  suite waits for populated evidence—the result count on `/search` and the named table region on
  `/coverage`—before invoking `AxeBuilder` (`frontend/e2e/accessibility.spec.ts`).
- Visual snapshots are a browser-environment contract as well as a UI contract. TASK-046 pins
  `@playwright/test` 1.63.0 in `package-lock.json`, installs that package's Chromium in CI, pins every CI
  action by commit SHA, pins the Ubuntu runner, and retains the platform token in `snapshotPathTemplate`;
  otherwise a baseline generated on macOS is silently treated as Linux-authoritative despite different
  font rasterization
  (`frontend/playwright.config.ts`, `.github/workflows/e2e.yml`).

## Dead ends — don't repeat these
- Do not treat `overflow-x-auto` as proof that a wide table cannot widen the root. At 320 px, inspect the
  document's actual `scrollWidth` and verify that horizontal scrolling occurs only inside a named,
  focusable region.
- Do not start axe immediately after `page.goto()` or accept a visible static heading as readiness for a
  client-populated route. Wait for content that only exists after the relevant API request has rendered.
- Do not reuse one screenshot baseline across macOS and Linux. Keep platform-suffixed baselines, pin the
  Linux runner, and do not let the test package float independently of the installed browser.

## Decisions (and what would change them)
- Commit a reviewed baseline for each platform that intentionally runs the visual suite. CI's pinned Linux
  baseline is authoritative for the merge gate; the macOS baseline keeps local development useful.
- Allow a wide semantic data table to scroll inside its own accessible region while prohibiting root
  horizontal scrolling. Replace the table with a reflowed presentation only if its row/column
  relationships remain equally understandable.

## Follow-ups
- None; TASK-046's browser, accessibility and CI checks cover the discovered failures.

## Propagated to
- `.claude/skills/accessibility/SKILL.md` — table containment, named focusable scroll regions and
  data-bearing readiness before axe are now explicit requirements.
- `.claude/agents/e2e-tester.md` — exact Playwright/browser/runner pins and platform-specific visual
  snapshot paths are now part of the E2E workflow.
- Test added — `frontend/e2e/accessibility.spec.ts` enforces root reflow and scans populated client states;
  `frontend/e2e/visual.spec.ts` plus `frontend/playwright.config.ts` enforce both-theme baselines.

## Addendum — 2026-09-29 (TASK-134)
A local Docker image does not stand in for CI's Linux renderer either. Checked by rendering the unchanged
`/search?q=trust` page in `mcr.microsoft.com/playwright:v1.63.0-noble` on an Apple-silicon host and comparing it
with the committed `search-*-linux.png` (made on CI's `ubuntu-24.04` x86 runner):
- `--platform linux/arm64` (native): 1440×7672 against the baseline's 1440×7891, 6–9% of pixels different, over
  the 2% the config allows. Font metrics differ, so the whole page shifts.
- the default amd64 image under emulation: Chromium lays the pager out 33,554,432 px (2^25) tall and
  `Page.captureScreenshot` fails ("Unable to capture screenshot"); a full-page screenshot also needs `--ipc=host`.

**Dead end:** don't regenerate `*-linux.png` from a local container and commit it as the CI baseline. Take the
Linux baseline from the CI `e2e` run itself (its `playwright-report` artifact holds the actual screenshot) after
reviewing it, and commit only the macOS baseline locally. TASK-134 left the Linux baselines stale for that reason.

Propagated to: `.claude/agents/e2e-tester.md` step 5.
