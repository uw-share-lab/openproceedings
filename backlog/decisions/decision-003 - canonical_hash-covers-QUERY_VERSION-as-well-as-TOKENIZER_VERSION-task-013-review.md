---
id: decision-003
title: >-
  canonical_hash covers QUERY_VERSION as well as TOKENIZER_VERSION (task-013
  review)
date: '2026-09-26 03:09'
status: accepted
---
## Context

Spec 02 defined `canonical_hash = sha256(canonical + TOKENIZER_VERSION)`. The review of task-013 pointed
out that a `QUERY_VERSION` bump (a parser, compiler, default-filter or alias-table change) can make the same
canonical string mean something else, yet it would keep the same hash. The RIS/BibTeX provenance line
(`N1` / `note`) carries only `index_version` and `canonical_hash`, so an exported file could not tell the
two meanings apart.

## Decision

`canonical_hash = sha256(canonical + "\0" + TOKENIZER_VERSION + "\0" + QUERY_VERSION)` (UTF-8). The NUL
separators keep the three parts unambiguous.

## Consequences

- Every version that can change what a query means is in the hash. Two hashes are equal only if the
  string and both versions are, so export provenance stays sufficient.
- Bumping either version changes every hash. That is intended: a search record's replay reports the
  change as a version difference, never as a silent match.
- Nothing has been released, so no stored record changes.
