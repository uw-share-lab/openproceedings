/**
 * The project's public repository, named once (gate C round 1): the issue tracker and the links a public page
 * gives to a file in the repository (a citation such as `docs/results/coverage-sources.md`), which a reader can't
 * open as a bare path.
 */
export const REPO_URL = "https://github.com/uw-share-lab/openproceedings";

/** The branch a file link points at: `main`, the released code and the repository's default branch (decision-052). */
export const DEFAULT_BRANCH = "main";

/** The GitHub page of a repository file on the default branch (`docs/x.md` → `…/blob/main/docs/x.md`). */
export function blobUrl(path: string): string {
  return `${REPO_URL}/blob/${DEFAULT_BRANCH}/${path}`;
}

/** A repository path as written in a citation: a top-level directory of the repo, then a file with an extension. */
export const REPO_PATH =
  /\b((?:docs|backend|frontend|deploy|backlog|scripts)\/[\w./-]*\w\.(?:md|py|toml|json|tsx?))/;
