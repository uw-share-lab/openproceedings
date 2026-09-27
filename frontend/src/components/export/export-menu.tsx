"use client";

/**
 * The search's Export menu (spec 05 §Components 7; design E1–E4, §Keyboard and screen reader; copy EX-E1–E7).
 * A menu button: ↓ / Enter / Space open it on the first format, ↑ on the last; arrows, Home and End move; Esc
 * closes it and returns focus to the button. The formats are the menu's only items; the heading and any
 * status or track warning are its description, and a one-line copy of each warning sits beside the closed
 * button, so it can be read without opening the menu. The warning is advice, not a block.
 *
 * Every format is pinned to the shown search (`q`, `mode`, `index_version`) and checked against the shown
 * `total` before a byte is saved (`lib/export.ts`).
 */
import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";
import { plural } from "@/editor/diagnostics";
import { FORMATS, warningLine, warningText, type ExportSource, type FieldWarning } from "@/lib/export";
import { Coded } from "../coded";
import { CovidenceHelp } from "./covidence-help";
import { button, ExportNotice } from "./export-notice";
import { useExport } from "./use-export";

export interface ExportMenuProps {
  readonly source: ExportSource & { readonly kind: "search" };
  /** Why exporting is off (a dirty draft, stale results), or `null`. */
  readonly disabledReason: string | null;
  /** The status and track warnings, or `null` while `/parse` hasn't reported on the shown query. */
  readonly warnings: readonly FieldWarning[] | null;
  /** Close the menu and move focus to that field's filter (design E2). */
  readonly onShowFilter: (field: "status" | "track") => void;
  /** Re-run the search (EX-E4 "Search again"). */
  readonly onSearchAgain: () => void;
}

const FIELD_NAME = { status: "Status", track: "Track" } as const;

export function ExportMenu({
  source,
  disabledReason,
  warnings,
  onShowFilter,
  onSearchAgain,
}: ExportMenuProps) {
  const exporter = useExport(source);
  const [open, setOpen] = useState(false);
  const wrapper = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const items = useRef<(HTMLButtonElement | null)[]>([]);
  const pendingFocus = useRef<number | null>(null);
  const menuId = useId();
  const headingId = useId();
  const reasonId = useId();
  const warnIds = useId();
  const total = source.total;
  const checking = warnings === null;

  // focus the item asked for once the menu is drawn
  useEffect(() => {
    if (open && pendingFocus.current !== null) {
      items.current[pendingFocus.current]?.focus();
      pendingFocus.current = null;
    }
  }, [open]);

  // a pointer press outside closes it
  useEffect(() => {
    if (!open) return;
    const onDown = (e: PointerEvent) => {
      if (e.target instanceof Node && !wrapper.current?.contains(e.target)) setOpen(false);
    };
    document.addEventListener("pointerdown", onDown);
    return () => document.removeEventListener("pointerdown", onDown);
  }, [open]);

  const openAt = (index: number) => {
    if (disabledReason !== null) return;
    pendingFocus.current = index;
    if (open) {
      items.current[index]?.focus();
      pendingFocus.current = null;
    } else {
      setOpen(true);
    }
  };
  const close = (refocus: boolean) => {
    setOpen(false);
    if (refocus) trigger.current?.focus();
  };

  const onTriggerKey = (e: KeyboardEvent) => {
    if (e.key === "ArrowDown" || e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      openAt(0);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      openAt(FORMATS.length - 1);
    }
  };

  const onMenuKey = (e: KeyboardEvent) => {
    const at = items.current.findIndex((el) => el === document.activeElement);
    const n = FORMATS.length;
    const go = (i: number) => {
      e.preventDefault();
      items.current[(i + n) % n]?.focus();
    };
    if (e.key === "ArrowDown") go(at + 1);
    else if (e.key === "ArrowUp") go(at - 1);
    else if (e.key === "Home") go(0);
    else if (e.key === "End") go(n - 1);
  };

  const warnList = warnings ?? [];
  const describedBy = [headingId, ...warnList.map((w) => `${warnIds}-${w.field}`)].join(" ");

  return (
    <div
      ref={wrapper}
      className="relative inline-flex flex-wrap items-center gap-2"
      onKeyDown={(e) => {
        if (e.key === "Escape" && open) {
          e.preventDefault();
          close(true);
        }
      }}
    >
      <button
        ref={trigger}
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        aria-label={`Export ${plural(total, "paper")}`}
        aria-disabled={disabledReason !== null ? true : undefined}
        aria-describedby={disabledReason !== null ? reasonId : undefined}
        onClick={() => (open ? close(false) : openAt(0))}
        onKeyDown={onTriggerKey}
        className={`${button} ${disabledReason !== null ? "opacity-60" : ""}`}
      >
        Export {total.toLocaleString("en-US")} <span aria-hidden="true">▾</span>
      </button>
      {disabledReason === null &&
        warnList.map((w) => (
          <button
            key={w.field}
            type="button"
            onClick={() => openAt(0)}
            className="text-xs text-warn-fg underline underline-offset-4"
          >
            <span aria-hidden="true">⚠ </span>
            {warningLine(w)} <span aria-hidden="true">▸</span>
          </button>
        ))}
      {disabledReason !== null && (
        <span id={reasonId} className="w-full text-xs text-muted-foreground">
          {disabledReason}
        </span>
      )}
      <p role="status" aria-live="polite" className="sr-only">
        {exporter.announcement}
      </p>
      {open && (
        <div className="absolute top-full left-0 z-20 mt-1 w-[min(34rem,calc(100vw-2rem))] space-y-3 rounded-md border bg-background p-3 text-sm shadow-md">
          <p id={headingId} className="break-words">
            Export all {plural(total, "paper")} of this search from index{" "}
            <code className="font-mono break-all">{source.indexVersion}</code>
          </p>
          {checking && (
            <p role="status" className="text-muted-foreground">
              Checking the query&apos;s filters…
            </p>
          )}
          {warnList.map((w) => (
            <div
              key={w.field}
              id={`${warnIds}-${w.field}`}
              className="space-y-2 rounded-md border border-warn-border bg-warn-bg p-2 text-warn-fg"
            >
              <p className="break-words">
                <span aria-hidden="true">⚠ </span>
                <Coded text={warningText(w)} />
              </p>
              <button
                type="button"
                onClick={() => {
                  close(false);
                  onShowFilter(w.field);
                }}
                className="underline underline-offset-4"
              >
                Show the {FIELD_NAME[w.field]} filter
              </button>
            </div>
          ))}
          {exporter.notice !== null && (
            <ExportNotice result={exporter.notice} onRetry={exporter.retry} onSearchAgain={onSearchAgain} />
          )}
          <ul
            id={menuId}
            role="menu"
            aria-label={`Export ${plural(total, "paper")}`}
            aria-describedby={describedBy}
            onKeyDown={onMenuKey}
            className="divide-y rounded-md border"
          >
            {FORMATS.map((f, i) => {
              const busy = exporter.busy === f.format;
              const off = checking || exporter.busy !== null;
              const name = `${f.label}${f.description === null ? "" : `, ${f.description}`}, ${plural(total, "paper")}`;
              return (
                <li key={f.format} role="none">
                  <button
                    ref={(el) => {
                      items.current[i] = el;
                    }}
                    type="button"
                    role="menuitem"
                    tabIndex={-1}
                    aria-label={busy ? `Preparing ${plural(total, "paper")}…` : name}
                    aria-disabled={off ? true : undefined}
                    onClick={() => {
                      if (!off) exporter.start(f.format);
                    }}
                    className={`flex w-full flex-wrap justify-between gap-x-4 px-3 py-2 text-left hover:bg-muted focus:bg-muted ${off && !busy ? "opacity-60" : ""}`}
                  >
                    {busy ? (
                      <span>Preparing {plural(total, "paper")}…</span>
                    ) : (
                      <>
                        <span>
                          {f.label}
                          {f.description !== null && ` — ${f.description}`}
                        </span>
                        <span className="text-muted-foreground tabular-nums">{plural(total, "paper")}</span>
                      </>
                    )}
                  </button>
                </li>
              );
            })}
          </ul>
          <CovidenceHelp />
        </div>
      )}
    </div>
  );
}
