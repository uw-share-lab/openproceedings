---
id: decision-022
title: >-
  A takedown withholds an abstract's display, not its matching, on every loaded
  index version; the takedown list and log live in the data directory (TASK-136)
date: '2026-09-30 14:36'
status: accepted
---
## Context

decision-018 has a public instance serve every abstract and name a takedown contact (TASK-133). TASK-133 proposed
a procedure (spec 08 §Deploy) that nothing implemented: withhold a listed record's abstract from the next
`index_version`. Two gaps were left for TASK-136:

1. **Older index versions keep the abstract.** Indexes are immutable, a search record pins the index it was run
   on, and `op index retire` refuses to delete a pinned version (TASK-085). So a new `index_version` alone leaves
   the abstract retrievable through `/export?index_version=` and `/export?record_id=`. The procedure proposed
   withholding it at serve time from every response of every loaded version, which leaves a question: a pinned
   version still *matches* on the withheld text (the "oracle leak": a query for a word only the withheld abstract
   holds still returns the paper there). Either accept that, or drop the field from matching on those versions.
   Dropping it would change the ids a replay returns, breaking guarantee 4 for every search record that pins the
   version: a systematic review could no longer reproduce the set it cited.
2. **Where the operator's takedown log lives, and who reads it.** It holds the requester's name and contact
   details.

The owner decided both on 2026-09-30. The remaining design points (the list's file, format and location, and
whether `snapshot_hash` and the manifest cover it; the withheld marker; replay and record-page behaviour) follow
spec 08's proposal and were settled in TASK-136.

## Decision

1. **The oracle leak is accepted (owner, 2026-09-30).** A takedown withholds what is *shown*, never what
   *matches*. Index versions pinned by search records keep matching on a withheld abstract, so replaying a saved
   search on its pinned version returns the same record ids (guarantee 4). The abstract is withheld at serve
   time from every response that carries one, on every index version the API loads: `/search` hits (`abstract`
   null, no abstract highlight spans, `abstract_source` null), `/papers/{id}` (no abstract, no abstract claim in
   its provenance, no abstract spans; `matched` stays the index's answer), and every export format (RIS, CSV,
   BibTeX, JSONL; served, `index_version=` and `record_id=`; and `op export`). Highlights and excerpts never
   reveal the withheld text, even where it matched.
2. **The takedown log is a file on the deployment host, outside the repository (owner, 2026-09-30):**
   `<data-dir>/takedowns/log.jsonl`, next to the list, owned by the operator's account, mode 0600, never
   committed. One JSON object per request with exactly `record_id`, `received`, `requester`, `basis`, `decision`
   (`withheld`, `declined` or `lifted`), `applied` and `first_index_version` (the first `index_version` built
   without the abstract; null until then). The API never reads it. `op takedown check` fails when it is owned by
   another account than the operator's running the check, readable by anyone but its owner, malformed, or when a
   listed id's latest entry isn't `withheld`; `.gitignore` ignores every
   `takedowns/` directory and `protect-data-dir.sh` refuses `git add` of any path through one; `.dockerignore`
   keeps it out of image build contexts.
3. **The list** (TASK-136) is `<data-dir>/takedowns/withheld.txt`: UTF-8, one record id per line, blank lines
   and everything after `#` ignored, ids only (so the API's service user may read it: 0644, or 0640 with the
   API's group). A line that is not one record id makes the whole list unusable: `op snapshot build` refuses to
   run and the API keeps what it already serves (at startup it serves nothing: 503), never a silent partial list.
   A missing file is an empty list, unless the API already applies a non-empty one or the index it loads has a
   snapshot that withheld abstracts: then a missing file fails the load (`takedowns_missing`), so an unmounted
   or renamed directory never lifts every takedown silently. A list named
   explicitly (`--takedowns`, `--list`) must exist.
4. **What covers it.** `op snapshot build` withholds each listed abstract after dedup and reconcile (the record
   keeps its title and every other field; its abstract claims, whose values are the text, are dropped, and so
   are the abstract texts of its `conflicts.csv` rows). So `snapshot_hash`, and with it `index_version`, covers
   the *effect* of the list; the list file itself is not hashed, since it is live serve-time state that changes
   without a rebuild. The manifest names the withheld ids (`withheld`) and counts them per venue-year and track
   (`abstract_withheld`, `abstract_withheld_by_track`), apart from `abstract_missing`; the keys appear only when
   something is withheld, so a snapshot withholding nothing is byte-identical to before (format 2 unchanged),
   and `withheld` is one of the keys a rebuild must reproduce. `withheld` names only the records the build took
   something out of: listing a record whose sources gave no abstract leaves the snapshot byte-identical (serve
   time marks it from the list), so it never blocks a rebuild. A listed id the build holds under another id
   (merged into another record, or rekeyed by a corrected venue or year) is followed: the new id's abstract is
   withheld too, so neither a rekey nor a merge brings it back, and the operator adds the new id to the list
   while **keeping the old one**, which older versions still hold. A listed id the build has no record of at all
   (a paper gone from its sources) is reported, never refused: refusing would push the operator to delete the
   line, which would lift the takedown on every older version that still holds the paper.
5. **The marker.** A withheld abstract is never shown as missing (guarantee 6): hits and `/papers/{id}` carry
   `abstract_withheld: true`, `/coverage` counts `abstract_withheld` apart from `abstract_missing`, exports say so
   in each record (RIS `N1` and BibTeX `abstract_withheld` = the takedown sentence; CSV `abstract_withheld` true
   and `abstract_withheld_reason` `takedown`; JSONL the same keys; the response counts them in
   `X-Abstracts-Withheld`, which the web app shows, EX-E9), and the UI says "Abstract removed from this site at a
   rights holder's request. Any terms it matched in the removed abstract aren't shown." An abstract the snapshot itself withheld is marked too, whether or not the
   list still names it. All of these are additive under `/api/v1` (spec 04 §Conventions; decision-021 rule 1).
6. **Replay and the record page.** A search record replays on its pinned index as before: `reproduced`, its ids
   unchanged. Its exports withhold the listed abstracts the pinned index still holds. The record page shows no
   abstract, so it changes only through its exports.

## Consequences

- **Every loaded version, from the next reload.** The API re-reads the list on every load and SIGHUP, even when
  `current` is unchanged, so an operator can withhold an abstract at once (list it, SIGHUP) and rebuild later;
  a reload whose new index fails to load still applies a new list to the index it keeps serving.
- **What a pinned version still reveals.** Whether a query matches the paper (it is a hit, `/papers?q=` says
  `matched: true`), and the paper's position in the ranking (BM25 over the withheld text). Nothing of the text:
  no words, spans or excerpt. Anyone able to guess the abstract's words can confirm them one query at a time;
  that is the accepted cost of guarantee 4. A version no record pins can be retired (`op index retire`) to end it.
- **The newest index doesn't match on it.** A version built after the takedown has no abstract for the paper,
  so a query that found it only through the abstract no longer does there; a record saved on an older version
  and replayed on the new one reports `drifted`, as for any rebuild.
- **`content_hash`.** A withheld record's `/papers/{id}` answer has the `content_hash` of what it shows (no
  abstract), the one the rebuilt snapshot holds.
- **Checking it.** `op takedown check --api <url>` asks the running API, and exits 1 on any served abstract,
  abstract claim, span, source or missing marker: `/papers` and `/search` on the served index, and every export
  format on every index version `/meta` lists (TASK-136 AC8); and on a log that is not the operator's, readable
  by others, or whose latest entry for a listed id isn't `withheld`.
- **Lifting a takedown** means removing the line (and logging `lifted`): the API shows the abstract again on the
  versions that still hold it after the next reload; a snapshot built while it was listed keeps it withheld
  until a rebuild without the id.
- **What would reopen it:** a request that the text must not be matched at all (then the pinned versions
  holding it must be retired, with the records that pin them marked as no longer reproducible), or a change of
  the hosting model that puts the log elsewhere.

## Addendum (2026-09-30, TASK-067 security review)

- **The same paper under another id.** The list names one id, but an older version may hold the paper under
  an id it had before (a venue or year corrected later: the same native id) or as a separate duplicate a
  later build merged. A version now withholds each of its records that is a listed paper under any id:
  linked to a listed id by any snapshot's `merges.csv`, or sharing its native id when that native id is
  globally unique (an OpenReview forum id, a PMLR volume key; never a NeurIPS or ICLR proceedings hash, which
  names one paper only within its venue-year, measured: `takedowns.global_native`),
  transitively
  (`takedowns.same_paper`), in the API and `op export`. `op takedown check` also exports each listed paper's
  title in every venue and year on every version, and reports a record with the same title and authors, under
  another id, that carries an abstract. Listing the old id too (as the build's `takedowns_followed` advises)
  stays good practice; it is no longer what keeps an older version from serving the text.
- **A missing list fails closed.** Besides the cases above (a list already applied, the served snapshot
  withheld one), a missing list now fails a load when `op serve` runs off loopback or behind a `--trusted-proxy` (every
  public instance) or
  when any snapshot on disk withheld an abstract; `op snapshot build` and `op export` refuse a missing default list
  on the same evidence, and `op takedown check` always requires it. An empty file is how every takedown is lifted.
- **The log checks the list, too.** An id whose latest log entry is `withheld` but that the list doesn't name
  is a problem: a deleted line never lifts a takedown silently.
- **Merges are read from every snapshot on disk**, older dedup rules included: a merge is the project's own
  verdict that two records are one paper. `op takedown check` names an id a merge links to a listed paper
  whose served title differs (a suspect merge). A merges.csv that doesn't match its manifest leaves that snapshot's
  merges out, the others' still applying (one ERROR `takedown_merges_unavailable` per damaged snapshot), so the
  list still applies rather than the reload failing.
- **Caches.** Every API response says `Cache-Control: no-store`, so a proxy can't keep serving a withheld
  abstract after the SIGHUP.

## Addendum (2026-10-02, TASK-065: where the log lives under compose)

- **The API's takedown mount holds only the list.** Under `deploy/compose.yml`, the `api` container mounts
  `<data-dir>/takedowns/` read-only. It mounts the directory, not the file, so a list that an editor saves by
  renaming is still re-read on SIGHUP. That directory holds only `withheld.txt`. The log moves out of it, to a
  directory of its own outside the data directory: for example `/srv/openproceedings/takedown-log/log.jsonl`,
  with the directory 0700 and the file 0600, both the operator's. Nothing else in §2 changes: the API never reads
  the log, and `op takedown check` reads it as the operator's account, with `--log` naming that path (the compose
  `takedown-check` service passes it). The list keeps its default path, so `op snapshot build` and `op export`
  need no flag. The default log path, `<data-dir>/takedowns/log.jsonl`, stays valid for a deployment without
  compose that keeps the log away from the API's user. This is the hosting-model change that "What would reopen
  it" anticipated, limited to where the file sits. It doesn't change who reads it.
