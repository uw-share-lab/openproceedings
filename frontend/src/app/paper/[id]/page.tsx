import { Placeholder } from "@/components/placeholder";

export default async function PaperPage({ params }: PageProps<"/paper/[id]">) {
  const { id } = await params;
  return (
    <Placeholder title="Paper" task="TASK-042">
      <p className="font-mono break-all">{id}</p>
    </Placeholder>
  );
}
