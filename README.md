# openproceedings

Exact, reproducible Boolean search over **NeurIPS, ICLR and ICML** titles and abstracts, for systematic reviews.

- **Title and abstract only.** It never searches the full text.
- **No stemming.** `benchmarking` matches `benchmarking`, not `benchmark`. Wildcards are opt-in (`benchmark*`, `model$`).
- **Track-aware.** Workshop, competition and rejected papers are indexed, but the default filters exclude them. Every search reports how many were excluded, which gives you the PRISMA "removed before screening" count.
- **Reproducible.** Every result carries an index version. Saved search records can be replayed.
- **Review-ready exports.** RIS (for Covidence), CSV and BibTeX, with full abstracts.

Status: **M2 built** (RIS ingestion, snapshots, the Tantivy index, `op search` / `op export`); M3 (the API and UI) is under way: the Next.js skeleton is in `frontend/`, its pages still placeholders. Start with [`docs/specs/00-overview.md`](docs/specs/00-overview.md); setup is in [`CONTRIBUTING.md`](CONTRIBUTING.md).

MIT © SHARE Lab, University of Waterloo
