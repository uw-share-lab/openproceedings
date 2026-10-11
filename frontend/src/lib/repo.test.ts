import { describe, expect, it } from "vitest";

import { blobUrl, REPO_PATH, REPO_URL } from "./repo";
import { TAKEDOWN_FALLBACK_URL } from "./takedown-contact";
import { ISSUES_URL } from "@/components/search/search-states";

describe("the repository's links", () => {
  it("point a repo path at its page on the default branch", () => {
    expect(blobUrl("docs/results/coverage-sources.md")).toBe(
      "https://github.com/uw-share-lab/openproceedings/blob/dev/docs/results/coverage-sources.md",
    );
  });

  it("find a repo path in a citation, not a URL's path or a bare word", () => {
    expect(REPO_PATH.exec("docs/research/2026-10-09-sources.md §Official counts")?.[1]).toBe(
      "docs/research/2026-10-09-sources.md",
    );
    expect(REPO_PATH.exec("the proceedings")).toBeNull();
  });

  it("are the one repository the issue links name", () => {
    expect(ISSUES_URL.startsWith(`${REPO_URL}/`)).toBe(true);
    expect(TAKEDOWN_FALLBACK_URL).toBe(`${REPO_URL}/issues`);
  });
});
