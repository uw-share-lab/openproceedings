# Overflow scrolling does not contain a wide table unless layout and browser baselines are pinned

**Key lesson:** At 320 px, put wide tables in named focusable overflow regions with layout containment, wait for populated client data before axe or screenshot assertions, and pin Playwright, Chromium and platform-neutral snapshot paths so local and CI exercise the same browser contract.

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
  action by commit SHA, and removes the platform token from `snapshotPathTemplate`; otherwise a baseline
  generated locally can have a different filename or rendering environment on the Linux runner
  (`frontend/playwright.config.ts`, `.github/workflows/e2e.yml`).

## Dead ends — don't repeat these
- Do not treat `overflow-x-auto` as proof that a wide table cannot widen the root. At 320 px, inspect the
  document's actual `scrollWidth` and verify that horizontal scrolling occurs only inside a named,
  focusable region.
- Do not start axe immediately after `page.goto()` or accept a visible static heading as readiness for a
  client-populated route. Wait for content that only exists after the relevant API request has rendered.
- Do not accept Playwright's default platform-suffixed screenshot path when one committed baseline must
  run on macOS and Linux, and do not let the test package float independently of the installed browser.

## Decisions (and what would change them)
- Commit one platform-neutral baseline per visual case and tolerate only the suite's bounded pixel ratio.
  Split baselines by platform only if verified, unavoidable renderer differences exceed that bound and
  each platform remains an intentional CI target.
- Allow a wide semantic data table to scroll inside its own accessible region while prohibiting root
  horizontal scrolling. Replace the table with a reflowed presentation only if its row/column
  relationships remain equally understandable.

## Follow-ups
- None; TASK-046's browser, accessibility and CI checks cover the discovered failures.

## Propagated to
- `.claude/skills/accessibility/SKILL.md` — table containment, named focusable scroll regions and
  data-bearing readiness before axe are now explicit requirements.
- `.claude/agents/e2e-tester.md` — exact Playwright/browser pins and platform-neutral visual snapshot
  paths are now part of the E2E workflow.
- Test added — `frontend/e2e/accessibility.spec.ts` enforces root reflow and scans populated client states;
  `frontend/e2e/visual.spec.ts` plus `frontend/playwright.config.ts` enforce both-theme baselines.
