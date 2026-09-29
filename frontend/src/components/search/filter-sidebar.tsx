"use client";

/**
 * The filter sidebar (spec 05 §4; design W5 "Sidebar", W13; copy SB-1–9). Venue, Year, Track, Status: every
 * option is a real checkbox labelled with its facet count, checked when the field's clause admits it, and a
 * click is a reducer action that rewrites `q` (guarantee 3). Clauses come from `/parse`'s `filters` for the
 * searched query; counts from `/search`'s `facets`. A control that can't act is `aria-disabled` (still
 * focusable) and described by the reason (`blockOf`), never refused after the click.
 *
 * Year uses the TASK-092 actions: a per-year tick adds or removes that year (`yearAdd`/`yearRemove`), a
 * from–to pair sets one range (`yearSet`), "All years" clears it (`yearClear`), and "Edit `year:` in the
 * query" selects the clause in the editor (pre-pass S14).
 */
import { useId, useState } from "react";
import { codePointLength } from "@/api/spans";
import {
  clauseFromParse,
  EVERY_YEAR,
  formatYearRange,
  yearClauseFromParse,
  type ParsedClause,
  type SearchAction,
  type YearRange,
} from "@/lib/search-state";
import { Coded } from "../coded";
import { trackDisplay } from "../paper-badges";
import {
  blockOf,
  NO_FILTERS_MESSAGE,
  useShowStale,
  VALUE_CODES,
  type Block,
  type Controls,
} from "./controls";
import { DRAFT_DIRTY_MESSAGE } from "./search-workspace";
import type { SearchResponse } from "./use-search";

type Facets = SearchResponse["facets"];
type ValueField = "venue" | "track" | "status";

const FIELD_TITLE: Record<ValueField | "year", string> = {
  venue: "Venue",
  year: "Year",
  track: "Track",
  status: "Status",
};

/** Reasons whose clauses `/parse` points at (`blocking_spans`), or the negated clause's own span. */
function clauseSpans(report: {
  reason: string | null;
  negated: boolean;
  span: readonly number[] | null;
  blocking_spans: readonly (readonly number[])[];
}): [number, number][] {
  const pair = (s: readonly number[]): [number, number] | null =>
    s.length === 2 && s[0] !== undefined && s[1] !== undefined ? [s[0], s[1]] : null;
  if (
    report.reason === "multiple_clauses" ||
    report.reason === "nested" ||
    report.reason === "mixed_fields"
  ) {
    return report.blocking_spans.flatMap((s) => {
      const p = pair(s);
      return p === null ? [] : [p];
    });
  }
  if (report.negated && report.span !== null) {
    const p = pair(report.span);
    return p === null ? [] : [p];
  }
  return [];
}

/** The field-level refusal among a field's controls (the first that isn't about one value). */
function fieldBlock(blocks: readonly (Block | null)[]): Block | null {
  return blocks.find((b) => b !== null && !VALUE_CODES.includes(b.code)) ?? null;
}

function FieldNote({
  id,
  block,
  spans,
  controls,
}: {
  id: string;
  block: Block | null;
  spans: [number, number][];
  controls: Controls;
}) {
  const stale = block?.code === "STALE_CLAUSE";
  const showStale = useShowStale(stale);
  // DRAFT_DIRTY and NO_FILTERS are said once, for the whole sidebar.
  const own = block !== null && block.code !== "DRAFT_DIRTY" && block.code !== "NO_FILTERS";
  const text = own && (!stale || showStale) ? block.message : "";
  return (
    <div id={id} className="text-xs text-muted-foreground">
      {text !== "" && (
        <p className="break-words">
          <span aria-hidden="true">ⓘ </span>
          <Coded text={text} />
        </p>
      )}
      {own && !stale && spans.length > 0 && spans[0] !== undefined && (
        <button
          type="button"
          onClick={() => spans[0] !== undefined && controls.selectInQuery(spans[0])}
          className="mt-1 min-h-6 rounded-sm border px-1.5 hover:bg-muted"
        >
          {spans.length > 1 ? "Show the clauses in the editor" : "Show the clause in the editor"}
        </button>
      )}
    </div>
  );
}

function Option({
  label,
  longLabel,
  count,
  checked,
  block,
  describedBy,
  onToggle,
}: {
  label: string;
  longLabel: string;
  count: number;
  /** `null`: whether the value is admitted can't be read from the report (drawn as `–`). */
  checked: boolean | null;
  block: Block | null;
  describedBy: string;
  onToggle: () => void;
}) {
  const ownNote = useId();
  const valueBlock = block !== null && VALUE_CODES.includes(block.code) ? block : null;
  const quiet = block?.code === "STALE_CLAUSE";
  return (
    <li>
      <label
        className={`flex min-h-6 items-center gap-2 ${block !== null && !quiet ? "opacity-60" : ""} ${count === 0 ? "text-muted-foreground" : ""}`}
      >
        <input
          type="checkbox"
          className="size-4 shrink-0"
          checked={checked === true}
          ref={(el) => {
            if (el !== null) el.indeterminate = checked === null;
          }}
          aria-disabled={block !== null ? true : undefined}
          aria-describedby={valueBlock !== null ? ownNote : block !== null ? describedBy : undefined}
          onClick={(e) => {
            if (block !== null) e.preventDefault();
          }}
          onChange={() => {
            if (block === null) onToggle();
          }}
        />
        <span className="min-w-0 flex-1 break-words">
          {label === longLabel ? (
            label
          ) : (
            <>
              <span aria-hidden="true">{label}</span>
              <span className="sr-only">{longLabel}</span>
            </>
          )}
          <span className="sr-only">,</span>
        </span>{" "}
        <span className="tabular-nums">{count.toLocaleString("en-US")}</span>{" "}
        <span className="sr-only">papers</span>
      </label>
      {valueBlock !== null && (
        <p id={ownNote} className="pl-6 text-xs text-muted-foreground">
          <Coded text={valueBlock.message} />
        </p>
      )}
    </li>
  );
}

function ValueFieldset({
  field,
  controls,
  counts,
  vocabulary,
  sidebarNote,
  anchor,
}: {
  field: ValueField;
  controls: Controls;
  counts: Readonly<Record<string, number>>;
  vocabulary: readonly string[];
  sidebarNote: string;
  /** The fieldset's id: the export menu's "Show the Status filter" moves focus here (design E2). */
  anchor: string;
}) {
  const noteId = useId();
  const { parse } = controls;
  const report: ParsedClause | null = parse?.filters?.[field] ?? null;
  const choice =
    parse === null ? { clause: null, reason: null } : clauseFromParse(report, parse.q, parse.mode);
  const isDefault = parse?.defaults.includes(field) ?? false;
  const values = [...new Set([...vocabulary, ...Object.keys(counts), ...(report?.values ?? [])])];
  const checkedOf = (v: string): boolean | null => {
    if (report === null || report.values === null) return null;
    const has = report.values.includes(v);
    return report.negated ? !has : has;
  };
  const rows = values.map((value) => {
    const action: SearchAction = { type: "facetToggle", field, value, ...choice };
    return { value, action, block: blockOf(controls, action), checked: checkedOf(value) };
  });
  const block = fieldBlock(rows.map((r) => r.block));
  const unrestricted =
    field === "venue" && report?.span != null && report.span[0] === report.span[1] && !isDefault;
  const title = FIELD_TITLE[field];
  const describedBy = block?.code === "DRAFT_DIRTY" || block?.code === "NO_FILTERS" ? sidebarNote : noteId;
  return (
    <fieldset id={anchor} tabIndex={-1} className="space-y-1">
      <legend className="text-sm font-semibold">
        {title}
        {isDefault && (
          <>
            {" "}
            <span className="font-normal text-muted-foreground">(default)</span>
          </>
        )}
      </legend>
      {unrestricted && (
        <p className="text-xs text-muted-foreground">All venues: untick one to leave it out.</p>
      )}
      <FieldNote
        id={noteId}
        block={block}
        spans={report === null ? [] : clauseSpans(report)}
        controls={controls}
      />
      <ul className="space-y-0.5 text-sm">
        {rows.map(({ value, action, block: b, checked }) => {
          const shown = field === "track" ? trackDisplay(value) : { short: value, long: value };
          return (
            <Option
              key={value}
              label={shown.short}
              longLabel={shown.long}
              count={counts[value] ?? 0}
              checked={checked}
              block={b}
              describedBy={describedBy}
              onToggle={() =>
                controls.act(action, `${title}: ${value} ${checked === true ? "left out" : "included"}.`)
              }
            />
          );
        })}
      </ul>
    </fieldset>
  );
}

const FOUR_DIGITS = /^[0-9]{4}$/;

function YearFieldset({
  controls,
  counts,
  sidebarNote,
}: {
  controls: Controls;
  counts: Readonly<Record<string, number>>;
  sidebarNote: string;
}) {
  const noteId = useId();
  const rangeNote = useId();
  const clearNote = useId();
  const editNote = useId();
  const { parse, state } = controls;
  const report = parse?.filters?.year ?? null;
  const choice =
    parse === null ? { clause: null, reason: null } : yearClauseFromParse(report, parse.q, parse.mode);
  const ranges = report?.ranges ?? null;
  const years = Object.keys(counts)
    .filter((y) => FOUR_DIGITS.test(y))
    .map(Number)
    .sort((a, b) => b - a);
  const admits = (y: number): boolean | null => {
    if (report === null || ranges === null) return null;
    const has = ranges.some((r) => r.lo <= y && y <= r.hi);
    return report.negated ? !has : has;
  };
  const rows = years.map((y) => {
    const one: YearRange = { lo: y, hi: y };
    const checked = admits(y);
    const action: SearchAction =
      checked === true
        ? { type: "yearRemove", range: one, ...choice }
        : { type: "yearAdd", range: one, ...choice };
    return { y, action, checked, block: blockOf(controls, action) };
  });

  // The from–to pair starts at the clause's one range, or at the years the facet shows.
  const single = ranges?.length === 1 && ranges[0] !== undefined ? ranges[0] : null;
  const start =
    single !== null && !(single.lo === EVERY_YEAR.lo && single.hi === EVERY_YEAR.hi)
      ? single
      : years.length > 0
        ? { lo: years.at(-1) ?? 0, hi: years[0] ?? 0 }
        : null;
  const [from, setFrom] = useState(start === null ? "" : String(start.lo));
  const [to, setTo] = useState(start === null ? "" : String(start.hi));
  const typed = FOUR_DIGITS.test(from.trim()) && FOUR_DIGITS.test(to.trim());
  const setAction: SearchAction | null = typed
    ? { type: "yearSet", range: { lo: Number(from.trim()), hi: Number(to.trim()) }, ...choice }
    : null;
  const setBlock: Block | null =
    setAction === null
      ? { code: "BAD_VALUE", message: "Type a four-digit year in both boxes, the earlier first." }
      : blockOf(controls, setAction);
  const clearAction: SearchAction = { type: "yearClear", ...choice };
  const clearBlock = blockOf(controls, clearAction);
  const block = fieldBlock([...rows.map((r) => r.block), setBlock, clearBlock]);
  const describedBy = block?.code === "DRAFT_DIRTY" || block?.code === "NO_FILTERS" ? sidebarNote : noteId;
  const quiet = (b: Block | null) => b?.code === "STALE_CLAUSE";
  const valueNote = (b: Block | null, own: string) =>
    b === null ? undefined : VALUE_CODES.includes(b.code) ? own : describedBy;

  const editYear = () => {
    const span = report?.span ?? null;
    if (
      span !== null &&
      span.length === 2 &&
      span[0] !== span[1] &&
      span[0] !== undefined &&
      span[1] !== undefined
    ) {
      controls.selectInQuery([span[0], span[1]]);
      return;
    }
    const spans = report === null ? [] : clauseSpans(report);
    if (spans[0] !== undefined) {
      controls.selectInQuery(spans[0]);
      return;
    }
    // No year clause: append one, with its range selected, so the reader types over it (pre-pass S14).
    const at = codePointLength(state.q) + " year:".length;
    controls.draftAndSelect(`${state.q} year:2020..2026`, [at, at + "2020..2026".length]);
  };
  const editBlocked = controls.dirty;

  return (
    <fieldset className="space-y-1">
      <legend className="text-sm font-semibold">Year</legend>
      <FieldNote
        id={noteId}
        block={block}
        spans={report === null ? [] : clauseSpans(report)}
        controls={controls}
      />
      {ranges !== null && report !== null && (
        <p className="text-xs text-muted-foreground">
          {ranges.length === 1 && ranges[0]?.lo === EVERY_YEAR.lo && ranges[0]?.hi === EVERY_YEAR.hi
            ? "Every year."
            : `${report.negated ? "Leaves out" : "Admits"} ${ranges.map(formatYearRange).join(", ")}.`}
        </p>
      )}
      <ul className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-sm">
        {rows.map(({ y, action, checked, block: b }) => (
          <Option
            key={y}
            label={String(y)}
            longLabel={String(y)}
            count={counts[String(y)] ?? 0}
            checked={checked}
            block={b}
            describedBy={describedBy}
            onToggle={() => controls.act(action, `Year: ${y} ${checked === true ? "left out" : "included"}.`)}
          />
        ))}
      </ul>
      <form
        className="flex flex-wrap items-end gap-2 pt-1 text-sm"
        onSubmit={(e) => {
          e.preventDefault();
          if (setBlock === null && setAction !== null && setAction.type === "yearSet") {
            controls.act(setAction, `Year: ${formatYearRange(setAction.range)}.`);
          }
        }}
      >
        <label className="flex flex-col text-xs">
          From year
          <input
            value={from}
            onChange={(e) => setFrom(e.target.value)}
            inputMode="numeric"
            size={5}
            className="min-h-8 rounded-md border border-input bg-background px-2 text-sm tabular-nums"
          />
        </label>
        <label className="flex flex-col text-xs">
          To year
          <input
            value={to}
            onChange={(e) => setTo(e.target.value)}
            inputMode="numeric"
            size={5}
            className="min-h-8 rounded-md border border-input bg-background px-2 text-sm tabular-nums"
          />
        </label>
        <button
          type="submit"
          aria-disabled={setBlock !== null ? true : undefined}
          aria-describedby={valueNote(setBlock, rangeNote)}
          className={`min-h-8 rounded-md border px-2 hover:bg-muted ${setBlock !== null && !quiet(setBlock) ? "opacity-60" : ""}`}
        >
          Set years
        </button>
      </form>
      {setBlock !== null && VALUE_CODES.includes(setBlock.code) && (
        <p id={rangeNote} className="text-xs text-muted-foreground">
          <Coded text={setBlock.message} />
        </p>
      )}
      <div className="flex flex-wrap gap-2 text-sm">
        <button
          type="button"
          aria-disabled={clearBlock !== null ? true : undefined}
          aria-describedby={valueNote(clearBlock, clearNote)}
          onClick={() => {
            if (clearBlock === null) controls.act(clearAction, "Year: every year included.");
          }}
          className={`min-h-8 rounded-md border px-2 hover:bg-muted ${clearBlock !== null && !quiet(clearBlock) ? "opacity-60" : ""}`}
        >
          All years
        </button>
        <button
          type="button"
          aria-disabled={editBlocked ? true : undefined}
          aria-describedby={editBlocked ? sidebarNote : editNote}
          onClick={() => {
            if (!editBlocked) editYear();
          }}
          className={`min-h-8 underline-offset-4 hover:underline ${editBlocked ? "opacity-60" : ""}`}
        >
          Edit <code className="font-mono">year:</code> in the query <span aria-hidden="true">▸</span>
        </button>
        <span id={editNote} className="sr-only">
          Selects the year clause in the editor, or adds one to type over
        </span>
      </div>
      {clearBlock !== null && VALUE_CODES.includes(clearBlock.code) && (
        <p id={clearNote} className="text-xs text-muted-foreground">
          <Coded text={clearBlock.message} />
        </p>
      )}
    </fieldset>
  );
}

export interface FilterSidebarProps {
  readonly id: string;
  readonly controls: Controls;
  readonly facets: Facets;
  readonly vocabulary: Readonly<Partial<Record<ValueField, readonly string[]>>>;
  /** Hidden below 768 px unless the "Filters (n active)" disclosure is open (design W14). */
  readonly hiddenWhenNarrow: boolean;
}

/** The id of a field's fieldset in the sidebar `sidebarId` (the export menu moves focus to it). */
export function filterAnchor(sidebarId: string, field: string): string {
  return `${sidebarId}-${field}`;
}

export function FilterSidebar({ id, controls, facets, vocabulary, hiddenWhenNarrow }: FilterSidebarProps) {
  const noteId = useId();
  const { dirty, parse, state } = controls;
  const noFilters =
    !dirty && parse !== null && parse.q === state.q && parse.mode === state.mode && parse.filters === null;
  const note = dirty ? DRAFT_DIRTY_MESSAGE : noFilters ? NO_FILTERS_MESSAGE : "";
  return (
    <section
      id={id}
      aria-labelledby={`${id}-h`}
      className={`space-y-4 ${hiddenWhenNarrow ? "hidden md:block" : ""}`}
    >
      <h2 id={`${id}-h`} className="text-sm font-semibold">
        Filters
      </h2>
      <p id={noteId} className="text-xs text-muted-foreground empty:hidden">
        {note}
      </p>
      <ValueFieldset
        field="venue"
        controls={controls}
        counts={facets.venue}
        vocabulary={vocabulary.venue ?? []}
        sidebarNote={noteId}
        anchor={filterAnchor(id, "venue")}
      />
      <YearFieldset
        key={`${state.q}\u0000${state.mode}\u0000${parse?.q === state.q && parse.mode === state.mode ? "parsed" : ""}`}
        controls={controls}
        counts={facets.year}
        sidebarNote={noteId}
      />
      <ValueFieldset
        field="track"
        controls={controls}
        counts={facets.track}
        vocabulary={vocabulary.track ?? []}
        sidebarNote={noteId}
        anchor={filterAnchor(id, "track")}
      />
      <ValueFieldset
        field="status"
        controls={controls}
        counts={facets.status}
        vocabulary={vocabulary.status ?? []}
        sidebarNote={noteId}
        anchor={filterAnchor(id, "status")}
      />
    </section>
  );
}
