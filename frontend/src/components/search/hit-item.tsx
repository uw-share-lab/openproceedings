"use client";

/**
 * One result (ui-design-system §Result item; design W5; copy RH-8–13): an `h3` title linking to
 * `/paper/<id>?q=&mode=`, the authors (the first three and "et al.", with a button for the full list), badges,
 * the abstract excerpt, the abstract's attribution ("Abstract: PMLR", linking to the paper's page there;
 * decision-018, the API's `abstract_source`) and the outbound links. Highlights are the API's spans only
 * (never re-matched); the excerpt window is chosen from them (`excerpt.ts`), so it never decides what matched.
 */
import Link from "next/link";
import { useId, useState } from "react";
import { excerpt, utf16Spans } from "@/lib/excerpt";
import type { Mode } from "@/lib/search-state";
import { Highlighted } from "../highlighted";
import { PaperBadges } from "../paper-badges";
import { PaperLinks } from "../paper-links";
import type { SearchHit } from "./use-search";

/** The paper page for a hit: the query rides in the URL, so a shared link shows the same highlights. */
export function paperHref(id: string, q: string, mode: Mode): string {
  return `/paper/${encodeURIComponent(id)}?${new URLSearchParams({ q, mode }).toString()}`;
}

/** Authors shown before "et al." (ui-design-system §Result item); the rest behind "Show all n authors". */
export const AUTHORS_SHOWN = 3;

/** The authors a result shows: all of them when there are at most `AUTHORS_SHOWN` or `full` is set. */
export function shownAuthors(authors: readonly string[], full: boolean): { names: string; cut: boolean } {
  const cut = !full && authors.length > AUTHORS_SHOWN;
  return { names: (cut ? authors.slice(0, AUTHORS_SHOWN) : authors).join(", "), cut };
}

function Authors({ authors }: { authors: readonly string[] }) {
  const [full, setFull] = useState(false);
  const regionId = useId();
  if (authors.length === 0) return null;
  const { names, cut } = shownAuthors(authors, full);
  return (
    <p className="text-sm break-words">
      <span id={regionId}>
        <span className="sr-only">Authors: </span>
        {names}
        {cut && " et al."}
      </span>
      {authors.length > AUTHORS_SHOWN && (
        <>
          {" "}
          <button
            type="button"
            aria-expanded={full}
            aria-controls={regionId}
            onClick={() => setFull(!full)}
            className="min-h-6 text-xs underline underline-offset-4"
          >
            {full ? "Show fewer authors" : `Show all ${authors.length} authors`}
          </button>
        </>
      )}
    </p>
  );
}

/** A source as the attribution names it (copy RH-12). Sources are an open set (decision-009): one this code
 * doesn't know is named as it came. */
const SOURCE_NAMES: Readonly<Record<string, string>> = {
  openreview_v2: "OpenReview",
  openreview_v1: "OpenReview",
  neurips_proceedings: "NeurIPS Proceedings",
  pmlr: "PMLR",
  iclr_archive: "ICLR archive",
  ris: "an imported RIS file",
};

export function sourceName(source: string): string {
  return SOURCE_NAMES[source] ?? source;
}

/** "Abstract: PMLR", the source a link to the paper's page there when it has one (decision-018). */
function AbstractSource({ from }: { from: NonNullable<SearchHit["abstract_source"]> }) {
  const name = sourceName(from.source);
  return (
    <p className="text-xs text-muted-foreground">
      Abstract:{" "}
      {from.url === null ? (
        name
      ) : (
        <a
          href={from.url}
          rel="noopener noreferrer"
          className="inline-flex min-h-6 items-center underline underline-offset-4"
        >
          {name}
        </a>
      )}
    </p>
  );
}

function Abstract({ text, spans }: { text: string; spans: readonly (readonly number[])[] }) {
  const [full, setFull] = useState(false);
  const regionId = useId();
  const drawn = utf16Spans(text, spans) ?? [];
  const cut = excerpt(text, drawn);
  const whole = !cut.cutBefore && !cut.cutAfter;
  return (
    <div className="text-sm">
      <p id={regionId} className="break-words">
        {full || whole ? (
          <Highlighted text={text} spans={drawn} />
        ) : (
          <>
            {cut.cutBefore && "…"}
            <Highlighted text={text.slice(cut.start, cut.end)} spans={cut.spans} />
            {cut.cutAfter && "…"}
          </>
        )}
      </p>
      {!whole && (
        <button
          type="button"
          aria-expanded={full}
          aria-controls={regionId}
          onClick={() => setFull(!full)}
          className="min-h-6 text-xs underline underline-offset-4"
        >
          {full ? "Show less" : "Show full abstract"}
        </button>
      )}
    </div>
  );
}

export function HitItem({ hit, q, mode }: { hit: SearchHit; q: string; mode: Mode }) {
  const title = utf16Spans(hit.title, hit.highlights.title) ?? [];
  return (
    <article className="space-y-1.5 border-t py-3">
      <h3 className="text-base font-semibold">
        <Link href={paperHref(hit.id, q, mode)} className="underline-offset-4 hover:underline">
          <Highlighted text={hit.title} spans={title} />
        </Link>
      </h3>
      <Authors authors={hit.authors} />
      <PaperBadges
        venue={hit.venue}
        year={hit.year}
        track={hit.track}
        presentation={hit.presentation}
        status={hit.status}
      />
      {hit.abstract === null ? (
        <p className="text-sm text-muted-foreground">No abstract in the index</p>
      ) : (
        <>
          <Abstract text={hit.abstract} spans={hit.highlights.abstract} />
          {hit.abstract_source !== null && <AbstractSource from={hit.abstract_source} />}
        </>
      )}
      <PaperLinks urls={hit.urls} label={`Links for ${hit.title}`} />
    </article>
  );
}
