/**
 * A paper's badges, `venue · year · track · presentation`, plus the status when it isn't `accepted`
 * (ui-design-system §Badges; copy RH-10, RH-11). Every badge is text; the workshop colour is never the only
 * cue. Values are open sets (decision-009): one this code doesn't know is shown as it came.
 */

/**
 * Track values shown by another name, with the full name for assistive technology (RH-11). An acronym a reader
 * types (`track:iaai`) or sees (`D&B`) keeps the visible short form at the start of its accessible name (WCAG 2.5.3
 * Label in Name). The badge's hover `title` is a courtesy for pointer users only: it sits on an `aria-hidden` span, so it is
 * neither announced nor reachable by keyboard; the screen-reader text carries the full name. `student_abstract` is shown as the value itself, which is what the reader types.
 */
const TRACK_SHORT: Readonly<Record<string, { short: string; long: string }>> = {
  datasets_benchmarks: { short: "D&B", long: "D&B, datasets and benchmarks" },
  iaai: { short: "IAAI", long: "IAAI, Innovative Applications of AI" },
  eaai: { short: "EAAI", long: "EAAI, Educational Advances in AI" },
};

/** A track as the sidebar and badges show it: its short form, and its accessible name. */
export function trackDisplay(track: string): { short: string; long: string } {
  return TRACK_SHORT[track] ?? { short: track, long: track };
}

/** A status in words (`desk_rejected` → `desk rejected`; `unknown` → `unknown status`), as RH-10 words it. */
export function statusWords(status: string): string {
  return status === "unknown" ? "unknown status" : status.replaceAll("_", " ");
}

const badge = "inline-flex min-h-6 items-center rounded-sm border px-1.5 text-xs";

export function PaperBadges({
  venue,
  year,
  track,
  presentation,
  status,
}: {
  venue: string;
  year: number;
  track: string;
  presentation: string | null;
  status: string;
}) {
  const t = trackDisplay(track);
  return (
    <ul aria-label="Details" className="flex flex-wrap gap-1.5">
      <li className={badge}>{venue}</li>
      <li className={`${badge} tabular-nums`}>{year}</li>
      <li className={track === "workshop" ? `${badge} border-track-workshop text-track-workshop` : badge}>
        {t.short === t.long ? (
          t.short
        ) : (
          <>
            <span aria-hidden="true" title={t.long}>
              {t.short}
            </span>
            <span className="sr-only">{t.long}</span>
          </>
        )}
      </li>
      {presentation !== null && <li className={badge}>{presentation}</li>}
      {status !== "accepted" && (
        <li className={`${badge} border-excluded-border bg-excluded-bg text-excluded-fg`}>
          <span aria-hidden="true">{statusWords(status)}</span>
          <span className="sr-only">
            {statusWords(status)}, status {status}
          </span>
        </li>
      )}
    </ul>
  );
}
