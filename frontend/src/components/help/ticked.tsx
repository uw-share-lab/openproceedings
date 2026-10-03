/**
 * A registry message as the API wrote it, with each `…` span shown as code (the message text itself is never
 * changed: the frontend shows diagnostics verbatim). An unpaired backtick stays as text.
 */
export function Ticked({ text }: { text: string }) {
  const parts = text.split("`");
  if (parts.length % 2 === 0) return <>{text}</>; // an odd number of backticks: nothing to pair
  return (
    <>
      {parts.map((part, i) =>
        i % 2 === 1 ? (
          <code key={i} className="font-mono">
            {part}
          </code>
        ) : (
          part
        ),
      )}
    </>
  );
}
