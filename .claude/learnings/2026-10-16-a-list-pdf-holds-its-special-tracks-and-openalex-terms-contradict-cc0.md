# A "main track" list PDF held its special track, and OpenAlex's terms contradict its CC0 page

**Key lesson:** Read the whole list document and every Wayback capture of its URL before citing a count, and read a data source's terms of service, not just its help page, before relying on a licence.

- **Date:** 2026-10-16 · **Task:** task-234, task-235, task-236 · **Area:** eval
- **Artifacts:** `backend/src/openproceedings/eval/openalex_audit.py` (`library_check`), `docs/results/2026-10-16-openalex-audit.md`, `docs/results/coverage-sources.md` (AAAI 2021 row), `docs/research/2026-10-09-aaai-aies-facct-iaseai-sources.md` (§OpenAlex Licence, §Official counts, §Sources checked)

## What we set out to do
Find where the AAAI 2021 gate row's 40 AI for Social Impact papers were counted, measure OpenAlex against `aaai_library`'s AAAI 1980–2008 abstracts, and record the OpenAlex licence pages' and aaai.org robots.txt's exact URLs and read dates.

## What we learned
- The 40 were never on a separate list: the cited "AAAI-21 Accepted Papers — Main Technical Track" PDF says on page 1 that the AI for Social Impact list "appears at the end of this document", and its last section (pp. 121–124) has exactly 40 entries; 1,656 come before it (evidence: `pdftotext` of the 2023-09-29 `id_` capture, entries counted by their `N:` numbers).
- The Wayback CDX `digest` is the file's base32 SHA-1, so captures can be matched to a local download. The cited copy (`SOFX7…`) is first captured on 2021-11-10, after the proceedings. An earlier copy at the pre-migration path `Conferences/AAAI-21/wp-content/uploads/2020/12/` (`DZJN…`, captured 2020-12-30) predates the conference and differs by one main paper (7140). Without the CDX listing of the old path, the list could not be shown to predate the proceedings.
- To measure a fallback where a higher-ranked source already filled the field, replay the fill twice: as the records stand, and with that source's abstracts and claims removed. Then subtract the first run's refusal counter from the second's. One record's outcome doesn't depend on another's abstract (the fill's ambiguity count runs over every DOI-less record either way), so the difference is exactly the set-aside records' outcomes.
- OpenAlex against AAAI's own text, AAAI 1980–2008: 51.6% exact or near-exact of 1,131, against 99.3% for AAAI 2010+ by DOI. Many `similar` cases differ only in OCR and hyphenation, and `differs` peaks in 1994–2002.
- OpenAlex's terms of service (https://openalex.org/OpenAlex_termsofservice.pdf, revised 2026-10-02) cover the API by name. They grant a "freely revocable, limited license" and forbid republishing the Data without "prior written consent". The Pricing page (https://help.openalex.org/access/pricing/) still says CC0. openalex.org pages are a JavaScript app: their content and PDF links are in the route's `_nuxt` chunk, and help.openalex.org pages have `.md` siblings.

## Dead ends — don't repeat these
- `help.openalex.org/pricing` and `help.openalex.org/terms` are 404s, and plain-HTML fetches of `openalex.org/terms` return only the app shell. `https://help.openalex.org/llms.txt` indexes every help page.
- Grepping `pdftotext` output for `^Special` failed because of the layout spacing; a Python regex with `\s+` found the heading.

## Decisions (and what would change them)
- The AAAI 2021 row keeps the cited copy's 1,696 (it is independent because its count differs from the proceedings) and names the earlier copy. If the owner prefers the pre-proceedings copy, the row becomes 1,697 (Δ −3, 0.18%), which still passes.
- The OpenAlex terms/CC0 conflict is recorded, not acted on. Whether OpenAlex stays the decision-049 fallback is an owner decision.

## Follow-ups
- [ ] Owner decision on OpenAlex's terms of service against its CC0 statement (reported to the lead; the lead files it).
- [ ] Owner choice of the AAAI 2021 row's copy: the cited 1,696, or the pre-proceedings 1,697 (reported to the lead).

## Propagated to
- Skill / agent / CLAUDE.md updated? `.claude/skills/coverage-reporting/SKILL.md` (count the whole cited document; date a list from every CDX capture of its URL and its pre-migration path) and `.claude/skills/logging-standards/SKILL.md` (`library_compared`).
- Test or hook added? `backend/tests/unit/eval/test_openalex_audit.py` (`library_check`, its section, the offline rerun, the command).
