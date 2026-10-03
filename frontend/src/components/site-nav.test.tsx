// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SiteNav } from "./site-nav";

let pathname = "/";
vi.mock("next/navigation", () => ({ usePathname: () => pathname }));

afterEach(cleanup);

function currentLinks(): string[] {
  render(<SiteNav />);
  return screen
    .getAllByRole("link")
    .filter((a) => a.getAttribute("aria-current") === "page")
    .map((a) => a.textContent ?? "");
}

describe("SiteNav", () => {
  it.each([
    ["/", []],
    ["/search", ["Search"]],
    ["/coverage", ["Coverage"]],
    ["/help/syntax", ["Syntax"]],
    ["/searching", []],
  ])("on %s marks %j as current", (path, expected) => {
    pathname = path;
    expect(currentLinks()).toEqual(expected);
  });

  it("styles the current link beyond colour (bold and underlined)", () => {
    pathname = "/search";
    render(<SiteNav />);
    const link = screen.getByRole("link", { name: "Search" });
    expect(link.className).toMatch(/aria-\[current=page\]:font-semibold/);
    expect(link.className).toMatch(/aria-\[current=page\]:underline/);
  });
});
