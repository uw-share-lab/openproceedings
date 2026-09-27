import type { Metadata } from "next";
import { Placeholder } from "@/components/placeholder";

// Not built yet: the search-record page arrives in TASK-044 (spec 05 §Pages).
export const metadata: Metadata = { title: "Search record" };

export default async function RecordPage({ params }: PageProps<"/record/[id]">) {
  const { id } = await params;
  return (
    <Placeholder title="Search record">
      <p className="font-mono break-all">{id}</p>
    </Placeholder>
  );
}
