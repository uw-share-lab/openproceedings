import type { Metadata } from "next";
import Link from "next/link";
import { SiteNav } from "@/components/site-nav";
import { ThemePicker } from "@/components/theme-picker";
import { ThemeProvider } from "@/components/theme-provider";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "openproceedings", template: "%s · openproceedings" },
  description: "Exact, reproducible Boolean search over NeurIPS, ICLR and ICML titles and abstracts.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    // suppressHydrationWarning: next-themes sets the theme class on <html> before React hydrates.
    <html lang="en" suppressHydrationWarning>
      <body className="flex min-h-dvh flex-col antialiased">
        <ThemeProvider attribute="class" defaultTheme="system" enableSystem disableTransitionOnChange>
          <a
            href="#main"
            className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:rounded-md focus:bg-background focus:px-3 focus:py-2 focus:text-sm"
          >
            Skip to main content
          </a>
          {/* Reflow (WCAG 1.4.10): at 320 px the nav drops to its own row below the brand and theme picker. */}
          <header className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b px-4 py-2 text-sm">
            <Link href="/" className="font-mono font-semibold">
              openproceedings
            </Link>
            <SiteNav className="order-last w-full sm:order-none sm:w-auto" />
            <div className="ml-auto shrink-0">
              <ThemePicker />
            </div>
          </header>
          {/* tabIndex -1: the skip link moves focus here; the region itself is not a control, so no ring. */}
          <main id="main" tabIndex={-1} className="min-w-0 flex-1 px-4 py-6 focus:outline-none">
            {children}
          </main>
        </ThemeProvider>
      </body>
    </html>
  );
}
