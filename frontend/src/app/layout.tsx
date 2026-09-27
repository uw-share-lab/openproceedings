import type { Metadata } from "next";
import Link from "next/link";
import { ThemeProvider } from "@/components/theme-provider";
import { ThemeToggle } from "@/components/theme-toggle";
import "./globals.css";

export const metadata: Metadata = {
  title: "openproceedings",
  description: "Exact, reproducible Boolean search over NeurIPS, ICLR and ICML titles and abstracts.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    // suppressHydrationWarning: next-themes sets the theme class on <html> before React hydrates.
    <html lang="en" suppressHydrationWarning>
      <body className="flex min-h-dvh flex-col antialiased">
        <ThemeProvider attribute="class" defaultTheme="system" enableSystem disableTransitionOnChange>
          <header className="flex items-center gap-4 border-b px-4 py-2 text-sm">
            <Link href="/" className="font-mono font-semibold">
              openproceedings
            </Link>
            <nav aria-label="Main" className="flex gap-3">
              <Link href="/search">Search</Link>
              <Link href="/coverage">Coverage</Link>
              <Link href="/help/syntax">Syntax</Link>
            </nav>
            <div className="ml-auto">
              <ThemeToggle />
            </div>
          </header>
          <main className="flex-1 px-4 py-6">{children}</main>
        </ThemeProvider>
      </body>
    </html>
  );
}
