# A Scholar collection needs its provenance sidecar and a separate corpus

**Key lesson:** Prepare raw Scholar RIS with scholarmend, import `mended.ris` alongside its matching `resolved.json`, and keep `OP_DATA_DIR` set through ingest, build, index promotion, serving and export to preserve the collection boundary; `source:` translates to a venue and cannot select import provenance.

- **Date:** 2026-10-02 · **Task:** n/a · **Area:** ingest
- **Artifacts:** [README.md](../../README.md), [RIS importer](../../backend/src/openproceedings/ingest/ris.py), [CLI data-directory resolution](../../backend/src/openproceedings/cli.py), [Scholar query aliases](../../backend/src/openproceedings/query/compat.py), [query parser](../../backend/src/openproceedings/query/parser.py)

## What we set out to do
Document how an existing Scholar collection becomes a searchable, filtered RIS export without requiring a whole-venue crawl.

## What we learned
- The importer consumes a scholarmend output pair, rather than an arbitrary raw RIS file. `ris.import_ris` reads the adjacent `resolved.json`, checks record counts and alignment, and derives identity and metadata evidence from its claims. The README now starts with preparation using scholarmend 0.1.5 and tells readers to retain both outputs and the original exports.
- Corpus membership comes from the selected data directory. `cli.default_data_dir` uses `OP_DATA_DIR`; the parser translates Scholar-compatible `source:` values to venues. A query over mixed crawl and RIS data cannot recover the original Scholar collection merely by adding `source:`.
- A later shell command can break an otherwise correct isolated workflow: the README's index-promotion step previously hard-coded `data/indexes`. It now uses `${OP_DATA_DIR:-data}/indexes`, and the import instructions carry the environment variable through building and serving.
- The README identifies the existing local prepared collection and distinguishes its input entries from imported or deduplicated papers. The documented import report reports skipped unresolved, ambiguous, conflicting and out-of-scope records. Source inputs were inspected without modification during this documentation task.

## Dead ends — don't repeat these
- Feeding raw Scholar RIS straight to the importer omits the claim ledger needed to resolve identities and classify records; prepare it first.
- Treating `source:` as an ingestion-source filter silently selects venues instead. Use a dedicated corpus when the review must remain inside an imported collection.
- Setting `OP_DATA_DIR` only for ingestion, then promoting an index through a hard-coded `data/` path, selects a different corpus at the final step.

## Decisions (and what would change them)
- Document the existing supported import path and a separate data directory. Revisit if the importer gains arbitrary RIS support or the query language gains an explicit provenance filter.
- Keep the original Scholar exports and scholarmend reports as audit inputs; prepared and indexed outputs are derived artifacts.

## Follow-ups
- None.

## Propagated to
- [README.md](../../README.md), in “Import an existing Google Scholar RIS collection” and the index-promotion command. No skill or agent change: these are user workflow instructions, now recorded in their owning Quickstart.
- Test or hook added? — no: documentation only; the existing importer and parser provide the evidence for the instructions.
