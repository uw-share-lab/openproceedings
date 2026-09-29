/**
 * A message whose `backticked` runs are query text (the reducer's refusals, copy SB-9), drawn with those runs
 * in monospace instead of showing the backticks. Text nodes only (react/no-danger).
 */
export function Coded({ text }: { text: string }) {
  const parts = text.split("`");
  // an odd number of backticks leaves the last run open: show the text as written
  if (parts.length % 2 === 0) return <>{text}</>;
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
