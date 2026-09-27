import type { ApiFailure } from "@/lib/api-result";

/**
 * Why a page's data didn't load, and a Retry (copy deck §1 ER-3–ER-7; no automatic retry). The API's own
 * message is shown verbatim; a non-JSON answer or no answer at all is said as such.
 */
export function LoadFailure({ failure, onRetry }: { failure: ApiFailure; onRetry: () => void }) {
  let heading: string;
  let detail: React.ReactNode;
  if (failure.kind === "network") {
    heading = "Couldn't reach the server";
    detail = "Check your connection and retry.";
  } else if (failure.kind === "server") {
    heading = "The server didn't answer";
    detail = `The server is busy or restarting (HTTP ${failure.status}, not from the search service).`;
  } else if (failure.error.code === "API_INDEX_NOT_LOADED") {
    heading = "Search index loading";
    detail = failure.error.message;
  } else if (failure.error.code === "API_INTERNAL") {
    heading = "Something went wrong on the server";
    detail = (
      <>
        <code className="font-mono">API_INTERNAL</code>: {failure.error.message} This is a bug in
        openproceedings.
      </>
    );
  } else {
    heading = "This page's data didn't load";
    detail = failure.error.message;
  }
  const wait = failure.kind === "api" ? failure.retryAfter : null;
  return (
    <div
      role="alert"
      className="space-y-2 rounded-md border border-warn-border bg-warn-bg p-3 text-sm text-warn-fg"
    >
      <h2 className="font-semibold">{heading}</h2>
      <p>{detail}</p>
      {wait !== null && wait > 0 ? <p>Retry in {wait} s.</p> : null}
      <button type="button" onClick={onRetry} className="rounded-md border border-warn-border px-2 py-0.5">
        Retry
      </button>
    </div>
  );
}
