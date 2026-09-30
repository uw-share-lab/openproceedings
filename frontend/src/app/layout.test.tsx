// @vitest-environment jsdom
/**
 * The root layout rendered to static markup, the way the server sends it. Reflow at 320/360 px (WCAG
 * 1.4.10) is checked on the classes that produce it: jsdom has no layout engine, so a width measurement
 * belongs in Playwright; these assertions pin the wrapping rules so a refactor cannot drop them.
 */
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import RootLayout, { metadata } from "./layout";

vi.mock("next/navigation", () => ({ usePathname: () => "/search" }));

// next-themes reads prefers-color-scheme through matchMedia, which jsdom lacks.
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

function renderLayout(): Document {
  const html = renderToStaticMarkup(
    <RootLayout params={Promise.resolve({})}>
      <p>content</p>
    </RootLayout>,
  );
  return new DOMParser().parseFromString(html, "text/html");
}

const classes = (el: Element | null) => (el?.getAttribute("class") ?? "").split(/\s+/);

describe("root layout", () => {
  it("titles every page `<page> · openproceedings`", () => {
    expect(metadata.title).toEqual({ default: "openproceedings", template: "%s · openproceedings" });
  });

  it("starts with a skip link to a focusable main landmark", () => {
    const doc = renderLayout();
    const first = doc.body.querySelector("a");
    expect(first?.textContent).toBe("Skip to main content");
    expect(first?.getAttribute("href")).toBe("#main");
    expect(classes(first)).toEqual(expect.arrayContaining(["sr-only", "focus:not-sr-only"]));
    const main = doc.querySelector("main");
    expect(main?.id).toBe("main");
    expect(main?.getAttribute("tabindex")).toBe("-1");
  });

  it("wraps the header instead of scrolling sideways at 320 px", () => {
    const doc = renderLayout();
    expect(classes(doc.querySelector("header"))).toEqual(expect.arrayContaining(["flex", "flex-wrap"]));
    // Under the sm breakpoint the nav takes a full row after the brand and the theme picker.
    expect(classes(doc.querySelector("nav"))).toEqual(
      expect.arrayContaining(["order-last", "w-full", "sm:order-none", "sm:w-auto"]),
    );
    expect(classes(doc.querySelector("nav ul"))).toContain("flex-wrap");
    // The theme picker keeps its size; it wraps as a whole rather than being squeezed.
    expect(classes(doc.querySelector("fieldset")?.parentElement ?? null)).toContain("shrink-0");
    expect(classes(doc.querySelector("main"))).toContain("min-w-0");
  });

  it("ends every page with a footer landmark naming the takedown contact (decision-018)", () => {
    const doc = renderLayout();
    const footer = doc.querySelector("body footer");
    // A <footer> outside <main> and <article> is the page's contentinfo landmark; it follows <main>.
    expect(footer?.closest("main, article, section, aside, nav")).toBeNull();
    expect(doc.querySelector("main ~ footer")).toBe(footer);
    expect(footer?.textContent).toMatch(/^To have an abstract removed from this site, /);
    expect(footer?.querySelector("a")?.getAttribute("href")).toBeTruthy();
  });

  it("marks the current section in the nav", () => {
    const current = renderLayout().querySelectorAll('nav a[aria-current="page"]');
    expect([...current].map((a) => a.textContent)).toEqual(["Search"]);
  });
});
