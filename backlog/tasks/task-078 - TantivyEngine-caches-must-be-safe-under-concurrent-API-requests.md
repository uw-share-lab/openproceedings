---
id: TASK-078
title: TantivyEngine caches must be safe under concurrent API requests
status: To Do
assignee: []
created_date: '2026-09-27 07:20'
labels:
  - api
  - engine
milestone: m-3
dependencies:
  - TASK-034
ordinal: 76000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found in task-034. The API serves one TantivyEngine to every request, and sync handlers run in FastAPI's thread pool, so its per-engine caches are touched concurrently. Two check-then-read sites can raise KeyError (a 500) when another thread clears the cache in between: engine/tantivy_engine.py compile() ('if key in self.compiled: return self._copy(self.compiled[key])' vs the clear() at >1,000 entries) and engine/compile.py verified() ('if key not in self.verified_cache: ... ; ids = self.verified_cache[key]' vs TantivyEngine.compile's self.verified.clear()). expand() has the same shape with self.expanded. Fix with a single .get() read (or a lock) and add a threaded test. Must land before task-035's routes serve traffic.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 No cache read in TantivyEngine/Compiler can observe a key vanish between check and read (single .get() or a lock)
- [ ] #2 A test runs many searches from several threads against one engine while the caches are forced to clear, with no exception and identical results to a serial run
<!-- AC:END -->
