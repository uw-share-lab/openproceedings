"""The M4 crawlers (spec 01 §Sources, §Pipeline 1): one module per source. Each fetches into
`<data-dir>/cache/<source>/`, never into snapshots or indexes; `op snapshot build` replays the cache offline.
The proceedings miners (`neurips`, `pmlr`) fetch through `http`; the OpenReview v2 crawler through
`openreview_client`."""
