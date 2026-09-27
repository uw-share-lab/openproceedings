import { Placeholder } from "@/components/placeholder";

export default async function RecordPage({ params }: PageProps<"/record/[id]">) {
  const { id } = await params;
  return (
    <Placeholder title="Search record" task="TASK-044">
      <p className="font-mono break-all">{id}</p>
    </Placeholder>
  );
}
