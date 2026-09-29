"use client";

/**
 * One result (ui-design-system §Result item; design W5; copy RH-8–11): an `h3` title linking to
 * `/paper/<id>?q=&mode=`, badges, the abstract excerpt and the outbound links. Highlights are the API's spans
 * only (never re-matched); the excerpt window is chosen from them (`excerpt.ts`), so it never decides what
 * matched.
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
        <Abstract text={hit.abstract} spans={hit.highlights.abstract} />
      )}
      <PaperLinks urls={hit.urls} label={`Links for ${hit.title}`} />
    </article>
  );
}
