import type { Metadata } from "next";
import { Placeholder } from "@/components/placeholder";

// Not built yet: the coverage table arrives in TASK-045 (spec 05 §Pages).
export const metadata: Metadata = { title: "Coverage" };

export default function CoveragePage() {
  return <Placeholder title="Coverage" />;
}
