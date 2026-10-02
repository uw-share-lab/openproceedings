# A base-image digest resolves without a Docker daemon, and a paths-filtered workflow can't be a required check

**Key lesson:** Resolve a base image's multi-arch index digest with `docker buildx imagetools inspect <image:tag>` (no running daemon needed) or the registry API, and keep any workflow behind a workflow-level `paths` filter advisory, because a required check it skips stays pending forever.

- **Date:** 2026-10-01 · **Task:** task-148, task-149, task-150, task-151 · **Area:** ops
- **Artifacts:** `.github/workflows/web-image.yml`, `.github/dependabot.yml`, `deploy/web.Dockerfile`, `.claude/scripts/check_digest_pins.py`, `.claude/scripts/tests/test-tooling-scripts.sh`, `docs/specs/08-ops-and-tooling.md` §CI, §Deploy, §Release, §Branch protection

## What we set out to do
Build `deploy/web.Dockerfile` in CI, digest-pin its base image with Dependabot bumping the digest, stop
Dependabot from bumping the exact `tantivy==` pin, and record the `v*` tag rulesets the owner applied.

## What we learned
- `docker buildx imagetools inspect node:22-bookworm-slim` answers with the Docker daemon stopped: it talks
  to the registry, prints `MediaType: application/vnd.oci.image.index.v1+json` and the index `Digest:`, then
  each platform's manifest digest. Pin the top-level one (the index), never a platform's (evidence: the same
  `sha256:43ac6c60…772c` came back from an anonymous Docker Hub token plus `HEAD
  /v2/library/node/manifests/22-bookworm-slim` with the OCI-index `Accept` header, in `Docker-Content-Digest`).
- Dependabot's `docker` ecosystem finds any file whose name matches `/dockerfile|containerfile/i`
  (dependabot-core `docker/lib/dependabot/docker/file_fetcher.rb`), so `web.Dockerfile` needs no rename.
- A `tag` like `22-bookworm-slim` has one version component, so Dependabot's only "newer tag" is the next
  Node major; ignoring `version-update:semver-major` for `node` leaves exactly the digest refreshes.
- A `# syntax=docker/dockerfile:1` line is itself an image BuildKit pulls at build time, unpinned; a
  Dockerfile that uses nothing beyond the built-in frontend can drop it rather than pin it.
- A `FROM`-only pin check is not enough: a `# syntax=` directive, `COPY --from=<image>` and
  `RUN --mount=…,from=<image>` pull images too, and a wrapped `FROM \` line must be joined before it is read
  (review round 1, security-reviewer and code-reviewer; `check_digest_pins.py` now reads instructions as
  Docker does).
- Dependabot's `directory: /deploy` does not look in subdirectories; `directories: ["/deploy", "/deploy/**"]`
  matches a check that searches `deploy/` recursively.
- In a mutation table where every failure path exits 1, a mutant that turns one refusal into a different
  refusal survives: kill it with an `ok` row that only the correct code accepts (here a pinned image after
  `--platform`, which the flag-less mutant reads as unpinned; evidence: `mutate.py --match 'pins:'`, every mutant killed).

## Dead ends — don't repeat these
- A first mutant set had "unreadable FROM passes" surviving: no row had a `FROM` the regex couldn't parse.
  Add a row per distinct refusal reason, not one per input shape.

## Decisions (and what would change them)
- `web-image` stays advisory behind a `paths` filter → a required version would need a changed-files step
  inside an always-running job → revisit when compose and the api image (TASK-065) make the build a release gate.
- Tantivy: Dependabot `ignore` over a CI check → no new gate to maintain for a rare, hand-verified upgrade →
  revisit if a tantivy bump ever reaches `dev` another way.

## Follow-ups
- [ ] none: the deferrals are listed in the PR body.

## Propagated to
- Skill / agent / CLAUDE.md updated? — `.claude/skills/repo-conventions/SKILL.md`, `.claude/skills/index-versioning/SKILL.md`, `.claude/skills/pr-workflow/SKILL.md`, `.claude/agents/ci-engineer.md`, `CLAUDE.md`
- Test or hook added? — `.claude/scripts/check_digest_pins.py` (run by `make tooling`), its rows in `.claude/scripts/tests/test-tooling-scripts.sh` and mutants in `.claude/scripts/mutants/gates.json`
