"""The M4 crawlers (spec 01 §Sources, §Pipeline 1): one module per source. Each fetches into
`<data-dir>/cache/<source>/`, never into snapshots or indexes; `op snapshot build` replays the cache offline.
Every crawler fetches through the one HTTP layer, `http` (the OpenReview crawlers through `openreview_client`,
its login and policy on top); `common` holds the shared report, crawl markers and replay."""
