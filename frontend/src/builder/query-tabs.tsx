"use client";

/**
 * The Text/Builder tabs (design §Interaction spec: Switching; accessibility skill §Keyboard flows 3). A
 * `role=tablist` whose tabs control two panels; ←/→ (and Home/End) move between the tabs and select them,
 * keeping focus on the tabs so the reader can go back; a click, Enter or Space selects a tab **and** moves
 * focus into its panel (the first term, the read-only notice, or the editor with the cursor at the end).
 */
import type { KeyboardEvent } from "react";

export type QueryTab = "text" | "builder";

const TABS: readonly { id: QueryTab; label: string }[] = [
  { id: "text", label: "Text" },
  { id: "builder", label: "Builder" },
];

export interface QueryTabListProps {
  readonly tab: QueryTab;
  /** `enter`: the reader asked to go into the panel (click, Enter, Space), so focus follows. */
  readonly onSelect: (tab: QueryTab, enter: boolean) => void;
  /** The id prefix of the tabs and their panels: `${idBase}-tab-text`, `${idBase}-panel-text`, … */
  readonly idBase: string;
}

export const tabId = (idBase: string, tab: QueryTab) => `${idBase}-tab-${tab}`;
export const panelId = (idBase: string, tab: QueryTab) => `${idBase}-panel-${tab}`;

export function QueryTabList({ tab, onSelect, idBase }: QueryTabListProps) {
  const onKeyDown = (e: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const n = TABS.length;
    const to =
      e.key === "ArrowRight"
        ? (index + 1) % n
        : e.key === "ArrowLeft"
          ? (index - 1 + n) % n
          : e.key === "Home"
            ? 0
            : e.key === "End"
              ? n - 1
              : null;
    if (to === null) return;
    e.preventDefault();
    const next = TABS[to];
    if (next === undefined) return;
    onSelect(next.id, false);
    document.getElementById(tabId(idBase, next.id))?.focus();
  };
  return (
    <div role="tablist" aria-label="Query input" className="inline-flex rounded-md border p-0.5">
      {TABS.map((t, i) => {
        const selected = t.id === tab;
        return (
          <button
            key={t.id}
            type="button"
            role="tab"
            id={tabId(idBase, t.id)}
            aria-selected={selected}
            aria-controls={panelId(idBase, t.id)}
            tabIndex={selected ? 0 : -1}
            onClick={() => onSelect(t.id, true)}
            onKeyDown={(e) => onKeyDown(e, i)}
            className={`min-h-7 rounded-sm px-3 ${selected ? "bg-primary text-primary-foreground" : "hover:bg-muted"}`}
          >
            {t.label}
          </button>
        );
      })}
    </div>
  );
}
