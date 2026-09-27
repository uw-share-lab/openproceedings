"use client";

import { useTheme } from "next-themes";
import { useSyncExternalStore } from "react";

const subscribe = () => () => {};

/** Light/dark switch. Renders a stable placeholder on the server: the resolved theme is only known client-side. */
export function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme();
  const mounted = useSyncExternalStore(
    subscribe,
    () => true,
    () => false,
  );
  const next = resolvedTheme === "dark" ? "light" : "dark";
  return (
    <button
      type="button"
      onClick={() => setTheme(next)}
      className="rounded-md border px-2 py-1 text-xs"
      aria-label={mounted ? `Switch to ${next} theme` : "Switch theme"}
    >
      {mounted ? (resolvedTheme === "dark" ? "Dark" : "Light") : "Theme"}
    </button>
  );
}
