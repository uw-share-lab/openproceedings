"use client";

/**
 * The exclusion banner (spec 05 §5; design W5, W8; copy BN-1–5): the standing `excluded:` string, the
 * unclassified records on their own line (never summed), one include button per non-zero bucket labelled
 * with the number it adds (the facet count; pre-pass M1, S5), and the PRISMA disclosure. Always shown, at
 * the top of the results, never inside the sidebar. Numbers are the API's (`excluded`, `facets`).
 */
import { useId, useRef, useState } from "react";
import { clauseFromParse } from "@/lib/search-state";
import { Coded } from "../coded";
import { blockOf, useShowStale, type Controls } from "./controls";
import { bannerOf, defaultsText, type IncludeButton } from "./exclusions";
import type { SearchResponse } from "./use-search";

function Include({
  button,
  controls,
  onIncluded,
}: {
  button: IncludeButton;
  controls: Controls;
  onIncluded: () => void;
}) {
  const descId = useId();
  const { parse } = controls;
  const report = parse?.filters?.[button.field] ?? null;
  const choice =
    parse === null || report === null
      ? { clause: null, reason: null }
      : clauseFromParse(report, parse.q, parse.mode);
  const action = { type: "includeExcluded", field: button.field, value: button.value, ...choice } as const;
  const block = blockOf(controls, action);
  const stale = block?.code === "STALE_CLAUSE";
  const showStale = useShowStale(stale);
  return (
    <li>
      <button
        type="button"
        aria-label={button.name}
        aria-disabled={block !== null ? true : undefined}
        aria-describedby={descId}
        onClick={() => {
          if (block !== null) return;
          const field = button.field === "track" ? "Track" : "Status";
          controls.act(action, `${field}: ${button.value} included.`);
          onIncluded();
        }}
        className={`min-h-6 rounded-sm border border-excluded-border px-1.5 text-left text-xs hover:bg-muted ${block !== null && !stale ? "opacity-60" : ""}`}
      >
        {button.label}
        {button.adds > 0 && <span aria-hidden="true"> ▸</span>}
      </button>
      <span id={descId} className="sr-only">
        <Coded text={button.description} />
        {block !== null && (!stale || showStale) && (
          <>
            {" "}
            <Coded text={block.message} />
          </>
        )}
      </span>
    </li>
  );
}

export function ExclusionBanner({
  response,
  controls,
  onIncluded,
}: {
  response: Pick<SearchResponse, "excluded" | "facets">;
  controls: Controls;
  /** Called after an include click: the banner line it was on may disappear, so focus moves on (W5). */
  onIncluded: () => void;
}) {
  const { parse, state } = controls;
  const current = parse !== null && parse.q === state.q && parse.mode === state.mode;
  const banner = bannerOf(
    response.excluded,
    response.facets,
    current ? parse.defaults : null,
    current ? parse.filters : null,
  );
  const [open, setOpen] = useState(false);
  const aboutId = useId();
  const aboutButton = useRef<HTMLButtonElement>(null);
  const defaults = defaultsText(banner.defaultClauses);
  return (
    <section
      aria-label="Exclusions"
      className="space-y-1 rounded-md border border-excluded-border bg-excluded-bg p-2 text-sm text-excluded-fg"
    >
      <div className="flex items-start gap-2">
        <div className="min-w-0 flex-1 space-y-1">
          <p className="break-words tabular-nums">{banner.excluded}</p>
          {banner.unclassified !== null && <p className="break-words tabular-nums">{banner.unclassified}</p>}
        </div>
        <button
          ref={aboutButton}
          type="button"
          aria-expanded={open}
          aria-controls={aboutId}
          aria-label="About these exclusions"
          onClick={() => setOpen(!open)}
          className="min-h-6 min-w-6 rounded-full border border-excluded-border text-xs"
        >
          i
        </button>
      </div>
      {open && (
        <div
          id={aboutId}
          onKeyDown={(e) => {
            if (e.key === "Escape") {
              setOpen(false);
              aboutButton.current?.focus();
            }
          }}
          className="rounded-sm border border-excluded-border bg-background p-2 text-xs text-foreground"
        >
          <p>
            {defaults} removed {`${response.excluded.total.toLocaleString("en-US")} `}records before
            screening. In a PRISMA 2020 flow diagram they are{" "}
            <em>records removed before screening — marked as ineligible by automation tools</em>; the
            unclassified records (track or status unknown) are reported on their own, not as ineligible. A
            paper that fails both filters is counted once, under track (buckets are counted track first, then
            status), so an include button can add fewer papers than its bucket shows. Including a value writes
            the filter into your query: it stops being a default, its exclusions become a limit you wrote, and
            the methods text reports it that way.
          </p>
          <button
            type="button"
            onClick={() => {
              setOpen(false);
              aboutButton.current?.focus();
            }}
            className="mt-1 min-h-6 rounded-sm border px-1.5"
          >
            Close
          </button>
        </div>
      )}
      {banner.includes.length > 0 && (
        <ul aria-label="Include excluded papers" className="flex flex-wrap gap-1.5">
          {banner.includes.map((b) => (
            <Include key={`${b.field}:${b.value}`} button={b} controls={controls} onIncluded={onIncluded} />
          ))}
        </ul>
      )}
    </section>
  );
}
