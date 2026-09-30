// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SiteFooter } from "./site-footer";

afterEach(() => {
  cleanup();
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
});

function footerOf(contact: string | undefined): { text: string; link: HTMLElement } {
  if (contact === undefined) vi.stubEnv("NEXT_PUBLIC_TAKEDOWN_CONTACT", undefined);
  else vi.stubEnv("NEXT_PUBLIC_TAKEDOWN_CONTACT", contact);
  render(<SiteFooter />);
  const footer = screen.getByRole("contentinfo");
  const links = [...footer.querySelectorAll("a")];
  expect(links).toHaveLength(1);
  return { text: footer.textContent ?? "", link: links[0] as HTMLElement };
}

describe("SiteFooter", () => {
  it("names the deployment's takedown address (FT-1)", () => {
    const { text, link } = footerOf("takedown@example.org");
    expect(text).toBe("To have an abstract removed from this site, email takedown@example.org.");
    expect(screen.getByRole("link", { name: "takedown@example.org" })).toBe(link);
    expect(link.getAttribute("href")).toBe("mailto:takedown@example.org");
  });

  it("follows the variable, so each deployment names its own contact", () => {
    const { text, link } = footerOf("mailto:rights@lab.example.ca");
    expect(text).toBe("To have an abstract removed from this site, email rights@lab.example.ca.");
    expect(link.getAttribute("href")).toBe("mailto:rights@lab.example.ca");
  });

  it("links a contact page (FT-2)", () => {
    const { text, link } = footerOf("https://example.org/takedown");
    expect(text).toBe("To have an abstract removed from this site, contact example.org/takedown.");
    expect(screen.getByRole("link", { name: "example.org/takedown" })).toBe(link);
    expect(link.getAttribute("href")).toBe("https://example.org/takedown");
  });

  it.each([undefined, ""])("still names a contact when the variable is %j (FT-3)", (contact) => {
    const { text, link } = footerOf(contact);
    expect(text).toBe(
      "To have an abstract removed from this site, open an issue at github.com/uw-share-lab/openproceedings/issues.",
    );
    expect(link.getAttribute("href")).toBe("https://github.com/uw-share-lab/openproceedings/issues");
  });

  it("falls back rather than render an unusable link", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const { link } = footerOf("javascript:alert(1)");
    expect(link.getAttribute("href")).toBe("https://github.com/uw-share-lab/openproceedings/issues");
    expect(warn).toHaveBeenCalledOnce();
  });

  it("underlines the link and lets a long address wrap at 320 px", () => {
    const { link } = footerOf("a-very-long-takedown-address-for-a-department@faculty.university.example.org");
    expect(link.className.split(" ")).toEqual(expect.arrayContaining(["underline", "wrap-anywhere"]));
  });
});
