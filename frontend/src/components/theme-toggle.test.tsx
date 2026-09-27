// @vitest-environment jsdom
import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { ThemeProvider } from "./theme-provider";
import { ThemeToggle } from "./theme-toggle";

// jsdom has no matchMedia; next-themes reads prefers-color-scheme through it.
window.matchMedia ??= (query: string) =>
  ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  }) satisfies MediaQueryList;

afterEach(() => {
  cleanup();
  localStorage.clear();
});

function renderToggle(defaultTheme: "light" | "dark") {
  render(
    <ThemeProvider attribute="class" defaultTheme={defaultTheme} enableSystem={false}>
      <ThemeToggle />
    </ThemeProvider>,
  );
  return screen.getByRole("button");
}

/** WCAG 2.5.3 Label in Name: the accessible name contains the visible label. */
function expectLabelInName(button: HTMLElement) {
  const visible = (button.textContent ?? "").trim().toLowerCase();
  const name = (button.getAttribute("aria-label") ?? button.textContent ?? "").trim().toLowerCase();
  expect(visible).not.toBe("");
  expect(name).toContain(visible);
}

describe("ThemeToggle", () => {
  it.each(["light", "dark"] as const)("keeps its visible label in its name (%s theme)", (theme) => {
    expectLabelInName(renderToggle(theme));
  });

  it("is a toggle button whose pressed state is the dark theme", () => {
    const button = renderToggle("light");
    expect(button.getAttribute("aria-pressed")).toBe("false");
    const nameBefore = button.textContent;
    act(() => button.click());
    expect(button.getAttribute("aria-pressed")).toBe("true");
    expect(document.documentElement.classList.contains("dark")).toBe(true);
    expect(button.textContent).toBe(nameBefore);
    expectLabelInName(button);
  });
});
