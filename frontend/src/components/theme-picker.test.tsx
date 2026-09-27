// @vitest-environment jsdom
import { act, cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { ThemePicker } from "./theme-picker";
import { ThemeProvider } from "./theme-provider";

/** The OS preference next-themes reads through matchMedia("(prefers-color-scheme: dark)"). */
let systemDark = false;

beforeEach(() => {
  // jsdom has no matchMedia.
  window.matchMedia = (query: string) =>
    ({
      matches: query === "(prefers-color-scheme: dark)" && systemDark,
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    }) satisfies MediaQueryList;
});

afterEach(() => {
  cleanup();
  localStorage.clear();
  document.documentElement.className = "";
  systemDark = false;
});

function renderPicker() {
  render(
    <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
      <ThemePicker />
    </ThemeProvider>,
  );
  return screen.getByRole("group", { name: "Theme" });
}

const isDark = () => document.documentElement.classList.contains("dark");

describe("ThemePicker", () => {
  it("offers System, Light and Dark, each named by its visible label (WCAG 2.5.3)", () => {
    const group = renderPicker();
    const radios = within(group).getAllByRole("radio");
    expect(radios.map((r) => r.closest("label")?.textContent)).toEqual(["System", "Light", "Dark"]);
    for (const label of ["System", "Light", "Dark"]) {
      expect(within(group).getByRole("radio", { name: label })).toBeTruthy();
    }
  });

  it("follows a dark system preference while System is chosen", () => {
    systemDark = true;
    const group = renderPicker();
    expect((within(group).getByRole("radio", { name: "System" }) as HTMLInputElement).checked).toBe(true);
    expect(isDark()).toBe(true);
  });

  it("switches to Light and back to System", () => {
    systemDark = true;
    const group = renderPicker();
    const light = within(group).getByRole("radio", { name: "Light" }) as HTMLInputElement;
    act(() => light.click());
    expect(light.checked).toBe(true);
    expect(isDark()).toBe(false);

    const system = within(group).getByRole("radio", { name: "System" }) as HTMLInputElement;
    act(() => system.click());
    expect(system.checked).toBe(true);
    expect(isDark()).toBe(true);
  });

  it("chooses Dark on a light system", () => {
    const group = renderPicker();
    const dark = within(group).getByRole("radio", { name: "Dark" }) as HTMLInputElement;
    act(() => dark.click());
    expect(dark.checked).toBe(true);
    expect(isDark()).toBe(true);
  });

  it("fills the chosen option (not only a tint) and draws focus on the visible label", () => {
    const label = renderPicker().querySelector("label");
    expect(label?.className).toMatch(/has-checked:bg-primary/);
    expect(label?.className).toMatch(/has-checked:text-primary-foreground/);
    expect(label?.className).toMatch(/has-focus-visible:outline-ring/);
  });
});
