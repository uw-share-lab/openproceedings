import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = { title: "Page not found" };

export default function NotFound() {
  return (
    <section className="mx-auto max-w-3xl space-y-3 text-sm">
      <h1 className="text-lg font-semibold">Page not found</h1>
      <p className="text-muted-foreground">
        No page exists at this address — the link may be mistyped or out of date.
      </p>
      <p>
        <Link href="/" className="underline underline-offset-4">
          Go to the openproceedings home page
        </Link>
      </p>
    </section>
  );
}
