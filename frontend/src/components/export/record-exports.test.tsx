// @vitest-environment jsdom
import { cleanup, fireEvent, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { renderWithApi } from "@/test/api-stub";
import { RecordExports } from "./record-exports";

beforeEach(() => {
  URL.createObjectURL = vi.fn(() => "blob:test");
  URL.revokeObjectURL = vi.fn();
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const RECORD = { recordId: "Ab3dE5fG7hJ9", indexVersion: "a1b2c3d4e5f6", total: 3 };

function file(abstractSource: string): Response {
  return new Response("TY  - CPAPER\nER  - \n", {
    headers: {
      "X-Index-Version": RECORD.indexVersion,
      "X-Total": String(RECORD.total),
      "Content-Disposition": 'attachment; filename="openproceedings-x.ris"',
      "X-Abstract-Source": abstractSource,
    },
  });
}

describe("a record's exports (spec 05 §Pages)", () => {
  it("saves a file whose abstracts were withheld, shows EX-E8 and announces it", async () => {
    renderWithApi(<RecordExports {...RECORD} indexGone={false} />, () => file("unavailable"));
    fireEvent.click(screen.getByRole("button", { name: "RIS, 3 papers" }));
    expect(await screen.findByText(/^Download ready\. This file has no abstracts/)).toBeTruthy();
    expect(URL.createObjectURL).toHaveBeenCalledOnce();
    expect(screen.getByText(/Covidence doesn't show that note to screeners/)).toBeTruthy();
  });

  it("shows no withheld notice for an attributed file", async () => {
    renderWithApi(<RecordExports {...RECORD} indexGone={false} />, () => file("attributed"));
    fireEvent.click(screen.getByRole("button", { name: "RIS, 3 papers" }));
    expect(await screen.findByText("Download ready.")).toBeTruthy();
    expect(screen.queryByText(/This file has no abstracts/)).toBeNull();
  });
});
