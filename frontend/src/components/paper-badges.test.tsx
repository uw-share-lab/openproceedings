// @vitest-environment jsdom
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { PaperBadges, trackDisplay } from "./paper-badges";

describe("trackDisplay", () => {
  it.each([
    ["datasets_benchmarks", "D&B", "datasets and benchmarks"],
    ["student_abstract", "student abstract", "student abstract"],
    ["iaai", "IAAI", "Innovative Applications of AI"],
    ["eaai", "EAAI", "Educational Advances in AI"],
  ])("shows %s as %s, named %s for assistive technology", (track, short, long) => {
    expect(trackDisplay(track)).toEqual({ short, long });
  });

  it("shows a track it doesn't know as it came", () => {
    expect(trackDisplay("consortium")).toEqual({ short: "consortium", long: "consortium" });
  });
});

describe("PaperBadges", () => {
  afterEach(cleanup);

  it.each([
    ["iaai", ["AAAI", "2024", "IAAIInnovative Applications of AI"]],
    ["eaai", ["AAAI", "2024", "EAAIEducational Advances in AI"]],
    ["student_abstract", ["AAAI", "2024", "student abstract"]],
  ])("badges a %s paper", (track, badges) => {
    render(<PaperBadges venue="AAAI" year={2024} track={track} presentation={null} status="accepted" />);
    const items = within(screen.getByRole("list", { name: "Details" })).getAllByRole("listitem");
    expect(items.map((li) => li.textContent)).toEqual(badges);
  });
});
