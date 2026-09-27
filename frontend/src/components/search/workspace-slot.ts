"use client";

/**
 * What the results half (TASK-042) needs from the query half (`SearchWorkspace`): whether the draft is dirty
 * (`DRAFT_DIRTY` disables every filter control, design W13), and the editor, to point at a clause ("Show the
 * clause in the editor", "Edit `year:` in the query"). `SearchWorkspace` provides it around its `results`.
 * Positions are UTF-16 offsets into the editor's text.
 */
import { createContext, useContext } from "react";

export interface WorkspaceSlot {
  readonly dirty: boolean;
  /** Select `[from, to)` of the editor's text and focus it. */
  readonly select: (from: number, to: number) => void;
  /** Make `text` the draft (not searched) and select `[from, to)` of it. */
  readonly draftAndSelect: (text: string, from: number, to: number) => void;
}

export const WorkspaceSlotContext = createContext<WorkspaceSlot | null>(null);

export function useWorkspaceSlot(): WorkspaceSlot {
  const slot = useContext(WorkspaceSlotContext);
  if (slot === null) {
    throw new Error("useWorkspaceSlot() is only for components drawn in SearchWorkspace's results");
  }
  return slot;
}
