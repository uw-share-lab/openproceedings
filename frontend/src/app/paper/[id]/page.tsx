import type { Metadata } from "next";
import { Placeholder } from "@/components/placeholder";

// Not built yet: the full record arrives in TASK-042 (spec 05 §Pages).
export const metadata: Metadata = { title: "Paper" };

export default async function PaperPage({ params }: PageProps<"/paper/[id]">) {
  const { id } = await params;
  return (
    <Placeholder title="Paper">
      <p className="font-mono break-all">{id}</p>
    </Placeholder>
  );
}
