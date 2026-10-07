"use client";

/**
 * One result (ui-design-system §Result item; design W5; copy RH-8–13): an `h3` title linking to
 * `/paper/<id>?q=&mode=`, the authors (the first three and "et al.", with a button for the full list), badges,
 * the abstract excerpt, the abstract's attribution ("Abstract: PMLR", linking to the paper's page there;
 * decision-018, the API's `abstract_source`) and the outbound links. An abstract this instance withholds at a
 * rights holder's request (the API's `abstract_withheld`, decision-022) says so (copy RH-15), never "No abstract
 * in the index". A record with twins (the API's `twins`, decision-029) names each, a link to its paper page (copy
 * RH-18). Highlights are the API's spans only
 * (never re-matched); the excerpt window is chosen from them (`excerpt.ts`), so it never decides what matched.
 */
import Link from "next/link";
import { Fragment, useId, useState } from "react";
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

/** A withheld abstract, in place of the text (copy RH-15 and PA-8; decision-022): the record is still found by
 * its title, and an older index may still match the query on the withheld words. */
export const ABSTRACT_WITHHELD = "Abstract removed from this site at a rights holder's request";
/** After it, on a result and a matched paper page: the search may have matched words in it (decision-022). */
export const WITHHELD_TERMS = "Any terms it matched in the removed abstract aren't shown.";
/** The same on a result, where nothing names the search first. */
export const WITHHELD_SEARCH_TERMS = "Any terms your search matched in the removed abstract aren't shown.";

/** The lead-in before a record's twins (copy RH-18, PA-10; decision-029): the same paper, listed again as
 * another record the index keeps (an ICLR 2017 workshop copy and its conference submission). */
export function seeAlsoLead(n: number): string {
  return n === 1 ? "See also (the same paper's other record):" : "See also (the same paper's other records):";
}

/** A record's twins, each id a link to its paper page; with a query, the query rides along as it does from a
 * result's title (`paperHref`), so the twin's page shows the same highlights. Nothing when it has none. */
export function TwinLinks({ twins, q, mode }: { twins: readonly string[]; q: string | null; mode: Mode }) {
  if (twins.length === 0) return null;
  return (
    <p className="text-sm break-words">
      {seeAlsoLead(twins.length)}{" "}
      {twins.map((id, i) => (
        <Fragment key={id}>
          {i > 0 && ", "}
          <Link
            href={q === null ? `/paper/${encodeURIComponent(id)}` : paperHref(id, q, mode)}
            className="inline-flex min-h-6 items-center font-mono break-all underline underline-offset-4"
          >
            {id}
          </Link>
        </Fragment>
      ))}
    </p>
  );
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

/** The site an abstract came from, as the attribution names it (copy RH-12). Origins are an open set
 * (decision-009): one this code doesn't know is named as it came. */
const ORIGIN_NAMES: Readonly<Record<string, string>> = {
  openreview: "OpenReview",
  neurips_proceedings: "NeurIPS Proceedings",
  iclr_proceedings: "ICLR Proceedings",
  pmlr: "PMLR",
  iclr_archive: "ICLR archive",
  icml_site: "ICML conference site",
};

type AbstractFrom = NonNullable<SearchHit["abstract_source"]>;

/** What the attribution says: the site ("PMLR"), and " (via RIS import)" when the claim came through an
 * imported RIS file; a route that names no known site is "an imported RIS file" (or the source as it came). */
export function attributionText(from: AbstractFrom): { site: string; via: string } {
  if (from.origin === null) {
    return { site: from.source === "ris" ? "an imported RIS file" : from.source, via: "" };
  }
  return {
    site: ORIGIN_NAMES[from.origin] ?? from.origin,
    via: from.source === "ris" ? " (via RIS import)" : "",
  };
}

/** "Abstract: PMLR", the site a link to the paper's page there when it has one (decision-018). The link's
 * accessible name starts with its visible text and adds "abstract source for <title>" (WCAG 2.5.3, 2.4.4), so
 * it is told apart from the Links list's own "OpenReview"/"Proceedings" and from other results' links. An
 * `aria-label`, not a hidden span: inside the inline-flex link a hidden span adds a space to the name. */
function AbstractSource({ from, title }: { from: AbstractFrom; title: string }) {
  const { site, via } = attributionText(from);
  return (
    <p className="text-xs text-muted-foreground">
      Abstract:{" "}
      {from.url === null ? (
        site
      ) : (
        <a
          href={from.url}
          rel="noopener noreferrer"
          aria-label={`${site}, abstract source for ${title}`}
          className="inline-flex min-h-6 items-center underline underline-offset-4"
        >
          {site}
        </a>
      )}
      {via}
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
      {hit.abstract_withheld ? (
        <p className="text-sm text-muted-foreground">
          {ABSTRACT_WITHHELD}. {WITHHELD_SEARCH_TERMS}
        </p>
      ) : hit.abstract === null ? (
        <p className="text-sm text-muted-foreground">No abstract in the index</p>
      ) : (
        <>
          <Abstract text={hit.abstract} spans={hit.highlights.abstract} />
          {hit.abstract_source !== null && <AbstractSource from={hit.abstract_source} title={hit.title} />}
        </>
      )}
      <TwinLinks twins={hit.twins} q={q} mode={mode} />
      <PaperLinks urls={hit.urls} label={`Links for ${hit.title}`} />
    </article>
  );
}
