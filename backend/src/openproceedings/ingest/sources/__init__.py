"""Crawlers (spec 01 §Sources, §Pipeline 1): each fetches one source into `<data-dir>/cache/<source>/`, never
into snapshots or indexes. `op snapshot build` replays the cache offline."""
