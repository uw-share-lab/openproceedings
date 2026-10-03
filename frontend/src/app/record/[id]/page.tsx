import type { Metadata } from "next";
import { RecordView } from "@/components/record/record-view";

// A search record (spec 05 §Pages; design R1–R6): the recorded search, its replay status, the methods text
// and the record's own exports. The page title names the record (copy RC-1).
export async function generateMetadata({ params }: PageProps<"/record/[id]">): Promise<Metadata> {
  const { id } = await params;
  return { title: `Search record ${decoded(id)}` };
}

export default async function RecordPage({ params }: PageProps<"/record/[id]">) {
  const { id } = await params;
  return <RecordView id={decoded(id)} />;
}

/** The id as written, whether or not the router already decoded it (a malformed one is the not-found state). */
function decoded(id: string): string {
  try {
    return decodeURIComponent(id);
  } catch {
    return id;
  }
}
