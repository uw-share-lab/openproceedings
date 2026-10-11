# New venues, milestone C (OpenAlex abstract fill for AAAI, AIES and FAccT; `abstract_kind`; index schema 4): implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task by task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** For AAAI, AIES and FAccT records that still have no abstract after every official source, fill the abstract from OpenAlex. Label each record's abstract origin with a derived `abstract_kind` (`official` | `openalex` | `none`), make it filterable (`abstract_kind:`) and facetable on index schema 4, and show and count it in the API, exports, `/coverage` and the frontend. Also: measure OpenAlex against the official abstracts, rebuild the snapshot and index, and re-run the coverage gate and the benchmarks.

**Architecture:**
- **Record.** `abstract_kind` is a derived field computed like `venue_name`. It is never stored and never hashed, and it is read from the abstract's claims.
- **Source.** `sources/openalex.py` does two things, both through the shared HTTP layer:
  - it looks up DOIs in batches of 50;
  - for DOI-less dblp AAAI records, it reads OpenAlex's per-year work listings of the AAAI proceedings sources that `ingest/openalex_sources.toml` names, matching by exact title key with exactly one candidate.
- **Extract.** A crawl writes a content-addressed extract (`<cache>/openalex/extract/<sha256>.json`). A marker names that extract.
- **Fill.** `op snapshot build` replays the extract with no network, as a **post-dedup fill** (after reconcile, before takedowns). This is not a `crawl.SOURCES` crawl, so OpenAlex can only touch a record whose resolved abstract is still `null`.
- **Index.** Index schema 4 adds a raw fast field `abstract_kind`. Facets and the combination aggregation (`COMBO`) become per engine, read from `SchemaForm`. A schema-3 engine refuses a query naming the field with a 422 (`FIELD_NOT_INDEXED`). Schema 2 is retired first, so at most two schemas are served (3 and 4).

**Tech Stack:** Python 3.12, pydantic v2, tantivy-py 0.26.2, stdlib `json`/`difflib`/`tomllib`, pytest + hypothesis, uv. Frontend: Next.js/TypeScript, Vitest, Playwright. No new dependency.

**Spec:** `docs/plans/2026-10-09-new-venues-design.md` is binding; read §Data model's abstract-precedence bullets and §Sources 6. Builds on milestone B (`.superpowers/sdd/milestone-b-plan-draft.md`, with the rulings in `milestone-b-rulings.md`): sources `crossref`/`facct_site`, `doi-` ids, AAAI `dblp-` ids, record schema 7, `Fetcher(user_agent=…)`. Repo rules: `CLAUDE.md`, `.claude/skills/index-versioning/SKILL.md`, `.claude/skills/api-contract/SKILL.md`.

## Controller rulings (binding; override the planner decisions and task text below where they conflict)

- All planner decisions below are accepted (controller, 2026-10-10).
- **Milestones A and B are merged** (PR #130 and PR #131, dev `fd2da91b`). The as-merged code differs in places from the
  B plan draft this plan was written against, so read the merged code by name, not by line numbers. Points to know:
  - `sources/crossref.py`, `sources/facct_site.py`, `acm_table.py`, `dblp_aaai.py`, `ojs_harvest.py` exist.
  - `dedup.attribution` credits `ojs`, `crossref` and `facct_site` abstracts to `urls.proceedings`.
  - `record.py` is at schema 7, with `DBLP_YEARS` and `DOI_YEARS` per venue. A `doi-` id must name its own venue-year's
    table row.
  - dedup repeats the forum link and steps 2 and 3 until a pass merges nothing.
  - `crawl.SOURCES` ends `…, OJS, DBLP_AAAI, CROSSREF`.
  - `takedowns.global_native` scopes dblp ids by venue, and `snapshot.diff` keys rekeys by it.
- **Schema-2 retirement prerequisite (Task 1):** the controller ran `op index retire <v> --dry-run` on 05a0541717f6,
  6508b8cf66ff, a7cfd04b656f and c76d7f26ee06 on 2026-10-10. All four are schema 2 with 0 pins, and there is no
  `data/records/` store. Task 1 may drop schema 2 from the code. The actual `op index retire` (deleting the
  directories) in Task 15 is irreversible, so it is confirmed with the owner first.
- **AAAI 1980–2008 records have no DOIs.** The OpenAlex title route is the only route for them.
- **The real counts as built:** AAAI 1980–2008 has 4,730 records over 23 held years (AAAI was also not held in 1995).
  FAccT has 1,230 records. AIES 2018–2023 has 575. 141 short AIES entries sit in `main` (TASK-224).
- **No contact address is sent to OpenAlex** (the planner decision stands). Never write any personal address in a tracked
  file.
- **e2e runs on `OP_E2E_API_PORT=8100 OP_E2E_WEB_PORT=3100`** (the owner's dev servers hold :8000 and :3000).
- **Never use `git stash`.** Verify anything "pre-existing" in a detached temporary worktree. When a Hypothesis test fails
  only locally, pin its stored falsifying example as an explicit `@example` before judging it.

## Planner decisions (where the spec is silent or the lessons override it; for the controller to rule on)

**Where the fill runs and what it may touch**
- Planner decision: the OpenAlex fill runs **after dedup and reconcile, before `withhold`**, inside `snapshot.build` (`openalex.apply(result, cache)`). It is not a `crawl.SOURCES` member.
  - It only ever sees resolved records whose `abstract is None` and whose venue is AAAI, AIES or FAccT.
  - It cannot overwrite an official abstract, and it never sees NeurIPS, ICLR or ICML.
  - A takedown still withholds a filled abstract, because `withhold` runs after the fill.
- Planner decision: two guards back this up.
  - `openalex` is the **last** text source in `dedup._TEXT`, after `ris`: any other claim holding an abstract wins.
  - The record model refuses an `openalex` claim on any field but `abstract`, or on a venue outside `record.OPENALEX_VENUES = {"AAAI", "AIES", "FAccT"}`. IASEAI is not in it: its abstracts are all official.
- Planner decision: `RECORD_SCHEMA_VERSION` goes `"7"` → `"8"` (new `Source` value `openalex`; the derived `abstract_kind`).

**`abstract_kind`**
- Planner decision: `record.abstract_kind_of(abstract, abstract_claims)` is the one rule, and it needs no precedence. The result is:
  - `none` when there is no abstract;
  - `openalex` when at least one claim holds the abstract's exact text and every such claim is `openalex`;
  - `official` otherwise, including a fixture with no provenance.
  - Every reader uses it: `PaperRecord.abstract_kind`, the snapshot reader's counts, and the index build.
- Planner decision: `abstract_kind` is an **open** enum (`api/openapi.py` `OPEN_ENUMS["abstract kind"]`). A later fallback source would add a value.
- Planner decision: `abstract_kind` is appended **last** to `FilterField`, so the canonical filter order becomes venue, year, track, status, abstract_kind. It is also inserted before `source` in `vocab.QUERY_FILTER_FIELDS`. It has no default filter.
- Planner decision: **no `QUERY_VERSION` bump.** A query naming `abstract_kind:` was a `FIELD_UNKNOWN` error before, so no query that parsed changes meaning or canonical form. The parse goldens pin that existing canonicals are unchanged.
- Planner decision: hits and exports read `abstract_kind` from the index's display record.
  - On schema 4 it comes from the stored fast field.
  - On a schema-3 index it is derived from the stored abstract (`none`/`official`). That is exact because a schema-3 build now refuses a record whose kind is `openalex` (`IndexBuildError`), so no schema-3 index can hold one.

**Index schema 4 and schema retirement**
- Planner decision: **schema 2 is retired first (Task 1).**
  - The real data dir has four schema-2 indexes (`05a0541717f6`, `6508b8cf66ff`, `a7cfd04b656f`, `c76d7f26ee06`) and no `data/records/` store, so nothing pins them.
  - The controller confirms this with `op index retire --dry-run` on each before Task 1 merges, and retires them in Task 15.
  - `SchemaForm.ord_indexed`, the text-`id` term-set path and their tests are deleted, as the skill requires.
  - Tokenizer "2" stays served, since it is independent of schema.
- Planner decision: `SchemaForm(abstract_kind: bool)`, with `SERVED_SCHEMAS = {"3": SchemaForm(False), "4": SchemaForm(True)}`.
  - Each engine has `facet_fields` and `combo`: `("venue", "year", "track", "status")`, plus `"abstract_kind"` on schema 4.
  - The module constant `COMBO` is schema 4's.
  - `TantivyEngine.MAX_FACET_COMBOS` triples, 100_000 → 300_000.
- Planner decision: a query naming `abstract_kind:` on a schema-3 engine raises `EngineInputError(DiagnosticCode.FIELD_NOT_INDEXED)`, an HTTP 422, from one `TantivyEngine.admit(ast)`. It is called by `compile`, `facets`, `counts` and `candidates`, so `/search`, `/export?index_version=…`, `/papers?q=` and record saves all refuse alike. It is never a 500.
- Planner decision: `Facets.abstract_kind` is `dict[str, int] | null`: null on a schema-3 index, which has no such field. That is not "no records". The sidebar hides the Abstract fieldset when it is null.

**OpenAlex crawl, extract and replay**
- Planner decision: the extract is **content-addressed and pinned by a marker**.
  - Layout: `<cache>/openalex/extract/<sha256 of its bytes>.json`, with marker `<cache>/openalex/crawls/openalex.json` = `{"source": "openalex", "format": "1", "extract": "<sha256>"}`.
  - The replay reads exactly the extract the marker names and re-hashes it (a mismatch is `CrawlError` `extract_changed`).
  - A new crawl writes a new extract and replaces the marker atomically. Old extracts are never rewritten.
- Planner decision: the extract holds each lookup's raw OpenAlex answer: work id, DOI, title, year, source ids, the raw `abstract_inverted_index`, and the fetch time.
  - The rebuild, hygiene and match rules run **at replay**, so a rule fix needs no refetch and the audit reads the same data.
  - The crawl's pages also sit in the ordinary `PageCache` (`<cache>/openalex/pages/`).
- Planner decision: there are two lookup routes, and no fuzzy match on either.
  - (a) A record with a DOI is looked up by DOI only, in batches of ≤ 50 sorted DOIs (`filter=doi:a|b|…`).
  - (b) A DOI-less record (dblp AAAI 1980–2008) is matched in the year's OpenAlex listing of the source ids `openalex_sources.toml` names for that venue-year, by exact `dedup.title_key`. It is attached only when exactly one listed work and exactly one DOI-less record of that venue-year share the key.
  - A listing's work count must equal both `meta.count` and the table's verified `works`, or the crawl stops (`count_mismatch`).
  - A table with no rows (if the census finds no AAAI source before 2009) leaves those records `none`, counted `not_queried`.
- Planner decision: refusals are counted in the fill report, never forced:
  - **DOI mismatch**, `doi_mismatch`:
    - a work returned for a DOI batch whose DOI is not one the batch asked for;
    - a title-route work whose DOI is another corpus record's DOI.
  - **Duplicate DOI.** Several works share a requested DOI:
    - attached once, citing every work id, when their rebuilt and cleaned texts are identical;
    - otherwise refused, `doi_duplicate`.
    - unless a cited `[[duplicate_choice]]` row of `openalex_sources.toml` names one of the works: that work attaches alone, counted `attached_doi` and `duplicate_chosen`; a row whose work is not among two or more works the extract answers for its DOI stops the build, `duplicate_choice_unmatched` (TASK-231, owner ruling 2026-10-10).
  - **Truncated DOI.** OpenAlex's DOI is a cut-off form, so the exact DOI lookup finds nothing: `doi_unmatched`. A truncated DOI is never widened to match.
- Planner decision: the inverted-index rebuild rules:
  - positions must cover `0..n-1` exactly (a gap → refused, `inverted_gap`);
  - one position claimed by two different words → refused, `inverted_conflict`;
  - the same word listed twice at one position is harmless and kept once;
  - any non-string word, an empty word, a non-list or empty position list, or a negative or non-integer position → refused, `inverted_unreadable`;
  - a key with whitespace inside (a line break OpenAlex left in one token) is one entry at its one position, read with each whitespace run as one space and none at its edges; an empty or whitespace-only key → refused, `inverted_unreadable` (TASK-231, owner ruling 2026-10-10; it replaces Task 7's rule that a key with whitespace inside is unreadable);
  - then `common.clean_abstract` (controls, `…` snippet, placeholders) and `caps.cap_record` (20,000 characters, combining marks).
- Planner decision: the claim's `url` is the work's API URL (`https://api.openalex.org/works/W…`). Its `evidence` names the work's page (`https://openalex.org/W…`) and the match rule. `dedup.attribution` credits `openalex` to the record's `urls.proceedings`, never the API URL.
  - This **deviates** from spec §Query/API's "names OpenAlex and the work's URL" wording, per the milestone A/B lessons.
  - The RIS line therefore reads `N1  - Abstract source: OpenAlex <paper page>`. The OpenAlex work page is in `/papers` provenance.
- Planner decision: the crawl's candidates are `crawl.replay_all(cache)`'s records with venue in `OPENALEX_VENUES` and `abstract is None`. No dedup is needed, because each venue-year has one paper-list source.
  - A rebuilt batch set reuses cached pages; one new DOI reshuffles the 50-DOI batches, which costs about 30 requests in all, acceptable at this size.
  - `op ingest openalex` runs last in a full crawl (spec 08).

**Credentials, politeness and audit**
- Planner decision: OpenAlex needs no key (help.openalex.org, read 2026-10-10: "you can make basic queries with no key at all"; a free key raises the daily budget ten times; key as `api_key` or `Authorization: Bearer`).
  - `OPENALEX_API_KEY` is **optional**, read from the environment or `.env`.
  - It is sent only as an `Authorization: Bearer` header. It never goes in a URL, so never in a cache key, cache file, claim, log line or exception text.
  - Requests are sequential, at least 1 s apart.
- Planner decision: **no contact address is sent to OpenAlex.** Its documentation no longer mentions a polite pool, and the owner's `CROSSREF_MAILTO` approval covers `api.crossref.org` only (B rulings). `CROSSREF_MAILTO` is not reused, and there is no `OPENALEX_MAILTO`.
- Planner decision: the fidelity audit is `op eval openalex`.
  - It fetches OpenAlex for records that have official abstracts: FAccT 2022/2025/2026 (`facct_site`), AIES 2024–2025 (`ojs`), and a seeded sample of 1,000 AAAI 2010+ DOIs (`ojs`).
  - It fetches through the same fetcher and cache, so an `--offline` re-run reproduces it. It writes no extract and never feeds a snapshot.
  - Classes, from best to worst:
    - `exact` (whitespace-collapsed equal);
    - `near_exact` (equal `dedup.title_key`: the same search tokens);
    - `truncated` (OpenAlex's tokens are a strict prefix);
    - `similar` (token `SequenceMatcher` ratio ≥ 0.9);
    - `differs`;
    - plus `no_openalex` and `refused` (a rebuild refusal).

**Snapshot, coverage, follow-ups**
- Planner decision: `op snapshot diff` gains `abstract_kind: {"<id>": ["<old>", "<new>"]}` for every id held by both snapshots whose kind differs, whether or not its hash changed, plus `abstract_kind_transitions` counts.
- Planner decision: the manifest gains `abstract_openalex` (venue → year → count), written **only when non-zero**, like `trimmed`. A snapshot with no OpenAlex abstract keeps its manifest byte for byte, and `FORMAT_VERSION` stays `"2"`. `RecordFile` counts the same from the lines and the coverage load checks the two agree.
- Planner decision: `/coverage` gains `abstract_official` and `abstract_openalex` on each `TrackCoverage`, `VenueYearCoverage` and the totals, so the client never adds counts.
- Planner decision: **TASK-222 is included as Task 11.** It touches the same coverage model, page and report, and is small:
  - `official_counts.UNGATED_NOTES` holds each note with its citation;
  - `/coverage` gets `gate_note`/`gate_note_citation`;
  - the report and the page show the notes.
- Planner decision: **TASK-220 folds into Task 15's benchmark step.** The group-count report is re-run on the new schema-4 index on a quiet machine. TASK-220 completes citing it; its old index `757641db0a20` is superseded.
- Planner decision: the IASEAI 2027 follow-up the design asks C to file already exists (TASK-216). Task 14 only links it.

## Global Constraints

**Versions**
- `RECORD_SCHEMA_VERSION` `"7"` → `"8"`; index `SCHEMA_VERSION` `"3"` → `"4"`; `SERVED_SCHEMAS` keys `["3", "4"]`; snapshot `FORMAT_VERSION` stays `"2"` (additive manifest key only).
- `TOKENIZER_VERSION` unchanged; `QUERY_VERSION` unchanged (Planner decision above).

**Vocabulary and the synthetic corpus**
- `vocab.AbstractKind = Literal["official", "openalex", "none"]`, `vocab.ABSTRACT_KINDS = get_args(AbstractKind)`.
- New claim source `"openalex"` (record and dedup `Origin`), `export.ORIGIN_NAMES["openalex"] == "OpenAlex"`.
- The synthetic 5k corpus (`backend/tests/fixtures/corpus/synthetic_5k.py`) is **never reshuffled**:
  - its records carry no provenance, so every record is `official` or `none`;
  - tests that need `openalex` records use the new small corpus `backend/tests/fixtures/corpus/abstract_kinds.py`;
  - contract fixtures regenerate only because responses gain fields (facets, `abstract_kind`), never because a record moved;
  - tests that enumerate the corpus read its pinned tuples.

**OpenAlex scope and politeness**
- OpenAlex touches only AAAI, AIES and FAccT records whose resolved abstract is `null`. It never touches NeurIPS, ICLR, ICML or IASEAI, and never overwrites an official abstract.
- Host `api.openalex.org` only, sequential, `openalex.MIN_INTERVAL = 1.0`, at most 50 DOIs per request. The optional `OPENALEX_API_KEY` goes in a header only. No contact address is sent.

**Stops**
- A count that differs from a table's verified count stops the crawl (`count_mismatch`), and so does a listing whose total moves mid-chain (`listing_changed`). A crawl is never a silently shorter harvest.

**Tests**
- No test reaches the network (`backend/tests/conftest.py`).
- Recorded fixtures are scrubbed: real ids, DOIs and counts; synthetic titles, authors and abstracts (decision-004).
- **Every task that touches vocab, records, the engine, dedup, sources or the API runs the full backend suite:** `uv run pytest backend/tests -q -n auto`.
- e2e runs on `OP_E2E_API_PORT=8100 OP_E2E_WEB_PORT=3100 make e2e`, because the owner's dev servers hold :8000 and :3000.

**Process**
- Logging: structured JSON, one line per unit of work. Never abstracts, query text, the API key or any contact address.
- Docs, specs and backlog are updated in the same commit as the change they describe; backlog only through the `backlog` CLI.
- Commits and PRs carry no AI attribution of any kind (hook `block-ai-attribution.sh`, CLAUDE.md §Authorship).
- Branch `feat/new-venues-c`, cut from `origin/dev` after milestone B merges, in its own worktree. The plan file `docs/plans/2026-10-10-new-venues-milestone-c.md` is the branch's first commit.

## Review Focus

1. **A schema-3 index served with a query that names `abstract_kind:`.** This could be `current` before promotion, a pinned `/export?index_version=` or `/papers?q=`.
   - A person expects HTTP 422 `FIELD_NOT_INDEXED` naming the field and the index's schema, and telling them to search the current index or drop the filter. Never a 500. The facets on a schema-3 index say `abstract_kind: null`, not `{}`.
   - Pinned by:
     - Task 3: `test_a_schema_3_engine_refuses_abstract_kind_on_every_entry_point`;
     - Task 5: `test_search_naming_abstract_kind_on_a_schema_3_index_is_422`, `test_a_pinned_schema_3_export_naming_abstract_kind_is_422`, `test_schema_3_facets_say_abstract_kind_null`.
2. **OpenAlex truncated or duplicate DOIs.** A FAccT 2025 DOI held by OpenAlex as `10.1145/3715275.373200`; two works sharing one DOI.
   - A person expects the truncated one to attach nothing (`doi_unmatched`); duplicates with differing texts to attach nothing (`doi_duplicate`); duplicates with one text to attach once and cite every work; and a work answering for a DOI the batch didn't ask for to be refused (`doi_mismatch`).
   - Pinned by Task 8: `test_a_truncated_openalex_doi_attaches_nothing`, `test_duplicate_works_with_differing_texts_attach_nothing`, `test_duplicate_works_with_one_text_attach_once_citing_both`, `test_a_work_for_a_doi_not_asked_is_refused`.
3. **An inverted index with gaps or repeated positions.**
   - A person expects no abstract with a silent hole: a gap or a position claimed by two words is refused and counted; a word repeated at its own position is kept once; positions out of order are rebuilt in position order.
   - Pinned by Task 7: `test_rebuild_orders_by_position`, `test_rebuild_refuses_a_gap`, `test_rebuild_refuses_two_words_at_one_position`, `test_rebuild_keeps_a_word_listed_twice_at_its_position_once`, `test_rebuild_refuses_unreadable_shapes`.
4. **An official abstract arriving after OpenAlex in a later crawl.** OJS publishes a `dc:description`, or B's FAccT CSV gains a row, while the pinned extract still holds the OpenAlex text.
   - A person expects the official abstract, `abstract_kind: official`, the extract hit counted `official_won`, and `op snapshot diff` naming the record's kind change `openalex` → `official`, even when the texts are equal and no hash changes.
   - Pinned by:
     - Task 2: `test_the_official_abstract_wins_whatever_the_claim_order`;
     - Task 8: `test_an_official_abstract_in_a_later_crawl_wins_over_the_extract`;
     - Task 9: `test_diff_names_a_kind_change_even_when_no_hash_changes`.
5. **`abstract_kind` facet counts with the combos tripled.**
   - A person expects every facet and group count on a schema-4 index to equal the reference oracle's and the one-collection-per-kept-set count, with `abstract_kind`'s own top-level filter set aside (disjunctive). The tripled combo memo should stay within its budget, and the bitwise path (`_combos_of`) should equal the aggregation path.
   - Pinned by Task 4: `test_abstract_kind_facets_equal_the_oracle_and_per_set_collections`, `test_bitwise_combos_equal_aggregated_combos_on_schema_4`, `test_a_schema_4_base_memo_stays_within_the_tripled_budget`.

---

## File map

| File | Responsibility | Task |
|---|---|---|
| `backend/src/openproceedings/engine/index.py` | `SchemaForm`, `SERVED_SCHEMAS`, schema 4 field, `_document`, schema-3 build guard | 1, 4 |
| `backend/src/openproceedings/engine/tantivy_engine.py` | drop the `ord_indexed` path; `admit`; per-engine `facet_fields`/`combo`; `_display`; `MAX_FACET_COMBOS` | 1, 3, 4 |
| `backend/src/openproceedings/engine/compile.py` | drop the text-`id` set path (`id_set`) once unused | 1 |
| `backend/src/openproceedings/engine/parity.py` | stored `abstract_kind` equals the record's (schema 4) | 4 |
| `backend/src/openproceedings/vocab.py` | `AbstractKind`, `ABSTRACT_KINDS`, `QUERY_FILTER_FIELDS` | 2, 3 |
| `backend/src/openproceedings/ingest/record.py` | `openalex` source, `OPENALEX_VENUES`, `abstract_kind_of`, computed field, `DERIVED`, guard, schema 8 | 2 |
| `ingest/dedup.py`, `ingest/statuses.py`, `export.py`, `api/models.py` (`ORIGIN_DOC`), `frontend/src/components/search/hit-item.tsx` | precedence, origin, attribution, names | 2 |
| `query/ast.py`, `query/parser.py`, `query/canonical.py`, `query/clauses.py`, `engine/protocol.py`, `engine/reference.py`, `diagnostics.py` | the `abstract_kind:` filter; the oracle; `FIELD_NOT_INDEXED` | 3 |
| `backend/tests/corpus.py`, `backend/tests/strategies.py`, `backend/tests/fixtures/corpus/abstract_kinds.py` | test records and generators | 3, 4 |
| `search.py`, `api/search.py`, `api/models.py`, `api/meta.py`, `api/openapi.py`, `export.py`, `api/export.py` | facets, hits, exports, meta, enums | 4, 5 |
| `ingest/sources/http.py` | `Fetcher(headers=…)`, never cached or logged | 6 |
| `ingest/openalex_table.py` + `ingest/openalex_sources.toml` | the AAAI listing table | 7 (loader), 12 (rows) |
| `ingest/sources/openalex.py` | parse, rebuild, hygiene, harvest, extract, replay, fill | 7, 8 |
| `ingest/sources/crawl.py`, `cli.py`, `ingest/snapshot.py` | `op ingest openalex`, the fill in `build` | 8 |
| `ingest/snapshot.py` (`diff`, `render`, `RecordFile`), `coverage.py`, `api/coverage.py`, `eval/coverage_report.py` | kind diff, manifest key, coverage counts | 9 |
| `frontend/src/components/search/filter-sidebar.tsx`, `lib/search-state.ts`, `lib/methods-text.ts`, `components/help/syntax-help.tsx`, `components/paper/paper-view.tsx`, `components/search/hit-item.tsx`, `components/coverage/coverage-report.tsx`, goldens | UI | 10 |
| `official_counts.py`, `api/models.py`, `coverage.py`, `eval/coverage_report.py`, `coverage-report.tsx` | TASK-222 ungated notes | 11 |
| `backend/tests/fixtures/http/openalex/…`, research note, `openalex_sources.toml` rows | live census | 12 |
| `eval/openalex_audit.py`, `cli.py`, `docs/results/<date>-openalex-audit.md` | fidelity audit | 13 |
| specs 01/02/03/04/05/07/08, README, CLAUDE.md, skills, copy deck, design status, decision-049, `.env.example`, cspell | docs as built | 14 |

---

### Task 1: Retire index schema 2

The controller runs this prerequisite first and records the output in the task ledger. With `export OP_DATA_DIR=/Users/jeevanparmar/school/Research/Ferguson/openproceedings/data`:

```bash
for v in 05a0541717f6 6508b8cf66ff a7cfd04b656f c76d7f26ee06; do uv run op index retire "$v" --dry-run; done
```

Expected: each reports 0 pins and that `current` does not point at it. If any is pinned, stop: Tasks 1 and 4 then need a decision (three served schemas are not allowed by the skill).

**Files:**
- Modify: `backend/src/openproceedings/engine/index.py:52-71, 148-169` (the comment, `SchemaForm`, `SERVED_SCHEMAS`, `schema()`)
- Modify: `backend/src/openproceedings/engine/tantivy_engine.py:215-229, 248-251, 736-749, 856-862` (`form` check, `ord_indexed`, `id_set`, `_indexes_ord`)
- Modify: `backend/src/openproceedings/engine/compile.py` (`id_set` of the text `id`: delete it once no caller is left; `grep -n "id_set" backend/src`)
- Modify tests:
  - `backend/tests/unit/engine/test_served_schemas.py`: keep only the single-schema tests; the 3-vs-4 pair returns in Task 4;
  - `backend/tests/contract/test_records.py:771-830` (delete the schema-2 replay test) and `:697` (the tokenizer test's `schema_version` parameter becomes `["3"]`);
  - `backend/tests/unit/engine/test_rank.py:238`;
  - `backend/tests/unit/engine/test_verified_exclusion.py:42-49`;
  - `backend/tests/bench/id_sets.py`, `backend/tests/bench/schemas_alternate.py`: delete them with their callers if they only compare schema 2 and 3; otherwise keep them parametrized on served schemas.

**Interfaces:**
- Produces:
  - `SERVED_SCHEMAS == {"3": SchemaForm()}`; `SchemaForm` is an empty frozen dataclass until Task 3 adds a field;
  - every engine names verified ids by the `ord` term set; `TantivyEngine.ord_indexed` is gone.

- [ ] **Step 1: Write the failing test** (replace `test_the_current_and_the_previous_schema_are_served_and_no_other`)

```python
def test_only_schema_3_is_served_once_schema_2_is_retired() -> None:
    """Schema 2 retired (index-versioning skill §Two served schemas): no record pinned a schema-2 index."""
    assert SCHEMA_VERSION == "3" and list(SERVED_SCHEMAS) == ["3"]
    assert unservable({**MANIFEST, "schema_version": "3"}) is None
    for refused in ("1", "2", "4", None, 3, [], {}, ["3"]):
        why = unservable({**MANIFEST, "schema_version": refused})
        assert why is not None and why[0] == "schema_version_mismatch" and "build a new index" in why[1]
    with pytest.raises(ValueError, match="not one this code builds"):
        schema("2")
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest backend/tests/unit/engine/test_served_schemas.py -q -k retired`. Expected: FAIL (`list(SERVED_SCHEMAS) == ["2", "3"]`).

- [ ] **Step 3: Implement**

In `index.py`, replace the comment block and form:

```python
# The schema versions this code serves (guarantee 4: an index a search record pins keeps replaying): the current
# one, which new indexes are built at, and at most the one before it. Schema 2 (verified ids as a term set on the
# text `id`) was retired once no record pinned a schema-2 index (decision-049 milestone C; `op index retire`
# refuses a pinned one, decision-030). A third schema while two are served first retires the oldest.
@dataclass(frozen=True, slots=True)
class SchemaForm:
    """What differs between the served schemas, read per index from its manifest's `schema_version`."""


SERVED_SCHEMAS: Mapping[str, SchemaForm] = MappingProxyType({SCHEMA_VERSION: SchemaForm()})
```

In `schema()`: `b.add_unsigned_field("ord", stored=False, indexed=True, fast=True)`.

In `tantivy_engine.py`:
- `__init__` keeps `self.form = SERVED_SCHEMAS[manifest["schema_version"]]`. The `_indexes_ord` check stays, unconditional, with the message "claims schema … but `ord` isn't indexed". This keeps the refusal of a tampered manifest.
- Delete `ord_indexed`.
- `id_set` loses its first branch.
- Remove the `id_set` import from `compile.py` if it is now unused.

Delete the schema-2 tests named under Files. `test_an_index_whose_manifest_claims_an_indexed_ord_it_lacks_is_refused` keeps its intent: build with `schema_version="3"` under a monkeypatched `schema()` that indexes no `ord`. If that is not reachable without schema 2, delete it and leave the guard covered by `_indexes_ord`'s unit test in `test_index.py`.

- [ ] **Step 4: Run the full backend suite**

Run: `uv run pytest backend/tests -q -n auto`, then `grep -rn 'schema_version="2"\|ord_indexed' backend frontend` (expected: no hit outside `docs/results` and `.claude/learnings`). Then `make lint`. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A backend
git commit -m "refactor(engine): retire index schema 2; every served index names verified ids by the indexed ord"
```

---

### Task 2: Record model: the `openalex` source and the derived `abstract_kind`; record schema 8

**Files:**
- Modify: `backend/src/openproceedings/vocab.py` (`AbstractKind`, `ABSTRACT_KINDS`)
- Modify: `backend/src/openproceedings/ingest/record.py` (schema comment and constant, `DERIVED`, `Source`, `OPENALEX_VENUES`, `abstract_kind_of`, the computed field, `_consistent`)
- Modify: `backend/src/openproceedings/ingest/statuses.py` (`"openalex"` claims no status: add the source to whatever table enumerates sources, with an empty or abstract-only entry, following how `icml_site`/`facct_site` are listed)
- Modify: `backend/src/openproceedings/ingest/dedup.py` (`_TEXT` ends `…, "ris", "openalex"`; `Origin` adds `"openalex"`; `_DIRECT_ORIGIN["openalex"]`; `attribution`)
- Modify: `backend/src/openproceedings/export.py` (`ORIGIN_NAMES["openalex"] = "OpenAlex"`), `frontend/src/components/search/hit-item.tsx` (`ORIGIN_NAMES`), `backend/src/openproceedings/api/models.py` (`ORIGIN_DOC`)
- Test: `backend/tests/unit/ingest/test_abstract_kind.py` (new); `test_dedup.py` (precedence tuple, attribution); `test_record.py` (schema 8)

**Interfaces:**
- Produces:
  - `record.abstract_kind_of(abstract: str | None, claims: Iterable[AbstractClaimLike]) -> AbstractKind`;
  - `PaperRecord.abstract_kind` (a computed field; `"abstract_kind" in DERIVED`);
  - `record.OPENALEX_VENUES = frozenset({"AAAI", "AIES", "FAccT"})`;
  - `dedup.PRECEDENCE["abstract"][-1] == "openalex"`;
  - `dedup.attribution` for an `openalex` claim returns `Attribution("openalex", "openalex", proceedings)`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/unit/ingest/test_abstract_kind.py
"""`abstract_kind` (docs/plans/2026-10-09-new-venues-design.md §Data model): derived from the abstract's claims,
never stored or hashed; `openalex` only when every claim holding the abstract's text is OpenAlex's."""

from datetime import UTC, datetime

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from openproceedings.ingest.dedup import PRECEDENCE, Attribution, attribution, resolve
from openproceedings.ingest.record import (
    DERIVED, RECORD_SCHEMA_VERSION, Claim, PaperRecord, abstract_kind_of,
)
from openproceedings.ingest.snapshot import record_line

T = datetime(2026, 10, 10, tzinfo=UTC)
TEXT = "An abstract about calibrated trust in language models."


def _claim(field: str, value: object, source: str, url: str | None = None) -> Claim:
    return Claim(field=field, value=value, source=source, url=url, fetched_at=T, evidence="test")


def _base(source: str = "crossref", venue: str = "FAccT", year: int = 2023) -> list[Claim]:
    url = "https://api.crossref.org/works/10.1145/3593013.3594011"
    return [_claim(f, v, source, url) for f, v in (
        ("title", "A Paper"), ("venue", venue), ("year", year), ("track", "main"), ("status", "accepted"),
        ("urls.doi", "10.1145/3593013.3594011"), ("urls.proceedings", "https://doi.org/10.1145/3593013.3594011"))]


def _openalex(text: str = TEXT) -> Claim:
    return _claim("abstract", text, "openalex", "https://api.openalex.org/works/W123")


def test_schema_is_8_and_the_kind_is_derived() -> None:
    assert RECORD_SCHEMA_VERSION == "8" and DERIVED == frozenset({"venue_name", "abstract_kind"})


@pytest.mark.parametrize(
    ("abstract", "sources", "kind"),
    [(None, (), "none"), (TEXT, (), "official"), (TEXT, ("openalex",), "openalex"),
     (TEXT, ("ojs", "openalex"), "official"), (TEXT, ("facct_site",), "official")],
)  # fmt: skip
def test_abstract_kind_of(abstract, sources, kind) -> None:
    claims = [_claim("abstract", abstract, s) for s in sources]
    assert abstract_kind_of(abstract, claims) == kind


def test_a_claim_holding_other_text_does_not_count() -> None:
    claims = [_claim("abstract", TEXT, "openalex"), _claim("abstract", "Another text.", "ojs")]
    assert abstract_kind_of(TEXT, claims) == "openalex"


def test_the_kind_is_sent_never_stored_and_never_hashed() -> None:
    record, _ = resolve("op:facct:2023:doi-3593013.3594011", [*_base(), _openalex()])
    assert record.abstract_kind == "openalex" and record.model_dump()["abstract_kind"] == "openalex"
    assert "abstract_kind" not in record_line(record)
    plain, _ = resolve("op:facct:2023:doi-3593013.3594011", [*_base(), _claim("abstract", TEXT, "facct_site")])
    assert plain.content_hash == record.content_hash  # same text, another source: no hash change


@given(st.permutations(["openalex", "ojs"]))
def test_the_official_abstract_wins_whatever_the_claim_order(order: list[str]) -> None:
    official, other = "The official abstract.", "OpenAlex's text of it."
    claims = [*_base("ojs", "AAAI", 2020)]
    for source in order:
        claims.append(_claim("abstract", official if source == "ojs" else other, source))
    record, _ = resolve("op:aaai:2020:ojs-28000", claims)
    assert record.abstract == official and record.abstract_kind == "official"
    assert PRECEDENCE["abstract"][-1] == "openalex"


@pytest.mark.parametrize(("venue", "year", "rid"), [("ICML", 2005, "op:icml:2005:dblp-Smith05"),
                                                     ("IASEAI", 2026, "op:iaseai:2026:ojs-40000")])
def test_an_openalex_claim_is_refused_outside_aaai_aies_and_facct(venue: str, year: int, rid: str) -> None:
    claims = [_claim(f, v, "dblp" if venue == "ICML" else "ojs") for f, v in (
        ("title", "A Paper"), ("venue", venue), ("year", year), ("track", "main"), ("status", "accepted"))]
    with pytest.raises((ValidationError, ValueError), match="OpenAlex"):
        resolve(rid, [*claims, _openalex()])


def test_an_openalex_claim_on_another_field_is_refused() -> None:
    with pytest.raises((ValidationError, ValueError), match="OpenAlex"):
        resolve("op:facct:2023:doi-3593013.3594011", [*_base(), _claim("title", "X", "openalex")])


def test_an_openalex_abstract_is_credited_to_the_papers_page_never_the_api() -> None:
    page = "https://doi.org/10.1145/3593013.3594011"
    got = attribution(TEXT, [_openalex()], forum=None, proceedings=page, native="doi-3593013.3594011")
    assert got == Attribution("openalex", "openalex", page)
```

Update `test_dedup.py::test_the_precedence_table_is_decision_005`: the text tuple ends `"ojs", "crossref", "facct_site", "ris", "openalex"`. Its status tuple is unchanged, because `openalex` claims no status.

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest backend/tests/unit/ingest/test_abstract_kind.py -q`. Expected: FAIL (`ImportError: abstract_kind_of`).

- [ ] **Step 3: Implement**

`vocab.py`, after `Status`:

```python
# where a record's abstract came from (decision-049): an official source, OpenAlex's fallback, or none. Derived
# from the abstract's claims (`record.abstract_kind_of`), never stored; an open set (a later fallback adds one)
AbstractKind = Literal["official", "openalex", "none"]
...
ABSTRACT_KINDS: tuple[str, ...] = get_args(AbstractKind)
```

`record.py`:

```python
# 8: the `openalex` source (abstract claims only, AAAI/AIES/FAccT) and the derived `abstract_kind` (decision-049,
# milestone C); 7: the `crossref` and `facct_site` sources, … (keep the existing lines)
RECORD_SCHEMA_VERSION = "8"
DERIVED = frozenset({"venue_name", "abstract_kind"})
Source = Literal[
    "openreview_v2", "openreview_v1", "iclr_archive", "neurips_proceedings", "pmlr", "dblp", "icml_site", "ojs",
    "crossref", "facct_site", "ris", "openalex",
]  # fmt: skip
# the venues an OpenAlex abstract may fill (decision-049): never NeurIPS, ICLR or ICML (spec 01's rule), nor IASEAI
OPENALEX_VENUES: frozenset[str] = frozenset({"AAAI", "AIES", "FAccT"})


class _HoldsText(Protocol):
    @property
    def source(self) -> Any: ...
    @property
    def value(self) -> Any: ...


def abstract_kind_of(abstract: str | None, claims: Iterable[_HoldsText]) -> AbstractKind:
    """`none` without an abstract; `openalex` when at least one of the abstract claims holds its exact text and
    every such claim is OpenAlex's; else `official` (a record without provenance, as fixtures are, included).
    `claims` are abstract claims (a `Claim`, or the snapshot reader's raw view of one)."""
    if abstract is None:
        return "none"
    held = {c.source for c in claims if c.value == abstract}
    return "openalex" if held == {"openalex"} else "official"
```

Add the computed field beside `venue_name`:

```python
    @computed_field(  # type: ignore[prop-decorator]
        description="Where the abstract came from: `official` (the venue's own source), `openalex` (OpenAlex's "
        "fallback, only for AAAI, AIES and FAccT papers no official source gives one), or `none`. Derived from the "
        "abstract's claims; never stored, never hashed. Open set."
    )
    @property
    def abstract_kind(self) -> AbstractKind:
        return abstract_kind_of(self.abstract, self.claims("abstract"))
```

In `_consistent`, before the hash:

```python
        for c in self.provenance:
            if c.source == "openalex" and (c.field != "abstract" or self.venue not in OPENALEX_VENUES):
                raise ValueError(
                    f"an OpenAlex claim may only fill an abstract of an AAAI, AIES or FAccT record, not "
                    f"{c.field} of {self.venue}"
                )
```

`dedup.py`:
- `_TEXT = (…, "ris", "openalex")`. Comment: "OpenAlex last: it only fills an abstract no other source gives (decision-049); the fill runs after dedup (`sources/openalex.apply`), so this order is the second guard".
- `Origin` adds `"openalex"`; `_DIRECT_ORIGIN["openalex"] = "openalex"`.
- In `attribution`, widen the B branch to `if origin in ("ojs", "crossref", "facct_site", "openalex"):`, with the comment naming OpenAlex's API work URL.

`statuses.py`: list `openalex` as a source that claims no status, mirroring `facct_site`. `export.ORIGIN_NAMES["openalex"] = "OpenAlex"`, and the same entry in `hit-item.tsx`. `ORIGIN_DOC` gains: "`openalex`: an AAAI, AIES or FAccT abstract no official source gives, filled from OpenAlex (decision-049); the url is the paper's own page, never OpenAlex's API."

- [ ] **Step 4: Run the full backend suite and regenerate the contract**

Run: `uv run pytest backend/tests -q -n auto`. Expected: PASS apart from staleness tests naming `openapi.json`, `record-fixture.json` or the coverage fixture (the `Source`/`Origin` literals; `abstract_kind` on `/papers`).

Then `make openapi` and the regenerators each failure names (`uv run python -m tests.contract.record_fixture` style, as the failure message says). Re-run `uv run pytest backend/tests/contract -q -n auto` and `npm test --workspace frontend`. Fix any test pinning schema `"7"` (`grep -rn 'RECORD_SCHEMA_VERSION == "7"\|"record_schema_version": "7"' backend/tests`).

- [ ] **Step 5: Commit**

```bash
git add -A backend frontend
git commit -m "feat: the openalex claim source (abstract only, AAAI/AIES/FAccT, last in precedence) and the derived abstract_kind; record schema 8 (decision-049)"
```

---

### Task 3: The `abstract_kind:` filter: query language, the reference oracle, and the schema-3 refusal

**Files:**
- Modify: `backend/src/openproceedings/vocab.py:37-43` (`QUERY_FILTER_FIELDS`: `"abstract_kind"` before `"source"`)
- Modify: `backend/src/openproceedings/query/ast.py:18-20, 128-131` (`FilterField` append; allowed values)
- Modify: `backend/src/openproceedings/query/parser.py:75-88` (`_EXAMPLES`, `_OR_EXAMPLES`, `_VALID`)
- Modify: `backend/src/openproceedings/query/canonical.py:46-50` (`_VALUE_WORDS`)
- Modify: `backend/src/openproceedings/query/clauses.py:78-82` (`VOCABULARY`), `ParsedFilters` (a field per `FILTER_FIELDS`, so it gains `abstract_kind`)
- Modify: `backend/src/openproceedings/engine/protocol.py` (`Searchable.abstract_kind`; docstring "five filters")
- Modify: `backend/src/openproceedings/engine/reference.py` (`_Doc.abstract_kind`; table row)
- Modify: `backend/src/openproceedings/search.py:94-107` (`Shown` gains `abstract_kind`), `cli.py`, `api/compare.py`, `eval/scholar_compare.py` adapters (each `Searchable` they build reads `abstract_kind` from the display record)
- Modify: `backend/src/openproceedings/diagnostics.py` (`FIELD_NOT_INDEXED`, 422 by the non-`API_` default)
- Modify: `backend/src/openproceedings/engine/index.py` (`SchemaForm(abstract_kind: bool)`, `"3": SchemaForm(abstract_kind=False)`), `tantivy_engine.py` (`filter_fields`, `admit`)
- Modify: `backend/tests/corpus.py` (`Rec.abstract_kind`), `backend/tests/strategies.py` (filters, `CLAUSE_VALUES`, `_FILTER_STRINGS`, a `fields` parameter)
- Test: `backend/tests/unit/test_abstract_kind_filter.py` (new); parse golden rows in `backend/tests/golden/` (follow the file the venue/track goldens live in)

**Interfaces:**
- Produces:
  - `FILTER_FIELDS == ("venue", "year", "track", "status", "abstract_kind")`;
  - `parse("trust abstract_kind:openalex").canonical == "trust AND abstract_kind:openalex AND status:accepted AND track:(datasets_benchmarks OR main OR position)"`. The exact default order follows `canonical.FILTER_ORDER`; take it from the golden run;
  - `TantivyEngine.filter_fields: tuple[str, ...]`;
  - `TantivyEngine.admit(ast) -> None`, which raises `EngineInputError(DiagnosticCode.FIELD_NOT_INDEXED, …)`;
  - `strategies.filters(fields=FILTER_FIELDS)`, `strategies.engine_asts(vocab, fields=FILTER_FIELDS)`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/unit/test_abstract_kind_filter.py
"""`abstract_kind:` (spec 02; decision-049): a filter, never text (guarantee 2), no default, the same rule in the
oracle and the index; a schema-3 index refuses it as input (422), never as an internal error."""

import pytest

from openproceedings.diagnostics import DiagnosticCode, http_status
from openproceedings.engine.protocol import EngineInputError
from openproceedings.engine.reference import ReferenceEngine
from openproceedings.query.ast import FILTER_FIELDS
from openproceedings.query.parser import parse

from tests.corpus import Rec
from tests.unit.engine.test_exclusions import tantivy_of

RECS = [
    Rec("op:aaai:1990:dblp-A90", "Trust in planning", "OpenAlex text.", venue="AAAI", year=1990,
        abstract_kind="openalex"),
    Rec("op:aaai:2020:ojs-1", "Trust in search", "Official text.", venue="AAAI", year=2020),
    Rec("op:aaai:2021:ojs-2", "Trust in games", None, venue="AAAI", year=2021),
]  # fmt: skip


def test_the_field_is_last_in_the_canonical_order() -> None:
    assert FILTER_FIELDS[-1] == "abstract_kind"


@pytest.mark.parametrize(("q", "ids"), [
    ("trust abstract_kind:openalex", {"op:aaai:1990:dblp-A90"}),
    ("trust abstract_kind:(official OR none)", {"op:aaai:2020:ojs-1", "op:aaai:2021:ojs-2"}),
    ("trust NOT abstract_kind:none", {"op:aaai:1990:dblp-A90", "op:aaai:2020:ojs-1"}),
    ("trust abstract_kind:OPENALEX", {"op:aaai:1990:dblp-A90"}),  # values are case-blind, as venue's
])  # fmt: skip
def test_the_oracle_filters_by_kind(q: str, ids: set[str]) -> None:
    ast = parse(q).ast
    assert ast is not None and ReferenceEngine(RECS).match_ids(ast) == ids


def test_a_kind_is_never_matched_as_text() -> None:  # guarantee 2: the word `openalex` alone matches no kind
    ast = parse("openalex").ast
    assert ast is not None and ReferenceEngine(RECS).match_ids(ast) == frozenset()


def test_an_unknown_value_is_refused_naming_the_values() -> None:
    result = parse("trust abstract_kind:crossref")
    (err,) = result.errors
    assert err.code == DiagnosticCode.FIELD_UNKNOWN_VALUE and "`openalex`" in err.message


def test_no_default_applies() -> None:
    result = parse("trust")
    assert "abstract_kind" not in (result.canonical or "") and "abstract_kind" not in result.defaults


def test_existing_canonicals_are_unchanged() -> None:  # no QUERY_VERSION bump (Planner decision)
    assert parse("trust venue:ICLR year:2024").canonical == (
        "trust AND venue:ICLR AND year:2024 AND status:accepted AND track:(datasets_benchmarks OR main OR position)"
    )


def test_a_schema_3_engine_refuses_abstract_kind_on_every_entry_point(tmp_path) -> None:
    engine = tantivy_of(RECS[1:], tmp_path, "3")  # no OpenAlex record: a schema-3 build refuses one (Task 4)
    assert "abstract_kind" not in engine.filter_fields
    ast = parse("trust abstract_kind:openalex").effective_ast
    assert ast is not None
    for call in (lambda: engine.compile(ast), lambda: engine.facets(ast), lambda: engine.counts([ast]),
                 lambda: engine.match_ids(ast), lambda: engine.candidates(ast)):  # fmt: skip
        with pytest.raises(EngineInputError) as refused:
            call()
        assert refused.value.code == DiagnosticCode.FIELD_NOT_INDEXED
        assert "schema 4" in str(refused.value) and engine.index_version in str(refused.value)
    assert http_status(DiagnosticCode.FIELD_NOT_INDEXED) == 422
```

(`http_status` is whatever `diagnostics.py` names its code → status function at line ~120; use that name. `tantivy_of(records, path, schema, tokenizer=…)` is the helper in `tests/unit/engine/test_exclusions.py`.)

In `backend/tests/corpus.py`:

```python
@dataclass(frozen=True)
class Rec:
    """A `Searchable` record (engine/protocol.py) with defaults for the fields a test doesn't care about;
    `abstract_kind` defaults to what a record without provenance derives (`none` or `official`)."""

    id: str
    title: str
    abstract: str | None
    venue: str = "ICLR"
    year: int = 2024
    track: str = "main"
    status: str = "accepted"
    abstract_kind: str | None = None

    def __post_init__(self) -> None:
        if self.abstract_kind is None:
            object.__setattr__(self, "abstract_kind", "none" if self.abstract is None else "official")
```

In `strategies.py`:
- `filters(draw, fields=FILTER_FIELDS)` draws `field` from `fields`, with the `abstract_kind` pool `list(ABSTRACT_KINDS)`;
- `_node`/`engine_asts` pass `fields` through;
- `CLAUSE_VALUES["abstract_kind"] = tuple(ABSTRACT_KINDS)`;
- `_FILTER_STRINGS` gains `"abstract_kind:official"`.

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest backend/tests/unit/test_abstract_kind_filter.py -q`. Expected: FAIL (`FILTER_FIELDS[-1] == "status"`).

- [ ] **Step 3: Implement**

`ast.py`:

```python
FilterField = Literal["venue", "year", "track", "status", "abstract_kind"]  # also the canonical filter order
...
        allowed = {"venue": VENUES.values(), "track": TRACKS, "status": STATUSES,
                   "abstract_kind": ABSTRACT_KINDS}.get(self.field)  # fmt: skip
```

`parser.py`:
- `_EXAMPLES["abstract_kind"] = "abstract_kind:official"`;
- `_OR_EXAMPLES["abstract_kind"] = "official OR none"`;
- `_VALID["abstract_kind"] = ABSTRACT_KINDS`.

`canonical.py`: `_VALUE_WORDS["abstract_kind"] = frozenset(ABSTRACT_KINDS)`. `clauses.py`: `VOCABULARY["abstract_kind"] = tuple(sorted(ABSTRACT_KINDS))`. `ParsedFilters` gains `abstract_kind: ParsedClause` if its fields are declared by hand.

`protocol.py`: `Searchable` gains `abstract_kind` (a `str` property). `reference.py`:
- `_Doc` gains `abstract_kind: str`, filled from `r.abstract_kind`;
- the docstring table's Filter row reads "venue/track/status/abstract_kind";
- `_filter_matches` needs no change (`getattr`).

`search.Shown` gains `abstract_kind`, read from the display record. Task 4 makes `_display` always send it; until then `Shown.of` uses `record.get("abstract_kind") or ("none" if record["abstract"] is None else "official")`. Task 4 tightens it to `record["abstract_kind"]`. Treat the `cli.py`, `api/compare.py` and `scholar_compare.py` adapters the same way.

`diagnostics.py`: `FIELD_NOT_INDEXED = "FIELD_NOT_INDEXED"`, under `# fields and filters`, with the comment "a filter field the queried index's schema doesn't hold (a pinned older index; decision-049)".

`index.py`: `class SchemaForm: abstract_kind: bool  # a stored fast `abstract_kind` (schema 4)` and `SERVED_SCHEMAS = MappingProxyType({SCHEMA_VERSION: SchemaForm(abstract_kind=False)})`.

`tantivy_engine.py`:

```python
BASE_COMBO: tuple[str, ...] = ("venue", "year", "track", "status")  # every served schema's filter fields
...
        self.filter_fields: tuple[str, ...] = BASE_COMBO + (("abstract_kind",) if self.form.abstract_kind else ())
...
    def admit(self, ast: Node) -> None:
        """Refuse, as the client's error (422), a query naming a filter field this index's schema doesn't hold:
        `abstract_kind:` on a schema-3 index (one a search record pins), never a 500 from Tantivy."""
        missing = sorted({f.field for f in _filters_in(ast)} - set(self.filter_fields))
        if missing:
            raise EngineInputError(
                DiagnosticCode.FIELD_NOT_INDEXED,
                f"`{missing[0]}:` needs index schema 4, and index {self.index_version} is schema "
                f"{self.schema_version}: search the current index, or remove the `{missing[0]}:` filter.",
            )
```

Here `self.schema_version = manifest["schema_version"]` and `_filters_in` walks `And`/`Or`/`Not` children yielding every `Filter`. Call `self.admit(ast)` first in `compile` (before the memo read), `facets`, `counts` (per tree, before `self.expansions`) and `candidates`. `facets`' `unknown` check and default `fields` use `self.filter_fields` (`fields: tuple[str, ...] | None = None` → `self.filter_fields`).

Add golden parse rows for `abstract_kind:` (accepted, OR-group, negated, bad value, `source:`-mode untouched) to the golden file that holds the venue/track rows. The trust-evals strings stay unchanged.

- [ ] **Step 4: Run the full backend suite; regenerate goldens and the contract**

Run: `uv run pytest backend/tests -q -n auto`. Expected failures: staleness only:
- the lexer golden and tables, because `FIELDS` changed (`frontend/src/editor/lang/lexer-tables.json`, `lexer-golden.json`);
- the help golden (`frontend/src/help/syntax-golden.json`);
- `openapi.json` (`FilterField`, `ParsedFilters`, `DiagnosticCode`).

Regenerate each by the command its failure prints (`PYTHONPATH=backend uv run python -m tests.contract.help_golden`, the lexer golden's generator in `test_frontend_lexer_golden.py`, `make openapi`). Then re-run the suite and `npm test --workspace frontend`.

Differential and property tests that compare a schema-3 Tantivy engine with the oracle must draw with `fields=("venue", "year", "track", "status")`. Change each `engine_asts(...)` call whose engine is schema 3; `grep -rn "engine_asts(" backend/tests` lists them. Task 4 moves them to schema 4 and the full field set.

- [ ] **Step 5: Commit**

```bash
git add -A backend frontend
git commit -m "feat(query): the abstract_kind: filter (official, openalex, none) in the parser, canonical form and oracle; a schema-3 index refuses it with FIELD_NOT_INDEXED (422)"
```

---

### Task 4: Index schema 4: the `abstract_kind` fast field, per-engine facets and combos

**Files:**
- Create: `backend/tests/fixtures/corpus/abstract_kinds.py` (about 60 records over AAAI/AIES/FAccT with real `Claim`s: OpenAlex-only, official + OpenAlex same text, official-only, none)
- Modify: `backend/src/openproceedings/engine/index.py` (`SCHEMA_VERSION = "4"`, `SchemaForm.facets`, `SERVED_SCHEMAS`, `FACETS`, `schema()`, `_document`, `_add_all` guard)
- Modify: `backend/src/openproceedings/engine/tantivy_engine.py`:
  - `COMBO`; `self.combo`; `_aggregated` becomes a method;
  - `counts`, `combos`, `_combos_of`, `_value_masks` read `self.combo`;
  - `_display`; `MAX_FACET_COMBOS = 300_000`.
- Modify: `backend/src/openproceedings/search.py:219` (`over = engine.combo if facets else ORDER`), `search.Shown.of` (`record["abstract_kind"]`)
- Modify: `backend/src/openproceedings/engine/parity.py` (schema 4: each document's stored `abstract_kind` equals its record's)
- Modify tests:
  - `backend/tests/unit/engine/test_served_schemas.py`: the pair returns as 3 vs 4;
  - `test_facets_equal.py:150-160`, `backend/tests/unit/test_group_counts.py:1046`, `test_memo_budget.py`;
  - `backend/tests/bench/exclusions_alternate.py:35`;
  - `backend/tests/contract/test_records.py`: a schema-3 → schema-4 replay test, modelled on the deleted schema-2 one.
- Test: `backend/tests/unit/engine/test_abstract_kind_index.py` (new)

**Interfaces:**
- Produces:
  - `SERVED_SCHEMAS == {"3": SchemaForm(abstract_kind=False), "4": SchemaForm(abstract_kind=True)}`;
  - `SchemaForm.facets -> tuple[str, ...]` (the stored raw fast text fields);
  - `COMBO == ("venue", "year", "track", "status", "abstract_kind")`;
  - `TantivyEngine.combo`, the engine's own;
  - every display record has `abstract_kind`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/fixtures/corpus/abstract_kinds.py
"""A small corpus with every abstract kind (decision-049), for the schema-4 differential and facet tests. Built
from claims through `dedup.resolve`, as the snapshot's records are, so `abstract_kind` is derived, never set.
Synthetic text (decision-004). Pinned: add records at the end only."""

from datetime import UTC, datetime

from openproceedings.ingest.dedup import resolve
from openproceedings.ingest.record import Claim, PaperRecord

T = datetime(2026, 10, 10, tzinfo=UTC)
WORDS = ("trust", "calibration", "agents", "fairness", "planning", "audit")


def _claims(source: str, venue: str, year: int, title: str, extra: list[tuple[str, object, str]]) -> list[Claim]:
    base = [("title", title), ("venue", venue), ("year", year), ("track", "main"), ("status", "accepted")]
    out = [Claim(field=f, value=v, source=source, fetched_at=T, evidence="fixture") for f, v in base]
    return out + [Claim(field=f, value=v, source=s, fetched_at=T, evidence="fixture") for f, v, s in extra]


def records() -> list[PaperRecord]:
    out = []
    for i in range(60):
        w, kind = WORDS[i % len(WORDS)], i % 4
        venue, year = (("AAAI", 1990 + i % 18), ("AIES", 2018 + i % 6), ("FAccT", 2019 + i % 8))[i % 3]
        source, native = {"AAAI": ("dblp", f"dblp-K{i}"), "AIES": ("crossref", f"doi-3278721.{3278700 + i}"),
                          "FAccT": ("crossref", f"doi-3593013.{3594000 + i}")}[venue]  # fmt: skip
        text = f"An abstract about {w} number {i}."
        extra = [[("abstract", text, "openalex")],
                 [("abstract", text, source if source != "dblp" else "ris"), ("abstract", text, "openalex")],
                 [("abstract", text, source if source != "dblp" else "ris")], []][kind]
        record, _ = resolve(f"op:{venue.lower()}:{year}:{native}", _claims(source, venue, year, f"{w} paper {i}", extra))
        out.append(record)
    return out
```

The DOI-native rule of B (`acm_table.TABLE` lists the toc) may refuse these synthetic `doi-` ids. In that case use `tests.unit.ingest.crossref.api.TABLE_TEXT` tocs, or give AIES/FAccT `ojs-`/`pmlr-v81-` forms valid for their years, so the records build without monkeypatching. Keep the kinds' pattern.

```python
# backend/tests/unit/engine/test_abstract_kind_index.py
"""Index schema 4 (decision-049): `abstract_kind` is a raw fast field; facets and combos are per engine."""

import pytest
from hypothesis import given, settings

from openproceedings.engine.index import SCHEMA_VERSION, SERVED_SCHEMAS, IndexBuildError
from openproceedings.engine.reference import ReferenceEngine
from openproceedings.engine.tantivy_engine import COMBO, TantivyEngine
from openproceedings.query.parser import parse

from tests.fixtures.corpus import abstract_kinds
from tests.strategies import engine_asts
from tests.unit.engine.test_exclusions import tantivy_of

CORPUS = abstract_kinds.records()


@pytest.fixture(scope="module")
def engine(tmp_path_factory) -> TantivyEngine:
    return tantivy_of(CORPUS, tmp_path_factory.mktemp("s4"), "4")


@pytest.fixture(scope="module")
def oracle() -> ReferenceEngine:
    return ReferenceEngine(CORPUS)


def test_schema_4_is_current_and_3_still_served() -> None:
    assert SCHEMA_VERSION == "4" and list(SERVED_SCHEMAS) == ["3", "4"]
    assert SERVED_SCHEMAS["4"].facets == ("venue", "track", "status", "abstract_kind")
    assert COMBO == ("venue", "year", "track", "status", "abstract_kind")


def test_every_kind_is_in_the_fixture() -> None:
    assert {r.abstract_kind for r in CORPUS} == {"official", "openalex", "none"}


@pytest.mark.parametrize("q", ["abstract_kind:openalex", "trust abstract_kind:(official OR none)",
                               "NOT abstract_kind:official agents", "venue:AAAI abstract_kind:openalex"])
def test_abstract_kind_facets_equal_the_oracle_and_per_set_collections(engine, oracle, q: str) -> None:
    ast = parse(q).effective_ast
    assert ast is not None
    assert engine.match_ids(ast) == oracle.match_ids(ast)
    assert engine.facets(ast) == oracle.facets(ast)
    assert set(engine.facets(ast)) == set(COMBO)


@settings(max_examples=200, deadline=None)
@given(engine_asts(abstract_kinds_vocab := None))  # the vocab helper the differential suite uses for a corpus
def test_generated_trees_agree_with_the_oracle_on_schema_4(engine, oracle, ast) -> None:
    assert engine.match_ids(ast) == oracle.match_ids(ast)
    assert engine.facets(ast) == oracle.facets(ast)


def test_bitwise_combos_equal_aggregated_combos_on_schema_4(engine) -> None:
    from openproceedings.engine.tantivy_engine import _Parts

    ast = parse("trust OR agents").effective_ast
    assert ast is not None
    parts = _Parts(engine, None)
    parts.bitwise = True
    engine.faceted.clear()
    bitwise = engine.combos([ast], parts=parts)
    engine.faceted.clear()
    assert bitwise == engine._aggregate([ast], None, engine.combo, None)
    assert {c[-1] for c, _n in bitwise} <= {"official", "openalex", "none"}


def test_a_schema_4_base_memo_stays_within_the_tripled_budget(engine) -> None:
    assert TantivyEngine.MAX_FACET_COMBOS == 300_000
    engine.faceted.clear()
    engine.facets(parse("trust").effective_ast)
    assert sum(engine.charges["faceted"]) <= TantivyEngine.MAX_FACET_COMBOS


def test_display_records_carry_the_kind_on_both_schemas(tmp_path, engine) -> None:
    hits = engine.display(sorted(engine.ids)[:10])
    assert all(h["abstract_kind"] == next(r for r in CORPUS if r.id == i).abstract_kind for i, h in hits.items())
    plain = [r for r in CORPUS if r.abstract_kind != "openalex"]
    old = tantivy_of(plain, tmp_path, "3")
    assert all(h["abstract_kind"] in ("official", "none") for h in old.display(sorted(old.ids)).values())


def test_a_schema_3_build_refuses_an_openalex_record(tmp_path) -> None:
    with pytest.raises(IndexBuildError, match="needs index schema 4"):
        tantivy_of(CORPUS, tmp_path, "3")
```

(Replace the `engine_asts(abstract_kinds_vocab := None)` placeholder with the vocab builder that `tests/fixtures/corpus/synthetic_5k.py::vocab()` uses, applied to `CORPUS`. If that builder is corpus-specific, add `vocab_of(records)` beside it.)

Rewrite `test_served_schemas.py`'s pair as `("3", "4")`, built from the synthetic 5k corpus (no OpenAlex record, so schema 3 builds):
- `pair` asserts `old.form.abstract_kind is False and new.form.abstract_kind is True`.
- The ranking tests draw `engine_asts(vocab(), fields=("venue", "year", "track", "status"))` and assert identical ids and float scores. Facets compare on the shared fields (`{k: v for k, v in new.facets(ast).items() if k in old.filter_fields} == old.facets(ast)`).
- Add `test_schema_3_refuses_what_schema_4_answers`: one `abstract_kind:` tree, which is `FIELD_NOT_INDEXED` on old and a list on new.
- The module docstring names the two schemas.

In `test_records.py`, add `test_a_record_saved_on_a_schema_3_index_reproduces_after_the_schema_4_build` (parametrized on tokenizer `"2"`, `"3"`). Model it on the deleted schema-2 test, with `schema_version="3"` for `old`, and assert `mine["schema_version"] == "3"`, `theirs["schema_version"] == "4"`, equal `ids_hash` and `excluded`.

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest backend/tests/unit/engine/test_abstract_kind_index.py -q`. Expected: FAIL (`SCHEMA_VERSION == "3"`).

- [ ] **Step 3: Implement**

`index.py`:

```python
SCHEMA_VERSION = "4"  # 4: `abstract_kind`, a raw fast field (decision-049); 3: `ord` indexed too (TASK-167)


@dataclass(frozen=True, slots=True)
class SchemaForm:
    """What differs between the served schemas, read per index from its manifest's `schema_version`."""

    abstract_kind: bool  # a stored raw fast `abstract_kind` (schema 4): its filter and facet

    @property
    def facets(self) -> tuple[str, ...]:
        """The raw fast text fields every document holds: filtered and counted (year is the u64 column)."""
        return ("venue", "track", "status", *(("abstract_kind",) if self.abstract_kind else ()))


SERVED_SCHEMAS: Mapping[str, SchemaForm] = MappingProxyType(
    {"3": SchemaForm(abstract_kind=False), SCHEMA_VERSION: SchemaForm(abstract_kind=True)}
)
FACETS = SERVED_SCHEMAS[SCHEMA_VERSION].facets
```

- `schema()` iterates `SERVED_SCHEMAS[version].facets`.
- `_document(r, fields, ord_, title_rank, form)` iterates `form.facets` (`getattr(r, "abstract_kind")` is the derived field).
- `_add_all` takes `form` and, before `_check_tokens`:

```python
        if not form.abstract_kind and r.abstract_kind == "openalex":
            raise IndexBuildError(f"{r.id}: an OpenAlex abstract needs index schema 4 (schema 3 can't filter or "
                                  "label it): build at the current schema")  # fmt: skip
```

`tantivy_engine.py`:
- `COMBO = ("venue", "year", "track", "status", "abstract_kind")`, with the comment "schema 4's; an engine's own is `self.combo`".
- In `__init__`, `self.combo = self.filter_fields`; the order already matches.
- `_aggregated` becomes `def _aggregated(self, over)`, checking against `self.combo`.
- Every `COMBO` use inside the class becomes `self.combo`: the `facets` default `over: tuple[str, ...] | None = None` → `self.combo`, `counts` (`self.combo.index(f)`), `combos`, the `parts.bitwise and over == self.combo` check, and `_value_masks`.
- `MAX_FACET_COMBOS = 300_000`, with the comment "a base's (venue, year, track, status, abstract_kind) combos, + 1: up to three times schema 3's".
- `_display`:

```python
    def _display(self, address: tantivy.DocAddress) -> dict[str, Any]:
        doc = self.searcher.doc(address).to_dict()
        shown = record_of(doc["record"][0])
        kind = doc["abstract_kind"][0] if self.form.abstract_kind else (
            "none" if shown.get("abstract") is None else "official")  # exact: a schema-3 build refuses openalex
        return {"id": doc["id"][0], **{f: doc[f][0] for f in ("venue", "track", "status", "year")},
                "abstract_kind": kind, **shown}  # fmt: skip
```

`parity.py`: when the index manifest's schema has `abstract_kind`, compare each document's stored `abstract_kind` with its record's, through `check_parity`'s existing walk; a difference fails like a token difference. Add a parity unit test for one tampered record (build, then compare against a snapshot whose record differs).

`search.py:219`: `over = engine.combo if facets else ORDER`. Update `test_facets_equal.py:150` to `assert sorted(engine.combo) == sorted(engine.filter_fields)` and `FACET_FIELDS == COMBO`. Update `test_group_counts.py:1046` and `bench/exclusions_alternate.py:35` to `engine.combo`.

- [ ] **Step 4: Run the full backend suite**

Run: `uv run pytest backend/tests -q -n auto`. Then `make openapi`, if `Facets` changed through `FACET_FIELDS`; the contract part is Task 5. Then `make lint`. Expected: PASS apart from Task 5's contract staleness. If `test_contract_v1`/the snapshot fails here only because `Facets` lacks `abstract_kind`, do Task 5's `Facets` step now and note it.

- [ ] **Step 5: Commit**

```bash
git add -A backend
git commit -m "feat(engine): index schema 4 stores abstract_kind as a raw fast field; facets and combos per engine; schema 3 still served (decision-049)"
```

---

### Task 5: API contract and exports: facets, hits, `/meta`, CSV/JSONL/RIS

**Files:**
- Modify: `backend/src/openproceedings/api/models.py`:
  - `Facets.abstract_kind: dict[str, int] | None`;
  - `Hit.abstract_kind: AbstractKind`;
  - `Vocabularies.abstract_kind: list[AbstractKind]`;
  - docs constants.
- Modify: `backend/src/openproceedings/api/search.py` (build `Facets` with `abstract_kind` or None; `Hit.abstract_kind` from the display record)
- Modify: `backend/src/openproceedings/api/meta.py` (`values` gains `abstract_kind`)
- Modify: `backend/src/openproceedings/api/openapi.py` (`OPEN_ENUMS["abstract kind"] = frozenset(ABSTRACT_KINDS)`)
- Modify: `backend/src/openproceedings/export.py`:
  - `CSV_COLUMNS` appends `"abstract_kind"` **last**;
  - the CSV row and the JSONL key from the display record;
  - module docstring.
- Test: `backend/tests/contract/test_abstract_kind_api.py` (new); `backend/tests/unit/test_export.py` (column order)

**Interfaces:**
- Produces:
  - `/search` facets carry `abstract_kind` (null on schema 3);
  - each hit carries `abstract_kind`;
  - `/papers/{id}` carries it (Task 2's computed field);
  - `/meta.values.abstract_kind == ["official", "openalex", "none"]`;
  - CSV's last column is `abstract_kind`;
  - JSONL records carry `abstract_kind`;
  - RIS `N1  - Abstract source: OpenAlex <url>` (Task 2's `ORIGIN_NAMES`).

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/contract/test_abstract_kind_api.py
"""`abstract_kind` through the API (spec 04; decision-049). Uses the contract suite's app builder (`build`,
`point_current`, `make_app` from tests/contract/test_records.py) over the abstract-kinds corpus."""

import csv
import io
import json

from fastapi.testclient import TestClient

from tests.contract.test_records import build, make_app, point_current
from tests.fixtures.corpus import abstract_kinds

CORPUS = abstract_kinds.records()


def _app(tmp_path, schema: str = "4", corpus=CORPUS):
    data = tmp_path / "data"
    version = build(corpus, data / "snapshots", "snap", data / "indexes", schema_version=schema)
    point_current(data, version)
    return make_app(data), version


def test_hits_facets_and_meta_carry_the_kind(tmp_path) -> None:
    app, _ = _app(tmp_path)
    with TestClient(app) as client:
        body = client.get("/api/v1/search", params={"q": "abstract_kind:openalex"}).json()
        assert body["total"] > 0 and {h["abstract_kind"] for h in body["hits"]} == {"openalex"}
        assert set(body["facets"]["abstract_kind"]) == {"official", "openalex", "none"}  # disjunctive
        assert client.get("/api/v1/meta").json()["values"]["abstract_kind"] == ["official", "openalex", "none"]
        rid = body["hits"][0]["id"]
        paper = client.get(f"/api/v1/papers/{rid}").json()
        assert paper["abstract_kind"] == "openalex"


def test_search_naming_abstract_kind_on_a_schema_3_index_is_422(tmp_path) -> None:
    app, version = _app(tmp_path, "3", [r for r in CORPUS if r.abstract_kind != "openalex"])
    with TestClient(app) as client:
        got = client.get("/api/v1/search", params={"q": "trust abstract_kind:official"})
    assert got.status_code == 422 and got.json()["code"] == "FIELD_NOT_INDEXED"
    assert version in got.json()["message"]


def test_schema_3_facets_say_abstract_kind_null(tmp_path) -> None:
    app, _ = _app(tmp_path, "3", [r for r in CORPUS if r.abstract_kind != "openalex"])
    with TestClient(app) as client:
        body = client.get("/api/v1/search", params={"q": "trust"}).json()
    assert body["facets"]["abstract_kind"] is None and {h["abstract_kind"] for h in body["hits"]} <= {"official", "none"}


def test_a_pinned_schema_3_export_naming_abstract_kind_is_422(tmp_path) -> None:
    data = tmp_path / "data"
    plain = [r for r in CORPUS if r.abstract_kind != "openalex"]
    old = build(plain, data / "snapshots", "snap", data / "indexes", schema_version="3")
    new = build(CORPUS, data / "snapshots", "snap2", data / "indexes")
    point_current(data, new)
    with TestClient(make_app(data, pinned_indexes=(old,))) as client:  # the app option that loads a pinned index
        got = client.get("/api/v1/export", params={"q": "abstract_kind:none", "format": "csv", "index_version": old})
    assert got.status_code == 422 and got.json()["code"] == "FIELD_NOT_INDEXED"


def test_csv_and_jsonl_carry_the_kind_last(tmp_path) -> None:
    app, _ = _app(tmp_path)
    with TestClient(app) as client:
        text = client.get("/api/v1/export", params={"q": "abstract_kind:openalex", "format": "csv"}).text
        lines = client.get("/api/v1/export", params={"q": "abstract_kind:openalex", "format": "jsonl"}).text
        ris = client.get("/api/v1/export", params={"q": "abstract_kind:openalex", "format": "ris"}).text
    rows = list(csv.reader(io.StringIO(text.removeprefix("\ufeff"))))
    assert rows[0][-1] == "abstract_kind" and {r[-1] for r in rows[1:]} == {"openalex"}
    assert {r[rows[0].index("abstract_source")] for r in rows[1:]} == {"openalex"}  # the claim source column
    assert {json.loads(x)["abstract_kind"] for x in lines.splitlines() if x} == {"openalex"}
    assert "N1  - Abstract source: OpenAlex" in ris
```

(Use the exact names the contract suite exposes for building a pinned app; `make_app`'s pinned option is the one `test_pinned.py` uses.)

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest backend/tests/contract/test_abstract_kind_api.py -q`. Expected: FAIL (`KeyError: 'abstract_kind'`).

- [ ] **Step 3: Implement**

`models.py`:

```python
ABSTRACT_KIND_DOC = (
    "Where the abstract came from (decision-049): `official` (the venue's own source: OpenReview, the "
    "proceedings, ojs.aaai.org, PMLR, the FAccT site), `openalex` (filled from OpenAlex only for an AAAI, AIES or "
    "FAccT paper no official source gives one), or `none`. The `abstract_kind:` filter selects by it. Distinct "
    "from `abstract_source`, the claim the abstract came from."
)
FACET_KIND_DOC = "Counts per `abstract_kind`; null on an index built before schema 4 (it has no such field)."


class Facets(Model):
    ...
    abstract_kind: dict[str, int] | None = Field(description=FACET_KIND_DOC)  # decision-049: additive
```

`Hit` gains `abstract_kind: AbstractKind = Field(description=ABSTRACT_KIND_DOC)` after `abstract_note`. `Vocabularies` gains `abstract_kind: list[AbstractKind]`.

`api/search.py`: `facets=Facets.model_validate({**found.facets, "abstract_kind": found.facets.get("abstract_kind")})`; the hit builder sets `abstract_kind=r["abstract_kind"]`. `meta.py`: `"abstract_kind": list(ABSTRACT_KINDS)`. `openapi.py`: the open enum entry, with the comment "decision-049: a later fallback source adds a value".

`export.py`:
- `CSV_COLUMNS = (…, "abstract_note", "abstract_kind")`, and the comment line "(… then decision-049's kind, appended last)";
- `_csv`: `"abstract_kind": r["abstract_kind"]`;
- JSONL: the same key;
- the docstring names both.

The RIS `N1` line needs no code: `credit` reads `ORIGIN_NAMES`.

- [ ] **Step 4: Run, regenerate, run the frontend**

Run: `uv run pytest backend/tests -q -n auto`. Then `make openapi`, regenerate the record, compare and coverage fixtures their staleness tests name, then `npm test --workspace frontend`. Update the frontend test stubs that build a `Facets` or `Hit` (`frontend/src/test/api-stub.tsx`; `grep -rn "facets:" frontend/src --include=*.ts*`) with `abstract_kind`. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A backend frontend
git commit -m "feat(api): abstract_kind on hits, papers, facets (null before schema 4), /meta and CSV/JSONL exports; OpenAlex named in RIS (decision-049)"
```

---

### Task 6: HTTP layer: request headers that are never cached or logged

**Files:**
- Modify: `backend/src/openproceedings/ingest/sources/http.py` (`Fetcher.__init__`, `_page`)
- Test: `backend/tests/unit/ingest/test_http.py` (append)

**Interfaces:**
- Produces: `Fetcher(..., user_agent=None, headers: Mapping[str, str] | None = None)`. Each header is sent on every request and never reaches a cache entry, a `Page`, a log line or an exception message.

- [ ] **Step 1: Write the failing test**

```python
OPENALEX = "https://api.openalex.org/works?filter=doi:10.1145/3593013.3594011&per-page=50"


def test_secret_headers_are_sent_and_never_stored_or_logged(tmp_path: Path, caplog) -> None:
    sent: list[dict[str, str]] = []

    def transport(request: Request, timeout: float) -> Response:
        sent.append(dict(request.headers))
        return response('{"meta": {"count": 0}, "results": []}', headers={"content-type": "application/json"})

    caplog.set_level(logging.DEBUG)
    f, _ = fetcher(tmp_path, transport, frozenset({"api.openalex.org"}), min_interval=0.0,
                   accept="application/json", expect="json", keep_query=True,
                   headers={"Authorization": "Bearer sk-test-secret"})  # fmt: skip
    assert f.get(OPENALEX).ok
    assert sent[0]["Authorization"] == "Bearer sk-test-secret"
    assert "sk-test-secret" not in caplog.text
    assert all("sk-test-secret" not in p.read_text() for p in tmp_path.rglob("*.json"))


def test_a_refused_request_never_names_a_secret_header(tmp_path: Path) -> None:
    t = FakeTransport({canonical(OPENALEX, keep_query=True): [response("", status=403)]})
    f, _ = fetcher(tmp_path, t, frozenset({"api.openalex.org"}), min_interval=0.0, attempts=1,
                   accept="application/json", expect="json", keep_query=True,
                   headers={"Authorization": "Bearer sk-test-secret"})  # fmt: skip
    with pytest.raises(HTTPRefused) as e:
        f.get(OPENALEX)
    assert "sk-test-secret" not in str(e.value)
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest backend/tests/unit/ingest/test_http.py -q -k secret`. Expected: FAIL (`unexpected keyword argument 'headers'`).

- [ ] **Step 3: Implement**

`Fetcher.__init__` gains `headers: Mapping[str, str] | None = None`, stored as `self._headers = dict(headers or {})`. In `_page`:

```python
        request = Request("GET", url, {**self._headers, "User-Agent": self.user_agent, "Accept": self.policy.accept})
```

`Request` must not echo its headers in its `repr` if it is a dataclass: give the headers field `repr=False`. The class docstring: "`headers`: sent on every request (an API key); never in the URL, so never in the cache key, a cache entry, a `Page`, a log line or an error".

- [ ] **Step 4: Run and commit**

Run: `uv run pytest backend/tests/unit/ingest/test_http.py backend/tests/unit/ingest/test_fetch.py -q`. Expected: PASS.

```bash
git add backend/src/openproceedings/ingest/sources/http.py backend/tests/unit/ingest/test_http.py
git commit -m "feat(http): a fetcher's own request headers (an API key), never cached, logged or quoted in an error"
```

---

### Task 7: OpenAlex parsing: works, the inverted-index rebuild, hygiene, the listing table

**Files:**
- Create: `backend/src/openproceedings/ingest/openalex_table.py`, `backend/src/openproceedings/ingest/openalex_sources.toml` (header only; rows in Task 12)
- Create: `backend/src/openproceedings/ingest/sources/openalex.py` (constants, URLs, `Work`, `parse_works`, `rebuild`, `bare_doi`, `abstract_of`, `api_key`)
- Create: `backend/tests/unit/ingest/openalex/__init__.py`, `api.py` (builders of OpenAlex answers), `test_openalex_parse.py`, `test_openalex_table.py`
- Modify: `.env.example` (`OPENALEX_API_KEY=`)

**Interfaces:**
- Produces:
  - `openalex_table.Listing(venue, year, source_ids: tuple[str, ...], works: int, verified: date, source: str)`;
  - `openalex_table.Table(listings: Mapping[tuple[str, int], Listing])`, with `openalex_table.load(text)` and `openalex_table.TABLE`;
  - constants `openalex.SOURCE = "openalex"`, `CACHE_DIR = "openalex"`, `HOST = "api.openalex.org"`, `HOSTS`, `MIN_INTERVAL = 1.0`, `BATCH = 50`, `PER_PAGE = 200`, `SELECT`, `KEY_ENV = "OPENALEX_API_KEY"`;
  - URL builders `openalex.doi_url(dois)`, `openalex.listing_url(row, cursor="*")`, `openalex.work_url(work_id)`, `openalex.work_page(work_id)`;
  - `openalex.Work(id, doi, title, year, sources, inverted)`;
  - `openalex.WorksPage(works, total, next_cursor)`;
  - `openalex.parse_works(text) -> WorksPage`;
  - `openalex.Rebuilt(text: str | None, refused: str | None)` and `openalex.rebuild(inverted) -> Rebuilt`;
  - `openalex.abstract_of(work) -> tuple[Cleaned | None, str | None]` (cleaned text, refusal);
  - `openalex.bare_doi(value) -> str | None`;
  - `openalex.api_key(environ, dotenv) -> str | None`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/unit/ingest/openalex/api.py
"""OpenAlex /works answers in the shape api.openalex.org serves (checked live in Task 12); synthetic text."""

import json
from typing import Any

JSON = {"content-type": "application/json"}


def inverted(text: str) -> dict[str, list[int]]:
    out: dict[str, list[int]] = {}
    for i, w in enumerate(text.split()):
        out.setdefault(w, []).append(i)
    return out


def work(wid: str, doi: str | None, *, title: str = "A Paper", year: int = 2023, text: str | None = "An abstract.",
         sources: tuple[str, ...] = ("S1",), raw: Any = None) -> dict[str, Any]:  # fmt: skip
    return {"id": f"https://openalex.org/{wid}", "doi": None if doi is None else f"https://doi.org/{doi}",
            "title": title, "publication_year": year,
            "primary_location": {"source": {"id": f"https://openalex.org/{sources[0]}"}} if sources else None,
            "abstract_inverted_index": raw if raw is not None else (None if text is None else inverted(text))}


def page(*works: dict[str, Any], count: int | None = None, cursor: str | None = None) -> str:
    meta = {"count": len(works) if count is None else count, "per_page": 200}
    if cursor is not None:
        meta["next_cursor"] = cursor
    return json.dumps({"meta": meta, "results": list(works)})
```

```python
# backend/tests/unit/ingest/openalex/test_openalex_parse.py
import pytest

from openproceedings.ingest.sources import openalex
from openproceedings.ingest.sources.common import CrawlError

from tests.unit.ingest.openalex import api


def test_rebuild_orders_by_position() -> None:
    assert openalex.rebuild({"world": [1], "hello": [0], "again": [2]}) == openalex.Rebuilt("hello world again", None)


def test_rebuild_refuses_a_gap() -> None:
    assert openalex.rebuild({"hello": [0], "again": [2]}) == openalex.Rebuilt(None, "inverted_gap")
    assert openalex.rebuild({"hello": [1]}) == openalex.Rebuilt(None, "inverted_gap")  # not from 0


def test_rebuild_refuses_two_words_at_one_position() -> None:
    assert openalex.rebuild({"a": [0], "b": [0, 1]}) == openalex.Rebuilt(None, "inverted_conflict")


def test_rebuild_keeps_a_word_listed_twice_at_its_position_once() -> None:
    assert openalex.rebuild({"the": [0, 2, 2], "cat": [1]}) == openalex.Rebuilt("the cat the", None)


@pytest.mark.parametrize("raw", [[], "x", {"": [0]}, {"a": []}, {"a": [-1]}, {"a": [True]}, {"a": [0.0]},
                                 {"a": "0"}, {1: [0]}, {"a": [10**7]}])  # fmt: skip
def test_rebuild_refuses_unreadable_shapes(raw) -> None:
    got = openalex.rebuild(raw)
    assert got.text is None and got.refused in ("inverted_unreadable", "inverted_gap")


def test_no_inverted_index_is_no_abstract_not_a_refusal() -> None:
    assert openalex.rebuild(None) == openalex.Rebuilt(None, None)


@pytest.mark.parametrize(("text", "kept"), [
    ("An abstract \x02with a control.", "An abstract with a control."),
    ("… a snippet that starts with an ellipsis", None),
    ("ends with an ellipsis …", None),
])  # fmt: skip
def test_hygiene_is_every_abstracts(text: str, kept: str | None) -> None:
    w = openalex.parse_works(api.page(api.work("W1", "10.1/x", text=text))).works[0]
    cleaned, refused = openalex.abstract_of(w)
    assert (cleaned.text if cleaned else None) == kept
    assert refused == (None if kept else "abstract_unusable")


def test_parse_works_reads_ids_dois_sources_and_the_cursor() -> None:
    page = openalex.parse_works(api.page(api.work("W1", "10.1145/3593013.3594011", sources=("S9",)), count=7,
                                         cursor="IlsxNjk"))  # fmt: skip
    (w,) = page.works
    assert (w.id, w.doi, w.sources, page.total, page.next_cursor) == (
        "W1", "10.1145/3593013.3594011", ("S9",), 7, "IlsxNjk")


@pytest.mark.parametrize("text", ["not json", "[]", '{"results": []}', '{"meta": {}, "results": {}}',
                                  '{"meta": {"count": 1}, "results": [{"doi": null}]}'])  # fmt: skip
def test_an_answer_that_is_not_a_work_list_stops(text: str) -> None:
    with pytest.raises(CrawlError) as e:
        openalex.parse_works(text)
    assert e.value.reason == "openalex_unreadable"


@pytest.mark.parametrize(("value", "doi"), [("https://doi.org/10.1145/ABC.1", "10.1145/abc.1"),
    ("10.1609/aaai.v34i01.5000", "10.1609/aaai.v34i01.5000"), ("https://doi.org/", None), (None, None),
    ("doi:10.1/x", None), ("https://doi.org/10.1/x y", None)])  # fmt: skip
def test_bare_doi(value, doi) -> None:
    assert openalex.bare_doi(value) == doi


def test_the_doi_url_is_sorted_and_capped() -> None:
    assert openalex.doi_url(["10.1/b", "10.1/a"]) == (
        f"https://api.openalex.org/works?filter=doi:10.1/a|10.1/b&per-page=50&select={openalex.SELECT}")
    with pytest.raises(ValueError):
        openalex.doi_url([f"10.1/{i}" for i in range(51)])


def test_the_key_is_optional_and_read_from_the_environment_first(tmp_path) -> None:
    env = tmp_path / ".env"
    env.write_text("OPENALEX_API_KEY=from-dotenv\n")
    assert openalex.api_key({}, None) is None
    assert openalex.api_key({}, env) == "from-dotenv"
    assert openalex.api_key({"OPENALEX_API_KEY": "from-env"}, env) == "from-env"
    assert openalex.api_key({"OPENALEX_API_KEY": "  "}, None) is None
```

`test_openalex_table.py` follows `test_ojs_table.py`: a `GOOD` TOML with one `[[listing]]` (`venue = "AAAI"`, `year = 1990`, `source_ids = ["S4306420609"]`, `works = 3`, `verified`, `source`). Refused edits:
- venue `"ICML"` ("AAAI, AIES or FAccT");
- year 2010 ("only years whose records carry no DOI": the listing route is for `record.DBLP_YEARS["AAAI"]`);
- a source id `"X1"` ("source id");
- `works = 0` ("positive");
- a duplicate row ("listed twice").

Plus `test_the_shipped_table_loads`.

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest backend/tests/unit/ingest/openalex -q`. Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement**

`openalex_table.py` is in `ojs_table.py`'s style. Docstring: the listing route's purpose (DOI-less dblp AAAI records, 1980–2008), why per venue-year source ids (OpenAlex files old AAAI proceedings under per-era sources), that `works` is the count verified on the date, and that a different count stops the crawl.

`sources/openalex.py`. Its module docstring covers:
- scope: AAAI, AIES and FAccT records whose resolved abstract is null;
- the two routes and the refusals (Planner decisions);
- the extract and its replay (Task 8);
- the claim and its attribution;
- the optional key (a header, never a URL);
- that no contact address is sent.

```python
SOURCE: Source = "openalex"
CACHE_DIR = "openalex"
HOST = "api.openalex.org"
HOSTS = frozenset({HOST})
MIN_INTERVAL = 1.0  # sequential, a second apart (OpenAlex refuses more than 100 requests a second; be gentle)
BATCH = 50  # DOIs per request (OpenAlex takes up to 100 OR values a filter; 50 keeps URLs short)
PER_PAGE = 200
SELECT = "id,doi,title,publication_year,primary_location,abstract_inverted_index"
KEY_ENV = "OPENALEX_API_KEY"
MAX_POSITIONS = 25_000  # more words than any abstract under caps.MAX_ABSTRACT characters: refused, not allocated
_DOI = re.compile(r"10\.[0-9]+(?:\.[0-9]+)*/\S+")
_ID = re.compile(r"(?:https://openalex\.org/)?(W[0-9]+)")
_SOURCE_ID = re.compile(r"(?:https://openalex\.org/)?(S[0-9]+)")


@dataclass(frozen=True, slots=True)
class Work:
    id: str  # `W…`
    doi: str | None  # bare, lower-case
    title: str | None
    year: int | None
    sources: tuple[str, ...]  # `S…` of the primary location
    inverted: Any  # the raw abstract_inverted_index (rebuilt at replay: `rebuild`)


@dataclass(frozen=True, slots=True)
class Rebuilt:
    text: str | None
    refused: str | None  # inverted_gap | inverted_conflict | inverted_unreadable


def rebuild(inverted: object) -> Rebuilt:
    """The abstract an `abstract_inverted_index` encodes, its words in position order. A position held by two
    different words, a gap, or anything not `{word: [position, …]}` is refused: no abstract with a silent hole."""
    if inverted is None:
        return Rebuilt(None, None)
    if not isinstance(inverted, dict) or not inverted:
        return Rebuilt(None, "inverted_unreadable")
    at: dict[int, str] = {}
    for word, positions in inverted.items():
        if not isinstance(word, str) or not word.strip() or not isinstance(positions, list) or not positions:
            return Rebuilt(None, "inverted_unreadable")
        for p in positions:
            if type(p) is not int or not 0 <= p < MAX_POSITIONS:
                return Rebuilt(None, "inverted_unreadable")
            if at.setdefault(p, word) != word:
                return Rebuilt(None, "inverted_conflict")
    if max(at) != len(at) - 1:  # keys are distinct non-negative ints: dense from 0 exactly when max = n - 1
        return Rebuilt(None, "inverted_gap")
    return Rebuilt(" ".join(at[i] for i in range(len(at))), None)


def abstract_of(work: Work) -> tuple[Cleaned | None, str | None]:
    """The work's abstract as a record may hold it (`common.clean_abstract`: controls, the `…` snippet rule,
    placeholders; the caps apply when the record is built), or None with why (`rebuild`'s refusal, or
    `abstract_unusable`); (None, None) when OpenAlex has no abstract."""
    rebuilt = rebuild(work.inverted)
    if rebuilt.text is None:
        return None, rebuilt.refused
    cleaned = clean_abstract(rebuilt.text)
    return (cleaned, None) if cleaned.text is not None else (None, "abstract_unusable")


def bare_doi(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    doi = value.strip().removeprefix("https://doi.org/").removeprefix("http://doi.org/").lower()
    return doi if _DOI.fullmatch(doi) else None


def doi_url(dois: Sequence[str]) -> str:
    if not 0 < len(dois) <= BATCH:
        raise ValueError(f"a DOI batch holds 1 to {BATCH} DOIs")
    return f"https://{HOST}/works?filter=doi:{'|'.join(sorted(dois))}&per-page={BATCH}&select={SELECT}"


def listing_url(row: Listing, cursor: str = "*") -> str:
    return (f"https://{HOST}/works?filter=primary_location.source.id:{'|'.join(row.source_ids)},"
            f"publication_year:{row.year}&per-page={PER_PAGE}&select={SELECT}&cursor={quote(cursor, safe='')}")  # fmt: skip


def work_url(work_id: str) -> str:  # the claim's url (OpenAlex's API)
    return f"https://{HOST}/works/{work_id}"


def work_page(work_id: str) -> str:  # named in the claim's evidence (OpenAlex's page for the work)
    return f"https://openalex.org/{work_id}"
```

`parse_works(text)`:
- `json.loads` fails, or the answer is not a dict with a dict `meta` holding an int `count` and a list `results` → `CrawlError(…, reason="openalex_unreadable")`.
- Each result must be a dict with an `id` matching `_ID`; otherwise `openalex_unreadable`.
- `Work(id, bare_doi(r.get("doi")), r.get("title") if isinstance(str) else None, year if int else None, tuple of _SOURCE_ID matches of primary_location.source.id, r.get("abstract_inverted_index"))`.
- `next_cursor = meta.get("next_cursor") or None`.
- Error messages never quote the body.

`api_key(environ, dotenv)`: as B's `crossref.contact`, through `openreview_client.read_dotenv`, but optional. It returns the stripped value or None, and never raises.

`.env.example`: `# an optional OpenAlex API key (op ingest openalex, op eval openalex): raises the daily budget; never committed` then `OPENALEX_API_KEY=`.

- [ ] **Step 4: Run and commit**

Run: `uv run pytest backend/tests/unit/ingest/openalex -q` and `make lint`. Expected: PASS.

```bash
git add -A backend .env.example
git commit -m "feat(openalex): work parsing, the inverted-index rebuild (gaps and conflicts refused), abstract hygiene, the AAAI listing table loader"
```

---

### Task 8: OpenAlex harvest, the pinned extract, `op ingest openalex`, and the fill in `op snapshot build`

**Files:**
- Modify: `backend/src/openproceedings/ingest/sources/openalex.py`:
  - `FillReport`, `Extract`, `harvest`, `write_extract`, `load_extract`;
  - `candidates`, `fill`, `apply`.
- Modify: `backend/src/openproceedings/ingest/sources/crawl.py` (`openalex_fetcher`, `ingest_openalex`); not in `SOURCES`
- Modify: `backend/src/openproceedings/cli.py` (`op ingest openalex`)
- Modify: `backend/src/openproceedings/ingest/snapshot.py` (`build`: `openalex.apply` after reconcile, before `withhold`; module docstring)
- Create: `backend/tests/unit/ingest/openalex/test_openalex_fill.py`, `test_openalex_crawl.py`; Modify: `backend/tests/unit/test_cli.py`, `backend/tests/unit/ingest/test_snapshot.py`

**Interfaces:**
- Produces:
  - **Extract.** `openalex.Lookup(route: Literal["doi", "listing"], url, fetched_at, requested: tuple[str, ...], venue: str | None, year: int | None, works: tuple[Work, ...])` and `openalex.Extract(sha256, lookups)`.
  - **Fill report.** `openalex.FillReport(Report)`, with `manifest_key = "fills"` and fields:
    - `extract`, `candidates`;
    - `attached_doi`, `attached_title`;
    - `official_won`, `not_queried`;
    - `refused: Counter[str]`, keyed by `doi_unmatched`, `doi_duplicate`, `doi_mismatch`, `title_unmatched`, `title_ambiguous`, `inverted_gap`, `inverted_conflict`, `inverted_unreadable`, `abstract_unusable`, `no_abstract`.
  - **Functions.**
    - `openalex.candidates(records) -> list[PaperRecord]` (venue in `OPENALEX_VENUES`, abstract None);
    - `openalex.harvest(records, fetcher, *, refresh=False, table=None) -> tuple[Lookup, ...]`;
    - `openalex.write_extract(cache, lookups) -> str` (its sha256), `openalex.load_extract(cache) -> Extract | None`;
    - `openalex.fill(records, extract, table=None) -> tuple[list[PaperRecord], FillReport]`;
    - `openalex.apply(result: DedupResult, cache) -> tuple[DedupResult, list[FillReport]]`;
    - `crawl.openalex_fetcher(cache, *, offline, transport=None, min_interval=DEFAULT_INTERVAL, key=None)`;
    - `crawl.ingest_openalex(cache, *, offline=False, dry_run=False, refresh=False, transport=None, min_interval=…, table=None, key=None) -> dict[str, Any]`.
  - **CLI.** `op ingest openalex [--dry-run | --offline] [--refresh] [--delay S]`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/unit/ingest/openalex/test_openalex_fill.py
"""The OpenAlex fill (decision-049): replayed from the pinned extract after dedup, only into a null abstract of
an AAAI, AIES or FAccT record; DOI exact or one-to-one title key; refusals counted, never forced."""

from datetime import UTC, datetime

import pytest

from openproceedings.ingest import openalex_table
from openproceedings.ingest.dedup import attribution, resolve
from openproceedings.ingest.record import Claim, PaperRecord
from openproceedings.ingest.sources import openalex

from tests.unit.ingest.openalex import api

T = datetime(2026, 10, 10, tzinfo=UTC)
D1, D2 = "10.1145/3593013.3594011", "10.1145/3593013.3594012"
TABLE = openalex_table.load("""
[[listing]]
venue = "AAAI"
year = 1990
source_ids = ["S77"]
works = 3
verified = 2026-10-10
source = "test"
""")


def rec(rid: str, venue: str, year: int, *, title: str = "A Paper", doi: str | None = None,
        abstract: tuple[str, str] | None = None, source: str = "crossref") -> PaperRecord:  # fmt: skip
    fields = [("title", title), ("venue", venue), ("year", year), ("track", "main"), ("status", "accepted")]
    if doi:
        fields += [("urls.doi", doi), ("urls.proceedings", f"https://doi.org/{doi}")]
    claims = [Claim(field=f, value=v, source=source, fetched_at=T, evidence="t") for f, v in fields]
    if abstract:
        claims.append(Claim(field="abstract", value=abstract[0], source=abstract[1], fetched_at=T, evidence="t"))
    return resolve(rid, claims)[0]


def doi_lookup(*works, requested=(D1, D2)) -> openalex.Lookup:
    parsed = openalex.parse_works(api.page(*works)).works
    return openalex.Lookup("doi", openalex.doi_url(list(requested)), T, tuple(sorted(requested)), None, None, parsed)


def ext(*lookups) -> openalex.Extract:
    return openalex.Extract("0" * 64, tuple(lookups))


def test_a_doi_match_fills_the_null_abstract_credited_to_the_papers_page() -> None:
    r = rec("op:facct:2023:doi-3593013.3594011", "FAccT", 2023, doi=D1)
    (out,), report = openalex.fill([r], ext(doi_lookup(api.work("W1", D1, text="An OpenAlex abstract."))), TABLE)
    assert out.abstract == "An OpenAlex abstract." and out.abstract_kind == "openalex"
    (claim,) = out.claims("abstract")
    assert claim.url == "https://api.openalex.org/works/W1" and "https://openalex.org/W1" in claim.evidence
    att = attribution(out.abstract, out.provenance, forum=None, proceedings=out.urls.proceedings, native=out.native)
    assert att is not None and att.url == f"https://doi.org/{D1}"
    assert (report.candidates, report.attached_doi) == (1, 1)


@pytest.mark.parametrize(("rid", "venue", "year", "source"), [
    ("op:icml:2005:dblp-Smith05", "ICML", 2005, "dblp"), ("op:iaseai:2026:ojs-40000", "IASEAI", 2026, "ojs")])
def test_other_venues_are_never_touched(rid, venue, year, source) -> None:
    r = rec(rid, venue, year, doi=D1, source=source)
    (out,), report = openalex.fill([r], ext(doi_lookup(api.work("W1", D1))), TABLE)
    assert out is r and report.candidates == 0


def test_an_official_abstract_is_never_overwritten() -> None:
    r = rec("op:facct:2022:doi-3593013.3594011", "FAccT", 2022, doi=D1, abstract=("Official.", "facct_site"))
    (out,), report = openalex.fill([r], ext(doi_lookup(api.work("W1", D1, text="Other."))), TABLE)
    assert out is r and out.abstract_kind == "official" and report.official_won == 1


def test_an_official_abstract_in_a_later_crawl_wins_over_the_extract() -> None:
    """The pinned extract still holds OpenAlex's text; the new build's record has OJS's: the official one stays."""
    lookup = doi_lookup(api.work("W1", D1, text="An OpenAlex abstract."))
    before = rec("op:aaai:2020:ojs-1", "AAAI", 2020, doi=D1, source="ojs")
    (filled,), _ = openalex.fill([before], ext(lookup), TABLE)
    later = rec("op:aaai:2020:ojs-1", "AAAI", 2020, doi=D1, source="ojs", abstract=("An official abstract.", "ojs"))
    (kept,), report = openalex.fill([later], ext(lookup), TABLE)
    assert (filled.abstract_kind, kept.abstract_kind, kept.abstract) == ("openalex", "official", "An official abstract.")
    assert report.official_won == 1 and report.attached_doi == 0


def test_a_truncated_openalex_doi_attaches_nothing() -> None:
    r = rec("op:facct:2025:doi-3715275.3732001", "FAccT", 2025, doi="10.1145/3715275.3732001")
    lookup = doi_lookup(requested=("10.1145/3715275.3732001",))  # OpenAlex holds `…373200`: the filter finds none
    (out,), report = openalex.fill([r], ext(lookup), TABLE)
    assert out.abstract is None and report.refused["doi_unmatched"] == 1


def test_duplicate_works_with_differing_texts_attach_nothing() -> None:
    r = rec("op:facct:2023:doi-3593013.3594011", "FAccT", 2023, doi=D1)
    lookup = doi_lookup(api.work("W1", D1, text="One text."), api.work("W2", D1, text="Another text."))
    (out,), report = openalex.fill([r], ext(lookup), TABLE)
    assert out.abstract is None and report.refused["doi_duplicate"] == 1


def test_duplicate_works_with_one_text_attach_once_citing_both() -> None:
    r = rec("op:facct:2023:doi-3593013.3594011", "FAccT", 2023, doi=D1)
    lookup = doi_lookup(api.work("W2", D1, text="Same text."), api.work("W1", D1, text="Same  text."))
    (out,), _ = openalex.fill([r], ext(lookup), TABLE)
    (claim,) = out.claims("abstract")
    assert out.abstract == "Same text." and claim.url.endswith("/W1") and "W2" in claim.evidence


def test_a_work_for_a_doi_not_asked_is_refused() -> None:
    r = rec("op:facct:2023:doi-3593013.3594011", "FAccT", 2023, doi=D1)
    lookup = doi_lookup(api.work("W9", "10.1145/9999999.1"), requested=(D1,))
    (out,), report = openalex.fill([r], ext(lookup), TABLE)
    assert out.abstract is None and report.refused["doi_mismatch"] == 1 and report.refused["doi_unmatched"] == 1


def _listing(*works) -> openalex.Lookup:
    row = TABLE.listings[("AAAI", 1990)]
    return openalex.Lookup("listing", openalex.listing_url(row), T, (), "AAAI", 1990,
                           openalex.parse_works(api.page(*works)).works)


def test_a_doi_less_record_matches_one_work_by_exact_title_key() -> None:
    r = rec("op:aaai:1990:dblp-Smith90", "AAAI", 1990, title="Planning Under Uncertainty", source="dblp")
    lookup = _listing(api.work("W5", None, title="Planning under uncertainty.", year=1990, text="Old abstract."),
                      api.work("W6", None, title="Planning under uncertainty, revisited", year=1990))
    (out,), report = openalex.fill([r], ext(lookup), TABLE)
    assert out.abstract == "Old abstract." and report.attached_title == 1
    assert "exact title key" in out.claims("abstract")[0].evidence


def test_two_works_or_two_records_sharing_a_title_key_attach_nothing() -> None:
    a = rec("op:aaai:1990:dblp-A90", "AAAI", 1990, title="Learning", source="dblp")
    b = rec("op:aaai:1990:dblp-B90", "AAAI", 1990, title="Learning.", source="dblp")
    one = _listing(api.work("W5", None, title="Learning", year=1990))
    two = _listing(api.work("W5", None, title="Learning", year=1990), api.work("W6", None, title="learning", year=1990))
    (x, y), report = openalex.fill([a, b], ext(one), TABLE)
    assert x.abstract is None and y.abstract is None and report.refused["title_ambiguous"] == 2
    (z,), report = openalex.fill([a], ext(two), TABLE)
    assert z.abstract is None and report.refused["title_ambiguous"] == 1


def test_a_title_match_whose_doi_is_another_records_is_refused() -> None:
    r = rec("op:aaai:1990:dblp-A90", "AAAI", 1990, title="Learning", source="dblp")
    other = rec("op:aaai:1991:dblp-B91", "AAAI", 1991, title="Other", source="dblp", doi="10.1609/x.1")
    lookup = _listing(api.work("W5", "10.1609/x.1", title="Learning", year=1990))
    (out, _o), report = openalex.fill([r, other], ext(lookup), TABLE)
    assert out.abstract is None and report.refused["doi_mismatch"] == 1


def test_a_record_nothing_looked_up_is_counted_not_queried() -> None:
    r = rec("op:aies:2019:doi-3306618.3314200", "AIES", 2019, doi="10.1145/3306618.3314200")
    (_out,), report = openalex.fill([r], ext(), TABLE)
    assert report.not_queried == 1
```

```python
# backend/tests/unit/ingest/openalex/test_openalex_crawl.py
import json
import logging

import pytest

from openproceedings.ingest.sources import crawl, openalex
from openproceedings.ingest.sources.common import CrawlError

from tests.unit.ingest.openalex import api
from tests.unit.ingest.openalex.test_openalex_fill import D1, TABLE, rec
from tests.unit.ingest.proceedings_helpers import FakeTransport, response


def _seed_doi_batch(t: FakeTransport, *works) -> None:
    from openproceedings.ingest.sources.http import canonical
    t.script[canonical(openalex.doi_url([D1]), keep_query=True)] = [response(api.page(*works), headers=api.JSON)]


def test_a_crawl_writes_a_pinned_extract_the_build_replays_offline(tmp_path, monkeypatch) -> None:
    r = rec("op:facct:2023:doi-3593013.3594011", "FAccT", 2023, doi=D1)
    monkeypatch.setattr(crawl, "replay_all", lambda cache: ([r], []))
    t = FakeTransport({})
    _seed_doi_batch(t, api.work("W1", D1, text="An OpenAlex abstract."))
    out = crawl.ingest_openalex(tmp_path, transport=t, min_interval=0, table=openalex_table_empty())
    marker = json.loads((tmp_path / "openalex" / "crawls" / "openalex.json").read_text())
    assert marker == {"source": "openalex", "format": "1", "extract": out["extract"]}
    assert (tmp_path / "openalex" / "extract" / f"{out['extract']}.json").exists()
    extract = openalex.load_extract(tmp_path)
    assert extract is not None and extract.sha256 == out["extract"]
    (filled,), report = openalex.fill([r], extract, openalex_table_empty())
    assert filled.abstract_kind == "openalex"


def test_the_replay_reads_only_the_marked_extract_and_refuses_a_changed_one(tmp_path, monkeypatch) -> None:
    test_a_crawl_writes_a_pinned_extract_the_build_replays_offline(tmp_path, monkeypatch)
    sha = json.loads((tmp_path / "openalex" / "crawls" / "openalex.json").read_text())["extract"]
    (tmp_path / "openalex" / "extract" / ("f" * 64 + ".json")).write_text("{}")  # another extract: ignored
    assert openalex.load_extract(tmp_path).sha256 == sha
    path = tmp_path / "openalex" / "extract" / f"{sha}.json"
    path.chmod(0o644)
    path.write_text(path.read_text().replace("OpenAlex abstract", "Changed abstract"))
    with pytest.raises(CrawlError) as e:
        openalex.load_extract(tmp_path)
    assert e.value.reason == "extract_changed"


def test_no_marker_means_no_fill(tmp_path) -> None:
    assert openalex.load_extract(tmp_path) is None


def test_the_key_goes_in_a_header_and_nowhere_else(tmp_path, monkeypatch, caplog) -> None:
    r = rec("op:facct:2023:doi-3593013.3594011", "FAccT", 2023, doi=D1)
    monkeypatch.setattr(crawl, "replay_all", lambda cache: ([r], []))
    t = FakeTransport({})
    _seed_doi_batch(t, api.work("W1", D1))
    caplog.set_level(logging.DEBUG)
    crawl.ingest_openalex(tmp_path, transport=t, min_interval=0, table=openalex_table_empty(), key="sk-secret")
    assert "sk-secret" not in caplog.text
    assert all("sk-secret" not in p.read_text() for p in tmp_path.rglob("*.json"))
    assert t.requests[0].headers["Authorization"] == "Bearer sk-secret"  # the FakeTransport's request log


def test_a_listing_whose_count_differs_from_the_table_stops(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(crawl, "replay_all", lambda cache: ([], []))
    t = FakeTransport({})
    row = TABLE.listings[("AAAI", 1990)]
    from openproceedings.ingest.sources.http import canonical
    t.script[canonical(openalex.listing_url(row), keep_query=True)] = [
        response(api.page(api.work("W5", None, year=1990), count=2, cursor="c2"), headers=api.JSON)]
    t.script[canonical(openalex.listing_url(row, "c2"), keep_query=True)] = [
        response(api.page(api.work("W6", None, year=1990), count=2), headers=api.JSON)]
    with pytest.raises(CrawlError) as e:  # 2 listed, the table verified 3
        crawl.ingest_openalex(tmp_path, transport=t, min_interval=0, table=TABLE)
    assert e.value.reason == "count_mismatch"


def test_a_dry_run_fetches_nothing_and_writes_no_marker(tmp_path, monkeypatch) -> None:
    r = rec("op:facct:2023:doi-3593013.3594011", "FAccT", 2023, doi=D1)
    monkeypatch.setattr(crawl, "replay_all", lambda cache: ([r], []))
    out = crawl.ingest_openalex(tmp_path, dry_run=True, table=openalex_table_empty())
    assert out["dry_run"] and out["candidates"] == 1 and out["doi_batches"] == 1 and out["requests"] == 0
    assert not (tmp_path / "openalex" / "crawls").exists()


def openalex_table_empty():
    from openproceedings.ingest import openalex_table
    return openalex_table.load("")
```

(`FakeTransport` may need a `requests` log of the `Request`s it saw. Add it in `proceedings_helpers.py` if it has none, alongside `calls`.)

In `test_snapshot.py`, following the file's PMLR/OJS pattern: seed a Crossref FAccT chain (B's helpers), the OpenAlex extract and its marker, then build. Assert:
- the record has the OpenAlex abstract and `abstract_kind == "openalex"`;
- `manifest["sources"]["openalex"]["fills"][0]["attached_doi"] == 1`;
- a takedown listing that id withholds the filled abstract (`withheld` names it, `abstract` null).

In `test_cli.py`:
- `op ingest openalex --offline` dispatches to `ingest_openalex(…, offline=True)`;
- `--dry-run --offline` exits 2.

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest backend/tests/unit/ingest/openalex -q`. Expected: FAIL (`AttributeError: fill`).

- [ ] **Step 3: Implement**

The report:

```python
@dataclass(kw_only=True)
class FillReport(Report):
    """The OpenAlex fill of one snapshot build, replayed from extract `extract` (manifest `sources.openalex.fills`)."""

    extract: str
    candidates: int = 0  # AAAI/AIES/FAccT records whose resolved abstract was null
    attached_doi: int = 0
    attached_title: int = 0
    official_won: int = 0  # records the extract has a work for whose own abstract is official now
    not_queried: int = 0  # candidates no lookup of the extract covered (a DOI not batched; no listing row)
    refused: Counter[str] = field(default_factory=Counter)

    manifest_key: ClassVar[str] = "fills"

    def to_manifest(self) -> dict[str, Any]:
        return {"extract": self.extract, "candidates": self.candidates, "attached_doi": self.attached_doi,
                "attached_title": self.attached_title, "official_won": self.official_won,
                "not_queried": self.not_queried, "refused": dict(sorted(self.refused.items()))}  # fmt: skip
```

**The extract.** `write_extract(cache, lookups)`:
- serializes `{"format": "1", "lookups": [...]}`, with each work as `{"id", "doi", "title", "year", "sources", "abstract_inverted_index"}` and lookups in URL order;
- uses `json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=False)`;
- names the file by the sha256 of those bytes (`storage.write_bytes`), then seals it read-only;
- writes the marker last with `common.write_marker(cache / CACHE_DIR / "crawls", "openalex", {...})`.

`load_extract(cache)`:
- no marker → None;
- a marker whose `format != "1"` or with no `extract` → `CrawlError("crawl_file_invalid")`;
- a missing file → `CrawlError("not_cached", "run op ingest openalex")`;
- bytes that don't hash to the marker's sha → `CrawlError("extract_changed")`;
- malformed JSON → `CrawlError("crawl_file_invalid")`.

**The harvest.** `harvest(records, fetcher, *, refresh, table)`:
- **DOI route.** `cands = candidates(records)`. DOIs: `sorted({d for r in cands if (d := bare_doi(r.urls.doi)) and "|" not in d and "," not in d})`; a DOI holding `|` or `,` is counted `doi_unqueryable` in the crawl output. Chunk them by `BATCH` and `fetcher.get(doi_url(chunk), refresh=refresh)`. A non-200 raises `CrawlError("no_listing")`, and so does an answer with `meta.count > BATCH * 2`, which means the filter was misread. Each chunk becomes a `Lookup("doi", …)`.
- **Listing route.** For each `table.listings` row, walk the cursor chain with B's `crossref._walk` pattern: the chain the cache holds whole, else fresh from `*` with the first page refreshed.
  - A total that moves mid-chain → `listing_changed`.
  - Collected works ≠ `meta.count` → `listing_changed`; ≠ `row.works` → `count_mismatch` (`"OpenAlex {venue} {year}: {n} works under {source_ids}, the table verified {works}: check openalex_sources.toml"`).
  - Each row becomes one `Lookup("listing", …)`, with all its pages' works and the first page's fetch time.

**The fill.** `fill(records, extract, table)`, in record id order:
- Build `by_doi: dict[str, list[tuple[Work, Lookup]]]` over DOI lookups, keeping a work only when its DOI is in `lookup.requested`; any other work counts `doi_mismatch`. Also build `queried = set().union(*requested)`, `listings[(venue, year)] = lookup`, `corpus_dois = {bare_doi(r.urls.doi) for r in records} - {None}`, and `doi_less[(venue, year)]` = the title keys of DOI-less candidates, counted.
- A record outside `OPENALEX_VENUES` passes through untouched.
- A record with an abstract passes through; `official_won += 1` when its DOI is in `by_doi`, or it is DOI-less and its title key has a listing work.
- Otherwise `candidates += 1`.
  - **With a DOI:** none in `queried` → `not_queried`; no works → refused `doi_unmatched`. Otherwise run `abstract_of` on each work:
    - all refused → count the first refusal;
    - any usable: the set of cleaned texts of size > 1 → `doi_duplicate`;
    - else attach, with the lowest work id as url and every id named.
  - **Without a DOI:** no listing → `not_queried`. Else: two DOI-less records share the key → `title_ambiguous`; matching works (`dedup.title_key(w.title) == key and w.year == r.year`) are 0 → `title_unmatched`, > 1 → `title_ambiguous`; one whose `w.doi in corpus_dois` → `doi_mismatch`; else attach.
  - Then the abstract refusals: nothing usable → `no_abstract` or the rebuild refusal.
- To attach:

```python
        claim = Claim(field="abstract", value=cleaned.text, source=SOURCE, url=work_url(first.id),
                      fetched_at=lookup.fetched_at, evidence=pdf_codes_evidence(controls_evidence(
                          f"OpenAlex work {', '.join(work_page(w.id) for w in works)}; matched {how}",
                          cleaned.spaced), cleaned.pdf_codes))  # fmt: skip
        out.append(cap_record(r.model_copy(update={"abstract": cleaned.text, "provenance": (*r.provenance, claim)})))
```

  Here `how` is `f"by DOI {doi}"` or `f"by exact title key, year and venue (openalex_sources.toml {venue} {year})"`.

`apply(result, cache)`: `extract = load_extract(cache)`; None → `(result, [])`. Otherwise `records, report = fill(result.records, extract)`; set `report.fetched` to the lookups' fetch times; return `replace(result, records=tuple(sorted(records, key=id)))` and `[report]`. Log `openalex_filled` (extract, candidates, attached, refused total) with no text.

`snapshot.build`: after `result = with_crawl_conflicts(…)`, add `result, fills = openalex.apply(result, cache)` and `crawls = [*crawls, *fills]`, before `withhold`. Wrap a `SourceError` as `SnapshotError` as `load_sources` does. Docstring: "… then fills OpenAlex abstracts from the pinned extract (`sources/openalex.apply`) …".

`crawl.py`:

```python
def openalex_fetcher(cache: Path, *, offline: bool, transport: Transport | None = None,
                     min_interval: float = DEFAULT_INTERVAL, key: str | None = None) -> Fetcher:  # fmt: skip
    live = None if offline else (transport or urllib_transport)
    headers = {"Authorization": f"Bearer {key}"} if key and not offline else None
    return Fetcher(PageCache(cache / openalex.CACHE_DIR), live, hosts=openalex.HOSTS,
                   min_interval=max(min_interval, openalex.MIN_INTERVAL), accept="application/json",
                   expect="json", keep_query=True, headers=headers)  # fmt: skip
```

`ingest_openalex(cache, …)`:
- `table = table or openalex_table.TABLE`; `records, _ = replay_all(cache)`.
- `key = key if key is not None else openalex.api_key(os.environ, repo_dotenv())`; offline or dry-run → None.
- A dry run returns `{"dry_run": True, "candidates", "doi_batches", "listings", "cached": …, "requests": 0}` from an offline fetcher's `is_cached`.
- Otherwise, under the `<cache>/openalex` lock (the `Crawls`/`storage.exclusive` pattern): `lookups = openalex.harvest(...)`, `sha = openalex.write_extract(cache, lookups)`.
- Log `openalex_ingested` (lookups, works, requests, candidates; never the key).
- Return `{"extract": sha, "lookups": …, "works": …, "candidates": …, "requests": f.stats.network, "cached": f.stats.cached}`.

`cli.py`: an `openalex` sub-parser with the shared crawl flags (`--dry-run`, `--offline`, `--refresh`, `--delay`) and `_ingest_openalex`, which checks `--delay` and refuses `--dry-run` with `--offline`, as `_ingest_ojs` does.

- [ ] **Step 4: Run the full backend suite and commit**

Run: `uv run pytest backend/tests -q -n auto` and `make lint`. Expected: PASS.

```bash
git add -A backend
git commit -m "feat(openalex): op ingest openalex writes a pinned extract; op snapshot build fills null AAAI/AIES/FAccT abstracts from it after dedup, refusals counted"
```

---

### Task 9: Snapshot diff, the manifest count and `/coverage`: `abstract_kind` on both sides

**Files:**
- Modify: `backend/src/openproceedings/ingest/snapshot.py`:
  - `diff`: the `abstract_kind` key and its transitions;
  - `render`: `abstract_openalex`, only when non-zero;
  - `RecordFile`: `abstract_openalex`, `track_openalex` counted from the lines with `abstract_kind_of`.
- Modify: `backend/src/openproceedings/coverage.py` (`abstract_openalex`, `abstract_official` per track, venue-year and totals; agreement check against the manifest key when present)
- Modify: `backend/src/openproceedings/api/models.py` (`TrackCoverage`, `VenueYearCoverage`, `CoverageTotals` gain both fields), `api/coverage.py`
- Modify: `backend/src/openproceedings/eval/coverage_report.py` (columns "Official abstract" and "OpenAlex abstract" in the per-venue-year table; a sentence on OpenAlex in the scope)
- Test: `backend/tests/unit/ingest/test_snapshot.py` (append), `backend/tests/unit/test_coverage.py` (append), `backend/tests/contract/test_coverage.py` (fixture regen)

**Interfaces:**
- Produces:
  - `snapshot.diff(a, b)["abstract_kind"]: dict[str, list[str]]` and `["abstract_kind_transitions"]: dict[str, int]` (keys like `"openalex->official"`);
  - manifest `abstract_openalex`, written only when non-zero;
  - `/coverage` `abstract_official`/`abstract_openalex` on each track, venue-year and the totals.

- [ ] **Step 1: Write the failing tests**

```python
def test_diff_names_a_kind_change_even_when_no_hash_changes(tmp_path: Path) -> None:
    """Same text, another source (OpenAlex's text, then the same text from OJS): content_hash is unchanged, so
    `changed` can't see it; `abstract_kind` must."""
    text = "Exactly the same abstract text."
    def build_with(source: str) -> Path:
        r = _record("op:aaai:2020:ojs-1", venue="AAAI", year=2020, abstract=(text, source))  # the file's helper
        return _snapshot(tmp_path / source, [r])  # the file's snapshot writer
    a, b = build_with("openalex"), build_with("ojs")
    out = diff(a, b)
    assert out["changed"] == {} and out["abstract_kind"] == {"op:aaai:2020:ojs-1": ["openalex", "official"]}
    assert out["abstract_kind_transitions"] == {"openalex->official": 1}


def test_the_manifest_counts_openalex_abstracts_only_when_there_are_any(tmp_path: Path) -> None:
    plain = render(DedupResult((_record("op:aaai:2020:ojs-1", venue="AAAI", year=2020),), (), ()), [], NOW)
    assert "abstract_openalex" not in json.loads(plain["manifest.json"])
    filled = render(DedupResult((_record("op:aaai:1990:dblp-A90", venue="AAAI", year=1990,
                                         abstract=("Text.", "openalex")),), (), ()), [], NOW)  # fmt: skip
    assert json.loads(filled["manifest.json"])["abstract_openalex"] == {"AAAI": {"1990": 1}}
```

(Use the helpers `test_snapshot.py` already has for records and snapshots. If none takes claims, build records with `dedup.resolve` as in Task 2's test, with a DOI-less dblp AAAI record for 1990.)

In `test_coverage.py`, for a venue-year with one OpenAlex, one official and one missing abstract:
- `abstract_official == 1`, `abstract_openalex == 1`, `abstract_missing == 1`, at track, venue-year and totals;
- `abstract_official + abstract_openalex + abstract_missing + abstract_withheld == records` holds in every row;
- a manifest whose `abstract_openalex` disagrees with the records is a `SnapshotError`.

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest backend/tests/unit/ingest/test_snapshot.py backend/tests/unit/test_coverage.py -q -k "kind or openalex"`. Expected: FAIL.

- [ ] **Step 3: Implement**

In `diff`, after the changed/display/provenance loop:

```python
    kinds = {rid: [old[rid].abstract_kind, new[rid].abstract_kind] for rid in sorted(old.keys() & new.keys())
             if old[rid].abstract_kind != new[rid].abstract_kind}  # derived, never hashed: compared on both sides
    ...
        "abstract_kind": kinds,
        "abstract_kind_transitions": dict(sorted(Counter(f"{a}->{b}" for a, b in kinds.values()).items())),
```

Update the docstring and the `op snapshot diff` CLI help.

In `render`, after `trimmed`:

```python
    # the records whose abstract OpenAlex filled (decision-049), written only when there are any (additive)
    if any(r.abstract_kind == "openalex" for r in records):
        manifest["abstract_openalex"] = _nested(records, lambda r: r.abstract_kind == "openalex")
```

In `RecordFile.__init__`'s pass: `kind = abstract_kind_of(line["abstract"], about)`, then `self.abstract_openalex[(venue, year)] += kind == "openalex"` and `self.track_openalex[track] += kind == "openalex"`. The coverage load (`coverage.breakdown` and its record-facts path) computes:
- `abstract_openalex` from the manifest key when present (checked equal to `RecordFile`'s), else from `RecordFile`;
- `abstract_official = records − abstract_missing − abstract_withheld − abstract_openalex`, checked ≥ 0.

Add both fields to the three models, with descriptions ("records whose abstract came from an official source" / "from OpenAlex's fallback (decision-049)").

`coverage_report.py`: the venue-year table gains the two columns, and the methods scope gains one sentence: "`<n>` abstracts (AAAI, AIES and FAccT) are OpenAlex's, filled where no official source gives one, and labelled `abstract_kind:openalex`."

- [ ] **Step 4: Run, regenerate and commit**

Run: `uv run pytest backend/tests -q -n auto`. Then `make openapi` and the coverage fixture regenerator (`test_frontend_coverage_fixture.py` names it). Then `npm test --workspace frontend`. Expected: PASS.

```bash
git add -A backend frontend
git commit -m "feat: op snapshot diff compares abstract_kind on both sides; the manifest and /coverage count official and OpenAlex abstracts"
```

---

### Task 10: Frontend: the Abstract facet, the OpenAlex label, coverage columns, help, methods text

**Files:**
- Modify: `frontend/src/components/search/filter-sidebar.tsx`:
  - `ValueField` adds `"abstract_kind"`;
  - `FIELD_TITLE.abstract_kind = "Abstract"`;
  - a `ValueFieldset` after Status, shown only when `facets.abstract_kind !== null`;
  - value labels.
- Modify: `frontend/src/lib/search-state.ts:333` (`FILTER_FIELDS` adds `"abstract_kind"`)
- Modify: `frontend/src/lib/methods-text.ts:78` (`FIELDS` adds `"abstract_kind"`)
- Modify: `frontend/src/components/help/syntax-help.tsx:371-390` (the `abstract_kind:` row; `data.values.abstract_kind` from the help golden)
- Modify: `frontend/src/components/search/hit-item.tsx` and `frontend/src/components/paper/paper-view.tsx` (the "Abstract via OpenAlex" label when `abstract_kind === "openalex"`)
- Modify: `frontend/src/components/coverage/coverage-report.tsx` (totals line, table columns, the OpenAlex explanation)
- Modify: `backend/tests/contract/help_golden.py` (`values` gains `abstract_kind`; one example `trust abstract_kind:official`), regenerate `frontend/src/help/syntax-golden.json`
- Modify: `docs/design/2026-09-27-copy-deck.md`: rows SB-1 (heading), SB-12 (values), RH-20 (hit label), PA-12 (paper label), CV-2 (totals), CV-4 (headers), CV-8 (explanation)
- Test: `filter-sidebar.test.tsx`, `hit-item.test.tsx`, `paper-view.test.tsx`, `coverage-report.test.tsx`, `methods-text.test.ts`, `search-state.test.ts`; e2e `frontend/e2e/abstract-kind.spec.ts` (new)

**Copy (verbatim; the copy deck rows say the same):**
- SB-1: heading "Abstract", no "(default)": it has no default.
- SB-12 value labels: `official` → "Official", `openalex` → "OpenAlex", `none` → "No abstract".
- RH-20 / PA-12, a line under the attribution: "Abstract via OpenAlex: no official source publishes one for this paper." The word OpenAlex links to the coverage page's CV-8 anchor (`/coverage#openalex`).
- CV-2 appends " · `<abstract_openalex>` abstracts from OpenAlex" when the count is above 0.
- CV-4 headers add "Official abstract" and "OpenAlex abstract".
- CV-8, under the table, `id="openalex"`: "OpenAlex abstracts fill AAAI, AIES and FAccT papers whose official source publishes no abstract: AAAI before 2010, AIES 2018–2023, and FAccT papers without one on the conference site. OpenAlex is an open catalogue that gathers abstracts from publishers and repositories, so its text can differ from the published one. Each is labelled, and `abstract_kind:official` leaves them out of a search."

- [ ] **Step 1: Write the failing tests** (Vitest; follow each file's existing render helpers)

```tsx
// filter-sidebar.test.tsx (append)
it("shows the Abstract fieldset with its counts after Status", () => {
  renderSidebar({ facets: { ...FACETS, abstract_kind: { official: 40, openalex: 7, none: 3 } } });
  const headings = screen.getAllByRole("group").map((g) => within(g).getByText(/^(Venue|Year|Track|Status|Abstract)$/).textContent);
  expect(headings).toEqual(["Venue", "Year", "Track", "Status", "Abstract"]);
  expect(screen.getByRole("checkbox", { name: "OpenAlex, 7 papers" })).toBeInTheDocument();
});

it("hides the Abstract fieldset on an index without the field", () => {
  renderSidebar({ facets: { ...FACETS, abstract_kind: null } });
  expect(screen.queryByText("Abstract")).toBeNull();
});
```

```tsx
// hit-item.test.tsx (append)
it("labels an OpenAlex abstract and links the explanation", () => {
  render(<HitItem hit={{ ...HIT, abstract_kind: "openalex", abstract_source: { source: "openalex", origin: "openalex", url: HIT.urls.proceedings } }} />);
  expect(screen.getByText(/Abstract via OpenAlex: no official source publishes one for this paper\./)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "OpenAlex" })).toHaveAttribute("href", "/coverage#openalex");
});

it("says nothing for an official abstract", () => {
  render(<HitItem hit={{ ...HIT, abstract_kind: "official" }} />);
  expect(screen.queryByText(/via OpenAlex/)).toBeNull();
});
```

Similar tests:
- `paper-view.test.tsx`: PA-12.
- `coverage-report.test.tsx`: the CV-2 suffix only above 0, the CV-4 headers, the CV-8 text and anchor.
- `methods-text.test.ts`: a record whose canonical holds `abstract_kind:official` names that clause like the other filters.
- `search-state.test.ts`: a `facetToggle` on `abstract_kind` writes `abstract_kind:(official OR none)` through `/parse`'s clause, as for status.

e2e `frontend/e2e/abstract-kind.spec.ts`: on the e2e fixture API (built at schema 4 from the backend e2e fixture), the sidebar shows the Abstract fieldset, and ticking "Official" alone puts `abstract_kind:official` in the editor. If the e2e fixture corpus has no OpenAlex record, assert only the fieldset and the clause.

- [ ] **Step 2: Run to verify failure**

Run: `npm test --workspace frontend -- filter-sidebar hit-item paper-view coverage-report methods-text search-state`. Expected: FAIL.

- [ ] **Step 3: Implement** the components to the copy above. Use the existing `ValueFieldset` with a `labels` map prop, adding the prop if it has none: a value shown by its label, while its accessible name keeps SB-2's form with the label. `FILTER_FIELDS` and `FIELDS` gain the field. Regenerate the help golden (`PYTHONPATH=backend uv run python -m tests.contract.help_golden`) after editing `help_golden.py`, and add the `abstract_kind:` row to the Filters section with the note "(on indexes built since schema 4)".

- [ ] **Step 4: Run**

Run: `npm test --workspace frontend`, `uv run pytest backend/tests/contract -q -n auto`, `make lint`, then `OP_E2E_API_PORT=8100 OP_E2E_WEB_PORT=3100 make e2e`. Refresh visual baselines only where the sidebar or coverage page changed, from CI's artifact for Linux, as TASK-182 did. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A frontend backend docs/design
git commit -m "feat(ui): the Abstract facet, the 'Abstract via OpenAlex' label, coverage's official and OpenAlex columns, help and methods text for abstract_kind:"
```

---

### Task 11: Ungated-cell notes on `/coverage` and in the report (TASK-222)

**Files:**
- Modify: `backend/src/openproceedings/official_counts.py` (`UngatedNote`, `UNGATED_NOTES`, `check_notes`)
- Modify: `docs/results/coverage-sources.md` (a section "Ungated cells with a note", mirrored by the test that already pins the official table to this file)
- Modify: `backend/src/openproceedings/coverage.py`, `api/models.py` (`TrackCoverage.gate_note`, `gate_note_citation`)
- Modify: `backend/src/openproceedings/eval/coverage_report.py` (a section listing each noted ungated cell with its note and citation)
- Modify: `frontend/src/components/coverage/coverage-report.tsx` (the note under the track row); copy deck CV-9
- Test: `backend/tests/unit/test_official_counts.py`, `backend/tests/unit/test_coverage.py`, `backend/tests/unit/eval/test_coverage_report.py` (or the file the report tests live in), `coverage-report.test.tsx`

**Interfaces:**
- Produces:
  - `official_counts.UngatedNote(note: str, citation: str, accessed: date)`;
  - `UNGATED_NOTES: dict[tuple[str, int, str], UngatedNote]`;
  - `/coverage` tracks carry `gate_note: str | null` and `gate_note_citation: str | null`.

- [ ] **Step 1: Write the failing tests**

```python
def test_an_ungated_note_needs_an_ungated_cell_and_a_citation() -> None:
    from openproceedings.official_counts import OFFICIAL_ACCEPTED, UNGATED_NOTES, UngatedNote, check_notes
    assert ("IASEAI", 2026, "main") in UNGATED_NOTES
    gated = next(k for k in OFFICIAL_ACCEPTED if k[2] == "main")
    with pytest.raises(ValueError, match="gated"):
        check_notes({gated: UngatedNote("x", "https://example.org", date(2026, 10, 10))})
    with pytest.raises(ValueError, match="citation"):
        check_notes({("IASEAI", 2026, "main"): UngatedNote("x", " ", date(2026, 10, 10))})
```

`test_coverage.py`: the IASEAI 2026 main track carries the note and citation; a track without a note carries nulls. Report test: the rendered report lists "IASEAI 2026 main:" with the note. Frontend: the note renders under the track's row with its citation link (CV-9).

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest backend/tests/unit/test_official_counts.py -q -k ungated`. Expected: FAIL.

- [ ] **Step 3: Implement**

```python
@dataclass(frozen=True, slots=True)
class UngatedNote:
    """Why a cell has no official count to gate on, with a citation a reader can check (TASK-222)."""

    note: str
    citation: str
    accessed: date


UNGATED_NOTES: dict[tuple[str, int, str], UngatedNote] = {
    ("IASEAI", 2026, "main"): UngatedNote(
        "57 archival papers are published in the proceedings; the conference accepted 92, and the 35 non-archival "
        "ones have no findable listing, so no official count of what the index can hold exists",
        "https://ojs.aaai.org/index.php/IASEAI/issue/view/741 (docs/research/2026-10-09-aaai-aies-facct-iaseai-sources.md §IASEAI)",
        date(2026, 10, 9),
    ),
}


def check_notes(notes: Mapping[tuple[str, int, str], UngatedNote], table: OfficialTable = OFFICIAL_ACCEPTED) -> None:
    for key, n in notes.items():
        if key in table and key[2] in GATED_TRACKS:
            raise ValueError(f"{key}: a gated cell takes its cause in coverage-causes.toml, not an ungated note")
        if not n.note.strip() or not n.citation.strip():
            raise ValueError(f"{key}: an ungated note needs its note and a citation")
```

Call `check_notes(UNGATED_NOTES)` at import, as `check_table` is called. Check the IASEAI numbers against the research note before committing. The controller may add rows for other ungated new-venue cells (FAccT 2019's tutorials, AAAI years without an official count) from the B and C census, each cited.

- [ ] **Step 4: Run, regenerate and commit**

Run: `uv run pytest backend/tests -q -n auto`, `make openapi`, regenerate the coverage fixture, `npm test --workspace frontend`. Then `backlog task edit 222 --check-ac 1` and, after the final summary, `backlog task complete 222` (read `backlog instructions task-finalization` first).

```bash
git add -A backend frontend docs backlog
git commit -m "feat(coverage): ungated cells carry a cited note on /coverage and in the report (TASK-222)"
```

---

### Task 12: Census (live): OpenAlex facts, the AAAI listing table rows, recorded fixtures

The controller runs this. It touches the network and is never a test. `export OP_DATA_DIR=/Users/jeevanparmar/school/Research/Ferguson/openproceedings/data`. Set `OPENALEX_API_KEY` in `.env` only if the owner provides one.

**Files:**
- Create: `scripts/openalex_census.py` (read-only helper: fetches through `crawl.openalex_fetcher` into the cache, prints facts and draft rows, writes nothing else)
- Modify: `backend/src/openproceedings/ingest/openalex_sources.toml` (every row)
- Create: `backend/tests/fixtures/http/openalex/doi-batch.json`, `listing-<year>.json`, scrubbed (`backend/tests/fixtures/http/scrub.py` gains an OpenAlex JSON branch: real ids, DOIs, counts; synthetic titles; inverted indexes rebuilt from synthetic text of the same word count)
- Create: `backend/tests/unit/ingest/openalex/test_openalex_recorded.py`
- Modify: `docs/research/2026-10-09-aaai-aies-facct-iaseai-sources.md` (§OpenAlex)

- [ ] **Step 1: Write `scripts/openalex_census.py`.** Given `--cache`, it prints:
  - Auth: whether a keyless request answers 200; the rate-limit and cost headers the answer carries; that the key goes as `Authorization: Bearer`.
  - Licence: OpenAlex's stated data licence and its URL.
  - The DOI route: candidate counts per venue-year (from `replay_all`); the number of batches; per batch the requested and returned DOIs, the DOIs returned twice, and the works whose DOI was not requested.
  - FAccT 2025/2026: a reconciliation of the research note's 195/206 and 293/317 against the DOIs requested.
  - The listing route: for AAAI 1980–2008, OpenAlex's sources named like the AAAI conference (`/sources?search=AAAI`, `/sources?search=National Conference on Artificial Intelligence`) with ids and work counts per year; per candidate year the count of works and how many DOI-less dblp records match one work by title key.
  - Draft `[[listing]]` rows.

- [ ] **Step 2: Run it** with `uv run python scripts/openalex_census.py --cache "$OP_DATA_DIR/cache" | tee "$TMPDIR/openalex-census.txt"`.

- [ ] **Step 3: Write the rows.**
  - One `[[listing]]` per AAAI year where a source holds that year's papers, with `works` = the census count and `verified` = today.
  - Years with no source get no row; the research note says the records stay `none`.
  - A year whose source mixes in IAAI or workshops is fine: matching is one-to-one by title key. Note it.

- [ ] **Step 4: Record fixtures and pin them.** Record one DOI batch (FAccT 2023, ≤ 50 DOIs) and one AAAI listing page, then scrub them. `test_openalex_recorded.py` checks:
  - each parses (`parse_works`);
  - every work's inverted index rebuilds;
  - the batch's returned DOIs ⊆ its requested DOIs, or the mismatch is counted as the census found;
  - the shipped `openalex_sources.toml` loads with the census's years.

- [ ] **Step 5: Research note §OpenAlex.** Record:
  - the date checked, the endpoints and queries used (URLs), auth and budget, the licence;
  - the DOI-route yield per venue-year, and the truncated and duplicate DOIs found (itemised: this closes the note's *(unverified here)* marks);
  - the AAAI sources per year and why each listing row exists;
  - what the census leaves for the owner.

- [ ] **Step 6: Run and commit**

Run: `uv run pytest backend/tests/unit/ingest/openalex -q` and `make lint`. Expected: PASS.

```bash
git add -A backend scripts docs
git commit -m "data: OpenAlex census (auth, licence, DOI yield, AAAI 1980-2008 sources); openalex_sources.toml rows; recorded fixtures"
```

---

### Task 13: The OpenAlex fidelity audit (`op eval openalex`)

**Files:**
- Create: `backend/src/openproceedings/eval/openalex_audit.py`
- Modify: `backend/src/openproceedings/cli.py` (`op eval openalex [--snapshot S] [--aaai-sample N] [--seed N] [--offline] [--out DIR]`)
- Create: `backend/tests/unit/eval/test_openalex_audit.py`
- Create (real run, Step 5): `docs/results/<date>-openalex-audit.md`

**Interfaces:**
- Produces:
  - `openalex_audit.Kind = Literal["exact", "near_exact", "truncated", "similar", "differs"]`;
  - `openalex_audit.compare(official: str, openalex: str) -> Kind`;
  - `openalex_audit.sample(records, *, aaai_sample=1000, seed=49) -> list[PaperRecord]`;
  - `openalex_audit.audit(records, fetcher) -> AuditResult`;
  - `openalex_audit.render(result, meta) -> str`.

- [ ] **Step 1: Write the failing tests**

```python
import pytest

from openproceedings.eval import openalex_audit as oa


@pytest.mark.parametrize(("official", "other", "kind"), [
    ("A study of trust.", "A study of trust.", "exact"),
    ("A study  of trust.", "A study of trust.", "exact"),
    ("A Study of Trust!", "a study of trust", "near_exact"),  # the same search tokens
    ("A study of trust in models.", "A study of trust", "truncated"),
    (" ".join(["word"] * 50) + " end", " ".join(["word"] * 50) + " fin", "similar"),
    ("A study of trust.", "Something else entirely.", "differs"),
])  # fmt: skip
def test_compare(official: str, other: str, kind: str) -> None:
    assert oa.compare(official, other) == kind


def test_the_sample_is_seeded_and_covers_the_named_venue_years() -> None:
    from tests.unit.eval.audit_fixture import records  # FAccT 2022/2025/2026, AIES 2024-2025, AAAI 2010+ (official)
    one, two = oa.sample(records(), aaai_sample=5, seed=49), oa.sample(records(), aaai_sample=5, seed=49)
    assert [r.id for r in one] == [r.id for r in two]
    assert {(r.venue, r.year) for r in one if r.venue != "AAAI"} == {
        ("FAccT", 2022), ("FAccT", 2025), ("FAccT", 2026), ("AIES", 2024), ("AIES", 2025)}
    assert sum(r.venue == "AAAI" for r in one) == 5 and all(r.abstract_kind == "official" for r in one)


def test_render_reports_rates_per_venue_year_and_the_reproduction_command() -> None:
    result = oa.AuditResult(rows={("FAccT", 2025): {"exact": 3, "near_exact": 1, "differs": 1, "no_openalex": 1}})
    text = oa.render(result, oa.Meta(snapshot="2026-10-11-abc", commit="0000000", seed=49, aaai_sample=1000))
    assert "| FAccT | 2025 | 6 | 3 (50.0%) | 1 (16.7%)" in text and "op eval openalex --offline" in text
```

(`tests/unit/eval/audit_fixture.py` is a small builder like `abstract_kinds.py`, with official claims only.)

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest backend/tests/unit/eval/test_openalex_audit.py -q`. Expected: FAIL.

- [ ] **Step 3: Implement**

```python
def compare(official: str, openalex: str) -> Kind:
    """How OpenAlex's text of an abstract compares with the official one: `exact` (equal once whitespace is
    collapsed), `near_exact` (the same search tokens: `dedup.title_key`, the token contract), `truncated`
    (OpenAlex's tokens a strict prefix of the official ones), `similar` (token ratio ≥ 0.9), else `differs`."""
    if " ".join(official.split()) == " ".join(openalex.split()):
        return "exact"
    a, b = title_key(official).split(), title_key(openalex).split()
    if a == b:
        return "near_exact"
    if b and len(b) < len(a) and a[: len(b)] == b:
        return "truncated"
    return "similar" if SequenceMatcher(None, a, b, autojunk=False).ratio() >= 0.9 else "differs"
```

`sample`:
- every record of FAccT 2022/2025/2026 and AIES 2024/2025 whose `abstract_kind == "official"` and which has a DOI;
- plus `random.Random(seed).sample` of the AAAI 2010+ such records, taken in id order before sampling.

`audit`:
- batches the sample's DOIs through `openalex.doi_url` with the given fetcher (the cache; `--offline` replays it);
- reuses `openalex.parse_works`/`abstract_of`, so the same rebuild and hygiene apply;
- counts per venue-year the `compare` kinds, plus `no_openalex` (no work), `refused` (a rebuild refusal) and `duplicate`.

`render` writes:
- a header: the snapshot, the commit, the seed and sample size, and the date;
- the command, `uv run op eval openalex --snapshot <S> --seed 49 --aaai-sample 1000 --offline`;
- a method paragraph defining each class;
- the per-venue-year table: venue, year, compared, then exact, near_exact, truncated, similar, differs, no_openalex, refused, each with its rate;
- a totals row;
- a closing paragraph stating the exact and near-exact rates. No abstract text appears in the report; ids only, for a few `differs` examples.

The CLI writes the report under `docs/results/` like `op eval coverage`.

- [ ] **Step 4: Run and commit the code**

Run: `uv run pytest backend/tests -q -n auto` and `make lint`. Expected: PASS.

```bash
git add -A backend
git commit -m "feat(eval): op eval openalex measures OpenAlex abstracts against official ones (exact, near-exact, truncated, similar, differs)"
```

- [ ] **Step 5: Real run (controller, after Task 15's snapshot exists)**

```bash
uv run op eval openalex --snapshot <new snapshot> --seed 49 --aaai-sample 1000
uv run op eval openalex --snapshot <new snapshot> --seed 49 --aaai-sample 1000 --offline   # must reproduce byte-identically
```

Commit the report: `git add docs/results/*-openalex-audit.md && git commit -m "docs: OpenAlex fidelity audit on snapshot <hash> (milestone C)"`. Then check TASK-215's AC #3.

---

### Task 14: Docs as built

**Files:**
- `docs/specs/01-ingestion.md`:
  - §Record schema: schema 8, `abstract_kind` derived beside `venue_name`, the `openalex` source and its guard;
  - §Sources: a new **OpenAlex** row covering scope, both routes, every refusal, the rebuild rules, the extract and marker and their pinning, the post-dedup fill and why, attribution, the optional key as a header, and that no contact address is sent;
  - §Pipeline (the fill's place);
  - §CLI (`op ingest openalex`);
  - the manifest's `sources.openalex.fills` and `abstract_openalex`.
- `docs/specs/02-query-language.md`: the `abstract_kind:` row (values, no default, guarantee 2, a schema-4 index only, `FIELD_NOT_INDEXED`), the canonical filter order, and why `QUERY_VERSION` is unchanged.
- `docs/specs/03-search-engine.md`:
  - §Index schema: the schema 4 field;
  - §Versioning: served schemas 3 and 4, schema 2 retired with the date and the four retired indexes;
  - the per-engine facets/COMBO and `MAX_FACET_COMBOS`;
  - §Performance budgets: Task 15's measured numbers and the citable group-count report.
- `docs/specs/04-backend-api.md`:
  - `Hit`/paper `abstract_kind`;
  - `Facets.abstract_kind` (nullable);
  - `/meta` vocabularies;
  - `/coverage` `abstract_official`, `abstract_openalex`, `gate_note`, `gate_note_citation`;
  - the CSV column appended last and the JSONL key;
  - the RIS `N1` naming OpenAlex with the paper's page, noting the deviation from the design's wording;
  - `ORIGIN_NAMES`/`ORIGIN_DOC`;
  - `FIELD_NOT_INDEXED`.
- `docs/specs/05-frontend.md` and `docs/design/2026-09-27-copy-deck.md`: SB-1, SB-12, RH-20, PA-12, CV-2, CV-4, CV-8 and CV-9, as built (Task 10's rows, checked against the components).
- `docs/specs/07-evaluation.md`: the audit (method, classes, the report link, the rates) and the coverage columns and ungated notes.
- `docs/specs/08-ops-and-tooling.md`: `op ingest openalex` (last in a full crawl), `op eval openalex`, the schema-2 retirement in the runbook's retention notes, `OPENALEX_API_KEY` optional.
- `README.md`, `CLAUDE.md`:
  - the `ingest/` layout line gains `openalex_table.py` + `openalex_sources.toml` and `sources/openalex.py`;
  - `eval/` gains `openalex_audit.py` → `op eval openalex`;
  - `op ingest … | openalex`.
- Skills:
  - `.claude/skills/index-versioning/SKILL.md`: served schemas 3/4, the schema-2 retirement done, the schema 3 × tokenizer 2/3 and schema 4 × tokenizer 2/3 combinations;
  - `record-schema`: schema 8, `abstract_kind` derived;
  - `dedup-rules`: `openalex` last, the fill after dedup, attribution;
  - `api-contract`: the new fields, nullable facets;
  - `query-grammar`: the new field;
  - `tantivy-indexing`: the schema 4 field, the schema-3 build guard;
  - `coverage-reporting`: the kind columns, ungated notes.
- `docs/plans/2026-10-09-new-venues-design.md`: the status line (milestone C built), a short "Milestone C as built" note with the accepted Planner decisions and the counts.
- decision-049's body: consequences for C (schema 8, index schema 4, schema 2 retired, OpenAlex fill).
- `.env.example` (done in Task 7), `cspell.json` (`OpenAlex`, `openalex` if flagged), `docs/README.md` (results rows).
- Backlog: run `backlog instructions overview`, then:
  - `backlog task edit 202 --append-notes "Milestone C adds op ingest openalex (last in a full run; OPENALEX_API_KEY optional) and the post-dedup fill in op snapshot build; promotion needs an index at schema 4."`;
  - TASK-215's ACs checked as met;
  - link TASK-216 (IASEAI 2027) from the design note.

- [ ] **Step 1:** Edit each document above as built in Tasks 1–13. Use no future tense for what C built.
- [ ] **Step 2:** Run `make lint` and `make tooling` (skills changed). Expected: PASS.
- [ ] **Step 3:** Commit. Add new files explicitly.

```bash
git add -A docs README.md CLAUDE.md .claude frontend cspell.json backlog
git commit -m "docs: specs, decision-049, README, skills and copy for OpenAlex abstracts, abstract_kind and index schema 4 (milestone C as built)"
```

---

### Task 15: Real-data verification, benchmarks (TASK-220 folded), then the closing workflow

The controller runs every step in the foreground: agents stall on background runs. `export OP_DATA_DIR=/Users/jeevanparmar/school/Research/Ferguson/openproceedings/data`, a data dir outside the worktree.

- [ ] **Step 1: Crawl OpenAlex.**

```bash
uv run op ingest openalex --dry-run
uv run op ingest openalex
```

  Expected: every listing at its table count (no stop), and the extract sha printed. Write candidates, lookups, requests and the extract sha into the PR body.

- [ ] **Step 2: Snapshot and diff.**

```bash
uv run op snapshot build
uv run op snapshot diff "$OP_DATA_DIR/snapshots/<latest before C>" "$OP_DATA_DIR/snapshots/<new>"
```

  Expected:
  - `added` 0, `removed` 0, `rekeyed` 0;
  - `changed` lists only AAAI/AIES/FAccT ids whose fields are exactly `["abstract"]`;
  - `abstract_kind` lists exactly those ids, each `["none", "openalex"]`;
  - `abstract_kind_transitions == {"none->openalex": <attached>}`, which equals `sources.openalex.fills[0].attached_doi + attached_title`;
  - no NeurIPS, ICLR, ICML or IASEAI id appears anywhere in `changed` or `abstract_kind`.

  Cite both snapshot hashes in the PR.

- [ ] **Step 3: Retire the schema-2 indexes** (Task 1's prerequisite, now for real):

```bash
for v in 05a0541717f6 6508b8cf66ff a7cfd04b656f c76d7f26ee06; do uv run op index retire "$v"; done
```

  Expected: each retired, no pin, no symlink.

- [ ] **Step 4: Index (schema 4) and full parity.**

```bash
uv run op index build --snapshot <new snapshot hash>
uv run op index parity --index <new index_version>
```

  Expected: manifest `schema_version: "4"`. Parity holds over the full corpus, the stored `abstract_kind` included. Spot-check:
  - `uv run op search 'abstract_kind:openalex' --index <new> --ids | wc -l` equals the attached count;
  - the same query with `--engine reference` gives the same ids.

- [ ] **Step 5: Coverage.**

```bash
uv run op eval coverage --index <new index_version> --check
```

  Expected:
  - every venue-year at its table count;
  - the gate passes;
  - the official and OpenAlex columns sum with missing and withheld to records;
  - IASEAI 2026 main shows its ungated note.

  Commit the report (`docs: coverage report on index <version> (milestone C)`).

- [ ] **Step 6: The fidelity audit:** Task 13 Step 5.

- [ ] **Step 7: Benchmarks on a quiet machine (TASK-220 folded in).**
  - Check `sysctl -n vm.loadavg` (the 1-minute figure < 5) before and after. Run nothing else.
  - Copy the new index aside, as the reports require, and run:

```bash
cd backend && uv run python -m tests.bench.group_counts_report --index <copy of the new index>
cd backend && uv run python -m tests.bench.report_80k
```

  - Expected: spec 03's p95 under 100 ms for every first page with facets and counts. The facets now aggregate five fields, up to three times the combos; compare with the 85.2 ms worst on `757641db0a20`.
  - A run whose load is ≥ 5 at either end is not cited; re-run.
  - Commit the reports. Spec 03 cites them (Task 14).
  - Complete TASK-220 ("A citable report on the current index"), citing the new index.
  - A budget miss becomes its own backlog task, filed last (task-hygiene §Ids), never a silent pass.

- [ ] **Step 8: Frontend e2e and visual baselines.** `OP_E2E_API_PORT=8100 OP_E2E_WEB_PORT=3100 make e2e`. Refresh Linux baselines from CI's artifact where Task 10 changed the sidebar or coverage page.

- [ ] **Step 9: Closing workflow** (CLAUDE.md, in order):
  1. `make test` (full), `make lint`, `make tooling`; `make mutate-changed` if any hook or tooling script changed.
  2. Backlog current: TASK-215's ACs checked with a final summary, then `backlog task complete 215`; TASK-220 and TASK-222 completed. File follow-ups last:
     - any `doi_duplicate`/`title_ambiguous` cases for owner review;
     - AAAI years without an OpenAlex source;
     - any bench miss;
     - a re-check of OpenAlex's budget terms if the census found a keyless limit close to the crawl's size.
  3. `/record-learnings`. Lessons worth recording:
     - the post-dedup fill;
     - kind diffs that no hash shows;
     - retiring a schema before adding one.
  4. `/review-gate`, with every Must and Should fixed.
  5. Push; `/open-pr` into `dev`; `gh pr merge <n> --auto`.

### Critical Files for Implementation
- /Users/jeevanparmar/school/Research/Ferguson/openproceedings-wt-new-venues/backend/src/openproceedings/engine/tantivy_engine.py
- /Users/jeevanparmar/school/Research/Ferguson/openproceedings-wt-new-venues/backend/src/openproceedings/engine/index.py
- /Users/jeevanparmar/school/Research/Ferguson/openproceedings-wt-new-venues/backend/src/openproceedings/ingest/record.py
- /Users/jeevanparmar/school/Research/Ferguson/openproceedings-wt-new-venues/backend/src/openproceedings/ingest/snapshot.py
- /Users/jeevanparmar/school/Research/Ferguson/openproceedings-wt-new-venues/backend/src/openproceedings/ingest/sources/openalex.py (new; patterns from `ingest/sources/crossref.py` in milestone B and `ingest/dedup.py`)
