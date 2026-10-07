# A source page that mixes abstracts with personal data is cut by structure, then checked by content, and tested on every surface

**Key lesson:** When a page holds an abstract beside personal data (the ICML 1997/1998 submission forms), keep only the span a structural rule bounds (after the `Abstract` heading, before the form's next field), then check what is kept for contact details and withhold the whole abstract when one is found, never cut it out; and prove it with one test that runs the real path (ingest, replay, snapshot, index, every export format, raw log records) against a page full of invented contact details.

- **Date:** 2026-10-07 · **Task:** TASK-207 · **Area:** ingest
- **Artifacts:** `backend/src/openproceedings/ingest/sources/icml_sites.py` (`icml1997`, `icml1998_paper`, `contact_detail`), `ingest/icml_sites.toml`, `backend/tests/unit/ingest/test_icml_submissions.py`, `docs/research/2026-10-06-icml-pre-2013-abstract-sources.md`, decision-047

## What we set out to do
Use the ICML 1997 and 1998 official pages for abstracts (owner decision of 2026-10-07) without letting the authors'
addresses, e-mails or phone numbers reach anything we store or serve.

## What we learned
- **The form's layout varies by paper, but its order doesn't.** Title, authors and addresses, abstract, keywords,
  contact e-mail and phone: every one of the 49 + 66 submissions puts contact details before the abstract heading or
  after a later field label, so the span between them is clean. Four entries have no `Abstract` heading at all; there
  the author block and the abstract run together, and leaving them null is the only safe reading (evidence: running
  the parsers over the real captures; research doc §1997 and 1998).
- **A content check is a backstop, and its false positives must be read against real text.** The first phone pattern
  stopped `time t+1` (a `+` and a digit) and a digit-group rule took the year range `1993-1997` for a phone number.
  Both were found by running the parsers over every real page and listing abstracts that did not end with a period.
  A withhold is the safe failure; a stop inside an abstract silently truncates, so the final rule only withholds.
- **`caplog.text` hides what a leak would look like.** It holds only the message names, not the `extra` fields the
  JSON formatter writes, and the formatter scrubs; the privacy test reads every `LogRecord.__dict__` instead.
- **The shared HTTP layer would have refused most of these pages.** It retries a 200 without `</html>` as truncated,
  and 27 of the 66 1998 captures and the 1997 page never had one; the unit tests seeded the cache, so only the
  end-to-end test through a transport showed it (5 retries, then `RetriesExhausted`). A capture's bytes are fixed and
  the archive states their `Content-Length`, so captures are now judged whole by that length (`by_length`).
- **Some archive captures are under another spelling of the same site.** Five ICML-98 papers' earliest captures are
  at `/ICML98/`, with the same digests as `/icml98/`; one of them has no lower-case capture of that content, so the
  official-site list names both spellings.

## Dead ends — don't repeat these
- A lazy `<a name="N"></a>\s*<pre>(.*?)</pre>` read 46 of 49 1997 entries: three anchors carry a page range before
  the `<pre>`. Split on the anchors instead (`_segments`).
- The Internet Archive dropped many of a burst of capture requests that day; a plain retry a few seconds
  later always worked. Don't conclude a capture is gone from one failure.
- In a worktree-isolated session, a shell loop with variables or `awk -v` is refused; write a small script file and
  run it with literal paths.

## Decisions (and what would change them)
- Withhold the whole abstract on any contact detail, never cut it out → a cut guesses where the detail ends → an
  owner decision to accept partial abstracts.
- Exact title keys only, as for every other year (6 of 1997's and 14 of 1998's entries are retitled papers and stay
  unattached) → an owner decision to map retitled submissions by hand.

## Follow-ups
- [ ] none filed: the unattached retitled submissions follow the exact-key rule every year follows.

## Propagated to
- Skill / agent / CLAUDE.md updated? — `.claude/skills/logging-standards/SKILL.md` (`icml_site_year_read`'s
  `withheld` count); spec 01 §Sources and decision-047 state the rule.
- Test or hook added? — `backend/tests/unit/ingest/test_icml_submissions.py` (every surface, through a transport, both
  years), hostile-input rows in `test_icml_sites.py`, `test_fetch.py` (a capture judged by length).
