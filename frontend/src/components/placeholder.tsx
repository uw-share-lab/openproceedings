/** A page that exists in the route map (spec 05 §Pages) but is not built yet. */
export function Placeholder({
  title,
  task,
  children,
}: {
  title: string;
  task: string;
  children?: React.ReactNode;
}) {
  return (
    <section className="mx-auto max-w-3xl space-y-2 text-sm">
      <h1 className="text-lg font-semibold">{title}</h1>
      <p className="text-muted-foreground">Not built yet ({task}).</p>
      {children}
    </section>
  );
}
