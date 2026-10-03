"use client";

/**
 * One export at a time, from a search or a record (design E1, R1): which format is being prepared, why the
 * last one didn't download, and what to announce ("Export started: 412 papers, RIS." then "Download ready.",
 * design §Keyboard and screen reader). The download continues when the menu closes. A download whose abstracts
 * were withheld (decision-021) is still saved, and says so until the next export starts (EX-E8).
 */
import { useRef, useState } from "react";
import { plural } from "@/editor/diagnostics";
import { useApi } from "@/components/providers";
import {
  fetchExport,
  FORMATS,
  saveBlob,
  type ExportFormat,
  type ExportResult,
  type ExportSource,
} from "@/lib/export";
import { removedText, WITHHELD_TEXT } from "./export-notice";

export type ExportNoticeResult = Exclude<ExportResult, { kind: "ok" }>;

export interface ExportState {
  /** The format being prepared, or `null`. */
  readonly busy: ExportFormat | null;
  /** Why the last export didn't download, until the next one starts. */
  readonly notice: ExportNoticeResult | null;
  /** The last download has no abstracts (`X-Abstract-Source: unavailable`), until the next one starts. */
  readonly withheld: boolean;
  /** Records of the last download whose abstract was removed at a rights holder's request (EX-E9). */
  readonly removed: number;
  readonly announcement: string;
  readonly start: (format: ExportFormat) => void;
  /** Start the last format again (the notice's Retry). */
  readonly retry: () => void;
}

export function useExport(source: ExportSource): ExportState {
  const api = useApi();
  const [busy, setBusy] = useState<ExportFormat | null>(null);
  const [notice, setNotice] = useState<ExportNoticeResult | null>(null);
  const [withheld, setWithheld] = useState(false);
  const [removed, setRemoved] = useState(0);
  const [announcement, setAnnouncement] = useState("");
  const last = useRef<ExportFormat | null>(null);
  const running = useRef(false);

  const start = (format: ExportFormat) => {
    if (running.current) return;
    running.current = true;
    last.current = format;
    const label = FORMATS.find((f) => f.format === format)?.label ?? format;
    setBusy(format);
    setNotice(null);
    setWithheld(false);
    setRemoved(0);
    setAnnouncement(`Export started: ${plural(source.total, "paper")}, ${label}.`);
    void fetchExport(api, source, format).then(
      (result) => {
        running.current = false;
        setBusy(null);
        if (result.kind === "ok") {
          saveBlob(result.blob, result.filename);
          setWithheld(result.abstractsWithheld);
          setRemoved(result.removed);
          setAnnouncement(
            [
              "Download ready.",
              result.abstractsWithheld ? WITHHELD_TEXT : "",
              result.removed > 0 ? removedText(result.removed) : "",
            ]
              .filter(Boolean)
              .join(" "),
          );
        } else {
          setNotice(result);
          setAnnouncement("Nothing was downloaded.");
        }
      },
      (e: unknown) => {
        running.current = false;
        setBusy(null);
        setNotice({ kind: "unreachable" });
        setAnnouncement("Nothing was downloaded.");
        console.error("openproceedings: the export failed", e);
      },
    );
  };

  return {
    busy,
    notice,
    withheld,
    removed,
    announcement,
    start,
    retry: () => {
      if (last.current !== null) start(last.current);
    },
  };
}
