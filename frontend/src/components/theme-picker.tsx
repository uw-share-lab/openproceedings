"use client";

import { useTheme } from "next-themes";
import { useSyncExternalStore } from "react";

const subscribe = () => () => {};

const OPTIONS = [
  { value: "system", label: "System" },
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
] as const;

/**
 * Theme choice as a radio group: System (follow the OS), Light, Dark. Each radio is named by its visible
 * label (WCAG 2.5.3 Label in Name), and the group by its legend. The radios are visually hidden; the
 * label shows the choice as a solid fill and draws the focus ring. The chosen theme is only known on the
 * client, so the server renders no option checked.
 */
export function ThemePicker() {
  const { theme, setTheme } = useTheme();
  const mounted = useSyncExternalStore(
    subscribe,
    () => true,
    () => false,
  );
  return (
    <fieldset className="flex rounded-md border p-0.5 text-xs">
      <legend className="sr-only">Theme</legend>
      {OPTIONS.map(({ value, label }) => (
        <label
          key={value}
          className="cursor-pointer rounded-sm px-2 py-0.5 has-checked:bg-primary has-checked:font-semibold has-checked:text-primary-foreground has-focus-visible:outline-2 has-focus-visible:outline-offset-2 has-focus-visible:outline-ring"
        >
          <input
            type="radio"
            name="theme"
            value={value}
            className="sr-only"
            checked={mounted && theme === value}
            onChange={() => setTheme(value)}
          />
          {label}
        </label>
      ))}
    </fieldset>
  );
}
