"use client";

import { useTheme } from "next-themes";
import { useSyncExternalStore } from "react";

const subscribe = () => () => {};

/**
 * Dark-theme toggle button. The name is stable ("Dark theme") and the state is `aria-pressed`, so the
 * visible label is the accessible name (WCAG 2.5.3 Label in Name). The resolved theme is only known on
 * the client, so the server renders the button without a pressed state.
 */
export function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme();
  const mounted = useSyncExternalStore(
    subscribe,
    () => true,
    () => false,
  );
  const dark = resolvedTheme === "dark";
  return (
    <button
      type="button"
      onClick={() => setTheme(dark ? "light" : "dark")}
      className="rounded-md border px-2 py-1 text-xs aria-pressed:bg-muted"
      aria-pressed={mounted ? dark : undefined}
    >
      Dark theme
    </button>
  );
}
