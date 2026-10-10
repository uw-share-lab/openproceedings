// @vitest-environment jsdom
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { PaperBadges, trackDisplay } from "./paper-badges";

describe("trackDisplay", () => {
  it.each([
    ["datasets_benchmarks", "D&B", "D&B, datasets and benchmarks"],
    ["student_abstract", "student_abstract", "student_abstract"], // the value itself, as typed
    ["iaai", "IAAI", "IAAI, Innovative Applications of AI"], // the acronym is in the name (WCAG 2.5.3)
    ["eaai", "EAAI", "EAAI, Educational Advances in AI"],
  ])("shows %s as %s, named %s for assistive technology", (track, short, long) => {
    expect(trackDisplay(track)).toEqual({ short, long });
  });

  it("shows a track it doesn't know as it came", () => {
    expect(trackDisplay("nonesuch")).toEqual({ short: "nonesuch", long: "nonesuch" });
  });
});

describe("PaperBadges", () => {
  afterEach(cleanup);

  it.each([
    ["iaai", ["AAAI", "2024", "IAAIIAAI, Innovative Applications of AI"]],
    ["eaai", ["AAAI", "2024", "EAAIEAAI, Educational Advances in AI"]],
    ["student_abstract", ["AAAI", "2024", "student_abstract"]],
  ])("badges a %s paper", (track, badges) => {
    render(<PaperBadges venue="AAAI" year={2024} track={track} presentation={null} status="accepted" />);
    const items = within(screen.getByRole("list", { name: "Details" })).getAllByRole("listitem");
    expect(items.map((li) => li.textContent)).toEqual(badges);
  });
});

describe("an acronym track badge", () => {
  afterEach(cleanup);

  it("is named with its acronym and shows its full name on hover", () => {
    render(<PaperBadges venue="AAAI" year={2024} track="iaai" presentation={null} status="accepted" />);
    const shown = screen.getByText("IAAI", { selector: "[aria-hidden=true]" });
    expect(shown.getAttribute("title")).toBe("IAAI, Innovative Applications of AI");
    expect(screen.getByText("IAAI, Innovative Applications of AI", { selector: ".sr-only" })).toBeTruthy();
  });
});
