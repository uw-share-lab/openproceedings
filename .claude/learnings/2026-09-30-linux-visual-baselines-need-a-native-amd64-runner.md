# Linux visual baselines can't be regenerated on an Apple-silicon Mac

**Key lesson:** Don't regenerate the Linux Playwright baselines on an arm64 Mac: the arm64 image renders differently from CI, and the amd64 image under emulation can't build Next or capture a screenshot. Keep build-configured text out of the /search screenshot (hide it in `e2e/visual.css` and assert it in its own test), or regenerate the Linux baselines on an amd64 host.

- **Date:** 2026-09-30 · **Task:** TASK-133 · **Area:** frontend
- **Artifacts:** `frontend/e2e/visual.css`, `frontend/e2e/accessibility.spec.ts`, `frontend/e2e/__screenshots__/`

## What we set out to do
Add a site-wide footer (the takedown contact) without breaking the full-page `/search` visual baselines, which
exist per platform (`search-*-darwin.png`, `search-*-linux.png`; CI compares the Linux ones on `ubuntu-24.04`).

## What we learned
- The footer made the page taller, so both baselines failed on size. The darwin pair regenerates locally with
  `npx playwright test e2e/visual.spec.ts --update-snapshots`.
- `mcr.microsoft.com/playwright:v1.63.0-noble` pulled on an Apple-silicon Mac can be arm64 or amd64. The arm64
  image runs, but its screenshots differ from the committed Linux baseline over about 9% of the pixels above
  the footer, and the page comes out a different height: it's a different renderer from CI's.
- Under `--platform linux/amd64` (QEMU), `next build` fails with `ERR_WORKER_INVALID_EXEC_ARGV`
  ("--no-opt is not allowed in NODE_OPTIONS": the emulated node is started with `--no-opt`, which Next's
  workers pass on). Building `.next` in the arm64 image and serving it in the amd64 one gets past that, but then
  Chromium fails `Page.captureScreenshot` ("Unable to capture screenshot").
- The footer's text depends on `NEXT_PUBLIC_TAKEDOWN_CONTACT` at build time, so it doesn't belong in a pixel
  baseline anyway. Hiding `body > footer` in `e2e/visual.css` kept both existing baselines valid, and
  `accessibility.spec.ts` asserts the footer on each page.

## Dead ends — don't repeat these
- Don't commit a `*-linux.png` taken from the arm64 Playwright image: it would fail CI's amd64 comparison.
- Don't try the amd64 image under emulation: first the Next build fails, then screenshot capture does.

## Decisions (and what would change them)
- Chrome that shows build-configured or per-deployment text is hidden from the visual baselines and asserted
  functionally. Revisit this if an amd64 host (or a CI job that uploads fresh baselines) becomes available for
  regenerating them.

## Follow-ups
- None.

## Propagated to
- Test added: `frontend/e2e/visual.css` hides the footer; `frontend/e2e/accessibility.spec.ts` checks it on
  the home, search, paper and coverage pages.
