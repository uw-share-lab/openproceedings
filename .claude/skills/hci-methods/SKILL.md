---
name: hci-methods
description: HCI research methods for studying openproceedings and its users — a method-selection table (interviews, contextual inquiry, usability tests, heuristic evaluation, diary studies, surveys, A/B tests and why they are rarely appropriate here), the verified-citation rule, anchor literature areas, and research ethics (University of Waterloo Office of Research Ethics clearance before any study with human participants, informed consent, participant data never in this public repo). Use when choosing a research method, citing HCI or IR literature, planning any study with people, or deciding where study data may be stored.
---

# HCI methods

## Method selection
| Question | Method | Why here | Not for |
|---|---|---|---|
| How do reviewers draft and revise Boolean strings today? | **Contextual inquiry** | Workflow is tacit (Scholar/PoP tabs, spreadsheets, Covidence) and people misreport it in interviews | Evaluating our UI |
| What jobs, pains and vocabulary do reviewers have? | **Semi-structured interviews** (5–8 per persona) | Cheap, fast, good for JTBD and personas | Measuring anything |
| Can people complete real tasks in our UI? | **Usability test** (moderated think-aloud) | Watches the actual failure: missed exclusion banner, misread tree | Preference or market questions |
| Where does a flow break known principles? | **Heuristic evaluation / cognitive walkthrough** | No participants, no clearance, runs on every diff (`usability-auditor`) | Replacing tests with users |
| How does use evolve over a review's weeks? | **Diary study** | Reviews run for months, and replay and drift matter later | Short-lived flows |
| How common is a pain across the community? | **Survey** | Reaches many reviewers once there are hypotheses | Discovering unknown problems |
| Which of two variants performs better? | **A/B test**, rarely | Only on synthetic tasks in a lab study | Live reviewers: changing the UI mid-protocol changes their search and reporting |
| Did we change a guarantee? | Not a user study | Tests and oracle (07) | — |

Default sequence for a new area: interviews or contextual inquiry → design doc → heuristic pass →
usability test → iterate.

## Verified-citation rule
- Cite only what you have opened (paper PDF, publisher page, DOI landing page). A search snippet is not
  a source.
- Every citation carries a DOI or stable URL and `opened: yes` in working notes.
- Can't verify → write "unverified" or drop it. **Never** construct a plausible reference.
- Report population, task and n with the finding, and say how far it transfers to expert Boolean
  searchers.

## Anchor areas (starting points to search. Verify each before citing)
- Search user interfaces and query formulation (e.g. Hearst, *Search User Interfaces*, 2009).
- Exploratory vs lookup search (e.g. Marchionini, CACM 2006).
- Expert and systematic-review searching: Boolean query formulation and refinement tools (e.g. work by
  Scells and Zuccon; Russell-Rose and colleagues on professional searchers and structured query builders).
- Trust calibration and appropriate reliance on automation (e.g. Lee and See, *Human Factors*, 2004).
- Search reporting standards: PRISMA 2020 and PRISMA-S (`prisma-reporting`).
The names above are orientation, not citations. The `hci-researcher` agent verifies the exact reference.

## Research ethics (University of Waterloo)
- **Any study with human participants** (interviews, usability tests, diaries, surveys, and recorded
  pilot sessions with people outside the core team) needs **Office of Research Ethics clearance first**.
  Whether an activity is exempt (e.g. internal quality improvement) is the Office's decision. Never make
  it yourself. The Canadian framework is TCPS 2. Verify the current application route and forms with the
  Office at planning time.
- **Informed consent**: purpose, what's recorded, storage, withdrawal, and whether quotes may be published.
  Record consent per participant. No consent, no data.
- **Status line** on every plan: `Ethics: not submitted | submitted <date> | cleared <file #> | not required (ORE confirmed <date>)`.
- **Participant data never enters this public repo.** Recordings, raw notes, transcripts, screener
  answers, emails and the code-to-identity key live in lab storage or under `data/research/` (gitignored;
  confirm with `git check-ignore -v data/research/<file>`). The repo holds only de-identified synthesis
  with participant codes (P1…) and roles. Removing it from history after a push doesn't undo publication.
- Reviewers' unpublished search strings are research data too. Handle them the same way (spec 04 doesn't
  log raw queries for this reason).
