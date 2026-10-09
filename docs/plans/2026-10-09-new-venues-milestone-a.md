# New venues, milestone A (AAAI 2010+, AIES 2024+, IASEAI 2026 from ojs.aaai.org) — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add AAAI, AIES, FAccT and IASEAI to the vocabulary and record model, and crawl every paper ojs.aaai.org
publishes for AAAI (2010–2026), AIES (2024–2025) and IASEAI (2026) into the corpus, with official abstracts.

**Architecture:** One new source module (`ingest/sources/ojs.py`) harvests each OJS journal through OAI-PMH
(`ListRecords`, `oai_dc`, resumption tokens) via the shared HTTP layer, which learns to recognise a whole XML
response. A data table (`ingest/ojs_sections.toml`, loaded by `ingest/ojs_table.py`) maps each journal, volume and
OAI set (an OJS section) to a track with a verified count; an unlisted volume or section stops the crawl. Records
are built from claims (`common.record_from_claims`) like every other miner, replayed offline by `op snapshot build`
through `crawl.SOURCES`.

**Tech Stack:** Python 3.12, pydantic v2, `xml.etree.ElementTree` over expat (stdlib, as `dblp_xml.py` uses; an expat
handler refuses any DOCTYPE, so no entity is declared or expanded: Task 4; no `defusedxml` dependency), tomllib, pytest + hypothesis, uv. Frontend: Next.js/TypeScript
(copy and badge only in this milestone).

**Spec:** `docs/plans/2026-10-09-new-venues-design.md` (read it first; this plan implements its milestone A). Repo
rules: `CLAUDE.md` (guarantees, hooks, closing workflow), `docs/specs/01-ingestion.md`.

## Global Constraints

- Venues added to `vocab.Venue`, in this order after the existing three: `AAAI`, `AIES`, `FAccT`, `IASEAI`.
- `vocab.CONFERENCES` rows (verbatim): `"AAAI": ("AAAI Conference on Artificial Intelligence", ((1980, "AAAI"),))`,
  `"AIES": ("AAAI/ACM Conference on AI, Ethics, and Society", ((2018, "AIES"),))`,
  `"FAccT": ("ACM Conference on Fairness, Accountability, and Transparency", ((2018, "FAT*"), (2021, "FAccT")))`,
  `"IASEAI": ("International Association for Safe and Ethical AI Conference", ((2025, "IASEAI"),))`.
- Tracks added to `vocab.Track`, before `"other"`: `student_abstract`, `consortium`, `demo`, `iaai`, `eaai`.
  `iaai` and `eaai` are valid only on `venue == "AAAI"` (the record refuses them elsewhere).
- The default track filter stays `track:(datasets_benchmarks OR main OR position)` (`query/defaults.py`); the new
  tracks are excluded by default (owner decision 4 in the spec). Do not touch `DEFAULT_CLAUSES`.
- `RECORD_SCHEMA_VERSION` `"5"` → `"6"`. Index `SCHEMA_VERSION` stays `"3"` in this milestone.
- New claim source `"ojs"`; native id `ojs-<article id>` (digits), valid for venues AAAI, AIES, IASEAI.
- OJS years: AAAI `year = volume + 1986` (Vol. 24 = 2010 … Vol. 40 = 2026); AIES `year = volume + 2017`
  (Vol. 7 = 2024); IASEAI `year = volume + 2024` (Vol. 2 = 2026).
- OAI-PMH base URL `https://ojs.aaai.org/index.php/<JOURNAL>/oai`; first request
  `?verb=ListRecords&metadataPrefix=oai_dc`, then `?verb=ListRecords&resumptionToken=<token>`. Host
  `ojs.aaai.org` only. Pace: at least 3 s between requests (`ojs.MIN_INTERVAL = 3.0`; the server takes 2–3 s a page).
- Every status is `accepted`. No abstract from anywhere but the record's own `dc:description` in this milestone.
- No test reaches the network (`backend/tests/conftest.py` blocks it); crawler tests use recorded fixtures.
- Commits and PRs carry no AI attribution of any kind (hook `block-ai-attribution.sh`, CLAUDE.md §Authorship).
- `main`/`dev` take no direct commits; work on `feat/new-venues` in `../openproceedings-wt-new-venues`.
- Logging: structured JSON, one line per unit of work, never abstracts, query text or credentials
  (`.claude/skills/logging-standards/SKILL.md`).
- Docs, specs and backlog are updated in the same commit as the change they describe (CLAUDE.md §Keep everything
  current); backlog only through the `backlog` CLI.

## Review Focus

1. **An OJS author string that is not `Last, First`** (`Smith, Jr., John`, a single name `Aristotle`, an empty
   `dc:creator`): a person expects the name kept as published, never mangled or dropped silently — Task 4 pins
   `display_name` on each shape (two commas or none → verbatim; empty → skipped and counted).
2. **An expired or rejected resumption token** (a crawl resumed a day later; OJS tokens expire after 24 h and come
   back as HTTP 200 `<error code="badResumptionToken">`): a person expects a clear stop telling them to re-run with
   `--refresh`, never a silently shorter harvest — Task 4 pins the `CrawlError` and Task 5 the CLI message.
3. **A record in a volume or section the table doesn't list** (AAAI Vol. 41 published before its rows exist; a new
   special-track set): a person expects the crawl to stop naming the journal, volume and set to add, never a
   record guessed into `main` — Task 4 pins both.
4. **A multilingual or repeated `dc:title`/`dc:description`** (OJS can emit one per locale): a person expects the
   English one (`xml:lang` starting `en`), else the first, never two titles concatenated — Task 4 pins the choice.
5. **A response that is an OAI-PMH error or not XML at all** (an HTML maintenance page with HTTP 200, a truncated
   body): a person expects a retry for a truncated body and a stop for anything else, never an empty harvest
   counted as complete — Task 3 pins truncation; Task 4 pins the HTML page and `<error>` codes.

---

## File map

| File | Responsibility | Task |
|---|---|---|
| `backend/src/openproceedings/vocab.py` | venues, tracks, conference names | 1 |
| `backend/src/openproceedings/ingest/record.py` | id regex, `ojs-` native form, venue-only tracks, `Source`, schema 6 | 1, 2 |
| `backend/src/openproceedings/ingest/statuses.py`, `ingest/dedup.py`, `export.py`, `frontend/src/components/search/hit-item.tsx` | the `ojs` source's statuses, precedence, origin and display name | 2 |
| `backend/tests/fixtures/corpus/synthetic_5k.py` | pinned to the pre-change venue/track tuples | 1 |
| `backend/tests/strategies.py`, `backend/tests/contract/conftest.py` and the tests the code map names | vocabulary-driven tests | 1 |
| `backend/src/openproceedings/query/compat.py`, `query/parser.py` | Scholar `source:` aliases; the venue hint text | 1 |
| `frontend/src/components/paper-badges.tsx` | short names for the new tracks | 1 |
| `backend/src/openproceedings/ingest/sources/http.py` | `Policy.expect = "xml"`; `Fetcher` keyword options | 3 |
| `backend/src/openproceedings/ingest/ojs_table.py` + `ingest/ojs_sections.toml` | the journal/volume/section table | 4 |
| `backend/src/openproceedings/ingest/sources/ojs.py` | OAI-PMH parse, harvest, records, reports | 4 |
| `backend/src/openproceedings/ingest/urls.py` | `ojs_article(url)` and `native()` for OJS article URLs | 4 |
| `backend/src/openproceedings/ingest/sources/crawl.py`, `cli.py` | `op ingest ojs`, `OJS` crawls in `SOURCES` | 5 |
| `backend/tests/fixtures/http/ojs/…` | recorded OAI-PMH pages | 4 (synthetic), 6 (recorded) |
| `docs/research/2026-10-09-aaai-aies-facct-iaseai-sources.md` | the live facts with dates | 6 |
| `ingest/ojs_sections.toml` (real rows), `official_counts.py` rows | built from the live harvest | 6 |
| `backlog/decisions/decision-049 …`, specs 00/01/02/04/05/07/08, README, CLAUDE.md, skills, copy deck | docs as built | 7 |

---

### Task 1: Vocabulary — four venues, five tracks, conference names

**Files:**
- Modify: `backend/src/openproceedings/vocab.py:12-23, 110-114` (and the comment above `CONFERENCES`)
- Modify: `backend/src/openproceedings/ingest/record.py:60` (`_ID`)
- Modify: `backend/tests/fixtures/corpus/synthetic_5k.py:26,30` (pin tuples)
- Modify: `backend/src/openproceedings/query/compat.py:21` (`SOURCE_ALIASES`), `query/parser.py:544` (hint text)
- Modify: `frontend/src/components/paper-badges.tsx:8-10`
- Modify (vocabulary-driven tests): `backend/tests/strategies.py:134,144,209-216,285-289`,
  `backend/tests/contract/conftest.py:74-78`, `backend/tests/unit/ingest/test_record.py:380-433` (`VENUE_NAMES`),
  `backend/tests/contract/test_parse_papers_meta.py:282-283`, `frontend/src/test/api-stub.tsx:134-135`,
  `frontend/src/editor/complete.test.ts:26`
- Test: `backend/tests/unit/test_vocab_new_venues.py` (new)

**Interfaces:**
- Produces: `vocab.Venue` with 7 values; `vocab.Track` with 14 values; `vocab.venue_name("FAccT", 2020) ==
  "ACM Conference on Fairness, Accountability, and Transparency (FAT* 2020)"`; `record._ID` accepting
  `op:(neurips|iclr|icml|aaai|aies|facct|iaseai):YYYY:<native>`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/test_vocab_new_venues.py
"""The four venues added by decision-049 (docs/plans/2026-10-09-new-venues-design.md §Data model)."""

import pytest

from openproceedings.ingest.record import is_paper_id
from openproceedings.vocab import TRACKS, VENUES, venue_name


@pytest.mark.parametrize(
    ("venue", "year", "expected"),
    [
        ("AAAI", 1980, "AAAI Conference on Artificial Intelligence (AAAI 1980)"),
        ("AAAI", 2026, "AAAI Conference on Artificial Intelligence (AAAI 2026)"),
        ("AIES", 2018, "AAAI/ACM Conference on AI, Ethics, and Society (AIES 2018)"),
        ("FAccT", 2018, "ACM Conference on Fairness, Accountability, and Transparency (FAT* 2018)"),
        ("FAccT", 2020, "ACM Conference on Fairness, Accountability, and Transparency (FAT* 2020)"),
        ("FAccT", 2021, "ACM Conference on Fairness, Accountability, and Transparency (FAccT 2021)"),
        ("IASEAI", 2026, "International Association for Safe and Ethical AI Conference (IASEAI 2026)"),
    ],
)
def test_venue_name_per_era(venue: str, year: int, expected: str) -> None:
    assert venue_name(venue, year) == expected


@pytest.mark.parametrize(("venue", "year"), [("AAAI", 1979), ("AIES", 2017), ("FAccT", 2017), ("IASEAI", 2024)])
def test_year_before_the_venue_is_refused(venue: str, year: int) -> None:
    with pytest.raises(ValueError, match="not held under that name"):
        venue_name(venue, year)


def test_venue_query_spellings_are_case_insensitive() -> None:
    assert VENUES["facct"] == "FAccT"
    assert VENUES["aaai"] == "AAAI"
    assert VENUES["iaseai"] == "IASEAI"
    assert list(VENUES.values())[-4:] == ["AAAI", "AIES", "FAccT", "IASEAI"]


def test_new_tracks_sit_before_other() -> None:
    assert TRACKS[TRACKS.index("blogpost") + 1 : TRACKS.index("other")] == (
        "student_abstract", "consortium", "demo", "iaai", "eaai",
    )


@pytest.mark.parametrize("prefix", ["aaai", "aies", "facct", "iaseai"])
def test_record_ids_of_new_venues_have_the_id_shape(prefix: str) -> None:
    assert is_paper_id(f"op:{prefix}:2024:ojs-28000")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest backend/tests/unit/test_vocab_new_venues.py -q`
Expected: FAIL (`KeyError: 'facct'`, `ValueError: no conference table for venue 'AAAI'`).

- [ ] **Step 3: Implement**

In `vocab.py`:

```python
Venue = Literal["NeurIPS", "ICLR", "ICML", "AAAI", "AIES", "FAccT", "IASEAI"]
Track = Literal[
    "main",
    "datasets_benchmarks",
    "position",
    "workshop",
    "competition",
    "tiny_papers",
    "blogpost",
    "student_abstract",  # AAAI and AIES student abstracts and posters (decision-049)
    "consortium",  # AAAI doctoral and undergraduate consortia
    "demo",  # AAAI demonstrations
    "iaai",  # Innovative Applications of AI, printed in the AAAI volumes (AAAI only)
    "eaai",  # Educational Advances in AI, printed in the AAAI volumes (AAAI only)
    "other",
    "unknown",
]
```

Extend the comment above `CONFERENCES` with one sentence per new venue (AAAI held as the National Conference on
AI from 1980, the name the conference uses today; AIES from 2018; FAccT held as FAT* 2018–2020 and renamed for
2021; IASEAI first met in 2025 though only 2026 published papers), then:

```python
CONFERENCES: ConferenceTable = {
    "NeurIPS": ("Conference on Neural Information Processing Systems", ((1987, "NIPS"), (2018, "NeurIPS"))),
    "ICLR": ("International Conference on Learning Representations", ((2013, "ICLR"),)),
    "ICML": ("International Conference on Machine Learning", ((1988, "ICML"),)),
    "AAAI": ("AAAI Conference on Artificial Intelligence", ((1980, "AAAI"),)),
    "AIES": ("AAAI/ACM Conference on AI, Ethics, and Society", ((2018, "AIES"),)),
    "FAccT": ("ACM Conference on Fairness, Accountability, and Transparency", ((2018, "FAT*"), (2021, "FAccT"))),
    "IASEAI": ("International Association for Safe and Ethical AI Conference", ((2025, "IASEAI"),)),
}
```

In `ingest/record.py`: `_ID = re.compile(r"op:(neurips|iclr|icml|aaai|aies|facct|iaseai):([0-9]{4}):(\S+)")`.

- [ ] **Step 4: Pin the synthetic corpus before anything reads the new tuples**

In `backend/tests/fixtures/corpus/synthetic_5k.py`, replace the `TRACKS` import so the 5k corpus (and every
contract fixture and benchmark derived from it) is byte-identical to before:

```python
from openproceedings.vocab import STATUSES
...
VENUES = ("NeurIPS", "ICLR", "ICML")
# pinned to the vocabulary before decision-049 added tracks: `product(VENUES, YEARS, TRACKS, STATUSES)` assigns
# every record, so reading vocab.TRACKS would reshuffle the whole corpus and every fixture and bench built on it
TRACKS = ("main", "datasets_benchmarks", "position", "workshop", "competition", "tiny_papers", "blogpost",
          "other", "unknown")  # fmt: skip
```

Run: `uv run pytest backend/tests/contract -q -x -p no:randomly` and confirm no fixture-staleness failure mentions
the synthetic corpus. If `make_reference_200.py:214` picks venues from `vocab`, pin it the same way.

- [ ] **Step 5: Update the vocabulary-driven tests and aliases**

- `backend/tests/strategies.py:144`: `"venue": list(VENUES.values())` stays derived if it already is; if it is the
  literal `["NeurIPS", "ICLR", "ICML"]`, replace it with `list(VENUES.values())` so generated queries cover the new
  venues. Do the same for `CLAUSE_VALUES`/`_FILTER_STRINGS` venue and track lists.
- `backend/tests/contract/conftest.py:74-78`: the venue → page dict gets an entry per new venue (follow the existing
  entries' shape).
- `backend/tests/unit/ingest/test_record.py` `VENUE_NAMES`: add the seven parametrized rows above.
- `backend/tests/contract/test_parse_papers_meta.py:282-283` and `frontend/src/test/api-stub.tsx:134-135`,
  `frontend/src/editor/complete.test.ts:26`: the vocabulary lists gain the new values.
- `query/compat.py` `SOURCE_ALIASES` gains (exact, after the token contract):
  `"aaai": "AAAI"`, `"association for the advancement of artificial intelligence": "AAAI"`, `"aies": "AIES"`,
  `"facct": "FAccT"`, `"fat*": "FAccT"` only if the lexer reads `fat*` as one token (check `normalize("FAT*")`; if it
  is a wildcard, leave it out and note why in a comment), `"iaseai": "IASEAI"`. Add one compat test per alias in
  `backend/tests/unit/test_compat.py`, mirroring an existing alias test.
- `query/parser.py:544` hint text: `"write venue:NeurIPS, venue:ICLR, venue:ICML, venue:AAAI, venue:AIES, venue:FAccT or venue:IASEAI"`; update the golden that pins it (search `backend/tests` for the old text).
- `frontend/src/components/paper-badges.tsx` `TRACK_SHORT` gains
  `student_abstract: { short: "student abstract", long: "student abstract" }`,
  `iaai: { short: "IAAI", long: "Innovative Applications of AI" }`,
  `eaai: { short: "EAAI", long: "Educational Advances in AI" }`, and a test in the badge's test file per entry.

- [ ] **Step 6: Run the affected suites**

Run: `uv run pytest backend/tests/unit backend/tests/contract -q -n auto` then `npm test --workspace frontend`.
Expected: PASS. Regenerate whatever a staleness test names (`make openapi` if `Vocabularies` changed the
snapshot; `uv run python backend/tests/contract/test_frontend_help_golden.py --write` style regenerators as their
failure message says) and re-run.

- [ ] **Step 7: Commit**

```bash
git add -A backend frontend
git commit -m "feat: AAAI, AIES, FAccT and IASEAI venues and five AAAI-family tracks in the vocabulary (decision-049)"
```

---

### Task 2: Record model — `ojs` source, `ojs-` native id, AAAI-only tracks, schema 6

**Files:**
- Modify: `backend/src/openproceedings/ingest/record.py:43-75, 315-340`
- Modify: `backend/src/openproceedings/ingest/statuses.py:33-42`
- Modify: `backend/src/openproceedings/ingest/dedup.py:75-80, 219-226`
- Modify: `backend/src/openproceedings/export.py:91` (`ORIGIN_NAMES`), `frontend/src/components/search/hit-item.tsx:105-112`
- Test: `backend/tests/unit/ingest/test_record.py` (append)

**Interfaces:**
- Consumes: Task 1's vocabulary.
- Produces: `record.Source` includes `"ojs"`; `record.PROCEEDINGS_NATIVE["ojs"] == (re.compile(r"ojs-[0-9]+"),
  frozenset({"AAAI", "AIES", "IASEAI"}))` (every entry's second element becomes a `frozenset[str]`);
  `record.VENUE_ONLY_TRACKS: Mapping[str, str] = {"iaai": "AAAI", "eaai": "AAAI"}`; `dedup.Origin` includes
  `"ojs"`; `export.ORIGIN_NAMES["ojs"] == "AAAI Digital Library"`.

- [ ] **Step 1: Write the failing tests** (append to `test_record.py`, reusing its existing record-building helper;
  if none exists, use `PaperRecord.build` directly as below)

```python
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from openproceedings.ingest.record import RECORD_SCHEMA_VERSION, PaperRecord

_T = datetime(2026, 10, 9, tzinfo=UTC)


def _ojs(venue: str = "AAAI", year: int = 2024, track: str = "main", native: str = "ojs-28000") -> PaperRecord:
    return PaperRecord.build(
        id=f"op:{venue.lower()}:{year}:{native}", title="A paper", abstract=None, authors=("A. Author",),
        venue=venue, year=year, track=track, status="accepted",
    )


def test_schema_is_6() -> None:
    assert RECORD_SCHEMA_VERSION == "6"


@pytest.mark.parametrize(("venue", "year"), [("AAAI", 2010), ("AIES", 2024), ("IASEAI", 2026)])
def test_ojs_native_id_is_valid_for_its_venues(venue: str, year: int) -> None:
    assert _ojs(venue, year).native == "ojs-28000"


def test_ojs_native_id_is_refused_for_another_venue() -> None:
    with pytest.raises(ValidationError, match="not a valid"):
        _ojs("ICML", 2024)


@pytest.mark.parametrize("native", ["ojs-", "ojs-12a", "ojs-1-2"])
def test_malformed_ojs_native_id_is_refused(native: str) -> None:
    with pytest.raises(ValidationError):
        _ojs(native=native)


@pytest.mark.parametrize("track", ["iaai", "eaai"])
def test_iaai_and_eaai_are_aaai_only(track: str) -> None:
    assert _ojs(track=track).track == track
    with pytest.raises(ValidationError, match="only an AAAI track"):
        _ojs("AIES", 2024, track=track)


@pytest.mark.parametrize("track", ["student_abstract", "consortium", "demo"])
def test_other_new_tracks_are_open_to_every_venue(track: str) -> None:
    assert _ojs("AIES", 2025, track=track).track == track
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest backend/tests/unit/ingest/test_record.py -q -k "ojs or schema_is_6 or aaai_only or open_to_every"`
Expected: FAIL (schema `"5"`; `native id 'ojs-28000' is neither an OpenReview forum id nor a proceedings id`).

- [ ] **Step 3: Implement in `record.py`**

```python
# 6: the AAAI, AIES, FAccT and IASEAI venues, five tracks, the `ojs` source and the `ojs-<article id>` native id
# (decision-049); 5: the `dblp` and `icml_site` sources and the `dblp-<key>` native id (TASK-205/206, decision-047);
# 4: the `twin` and `invitation` claim fields (TASK-159, TASK-157; decision-029)
RECORD_SCHEMA_VERSION = "6"
...
Source = Literal[
    "openreview_v2", "openreview_v1", "iclr_archive", "neurips_proceedings", "pmlr", "dblp", "icml_site", "ojs",
    "ris",
]  # fmt: skip
...
PROCEEDINGS_NATIVE: dict[str, tuple[re.Pattern[str], frozenset[str]]] = {
    "pmlr": (re.compile(r"pmlr-v[0-9]+-[A-Za-z0-9_-]+"), frozenset({"ICML"})),
    "nips": (
        re.compile(rf"nips-[0-9a-f]{{32}}(?:-(?:{'|'.join(sorted(NEURIPS_DB_2021_ROUNDS))}))?"),
        frozenset({"NeurIPS"}),
    ),
    "iclr": (re.compile(r"iclr-[0-9a-f]{32}"), frozenset({"ICLR"})),
    "dblp": (re.compile(r"dblp-[A-Za-z0-9_-]+"), frozenset({"ICML"})),
    # an ojs.aaai.org article id (`oai:ojs.aaai.org:article/<id>`), unique across its journals (sources/ojs.py)
    "ojs": (re.compile(r"ojs-[0-9]+"), frozenset({"AAAI", "AIES", "IASEAI"})),
}
# tracks only one venue has (decision-049): IAAI and EAAI are printed in the AAAI volumes alone
VENUE_ONLY_TRACKS: Mapping[str, str] = MappingProxyType({"iaai": "AAAI", "eaai": "AAAI"})
```

(import `MappingProxyType` from `types`). In `_consistent`, replace the venue check:

```python
        if form is not None:
            pattern, venues = form
            if not pattern.fullmatch(native) or self.venue not in venues:
                raise ValueError(
                    f"native id {native!r} is not a valid {'/'.join(sorted(venues))} proceedings id for {self.venue}"
                )
```

and after the native-id block, before the hash:

```python
        if (only := VENUE_ONLY_TRACKS.get(self.track)) is not None and only != self.venue:
            raise ValueError(f"track {self.track!r} is only an {only} track, not {self.venue}'s")
```

Search the package for other readers of `PROCEEDINGS_NATIVE[...][1]` (`grep -rn "PROCEEDINGS_NATIVE" backend/src`)
and adapt each to the frozenset.

- [ ] **Step 4: The `ojs` source everywhere a source is enumerated**

- `statuses.py` `SOURCE_STATUSES`: `"ojs": (ACCEPTED_ONLY, ACCEPTED_ONLY),` with the comment
  `# AAAI 2010+, AIES 2024+, IASEAI 2026+ from ojs.aaai.org: published papers only (decision-049)`.
- `dedup.py` `_TEXT`: insert `"ojs"` after `"icml_site"` (before `"ris"`); `_ACCEPTANCE`: insert `"ojs"` after
  `"dblp"`. `ojs` is **not** added to `PROCEEDINGS_SOURCES` (as dblp isn't: no other source holds its venue-years,
  so reconcile never judges them); add one comment line saying so beside the dblp one.
- `dedup.py` `Origin`: add `"ojs"`; `_DIRECT_ORIGIN["ojs"] = "ojs"`.
- `export.py` `ORIGIN_NAMES["ojs"] = "AAAI Digital Library"` (the name ojs.aaai.org gives itself) and the same
  entry in `frontend/src/components/search/hit-item.tsx` `ORIGIN_NAMES`; add the row to any test that enumerates
  `ORIGIN_NAMES` (`grep -rn ORIGIN_NAMES backend/tests frontend/src`).

- [ ] **Step 5: Run**

Run: `uv run pytest backend/tests/unit -q -n auto` and `npm test --workspace frontend`. Expected: PASS. Then
`make openapi` (the `Source`/`Origin` literals are in the API schema) and commit both generated files.

- [ ] **Step 6: Commit**

```bash
git add -A backend frontend
git commit -m "feat: the ojs claim source and ojs-<article id> native id; iaai/eaai only on AAAI; record schema 6 (decision-049)"
```

---

### Task 3: HTTP layer — whole-XML check and Fetcher options

**Files:**
- Modify: `backend/src/openproceedings/ingest/sources/http.py:264-286` (`Policy`), `:450-470` (`_truncated`),
  `:576-590` (`Fetcher.__init__`), module docstring bullet on truncation
- Test: `backend/tests/unit/ingest/test_http.py` (append)

**Interfaces:**
- Produces: `Policy.expect: Literal["html", "json", "xml"]`; `Fetcher(cache, transport, *, hosts, min_interval=1.0,
  attempts=5, max_wait=3600.0, timeout=30.0, clock=None, accept="text/html", expect="html", keep_query=False)`.
  With `expect="xml"` a 200 is whole when its body, stripped of trailing whitespace, ends with the closing tag of
  its root element (`</OAI-PMH>` for OAI-PMH); otherwise `truncated` and retried.

- [ ] **Step 1: Write the failing tests** (use the file's existing `FakeTransport`/`response` helpers from
  `proceedings_helpers.py`)

```python
from openproceedings.ingest.sources.http import Fetcher, PageCache, RetriesExhausted
from tests.unit.ingest.proceedings_helpers import FakeTransport, response

OAI = "https://ojs.aaai.org/index.php/AAAI/oai?verb=ListRecords&metadataPrefix=oai_dc"
WHOLE = '<?xml version="1.0"?><OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/"><ListRecords/></OAI-PMH>\n'
CUT = WHOLE[:60]


def _xml_fetcher(tmp_path, transport):
    return Fetcher(PageCache(tmp_path), transport, hosts=frozenset({"ojs.aaai.org"}), min_interval=0.0,
                   attempts=2, accept="application/xml", expect="xml", keep_query=True)


def test_xml_page_is_kept_with_its_query(tmp_path, no_sleep) -> None:
    t = FakeTransport({OAI: response(WHOLE, headers={"content-type": "text/xml; charset=utf-8"})})
    page = _xml_fetcher(tmp_path, t).get(OAI)
    assert page.ok and page.url == OAI  # the query names the resource: kept in the URL and the cache key


def test_truncated_xml_is_retried_then_refused(tmp_path, no_sleep) -> None:
    t = FakeTransport({OAI: [response(CUT, headers={"content-type": "text/xml"})]})
    with pytest.raises(RetriesExhausted):
        _xml_fetcher(tmp_path, t).get(OAI)


def test_html_rule_unchanged_for_the_default_fetcher(tmp_path, no_sleep) -> None:
    url = "https://ojs.aaai.org/index.php/AAAI/issue/archive"
    t = FakeTransport({url: response("<html><body>ok</body></html>")})
    f = Fetcher(PageCache(tmp_path), t, hosts=frozenset({"ojs.aaai.org"}), min_interval=0.0)
    assert f.get(url).ok
```

(`no_sleep` is the fixture the existing http tests use to skip waits; if it is named differently in
`test_http.py`, use that name. If `FakeTransport` needs the canonical URL as its key, build the key with
`canonical(OAI, keep_query=True)`.)

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest backend/tests/unit/ingest/test_http.py -q -k xml`
Expected: FAIL (`TypeError: Fetcher.__init__() got an unexpected keyword argument 'accept'`).

- [ ] **Step 3: Implement**

`Policy.expect: Literal["html", "json", "xml"] = "html"`. In `_truncated`, before the JSON branch:

```python
        if self.policy.expect == "xml":
            # whole when the body ends with its root element's closing tag (`</OAI-PMH>`); a cut-off body never does
            root = _XML_ROOT.search(response.body[:4096])
            tail = response.body.rstrip()[-256:]
            return None if root and tail.endswith(b"</" + root.group(1) + b">") else "truncated"
```

with, at module level, `_XML_ROOT = re.compile(rb"<([A-Za-z_][\w.-]*(?::[\w.-]+)?)[\s>/]")` skipping the XML
declaration and processing instructions — so match after them:

```python
_XML_ROOT = re.compile(rb"(?:<\?[^>]*\?>\s*)*<([A-Za-z_][\w.:-]*)[\s>/]")
```

and use `_XML_ROOT.match(response.body.lstrip()[:4096])`. `Fetcher.__init__` gains `accept: str = "text/html",
expect: Literal["html", "json", "xml"] = "html", keep_query: bool = False` and passes them to
`replace(PROCEEDINGS, …)`. Update the module docstring's truncation sentence: "(an HTML page without `</html>`, an
XML document not ending in its root's closing tag, or JSON that doesn't parse; …)".

- [ ] **Step 4: Run and commit**

Run: `uv run pytest backend/tests/unit/ingest/test_http.py backend/tests/unit/ingest/test_fetch.py -q`. Expected: PASS.

```bash
git add backend/src/openproceedings/ingest/sources/http.py backend/tests/unit/ingest/test_http.py
git commit -m "feat: the HTTP layer judges an XML response whole by its root's closing tag; Fetcher takes accept/expect/keep_query"
```

---

### Task 4: The OJS table and miner

**Files:**
- Create: `backend/src/openproceedings/ingest/ojs_table.py`, `backend/src/openproceedings/ingest/ojs_sections.toml`
- Create: `backend/src/openproceedings/ingest/sources/ojs.py`
- Modify: `backend/src/openproceedings/ingest/urls.py` (`ojs_article`, `native`)
- Create: `backend/tests/unit/ingest/ojs/__init__.py`, `test_ojs_table.py`, `test_ojs_parse.py`, `test_ojs_mine.py`,
  `backend/tests/unit/ingest/ojs/oai.py` (builders for synthetic OAI-PMH pages)
- Modify: `backend/tests/unit/ingest/proceedings_helpers.py` (`seed(..., keep_query=False)`)

**Interfaces:**
- Consumes: Task 1–3 (`Fetcher(..., expect="xml", keep_query=True)`, `Source "ojs"`, the `ojs-` native id).
- Produces:
  - `ojs_table.Journal(code: str, venue: str, year_offset: int, verified: date, source: str)`;
    `ojs_table.Section(journal: str, volume: int, set_spec: str, kind: Literal["papers", "front_matter"],
    track: str | None, label: str, papers: int, verified: date, source: str)`;
    `ojs_table.Table(journals: Mapping[str, Journal], sections: Mapping[tuple[str, int, str], Section])` with
    `year(journal, volume) -> int`, `volumes(journal) -> tuple[int, ...]`, `expected(journal, volume) -> int` (sum
    of `papers` over `kind == "papers"` rows); `ojs_table.load(text: str) -> Table`; `ojs_table.TABLE: Table`.
  - `ojs.SOURCE = "ojs"`, `ojs.CACHE_DIR = "ojs"`, `ojs.HOST = "ojs.aaai.org"`, `ojs.HOSTS`, `ojs.MIN_INTERVAL = 3.0`.
  - `ojs.OaiRecord(article: int, deleted: bool, set_spec: str, title: str | None, creators: tuple[str, ...],
    description: str | None, doi: str | None, article_url: str | None, pdf_url: str | None, volume: int | None)`.
  - `ojs.parse_page(text: str) -> tuple[list[OaiRecord], str | None]` (records, next resumption token or None);
    raises `CrawlError` (reason `oai_error` with the OAI code, or `oai_unreadable`).
  - `ojs.display_name(creator: str) -> str`.
  - `ojs.JournalResult(records: list[PaperRecord], reports: list[ListingReport], deleted: int, front_matter: int,
    pages: int)`.
  - `ojs.mine_journal(journal: str, fetcher: Fetcher, *, refresh: bool = False, table: Table | None = None) ->
    JournalResult` (None: `ojs.TABLE`, read when called).
  - `urls.ojs_article(url: str) -> int | None`; `urls.native()` returns `ojs-<id>` for an OJS article URL.

- [ ] **Step 1: The table loader — failing tests**

```python
# backend/tests/unit/ingest/ojs/test_ojs_table.py
from datetime import date

import pytest

from openproceedings.ingest import ojs_table

GOOD = """
[[journal]]
code = "AAAI"
venue = "AAAI"
year_offset = 1986
verified = 2026-10-09
source = "docs/research/2026-10-09-aaai-aies-facct-iaseai-sources.md"

[[section]]
journal = "AAAI"
volume = 34
set_spec = "AAAI:AISI"
kind = "papers"
track = "main"
label = "Special Track on AI for Social Impact"
papers = 70
verified = 2026-10-09
source = "backend/tests/fixtures/http/ojs/aaai-v34-aisi.json"

[[section]]
journal = "AAAI"
volume = 34
set_spec = "AAAI:FMT"
kind = "front_matter"
label = "Front Matter"
papers = 1
verified = 2026-10-09
source = "x"
"""


def test_loads_and_derives_year_and_expected_count() -> None:
    t = ojs_table.load(GOOD)
    assert t.year("AAAI", 34) == 2020
    assert t.volumes("AAAI") == (34,)
    assert t.expected("AAAI", 34) == 70  # front matter is counted, never a paper
    assert t.sections[("AAAI", 34, "AAAI:AISI")].track == "main"
    assert t.journals["AAAI"].verified == date(2026, 10, 9)


@pytest.mark.parametrize(
    ("edit", "message"),
    [
        (lambda s: s.replace('track = "main"', 'track = "mainn"'), "not a spec 01 track"),
        (lambda s: s.replace('venue = "AAAI"', 'venue = "AAAJ"'), "not one of"),
        (lambda s: s.replace('kind = "papers"', 'kind = "paper"'), "kind"),
        (lambda s: s.replace("papers = 70", "papers = 0"), "positive"),
        (lambda s: s.replace('kind = "front_matter"\nlabel', 'kind = "front_matter"\ntrack = "main"\nlabel'),
         "front matter has no track"),
        (lambda s: s + s[s.index("[[section]]"):s.index("[[section]]", s.index("[[section]]") + 1)],
         "listed twice"),
        (lambda s: s.replace("year_offset = 1986", "year_offset = 1900"), "not held under that name"),
        (lambda s: s.replace('track = "main"', 'track = "iaai"').replace('venue = "AAAI"', 'venue = "AIES"')
         .replace('code = "AAAI"', 'code = "AIES"').replace('journal = "AAAI"', 'journal = "AIES"')
         .replace("year_offset = 1986", "year_offset = 2017").replace("volume = 34", "volume = 7"),
         "only an AAAI track"),
        (lambda s: s.replace('journal = "AAAI"\nvolume = 34\nset_spec = "AAAI:AISI"',
                             'journal = "AIES"\nvolume = 34\nset_spec = "AAAI:AISI"'), "no journal row"),
    ],
)
def test_bad_rows_are_refused(edit, message) -> None:
    with pytest.raises(ValueError, match=message):
        ojs_table.load(edit(GOOD))


def test_the_shipped_table_loads() -> None:
    assert set(ojs_table.TABLE.journals) == {"AAAI", "AIES", "IASEAI"}
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest backend/tests/unit/ingest/ojs/test_ojs_table.py -q` — Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement `ojs_table.py`** (pattern: `ingest/volumes.py`)

```python
"""The ojs.aaai.org table (spec 01 §Sources, OJS row; decision-049): which journals are harvested, how a volume
names its year, and, per journal, volume and OAI set (an OJS section), the track and the verified paper count.

Data, not code: `ojs_sections.toml` beside this module, loaded and checked once at import; a malformed row is an
import error, never a best guess. An OJS issue is not a track (AAAI 2026 has 48 issues, most "Technical Tracks N";
an issue may mix IAAI, EAAI and student abstracts), so the track comes from the record's section (its OAI
`setSpec`, one per record), and set names change by year (`ML-I`, `ML-I-23`; `AI24-n` and `AI26-n` mean different
tracks), so every row names its volume. A record whose volume or section has no row stops the crawl
(`sources/ojs.py`). `front_matter` rows (prefaces, indexes) are counted, never records.
"""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from importlib.resources import files
from types import MappingProxyType
from typing import Any, Literal, get_args

from openproceedings.ingest.record import VENUE_ONLY_TRACKS
from openproceedings.vocab import TRACKS, VENUES, venue_name

Kind = Literal["papers", "front_matter"]
KINDS: tuple[str, ...] = get_args(Kind)
_JOURNAL_COLUMNS = {"code", "venue", "year_offset", "verified", "source"}
_SECTION_COLUMNS = {"journal", "volume", "set_spec", "kind", "track", "label", "papers", "verified", "source"}


@dataclass(frozen=True, slots=True)
class Journal:
    code: str  # the OJS path, `https://ojs.aaai.org/index.php/<code>/oai`
    venue: str
    year_offset: int  # year = volume + year_offset
    verified: date
    source: str


@dataclass(frozen=True, slots=True)
class Section:
    journal: str
    volume: int
    set_spec: str  # the OAI setSpec, e.g. `AAAI:AISI`
    kind: Kind
    track: str | None  # None only for front matter
    label: str  # the section's title on ojs.aaai.org, kept in the track claim's evidence
    papers: int  # records in this section of this volume when verified
    verified: date
    source: str


@dataclass(frozen=True, slots=True)
class Table:
    journals: Mapping[str, Journal]
    sections: Mapping[tuple[str, int, str], Section]

    def year(self, journal: str, volume: int) -> int:
        return volume + self.journals[journal].year_offset

    def volumes(self, journal: str) -> tuple[int, ...]:
        return tuple(sorted({v for (j, v, _s) in self.sections if j == journal}))

    def expected(self, journal: str, volume: int) -> int:
        return sum(s.papers for (j, v, _s), s in self.sections.items() if (j, v) == (journal, volume)
                   and s.kind == "papers")  # fmt: skip


def _check(raw: Mapping[str, Any], columns: set[str], required: set[str], where: str) -> None:
    if unknown := set(raw) - columns:
        raise ValueError(f"{where}: unknown columns {sorted(unknown)}")
    if missing := required - set(raw):
        raise ValueError(f"{where}: missing columns {sorted(missing)}")
    if not isinstance(raw["verified"], date) or not isinstance(raw["source"], str) or not raw["source"]:
        raise ValueError(f"{where}: every row needs a verified date and a source")


def _journal(raw: Mapping[str, Any]) -> Journal:
    where = f"ojs_sections.toml journal {raw.get('code')!r}"
    _check(raw, _JOURNAL_COLUMNS, _JOURNAL_COLUMNS, where)
    if raw["venue"] not in VENUES.values():
        raise ValueError(f"{where}: venue {raw['venue']!r} is not one of {sorted(VENUES.values())}")
    if type(raw["year_offset"]) is not int:
        raise ValueError(f"{where}: year_offset must be an integer")
    return Journal(raw["code"], raw["venue"], raw["year_offset"], raw["verified"], raw["source"])


def _section(raw: Mapping[str, Any], journals: Mapping[str, Journal]) -> Section:
    where = f"ojs_sections.toml section {raw.get('journal')!r} v{raw.get('volume')!r} {raw.get('set_spec')!r}"
    _check(raw, _SECTION_COLUMNS, _SECTION_COLUMNS - {"track"}, where)
    journal = journals.get(raw["journal"])
    if journal is None:
        raise ValueError(f"{where}: no journal row for {raw['journal']!r}")
    volume, papers, kind, track = raw["volume"], raw["papers"], raw["kind"], raw.get("track")
    if type(volume) is not int or volume <= 0:
        raise ValueError(f"{where}: volume must be a positive integer")
    if type(papers) is not int or papers <= 0:
        raise ValueError(f"{where}: papers must be a positive integer")
    if kind not in KINDS:
        raise ValueError(f"{where}: kind {kind!r} is not one of {KINDS}")
    if kind == "front_matter" and track is not None:
        raise ValueError(f"{where}: front matter has no track (it is counted, never a record)")
    if kind == "papers":
        if track not in TRACKS:
            raise ValueError(f"{where}: track {track!r} is not a spec 01 track")
        if (only := VENUE_ONLY_TRACKS.get(track)) is not None and only != journal.venue:
            raise ValueError(f"{where}: {track!r} is only an {only} track")
    venue_name(journal.venue, volume + journal.year_offset)  # a year the venue wasn't held is refused
    if not isinstance(raw["label"], str) or not raw["label"]:
        raise ValueError(f"{where}: label must be the section's title")
    return Section(raw["journal"], volume, raw["set_spec"], kind, track, raw["label"], papers, raw["verified"],
                   raw["source"])  # fmt: skip


def load(text: str) -> Table:
    data = tomllib.loads(text)
    journals: dict[str, Journal] = {}
    for j in (_journal(r) for r in data.get("journal", [])):
        if j.code in journals:
            raise ValueError(f"ojs_sections.toml: journal {j.code} is listed twice")
        journals[j.code] = j
    sections: dict[tuple[str, int, str], Section] = {}
    for s in (_section(r, journals) for r in data.get("section", [])):
        key = (s.journal, s.volume, s.set_spec)
        if key in sections:
            raise ValueError(f"ojs_sections.toml: section {key} is listed twice")
        sections[key] = s
    return Table(MappingProxyType(journals), MappingProxyType(dict(sorted(sections.items()))))


TABLE: Table = load(files("openproceedings.ingest").joinpath("ojs_sections.toml").read_text(encoding="utf-8"))
```

Create `ojs_sections.toml` with the header comment (columns, as `pmlr_volumes.toml` documents its own) and the
three `[[journal]]` rows (AAAI 1986, AIES 2017, IASEAI 2024; `verified = 2026-10-09`, source the research note).
Section rows arrive in Task 6; until then the shipped table has journals only, and `test_the_shipped_table_loads`
passes. Check that `pyproject.toml`/the package build includes `*.toml` under `ingest/` (it already ships
`pmlr_volumes.toml`; confirm the glob covers the new file).

Run: `uv run pytest backend/tests/unit/ingest/ojs/test_ojs_table.py -q` — Expected: PASS. Commit:

```bash
git add backend/src/openproceedings/ingest/ojs_table.py backend/src/openproceedings/ingest/ojs_sections.toml backend/tests/unit/ingest/ojs
git commit -m "feat: the ojs.aaai.org journal and section table (decision-049)"
```

- [ ] **Step 4: The OAI-PMH parser — failing tests**

`backend/tests/unit/ingest/ojs/oai.py` builds synthetic pages, so each test states its own input:

```python
"""Synthetic OAI-PMH ListRecords pages in the shape ojs.aaai.org serves (checked live 2026-10-09)."""

from xml.sax.saxutils import escape

BASE = "https://ojs.aaai.org/index.php/{j}/oai"


def record(article: int, set_spec: str = "AAAI:AISI", *, title: str = "A Paper", creators=("Doe, Jane",),
           description: str | None = "An abstract.", volume: str = "Vol. 34 No. 01: AAAI-20 Technical Tracks 1",
           journal: str = "AAAI", extra: str = "") -> str:
    desc = "" if description is None else f'<dc:description xml:lang="en-US">{escape(description)}</dc:description>'
    names = "".join(f"<dc:creator>{escape(c)}</dc:creator>" for c in creators)
    return f"""<record><header><identifier>oai:ojs.aaai.org:article/{article}</identifier>
<datestamp>2026-07-15T06:11:29Z</datestamp><setSpec>{set_spec}</setSpec></header><metadata>
<oai_dc:dc xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/" xmlns:dc="http://purl.org/dc/elements/1.1/">
<dc:title xml:lang="en-US">{escape(title)}</dc:title>{names}{desc}{extra}
<dc:identifier>https://ojs.aaai.org/index.php/{journal}/article/view/{article}</dc:identifier>
<dc:identifier>10.1609/{journal.lower()}.v34i01.{article}</dc:identifier>
<dc:source xml:lang="en-US">Proceedings of the AAAI Conference on Artificial Intelligence; {volume}; 1-8</dc:source>
<dc:source>2374-3468</dc:source>
<dc:relation>https://ojs.aaai.org/index.php/{journal}/article/view/{article}/{article + 7000}</dc:relation>
</oai_dc:dc></metadata></record>"""


def deleted(article: int, set_spec: str = "AAAI:AISI") -> str:
    return f"""<record><header status="deleted"><identifier>oai:ojs.aaai.org:article/{article}</identifier>
<datestamp>2026-07-15T06:11:29Z</datestamp><setSpec>{set_spec}</setSpec></header></record>"""


def page(*records: str, token: str | None = None, size: int | None = None) -> str:
    rt = "" if token is None else (
        f'<resumptionToken expirationDate="2026-10-10T22:01:20Z" completeListSize="{size or 0}" cursor="0">'
        f"{token}</resumptionToken>")
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/"><responseDate>2026-10-09T22:01:20Z</responseDate>
<request verb="ListRecords" metadataPrefix="oai_dc">https://ojs.aaai.org/index.php/AAAI/oai</request>
<ListRecords>{''.join(records)}{rt}</ListRecords></OAI-PMH>
"""


def error(code: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/"><responseDate>2026-10-09T22:01:20Z</responseDate>
<request>https://ojs.aaai.org/index.php/AAAI/oai</request><error code="{code}">message</error></OAI-PMH>
"""
```

```python
# backend/tests/unit/ingest/ojs/test_ojs_parse.py
import pytest

from openproceedings.ingest.sources import ojs
from openproceedings.ingest.sources.common import CrawlError
from tests.unit.ingest.ojs import oai


def test_a_record_and_the_next_token() -> None:
    records, token = ojs.parse_page(oai.page(oai.record(28000), token="c83a", size=115))
    assert token == "c83a"
    (r,) = records
    assert (r.article, r.deleted, r.set_spec, r.volume) == (28000, False, "AAAI:AISI", 34)
    assert r.title == "A Paper" and r.creators == ("Doe, Jane",) and r.description == "An abstract."
    assert r.doi == "10.1609/aaai.v34i01.28000"
    assert r.article_url == "https://ojs.aaai.org/index.php/AAAI/article/view/28000"
    assert r.pdf_url == "https://ojs.aaai.org/index.php/AAAI/article/view/28000/35000"


def test_last_page_has_no_token_and_an_empty_token_is_the_end() -> None:
    assert ojs.parse_page(oai.page(oai.record(1)))[1] is None
    assert ojs.parse_page(oai.page(oai.record(1), token=""))[1] is None  # OAI-PMH: empty token = list complete


def test_deleted_header_has_no_metadata() -> None:
    (r,), _ = ojs.parse_page(oai.page(oai.deleted(42953)))
    assert r.deleted and r.title is None and r.volume is None


def test_english_title_wins_over_other_locales() -> None:
    extra = '<dc:title xml:lang="fr-FR">Un article</dc:title>'
    rec = oai.record(5, extra=extra).replace('<dc:title xml:lang="en-US">A Paper</dc:title>', extra + '<dc:title xml:lang="en-US">A Paper</dc:title>', 1)
    (r,), _ = ojs.parse_page(oai.page(rec))
    assert r.title == "A Paper"


def test_first_title_when_none_is_english() -> None:
    rec = oai.record(5).replace('xml:lang="en-US">A Paper', 'xml:lang="de-DE">Ein Papier')
    (r,), _ = ojs.parse_page(oai.page(rec))
    assert r.title == "Ein Papier"


def test_missing_description_is_none() -> None:
    (r,), _ = ojs.parse_page(oai.page(oai.record(5, description=None)))
    assert r.description is None


@pytest.mark.parametrize("code", ["badResumptionToken", "badArgument", "cannotDisseminateFormat"])
def test_oai_error_stops(code: str) -> None:
    with pytest.raises(CrawlError, match=code) as e:
        ojs.parse_page(oai.error(code))
    assert e.value.reason == "oai_error"


def test_no_records_match_is_an_empty_page() -> None:
    assert ojs.parse_page(oai.error("noRecordsMatch")) == ([], None)


@pytest.mark.parametrize("text", ["<html><body>Maintenance</body></html>", "not xml", ""])
def test_a_page_that_is_not_oai_pmh_stops(text: str) -> None:
    with pytest.raises(CrawlError) as e:
        ojs.parse_page(text)
    assert e.value.reason == "oai_unreadable"


@pytest.mark.parametrize("prolog", ["", "<!-- " + "x" * 5000 + " -->"])
def test_a_doctype_is_refused_wherever_it_sits(prolog: str) -> None:  # no entity expansion from a response
    text = f'<?xml version="1.0"?>{prolog}<!DOCTYPE x [<!ENTITY a "b">]><OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/"/>'
    with pytest.raises(CrawlError, match="DOCTYPE") as e:
        ojs.parse_page(text)
    assert e.value.reason == "oai_unreadable"


@pytest.mark.parametrize(
    ("raw", "shown"),
    [("Doe, Jane", "Jane Doe"), ("van der Berg, Anna-Lena", "Anna-Lena van der Berg"),
     ("Smith, Jr., John", "Smith, Jr., John"), ("Aristotle", "Aristotle"), ("  Doe ,  Jane ", "Jane Doe")],
)
def test_display_name(raw: str, shown: str) -> None:
    assert ojs.display_name(raw) == shown
```

Run: `uv run pytest backend/tests/unit/ingest/ojs/test_ojs_parse.py -q` — Expected: FAIL (`ImportError`).

- [ ] **Step 5: Implement the parser part of `sources/ojs.py`**

```python
"""ojs.aaai.org miner: AAAI 2010-2026, AIES 2024+ and IASEAI 2026+ through OAI-PMH (spec 01 §Sources, OJS row;
decision-049).

Each journal (`ojs_table.TABLE.journals`) is harvested whole: `ListRecords` in `oai_dc`, then each
`resumptionToken` in turn, every page through the shared HTTP layer (XML judged whole by its root's closing tag;
the query string names the page, so it is the cache key). A crawl is replayed offline by following the same chain
through the cache. OJS tokens are opaque and expire after 24 h: a resumed crawl whose next token the server no
longer knows gets `badResumptionToken`, which stops the crawl with what to do (`--refresh` starts the chain again).

A record's article id is its native id (`ojs-<id>`), its section (`setSpec`) and volume (`dc:source`'s
`Vol. N No. M`) name its table row, which gives the track and the year (`ojs_table`); a volume or section the table
lacks stops the crawl. Deleted headers and front-matter sections are counted, never records. The abstract is
`dc:description` (the English one, else the first), cleaned like every abstract (`common.clean_abstract`).
Authors come as `Last, First` and are shown `First Last` (`display_name`). Every record is `accepted`.
"""

from __future__ import annotations

import logging
import re
import time
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import quote

from pydantic import ValidationError

from openproceedings.ingest.ojs_table import TABLE, Table
from openproceedings.ingest.record import (
    Claim, ClaimField, ClaimValue, PaperRecord, Source, controls_evidence, is_url, title_evidence, title_text,
)  # fmt: skip
from openproceedings.ingest.sources.common import (
    CrawlError, ListingReport, clean_abstract, pdf_codes_evidence, record_from_claims,
)  # fmt: skip
from openproceedings.ingest.sources.http import Fetcher, Page
from openproceedings.logs import elapsed_ms

log = logging.getLogger(__name__)

SOURCE: Source = "ojs"
CACHE_DIR = "ojs"  # <data>/cache/ojs
HOST = "ojs.aaai.org"
HOSTS = frozenset({HOST})
MIN_INTERVAL = 3.0  # seconds between requests: the server takes 2-3 s a page (checked 2026-10-09)
PROGRESS_SECONDS = 30.0

_OAI = "{http://www.openarchives.org/OAI/2.0/}"
_DC = "{http://purl.org/dc/elements/1.1/}"
_LANG = "{http://www.w3.org/XML/1998/namespace}lang"
_ARTICLE = re.compile(r"oai:ojs\.aaai\.org:article/([0-9]+)")
_VOLUME = re.compile(r";\s*Vol\.\s*([0-9]+)\s+No\.\s*[0-9]+")
_DOI = re.compile(r"10\.1609/\S+")
_EMPTY_LIST = "noRecordsMatch"  # an OAI-PMH error code that means an empty list, not a failure


def oai_url(journal: str, token: str | None = None) -> str:
    base = f"https://{HOST}/index.php/{journal}/oai?verb=ListRecords&"
    return base + ("metadataPrefix=oai_dc" if token is None else f"resumptionToken={quote(token, safe='')}")


@dataclass(frozen=True, slots=True)
class OaiRecord:
    article: int
    deleted: bool
    set_spec: str
    title: str | None = None
    creators: tuple[str, ...] = ()
    description: str | None = None
    doi: str | None = None
    article_url: str | None = None
    pdf_url: str | None = None
    volume: int | None = None


def _refuse_doctype(*_args: object) -> None:
    raise CrawlError("an OAI-PMH page declared a DOCTYPE; refused (no entities from a response)",
                     reason="oai_unreadable")


def _parser() -> ET.XMLParser:
    """The stdlib parser with every DOCTYPE refused, wherever it sits: no entity is ever declared or expanded
    (no XXE, no billion laughs), the posture `dblp_xml.py` takes with expat (it allows only its pinned DTD)."""
    parser = ET.XMLParser()
    parser.parser.StartDoctypeDeclHandler = _refuse_doctype  # type: ignore[attr-defined]
    parser.parser.EntityDeclHandler = _refuse_doctype  # type: ignore[attr-defined]
    return parser


def _english_first(nodes: list[ET.Element]) -> str | None:
    texts = [(n.get(_LANG, ""), (n.text or "").strip()) for n in nodes if (n.text or "").strip()]
    return next((t for lang, t in texts if lang.lower().startswith("en")), texts[0][1] if texts else None)


def parse_page(text: str) -> tuple[list[OaiRecord], str | None]:
    """The records on one ListRecords page and the next resumption token (None: the list is complete)."""
    try:
        root = ET.fromstring(text, parser=_parser())
    except ET.ParseError:
        raise CrawlError("an ojs.aaai.org OAI-PMH page is not XML", reason="oai_unreadable") from None
    if root.tag != f"{_OAI}OAI-PMH":
        raise CrawlError("an ojs.aaai.org page is not an OAI-PMH response", reason="oai_unreadable")
    if (err := root.find(f"{_OAI}error")) is not None:
        code = err.get("code", "")
        if code == _EMPTY_LIST:
            return [], None
        hint = " (the resumption token expired: re-run with --refresh)" if code == "badResumptionToken" else ""
        raise CrawlError(f"ojs.aaai.org answered OAI-PMH error {code}{hint}", reason="oai_error")
    listing = root.find(f"{_OAI}ListRecords")
    if listing is None:
        raise CrawlError("an OAI-PMH response has no ListRecords", reason="oai_unreadable")
    out = []
    for rec in listing.findall(f"{_OAI}record"):
        header = rec.find(f"{_OAI}header")
        ident = header.findtext(f"{_OAI}identifier", "") if header is not None else ""
        m = _ARTICLE.fullmatch(ident.strip())
        if header is None or m is None:
            raise CrawlError(f"an OAI-PMH record has no ojs.aaai.org article id ({ident[:80]!r})",
                             reason="oai_unreadable")  # fmt: skip
        set_spec = (header.findtext(f"{_OAI}setSpec") or "").strip()
        if header.get("status") == "deleted":
            out.append(OaiRecord(int(m.group(1)), True, set_spec))
            continue
        dc = rec.find(f"{_OAI}metadata/*")
        dc = dc if dc is not None else ET.Element("none")
        idents = [(n.text or "").strip() for n in dc.findall(f"{_DC}identifier")]
        sources = " ".join((n.text or "") for n in dc.findall(f"{_DC}source"))
        volume = _VOLUME.search(sources)
        relations = [(n.text or "").strip() for n in dc.findall(f"{_DC}relation")]
        out.append(OaiRecord(
            article=int(m.group(1)), deleted=False, set_spec=set_spec,
            title=_english_first(dc.findall(f"{_DC}title")),
            creators=tuple(c for n in dc.findall(f"{_DC}creator") if (c := (n.text or "").strip())),
            description=_english_first(dc.findall(f"{_DC}description")),
            doi=next((i for i in idents if _DOI.fullmatch(i)), None),
            article_url=next((i for i in idents if i.startswith(f"https://{HOST}/") and "/article/view/" in i), None),
            pdf_url=next((r for r in relations if r.startswith(f"https://{HOST}/") and "/article/view/" in r), None),
            volume=int(volume.group(1)) if volume else None,
        ))  # fmt: skip
    token_node = listing.find(f"{_OAI}resumptionToken")
    token = (token_node.text or "").strip() if token_node is not None else ""
    return out, token or None


def display_name(creator: str) -> str:
    """`Doe, Jane` → `Jane Doe` (OJS writes surname first); any other shape (no comma, or more than one, as in
    `Smith, Jr., John`) is kept as published, whitespace collapsed."""
    parts = [" ".join(p.split()) for p in creator.split(",")]
    if len(parts) == 2 and all(parts):
        return f"{parts[1]} {parts[0]}"
    return " ".join(creator.split())
```

Run: `uv run pytest backend/tests/unit/ingest/ojs/test_ojs_parse.py -q` — Expected: PASS (adjust `display_name`
only if a case fails for a reason the test names). Commit:

```bash
git add backend/src/openproceedings/ingest/sources/ojs.py backend/tests/unit/ingest/ojs
git commit -m "feat: OAI-PMH ListRecords parser for ojs.aaai.org (records, tokens, errors, locales, names)"
```

- [ ] **Step 6: The miner — failing tests**

Extend `proceedings_helpers.seed` with `keep_query: bool = False` passed to `canonical(url, keep_query=…)`.

```python
# backend/tests/unit/ingest/ojs/test_ojs_mine.py
from datetime import date

import pytest

from openproceedings.ingest import ojs_table
from openproceedings.ingest.sources import ojs
from openproceedings.ingest.sources.common import CrawlError
from openproceedings.ingest.sources.http import Fetcher, PageCache
from tests.unit.ingest.ojs import oai
from tests.unit.ingest.proceedings_helpers import seed

TABLE = ojs_table.load("""
[[journal]]
code = "AAAI"
venue = "AAAI"
year_offset = 1986
verified = 2026-10-09
source = "test"

[[section]]
journal = "AAAI"
volume = 34
set_spec = "AAAI:AISI"
kind = "papers"
track = "main"
label = "Special Track on AI for Social Impact"
papers = 2
verified = 2026-10-09
source = "test"

[[section]]
journal = "AAAI"
volume = 34
set_spec = "AAAI:IAAI"
kind = "papers"
track = "iaai"
label = "IAAI Technical Track on Emerging Applications of AI"
papers = 1
verified = 2026-10-09
source = "test"

[[section]]
journal = "AAAI"
volume = 34
set_spec = "AAAI:FMT"
kind = "front_matter"
label = "Front Matter"
papers = 1
verified = 2026-10-09
source = "test"
""")


def _offline(tmp_path) -> Fetcher:
    return Fetcher(PageCache(tmp_path / "ojs"), None, hosts=ojs.HOSTS, expect="xml", keep_query=True)


def _seed(tmp_path, *pages: str) -> None:
    """Seed a token chain: page i links to page i+1 by token `t<i+1>`."""
    for i, text in enumerate(pages):
        seed(tmp_path, "ojs", ojs.oai_url("AAAI", None if i == 0 else f"t{i}"), text, keep_query=True)


def test_two_pages_become_records_with_claims(tmp_path) -> None:
    _seed(tmp_path,
          oai.page(oai.record(28000, title="First"), oai.deleted(27999), token="t1"),
          oai.page(oai.record(28001, title="Second"), oai.record(28002, "AAAI:IAAI", title="Third"),
                   oai.record(28003, "AAAI:FMT", title="Preface")))
    result = ojs.mine_journal("AAAI", _offline(tmp_path), table=TABLE)
    ids = sorted(r.id for r in result.records)
    assert ids == ["op:aaai:2020:ojs-28000", "op:aaai:2020:ojs-28001", "op:aaai:2020:ojs-28002"]
    first = next(r for r in result.records if r.native == "ojs-28000")
    assert (first.track, first.status, first.authors, first.abstract) == ("main", "accepted", ("Jane Doe",), "An abstract.")
    assert first.urls.doi == "10.1609/aaai.v34i01.28000"
    assert first.urls.proceedings == "https://ojs.aaai.org/index.php/AAAI/article/view/28000"
    assert {c.source for c in first.provenance} == {"ojs"}
    track = next(c for c in first.provenance if c.field == "track")
    assert "Special Track on AI for Social Impact" in (track.evidence or "") and "AAAI:AISI" in (track.evidence or "")
    third = next(r for r in result.records if r.native == "ojs-28002")
    assert third.track == "iaai"
    assert (result.deleted, result.front_matter, result.pages) == (1, 1, 2)
    (report,) = result.reports
    assert (report.venue, report.year, report.volume, report.stated, report.listed, report.records) == (
        "AAAI", 2020, 34, 3, 3, 3)
    assert report.count_ok and report.tracks == {"main": 2, "iaai": 1}


def test_unlisted_section_stops(tmp_path) -> None:
    _seed(tmp_path, oai.page(oai.record(1, "AAAI:NEW")))
    with pytest.raises(CrawlError, match=r"AAAI v34 section AAAI:NEW") as e:
        ojs.mine_journal("AAAI", _offline(tmp_path), table=TABLE)
    assert e.value.reason == "unlisted_section"


def test_unlisted_volume_stops(tmp_path) -> None:
    _seed(tmp_path, oai.page(oai.record(1, volume="Vol. 41 No. 1: AAAI-27")))
    with pytest.raises(CrawlError, match=r"AAAI v41") as e:
        ojs.mine_journal("AAAI", _offline(tmp_path), table=TABLE)
    assert e.value.reason == "unlisted_volume"


def test_record_without_a_volume_stops(tmp_path) -> None:
    _seed(tmp_path, oai.page(oai.record(1, volume="no volume here")))
    with pytest.raises(CrawlError, match="no volume") as e:
        ojs.mine_journal("AAAI", _offline(tmp_path), table=TABLE)
    assert e.value.reason == "oai_unreadable"


def test_count_mismatch_is_reported_not_hidden(tmp_path) -> None:
    _seed(tmp_path, oai.page(oai.record(1), oai.record(2, "AAAI:IAAI")))  # AISI has 1 of its 2
    (report,) = ojs.mine_journal("AAAI", _offline(tmp_path), table=TABLE).reports
    assert not report.count_ok and (report.stated, report.listed) == (3, 2)


def test_a_record_without_title_is_skipped_and_counted(tmp_path) -> None:
    rec = oai.record(1).replace('<dc:title xml:lang="en-US">A Paper</dc:title>', "")
    _seed(tmp_path, oai.page(rec, oai.record(2), oai.record(3, "AAAI:IAAI")))
    result = ojs.mine_journal("AAAI", _offline(tmp_path), table=TABLE)
    assert result.reports[0].skipped == {"no_title": 1}
    assert len(result.records) == 2


def test_an_empty_creator_is_skipped(tmp_path) -> None:
    _seed(tmp_path, oai.page(oai.record(1, creators=("Doe, Jane", " ")), oai.record(2), oai.record(3, "AAAI:IAAI")))
    rec = next(r for r in ojs.mine_journal("AAAI", _offline(tmp_path), table=TABLE).records if r.native == "ojs-1")
    assert rec.authors == ("Jane Doe",)


def test_a_snippet_abstract_is_dropped(tmp_path) -> None:
    _seed(tmp_path, oai.page(oai.record(1, description="…a snippet"), oai.record(2), oai.record(3, "AAAI:IAAI")))
    rec = next(r for r in ojs.mine_journal("AAAI", _offline(tmp_path), table=TABLE).records if r.native == "ojs-1")
    assert rec.abstract is None


def test_the_same_article_twice_is_counted_once(tmp_path) -> None:
    _seed(tmp_path, oai.page(oai.record(1), token="t1"), oai.page(oai.record(1), oai.record(2), oai.record(3, "AAAI:IAAI")))
    result = ojs.mine_journal("AAAI", _offline(tmp_path), table=TABLE)
    assert len(result.records) == 3 and result.reports[0].skipped == {"duplicate": 1}


def test_a_journal_without_a_row_is_refused(tmp_path) -> None:
    with pytest.raises(CrawlError, match="not in ojs_sections.toml"):
        ojs.mine_journal("XYZ", _offline(tmp_path), table=TABLE)
```

Run: `uv run pytest backend/tests/unit/ingest/ojs/test_ojs_mine.py -q` — Expected: FAIL (`AttributeError: mine_journal`).

- [ ] **Step 7: Implement the miner** (append to `sources/ojs.py`)

```python
@dataclass
class JournalResult:
    records: list[PaperRecord]
    reports: list[ListingReport]
    deleted: int = 0  # deleted headers: counted, never records
    front_matter: int = 0
    pages: int = 0


def mine_journal(
    journal: str, fetcher: Fetcher, *, refresh: bool = False, table: Table | None = None
) -> JournalResult:
    """Every record of one journal, harvested page by page (`refresh`: start the token chain again, fetching the
    first page anew; the next pages' tokens are new, so they are fetched too). `table` is the shipped one unless a
    test passes its own (read when called, so a test may also monkeypatch `ojs.TABLE`)."""
    table = table or TABLE
    if journal not in table.journals:
        raise CrawlError(f"OJS journal {journal} is not in ojs_sections.toml", reason="unlisted_journal")
    venue = table.journals[journal].venue
    base = f"https://{HOST}/index.php/{journal}/oai"
    reports: dict[int, ListingReport] = {}
    records: list[PaperRecord] = []
    seen: set[int] = set()
    result = JournalResult(records, [])
    token: str | None = None
    started = last = time.monotonic()
    while True:
        page = fetcher.get(oai_url(journal, token), refresh=refresh and token is None)
        if not page.ok:
            raise CrawlError(f"{base} answered HTTP {page.status}", reason="no_listing")
        result.pages += 1
        entries, token = parse_page(page.text)
        for e in entries:
            if e.deleted:
                result.deleted += 1
                continue
            if e.volume is None:
                raise CrawlError(f"OJS {journal} article {e.article}: dc:source names no volume",
                                 reason="oai_unreadable")  # fmt: skip
            if e.volume not in table.volumes(journal):
                raise CrawlError(f"OJS {journal} v{e.volume} is not in ojs_sections.toml: add its sections "
                                 f"(article {e.article}, set {e.set_spec})", reason="unlisted_volume")  # fmt: skip
            section = table.sections.get((journal, e.volume, e.set_spec))
            if section is None:
                raise CrawlError(f"OJS {journal} v{e.volume} section {e.set_spec} is not in ojs_sections.toml: add "
                                 f"its row (article {e.article})", reason="unlisted_section")  # fmt: skip
            if section.kind == "front_matter":
                result.front_matter += 1
                continue
            year = table.year(journal, e.volume)
            report = reports.get(e.volume)
            if report is None:
                report = reports[e.volume] = ListingReport(
                    SOURCE, venue, year, base, "primary", table.expected(journal, e.volume), volume=e.volume)
                report.fetched.append(page.fetched_at)
            elif page.fetched_at not in report.fetched:
                report.fetched.append(page.fetched_at)
            report.listed += 1
            if e.article in seen:
                report.skipped["duplicate"] += 1
                continue
            seen.add(e.article)
            if not e.title:
                report.skipped["no_title"] += 1
                continue
            try:
                record, cleaned = _record(journal, venue, year, section.track or "", section.label, e, page)
            except (ValidationError, ValueError) as exc:
                report.skipped["invalid"] += 1
                log.debug("ojs_record_invalid", extra={"journal": journal, "article": e.article,
                                                       "error": type(exc).__name__})  # fmt: skip
                continue
            records.append(record)
            report.count(record, None if record.abstract else "no_abstract", cleaned.spaced, cleaned.pdf_codes)
        if time.monotonic() - last >= PROGRESS_SECONDS:
            last = time.monotonic()
            log.info("ojs_journal_progress", extra={"journal": journal, "pages": result.pages,
                                                    "records": len(records)})  # fmt: skip
        if token is None:
            break
    result.reports = [reports[v] for v in sorted(reports)]
    for r in result.reports:
        if not r.count_ok:
            log.warning("listing_count_mismatch", extra={"journal": journal, "volume": r.volume,
                                                         "listed": r.listed, "stated": r.stated})  # fmt: skip
        if r.skipped:
            log.warning("listing_attention", extra={"journal": journal, "volume": r.volume,
                                                    "skipped": dict(r.skipped)})  # fmt: skip
    log.info("ojs_journal_mined", extra={
        "journal": journal, "pages": result.pages, "records": len(records), "deleted": result.deleted,
        "front_matter": result.front_matter, "ms": elapsed_ms(started, time.monotonic)})  # fmt: skip
    return result


def _record(journal: str, venue: str, year: int, track: str, label: str, e: OaiRecord, page: Page):
    """The record and what cleaning its abstract changed. Claims carry the OAI page's URL and fetch time."""
    assert e.title is not None
    title, replaced = title_text(e.title)
    claims: list[Claim] = []
    at: datetime = page.fetched_at

    def claim(fld: ClaimField, value: ClaimValue, evidence: str) -> None:
        claims.append(Claim(field=fld, value=value, source=SOURCE, url=page.url, fetched_at=at, evidence=evidence))

    row = f"ojs_sections.toml {journal} v{e.volume} {e.set_spec} ({label})"
    listed = f"OAI-PMH record oai:ojs.aaai.org:article/{e.article}"
    claim("venue", venue, f"ojs_sections.toml journal {journal}")
    claim("year", year, f"ojs_sections.toml {journal} v{e.volume}")
    claim("track", track, row)
    claim("status", "accepted", f"published in {journal} v{e.volume}")
    claim("title", title, title_evidence(listed, replaced))
    if authors := tuple(display_name(c) for c in e.creators):
        claim("authors", authors, f"{listed} dc:creator (Last, First shown First Last)")
    cleaned = clean_abstract(e.description)
    if cleaned.text is not None:
        claim("abstract", cleaned.text,
              pdf_codes_evidence(controls_evidence(f"{listed} dc:description", cleaned.spaced), cleaned.pdf_codes))
    if e.doi:
        claim("urls.doi", e.doi, f"{listed} dc:identifier")
    if e.article_url and is_url(e.article_url):
        claim("urls.proceedings", e.article_url, f"{listed} dc:identifier")
    if e.pdf_url and is_url(e.pdf_url):
        claim("urls.pdf", e.pdf_url, f"{listed} dc:relation (the article's galley)")
    return record_from_claims(f"op:{venue.lower()}:{year}:ojs-{e.article}", claims), cleaned
```

(If `ListingReport.count`'s `missing` argument has a closed set of values, use `"no_abstract"` as above — it is one of
`missing_reason`'s values.) Run the miner tests — Expected: PASS.

- [ ] **Step 8: `urls.ojs_article` and `urls.native`** — test first in `backend/tests/unit/ingest/test_urls.py`:

```python
@pytest.mark.parametrize(
    ("url", "article"),
    [("https://ojs.aaai.org/index.php/AAAI/article/view/28000", 28000),
     ("https://OJS.aaai.org/index.php/AIES/article/view/31600/33767", 31600),
     ("http://ojs.aaai.org/index.php/IASEAI/article/view/43010?x=1", 43010),
     ("https://ojs.aaai.org/index.php/AAAI/issue/view/741", None),
     ("https://example.org/index.php/AAAI/article/view/1", None)],
)
def test_ojs_article(url, article) -> None:
    assert urls.ojs_article(url) == article
    assert urls.native(url) == (None if article is None else f"ojs-{article}")
```

Implement:

```python
_OJS_HOST = "ojs.aaai.org"
_OJS_PATH = re.compile(r"/index\.php/(?:AAAI|AIES|IASEAI)/article/view/([0-9]+)(?:/[0-9]+)?/?")


def ojs_article(url: str) -> int | None:
    """The article id of an ojs.aaai.org article or galley URL (AAAI, AIES, IASEAI; decision-049), or None."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or parsed.netloc.lower() != _OJS_HOST:
        return None
    m = _OJS_PATH.fullmatch(parsed.path)
    return int(m.group(1)) if m else None
```

and in `native()` before `return None`: `if (article := ojs_article(url)) is not None: return f"ojs-{article}"`.
Update `native`'s docstring.

- [ ] **Step 9: Run all ingest tests and commit**

Run: `uv run pytest backend/tests/unit/ingest -q -n auto` — Expected: PASS.

```bash
git add -A backend
git commit -m "feat: ojs.aaai.org journal miner (tracks from sections, counts per volume, deleted and front matter counted)"
```

---

### Task 5: `op ingest ojs` and the offline replay

**Files:**
- Modify: `backend/src/openproceedings/ingest/sources/crawl.py` (module docstring, `ingest_ojs`, `OJS`, `SOURCES`)
- Modify: `backend/src/openproceedings/cli.py:5, 114, 140-170, 554-563` (parser and dispatch)
- Test: `backend/tests/unit/ingest/ojs/test_ojs_crawl.py` (new), `backend/tests/unit/test_cli.py` (append)

**Interfaces:**
- Consumes: Task 4 (`ojs.mine_journal`, `ojs.JournalResult`, `ojs.oai_url`, `ojs_table.TABLE`).
- Produces: `crawl.ingest_ojs(journals: Iterable[str], cache: Path, *, offline=False, dry_run=False, refresh=False,
  transport=None, min_interval=DEFAULT_INTERVAL, table=TABLE) -> dict[str, Any]`; `crawl.OJS: Crawls[JournalResult]`
  keyed `(journal,)`, marker `<cache>/ojs/crawls/<journal>.json` = `{"source": "ojs", "journal": "<code>"}`;
  `crawl.SOURCES` ends `…, PMLR, DBLP, OJS)`. CLI: `op ingest ojs [--journal AAAI|AIES|IASEAI]... [--dry-run |
  --offline] [--refresh] [--delay S]` (no `--journal`: every journal in the table).

- [ ] **Step 1: Failing tests**

```python
# backend/tests/unit/ingest/ojs/test_ojs_crawl.py
import json

import pytest

from openproceedings.ingest.sources import crawl, ojs
from tests.unit.ingest.ojs import oai
from tests.unit.ingest.ojs.test_ojs_mine import TABLE, _seed  # the 3-paper AAAI v34 table and chain seeder


def test_offline_ingest_writes_a_marker_and_replay_rebuilds_the_same_records(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ojs, "TABLE", TABLE)  # the replay reads the shipped table
    cache = tmp_path
    _seed(cache, oai.page(oai.record(1), oai.record(2), oai.record(3, "AAAI:IAAI")))
    out = crawl.ingest_ojs(["AAAI"], cache, offline=True, table=TABLE)
    assert out["listings"][0]["records"] == 3
    marker = json.loads((cache / "ojs" / "crawls" / "AAAI.json").read_text())
    assert marker == {"source": "ojs", "journal": "AAAI"}
    (replayed,) = crawl.OJS.replay(cache)
    assert sorted(r.id for r in replayed.records) == sorted(f"op:aaai:2020:ojs-{n}" for n in (1, 2, 3))


def test_dry_run_writes_no_marker(tmp_path) -> None:
    _seed(tmp_path, oai.page(oai.record(1), oai.record(2), oai.record(3, "AAAI:IAAI")))
    crawl.ingest_ojs(["AAAI"], tmp_path, offline=True, dry_run=True, table=TABLE)
    assert not (tmp_path / "ojs" / "crawls").exists() or not list((tmp_path / "ojs" / "crawls").iterdir())


def test_unknown_journal_is_refused(tmp_path) -> None:
    with pytest.raises(Exception, match="not in ojs_sections.toml"):
        crawl.ingest_ojs(["XYZ"], tmp_path, offline=True, table=TABLE)


def test_ojs_is_replayed_last() -> None:
    assert crawl.SOURCES[-1] is crawl.OJS
```

`ingest_ojs` with `dry_run=True` reads the cached chain (offline in tests) and reports `to_fetch` = 0 when every
page is cached; with the live transport it fetches only the first page and reports `completeListSize` from it
(`"complete_list_size"` in the output) — no marker either way.

In `backend/tests/unit/test_cli.py`, add a parser test mirroring the existing `pmlr` one: `op ingest ojs --journal
AAAI --offline` dispatches to `ingest_ojs(["AAAI"], …, offline=True)` (monkeypatch `crawl.ingest_ojs` to record its
arguments), and `op ingest ojs --journal AAAJ` exits 2 with `invalid choice`.

- [ ] **Step 2: Run to verify failure** — `uv run pytest backend/tests/unit/ingest/ojs/test_ojs_crawl.py -q`
  Expected: FAIL (`AttributeError: module … has no attribute 'ingest_ojs'`).

- [ ] **Step 3: Implement in `crawl.py`**

```python
from openproceedings.ingest.ojs_table import TABLE as OJS_TABLE
from openproceedings.ingest.ojs_table import Table as OjsTable
from openproceedings.ingest.sources import dblp, iclr, icml_sites, neurips, ojs, openreview_v1, openreview_v2, pmlr


def ojs_fetcher(cache: Path, *, offline: bool, transport: Transport | None = None,
                min_interval: float = DEFAULT_INTERVAL) -> Fetcher:  # fmt: skip
    live = None if offline else (transport or urllib_transport)
    return Fetcher(PageCache(cache / ojs.CACHE_DIR), live, hosts=ojs.HOSTS,
                   min_interval=max(min_interval, ojs.MIN_INTERVAL), accept="application/xml, text/xml",
                   expect="xml", keep_query=True)  # fmt: skip


def ingest_ojs(
    journals: Iterable[str], cache: Path, *, offline: bool = False, dry_run: bool = False, refresh: bool = False,
    transport: Transport | None = None, min_interval: float = DEFAULT_INTERVAL, table: OjsTable = OJS_TABLE,
) -> dict[str, Any]:  # fmt: skip
    """Harvest each ojs.aaai.org journal (AAAI, AIES, IASEAI; `ojs_table`) into the cache through OAI-PMH. A dry
    run fetches at most each journal's first page and writes no marker."""
    wanted = sorted(set(journals)) or sorted(table.journals)
    for j in wanted:
        if j not in table.journals:
            raise MinerError(f"OJS journal {j} is not in ojs_sections.toml", reason="unlisted_journal")
    f = ojs_fetcher(cache, offline=offline, transport=transport, min_interval=min_interval)
    if dry_run:
        plans = []
        for j in wanted:
            first = f.get(ojs.oai_url(j))
            _records, token = ojs.parse_page(first.text) if first.ok else ([], None)
            plans.append({"journal": j, "first_page_cached": f.is_cached(ojs.oai_url(j)), "more_pages": token is not None})
        return {"dry_run": True, "journals": plans, "requests": f.stats.network, "cached": f.stats.cached}
    mined = OJS.ingest(
        cache, wanted, lambda j: ojs.mine_journal(j, f, refresh=refresh, table=table),
        lambda j, _: (j, {"source": ojs.SOURCE, "journal": j}),
    )  # fmt: skip
    reports = [r for m in mined for r in m.reports]
    log.info("ojs_ingested", extra={"journals": len(wanted), "listings": len(reports), "requests": f.stats.network,
                                    "deleted": sum(m.deleted for m in mined),
                                    "front_matter": sum(m.front_matter for m in mined)})  # fmt: skip
    out = _output(reports, f, False)
    out["journals"] = [{"journal": j, "pages": m.pages, "deleted": m.deleted, "front_matter": m.front_matter}
                       for j, m in zip(wanted, mined, strict=True)]  # fmt: skip
    return out


OJS: Crawls[ojs.JournalResult] = Crawls(
    lambda cache: crawls_dir(cache, ojs.CACHE_DIR), lambda m: (str(m["journal"]),),
    lambda k: f"OJS {k[0]}", "op ingest ojs",
    lambda cache, k: ojs.mine_journal(k[0], ojs_fetcher(cache, offline=True)),
)  # fmt: skip
SOURCES: tuple[Crawls[Any], ...] = (openreview_v2.CRAWLS, openreview_v1.CRAWLS, ICLR, NEURIPS, PMLR, DBLP, OJS)
```

The replay calls `ojs.mine_journal` with no table, so it reads `ojs.TABLE` when called (Task 4's `None`
default); the replay test monkeypatches `ojs.TABLE`. Update the module docstring's source list (`… PMLR, dblp and OJS`).

In `cli.py`: add `ojs` to the `ingest` help string and the module docstring line; a dedicated sub-parser (it takes
journals, not years):

```python
    ojs_parser = sources.add_parser(
        "ojs",
        help="harvest ojs.aaai.org journals (AAAI 2010+, AIES 2024+, IASEAI 2026+; ingest/ojs_sections.toml) "
        "through OAI-PMH into <data-dir>/cache/ojs",
    )
    ojs_parser.add_argument("--journal", dest="journals", action="append", default=[],
                            choices=("AAAI", "AIES", "IASEAI"), help="repeatable; default every journal")
```

with the same `--dry-run`/`--offline`/`--refresh`/`--delay` arguments the crawl parsers take (factor the shared
block into a helper `_crawl_flags(parser)` if it is not one already, used by both loops), and
`ojs_parser.set_defaults(run=_ingest_ojs)`:

```python
def _ingest_ojs(ns: argparse.Namespace) -> int:
    from openproceedings.ingest.sources.crawl import ingest_ojs

    if not math.isfinite(ns.delay) or ns.delay < MIN_DELAY:
        raise _usage(f"--delay must be finite and at least {MIN_DELAY} seconds (politeness)")
    if ns.dry_run and ns.offline:
        raise _usage("--dry-run and --offline don't combine: a dry run reads the live first page")
    _print(ingest_ojs(ns.journals, ns.data_dir / "cache", offline=ns.offline, dry_run=ns.dry_run,
                      refresh=ns.refresh, min_interval=ns.delay))  # fmt: skip
    return 0
```

A `CrawlError` whose reason is `oai_error` already reaches `cli.main`'s one `SourceError` handler, which prints
its message (with the `--refresh` hint from Task 4). Add a CLI test that a seeded `badResumptionToken` page makes
`op ingest ojs --journal AAAI --offline` exit non-zero with `--refresh` in stderr.

- [ ] **Step 4: Snapshot build sees OJS records** — in `backend/tests/unit/ingest/test_snapshot.py`, add a test
  following the file's existing pattern for PMLR/dblp: seed the OJS chain and marker in a cache, run the snapshot
  build function the file uses, and assert the three `op:aaai:2020:ojs-*` records are in `records.jsonl` and the
  manifest's `sources["ojs"]["listings"]` has one listing with `count_ok: true`.

- [ ] **Step 5: Run and commit**

Run: `uv run pytest backend/tests/unit -q -n auto` then `make lint`. Expected: PASS.

```bash
git add -A backend
git commit -m "feat: op ingest ojs and the OJS crawls in the offline snapshot replay"
```

---

### Task 6: Live harvest — the real section table, recorded fixtures, research note, official counts

This task touches the network (run by a person or the main session, never inside a test). It turns the live
endpoint into the shipped table and the recorded fixtures that pin it.

**Files:**
- Modify: `backend/src/openproceedings/ingest/ojs_sections.toml` (every section row)
- Create: `backend/tests/fixtures/http/ojs/<journal>-first-page.json` per journal (recorded, scrubbed with
  `backend/tests/fixtures/http/scrub.py` if it applies) and a test pinning each to the table
- Create: `docs/research/2026-10-09-aaai-aies-facct-iaseai-sources.md`
- Modify: `backend/src/openproceedings/official_counts.py` only if a new venue-year has an official accepted count
  a reader can check (spec 07 §C); otherwise record in the research note why none is gated
- Create: `scripts/ojs_section_census.py` (a read-only helper that turns a harvested cache into draft table rows)

- [ ] **Step 1: Harvest into a scratch data dir** (not the main `data/`; the protect-data-dir hook guards it):

```bash
OP_DATA_DIR=/private/tmp/op-ojs uv run op ingest ojs --journal IASEAI
OP_DATA_DIR=/private/tmp/op-ojs uv run op ingest ojs --journal AIES
OP_DATA_DIR=/private/tmp/op-ojs uv run op ingest ojs --journal AAAI
```

Each stops at the first unlisted volume/section — expected with an empty table. To get the census in one pass, the
census script reads the raw cached pages instead: write `scripts/ojs_section_census.py` that walks
`<cache>/ojs/pages/**.json` for a journal's chain (follow tokens from the first page with `ojs.parse_page`, reading
pages by `ojs.oai_url`), and prints, per (volume, setSpec), the record count, the deleted count, a sample title, and
the section label. Labels come from the OAI `ListSets` response (`?verb=ListSets`, fetched once per journal through
the same fetcher; add `ojs.list_sets(journal, fetcher) -> dict[str, str]` with a parse test on a synthetic page in
`test_ojs_parse.py`). To fill the cache without the table, run the harvest with `mine_journal` disabled — simplest:
the census script itself drives `ojs_fetcher(cache, offline=False)` through the chain with `parse_page` only.

- [ ] **Step 2: Reconcile the counts.** For each journal, sum of live records + deleted headers must equal the first
  page's `completeListSize`; per AAAI volume, live paper records must match the issue pages' article counts from the
  spec (2010: 333 … 2026: 4,920). Write every difference and its cause (deleted headers, front matter, a section
  shared across volumes) into the research note. The ~1,050-record gap must be explained here (spec §Risks).

- [ ] **Step 3: Write the section rows.** One `[[section]]` per (journal, volume, setSpec), `papers` = the census
  count, `label` = the ListSets name, `track` by the spec's mapping table (main: technical tracks, special tracks,
  journal track, AIES full papers, IASEAI main; `student_abstract`; `consortium`; `demo`; `iaai`; `eaai`; `other`:
  senior member, new faculty highlights, emerging trends; `front_matter` kind for prefaces and indexes). A section
  whose label doesn't fit a row of the mapping is written as `other` with a comment naming it, and listed in the
  research note for owner review. Re-run the three harvests; each must finish with every listing `count_ok: true`.

- [ ] **Step 4: Record fixtures and pin them.** Save each journal's first OAI page as a fixture
  (`{"request": {"method": "GET", "url": …}, "response": {"status": 200, "headers": {"content-type": …}, "text": …}}`,
  the shape `entry_from_fixture` reads). Add `backend/tests/unit/ingest/ojs/test_ojs_recorded.py`: each fixture
  parses with `ojs.parse_page`, every non-deleted record's (volume, setSpec) has a table row, and the IASEAI fixture
  (whole journal, two pages if needed) mines to exactly 57 records with track `main`.

- [ ] **Step 5: Research note.** `docs/research/2026-10-09-aaai-aies-facct-iaseai-sources.md`: the three agents'
  live facts (dates checked, URLs, robots.txt, counts per venue-year, Crossref/ACM DL/OpenAlex findings, the
  IASEAI '25/'26/'27 situation), the census and reconciliation from Step 2, and the section mapping decisions from
  Step 3. Link it from `docs/README.md`'s research row if that row lists files.

- [ ] **Step 6: Run and commit**

Run: `uv run pytest backend/tests/unit/ingest/ojs -q` and `make lint`. Expected: PASS.

```bash
git add -A backend scripts docs
git commit -m "data: ojs.aaai.org section table from the live census (AAAI 2010-2026, AIES 2024-2025, IASEAI 2026); recorded fixtures; research note"
```

---

### Task 7: Docs as built, decision-049, coverage copy

**Files:**
- Create: decision-049 via `backlog decision create` (read `backlog instructions overview` first; decision bodies may
  be edited by hand afterwards per `enforce-backlog-cli.sh`)
- Modify: `docs/specs/00-overview.md` (§Why/§Scope: seven venues; the "later extension" line names only what is
  still out: ACL, EMNLP, NAACL, CHI, CSCW), `docs/specs/01-ingestion.md` (§Record schema `id`/`venue`/`track` rows;
  §Track taxonomy rows for the five tracks; §Sources: a new OJS row in the house style of the PMLR row; §Crawl
  window: AAAI from 2010 via OJS in this milestone, 1980–2008 arriving in milestone B; AIES 2024+, IASEAI 2026),
  `docs/specs/02-query-language.md` (venue and track value rows; the default-filter paragraph names the new tracks
  as excluded by default), `docs/specs/04-backend-api.md` (venue strings; `ORIGIN_NAMES` gains AAAI Digital
  Library), `docs/specs/05-frontend.md` and `docs/design/2026-09-27-copy-deck.md` (RH-11 short names; CV-7 venue
  spans; RH-12 and the home/layout line "NeurIPS, ICLR and ICML" → the seven venues), `docs/specs/07-evaluation.md`
  (coverage cells for the new venue-years; which are gated and why), `docs/specs/08-ops-and-tooling.md` (`op ingest
  ojs`; the crawl order)
- Modify: `README.md`, `CLAUDE.md` (first line's venue list; `ingest/` layout line gains `ojs_table.py` +
  `ojs_sections.toml`, `sources/ojs.py`), `frontend/src/app/page.tsx:11`, `frontend/src/app/layout.tsx:12`,
  `frontend/src/components/search/examples.ts` if it names venues, `frontend/src/components/coverage/coverage-report.tsx`
  CV-7 text
- Modify: `.claude/skills/record-schema/SKILL.md`, `track-taxonomy`, `default-filters`, `openreview-venueids`
  (description), `query-grammar`, `pmlr-proceedings` (if it says only ICML), and the `docs/plans` design's status line
- Backlog: TASK-202 — add the acceptance criterion and note agreed in the spec (`backlog task edit 202 --ac "…"
  --append-notes "…"`): "#4 The schedule runs every source in scope (OpenReview, ICLR archive, NeurIPS, PMLR, dblp,
  OJS, and in later milestones Crossref, the FAccT site and OpenAlex), each driven by its table; a venue's first
  appearance is not a per-venue-year drop; a new venue-year at an existing source needs a table row, not code."

- [ ] **Step 1:** `backlog instructions overview`, then `backlog decision create "AAAI, AIES, FAccT and IASEAI are in
  scope, every year; official abstracts first, OpenAlex as a labelled fallback; AAAI-family tracks indexed and
  excluded by default"`; write its body: context (owner request 2026-10-09), the seven owner decisions from the spec,
  what it supersedes (spec 00 §Scope's venue list), consequences (schema 6; corpus ~172k; milestones A–C).
- [ ] **Step 2:** Edit each doc above, as built in Tasks 1–6 (no future tense for what this milestone didn't build;
  milestone B/C pieces are named as planned with the design doc linked).
- [ ] **Step 3:** Run `make lint` (cspell covers docs: add `AIES`, `FAccT`, `IASEAI`, `IAAI`, `EAAI`, `OAI`, `PMH`,
  `setSpec` to `cspell.json` if flagged) and `make tooling` (skills changed). Expected: PASS.
- [ ] **Step 4:** Commit: `git commit -am "docs: specs, decision-049, README, skills and copy for AAAI, AIES, FAccT and IASEAI (milestone A as built)"`
  (add new files explicitly).

---

### Task 8: Real-data verification, then the closing workflow

- [ ] **Step 1: Full harvest into the real cache** (owner-run or main session; foreground with a wait loop per the
  handoff note that agents stall on background runs): `uv run op ingest ojs` (all three journals). Expected: every
  listing `count_ok: true`; output `deleted`/`front_matter` match the research note.
- [ ] **Step 2: Snapshot and diff:** `uv run op snapshot build`, then `uv run op snapshot diff <current snapshot>
  <new snapshot>`. Expected: only additions (≈25.5k `op:aaai|aies|iaseai:*` ids), no existing record changed or
  removed. Cite both snapshot hashes in the PR.
- [ ] **Step 3: Index and parity:** `uv run op index build`, `uv run op index parity` over the full corpus. Expected:
  parity holds (the reference matcher and Tantivy agree on every golden query).
- [ ] **Step 4: Coverage:** `uv run op eval coverage --check`. Expected: the new venue-years appear with their table
  counts; unknown-track cells 0 for the new venues.
- [ ] **Step 5: Benchmarks at ~166k records:** run the spec 03 benchmarks (`make bench` or the command spec 03
  names). A budget miss becomes a backlog task created at the end of the branch (task-hygiene §Ids), never a
  silent pass.
- [ ] **Step 6: Frontend e2e and visual baselines:** `make e2e`; refresh Linux baselines from CI's artifact if the
  home/layout copy changed them (as TASK-182 did).
- [ ] **Step 7: Closing workflow (CLAUDE.md, in order):** `make test` (full, backend/src changed) + `make lint` +
  `make tooling`; backlog current (file follow-up tasks last: IASEAI 2027 via OpenReview after 2026-11-20; any
  bench miss; any `other`-mapped section for owner review); `/record-learnings`; `/review-gate` with every Must and
  Should fixed; push; `/open-pr` into `dev`; `gh pr merge <n> --auto`.
