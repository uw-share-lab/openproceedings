---
id: decision-035
title: >-
  POST /compare is an operator-controlled capability with a per-network cooldown
  and no retained upload (TASK-177)
date: '2026-10-05 07:20'
status: accepted
---
## Context

A reviewer moving from Google Scholar asks what a query does to the records they already hold: which it keeps,
drops and adds. TASK-056 built that comparison for the project's own report (`op eval scholar`,
`eval/scholar_compare.py`); TASK-177 serves it to any user as `POST /api/v1/compare` and the search page's
"Compare with your records". That makes it the API's first route that takes a file from a stranger, and its
most expensive one: the classes are decided by the reference matcher, about 10 s of CPU per 1,000 records
(measured on index `05a0541717f6`: the review's 1,834-record, 3.7 MB export against its `$` string took 20 to
24 s; 51 kept, 1,756 dropped, 8 not in the index, 16 added).

Options considered:
1. CLI only. No upload surface, but the question is asked by people who will never run a checkout.
2. Always on, like `/export`. Every public instance would accept megabyte uploads and minute-long requests
   because the software shipped them.
3. On for a local instance, an operator's explicit choice anywhere else (chosen).

And for the request: a multipart upload with one request per export, or the file as the raw body with every
export in the one answer (chosen: Starlette's form parser spools parts over 1 MB to disk, and a second
request would re-upload the file and repeat the whole comparison, or force the server to keep something).

The security review (2026-10-05) found that token buckets alone do not bound the one comparison slot: a
network's bucket refills four times as fast as a client's, so three addresses of one /24, or three /64s of
one IPv6 /48, held the slot 100% of the time.

## Decision

1. **Operator-controlled.** `ApiConfig.compare_enabled` is off by default. `op serve` turns it on for a
   loopback `--host` with no `--trusted-proxy`, or with `--compare`; `--no-compare` turns it off. Off, the
   route answers 403 `API_COMPARE_DISABLED` as its first act, `/meta` `limits.compare` is null (the web app
   then offers nothing), no match table is built, and the path reads no body over `max_body_bytes`.
2. **No retained upload.** The file is the raw request body (`application/x-research-info-systems`, UTF-8; no
   form, no content encoding), read into memory for that one request and released once decoded. It is never
   written to disk, stored, logged (the access line carries counts only), cached between requests, or added
   to the index, a search record or an export. One answer carries everything a later click needs (the lists,
   each as CSV text, the added papers as RIS), because nothing is kept to answer a second request from.
3. **What is echoed.** To the client that sent the file, and nothing else of it: each record's title, its
   venue string, and in the evidence of a record the index doesn't hold, the host names of at most three of
   its links (valid DNS host names only). No refusal quotes the file. The lists hold no abstract; the added
   papers' RIS holds what `/export` serves for those hits, withheld abstracts left out (decision-022).
4. **Caps**, stated in `/meta` `limits.compare`, each a typed refusal, nothing cut: 16 MiB body (as it
   arrives), 5,000 records, 64 lines per allowed record, 32,768 characters a line, 1,000 a title or venue
   line, 5,000 papers of the result that the file lacks, a 16 MiB answer, 60 s of work (checked per record
   and per row), 30 s for the file to arrive, one comparison at a time.
5. **Cost and the per-network cooldown.** The request costs `export_weight` and its query's verified charge
   like an export (decision-010), and the slot time is debited afterwards at one token per 500 ms, the
   upload's wall time counted four times. The bound on the slot is a cooldown: a client network (IPv4 /24,
   IPv6 /48) runs one comparison at a time, and after one starts no other for three times the slot time it
   used (upload time counted four times). One network therefore holds a slot at most 25% of the time with
   comparisons back to back and 7.7% with uploads that stall, whatever number of addresses it uses. The
   token price stays at 500 ms rather than the verification slot's 100 ms: at 100 one ordinary comparison
   would lock a reviewer out of search for minutes, and the cooldown already bounds the slot.
6. **The match table** (each index record's merge keys; 13 to 15 s and about 80 MB for 95,877 records) is
   built once per served index after the swap and lives on the served bundle, so a hot swap cannot pair one
   index's result with another's table; a failed build is retried on every reload.

## Consequences

- `POST /compare` never changes a search: its result is `engine.match_ids` of the query, the set `/search`
  counts (guarantee 5), and the same query, `index_version` and file give the same bytes. It never counts
  concept groups or facets (decision-034's work is `/search`'s alone).
- **Stated limits.** Many distinct networks together can still fill the slot: comparisons are then refused
  (503) while searches are not; the cooldown bounds one network, not a crowd. With the rate limit off
  (`--no-rate-limit`, loopback only) there is no cooldown and no debit: only the slot, the caps and the time
  limit bound a comparison. A reviewer waits about three times a comparison's length before the next one
  from the same network (54 s after 18 s), a whole lab behind one /24 included.
- **Before any public instance enables comparisons**, the proxy block in `deploy/README.md` (a 16MB body and
  buffer for `/api/v1/compare` only) must pass `deploy/smoke-test.sh` on that stack. It is written from
  Caddy's documentation and has not been run; it is what keeps a slow upload off the API's slot. A loopback
  bind behind a same-host proxy must pass `--trusted-proxy` or `--no-compare`, or it takes itself for a local
  instance.
- The comparison's classes and matching are the report's (spec 07 §B): a change to either changes both. The
  inflection-only stand-in for Scholar's stemmer is decision-038's.
- Turning the capability on costs an instance about 80 MB for the table and up to a minute of CPU per
  comparison, during which searches are slower.
- Not decided here: `op serve` flags for the caps, the cooldown factor and the upload weight (only
  `--compare` exists); matching on DOI for files from other databases; a class of its own for a file's paper
  outside the query's own `year:` or `venue:` limit (today `full_text`).
- Pinned by `backend/tests/contract/test_compare.py` and `test_compare_review.py` (the cooldown's shares are
  a simulation with the real buckets at their defaults); spec 04 §Comparing with a RIS file, spec 08 §Deploy.
