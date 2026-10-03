"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/search", label: "Search" },
  { href: "/coverage", label: "Coverage" },
  { href: "/help/syntax", label: "Syntax" },
] as const;

/** The main navigation. The current section is marked with `aria-current="page"` and shown bold and underlined. */
export function SiteNav({ className }: { className?: string }) {
  const pathname = usePathname() ?? "";
  return (
    <nav aria-label="Main" className={className}>
      <ul className="flex flex-wrap gap-x-3 gap-y-1">
        {LINKS.map(({ href, label }) => {
          const current = pathname === href || pathname.startsWith(`${href}/`);
          return (
            <li key={href}>
              <Link
                href={href}
                aria-current={current ? "page" : undefined}
                className="underline-offset-4 hover:underline aria-[current=page]:font-semibold aria-[current=page]:underline"
              >
                {label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
