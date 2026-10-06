// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CopyButton } from "./copy-button";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function clipboard(writeText: () => Promise<void>) {
  Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
}

describe("CopyButton", () => {
  it("says Copied again on every press, so a screen reader announces each one", async () => {
    clipboard(() => Promise.resolve());
    render(<CopyButton text="abc" label="Copy it" />);
    const status = screen.getByRole("status");
    fireEvent.click(screen.getByRole("button", { name: "Copy it" }));
    await waitFor(() => expect(status.textContent).toBe("Copied"));
    fireEvent.click(screen.getByRole("button", { name: "Copy it" }));
    expect(status.textContent).toBe(""); // cleared at once: the same text set again is not a change
    await waitFor(() => expect(status.textContent).toBe("Copied"));
  });

  it("says to select the text where the clipboard refuses, and hands the selection to its owner", async () => {
    clipboard(() => Promise.reject(new Error("denied")));
    const onFailed = vi.fn();
    const { rerender } = render(<CopyButton text="abc" label="Copy it" />);
    fireEvent.click(screen.getByRole("button", { name: "Copy it" }));
    await waitFor(() =>
      expect(screen.getByRole("status").textContent).toBe("Couldn't copy: select the text and copy it"),
    );
    rerender(<CopyButton text="abc" label="Copy it" onFailed={onFailed} />);
    fireEvent.click(screen.getByRole("button", { name: "Copy it" }));
    await waitFor(() => expect(onFailed).toHaveBeenCalledOnce());
    await waitFor(() =>
      expect(screen.getByRole("status").textContent).toBe(
        "Couldn't copy: the text is selected; copy it with Ctrl+C (⌘C on a Mac)",
      ),
    );
  });
});
