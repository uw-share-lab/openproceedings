import { COVIDENCE_TEXT } from "@/lib/export";

/** EX-E7: "Importing into Covidence", a disclosure. `*…*` in the copy is a Covidence screen's name (italic). */
export function CovidenceHelp() {
  const parts = COVIDENCE_TEXT.split("*");
  return (
    <details className="text-sm">
      <summary className="cursor-pointer">Importing into Covidence</summary>
      <p className="mt-2 break-words">
        {parts.map((part, i) => (i % 2 === 1 ? <em key={i}>{part}</em> : part))}
      </p>
    </details>
  );
}
