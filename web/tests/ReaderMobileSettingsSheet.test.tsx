import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent } from "@solidjs/testing-library";
import { ReaderMobileSettingsSheet } from "~/Reader/components/ReaderMobileSettingsSheet";

const KEY = "minerva-reader-text-scale";

function renderSheet() {
  return render(() => (
    <ReaderMobileSettingsSheet open target="eng" onTarget={vi.fn()} onClose={vi.fn()} />
  ));
}

const btn = (label: string) => screen.getByRole("button", { name: label });

describe("<ReaderMobileSettingsSheet /> text size", () => {
  beforeEach(() => {
    localStorage.removeItem(KEY);
    document.documentElement.style.removeProperty("--reader-text-size");
  });

  it("defaults to M when nothing is saved", () => {
    renderSheet();
    expect(btn("M")).toHaveClass("active");
    expect(btn("S")).not.toHaveClass("active");
    expect(document.documentElement.style.getPropertyValue("--reader-text-size")).toBe("");
  });

  it("clicking a size selects it, persists it and applies the CSS size", () => {
    renderSheet();
    fireEvent.click(btn("L"));
    expect(btn("L")).toHaveClass("active");
    expect(btn("M")).not.toHaveClass("active");
    expect(localStorage.getItem(KEY)).toBe("l");
    expect(document.documentElement.style.getPropertyValue("--reader-text-size")).toBe("20px");

    fireEvent.click(btn("S"));
    expect(btn("S")).toHaveClass("active");
    expect(btn("L")).not.toHaveClass("active");
    expect(localStorage.getItem(KEY)).toBe("s");
    expect(document.documentElement.style.getPropertyValue("--reader-text-size")).toBe("16px");
  });

  it("restores a saved size on mount", () => {
    localStorage.setItem(KEY, "s");
    renderSheet();
    expect(btn("S")).toHaveClass("active");
    expect(document.documentElement.style.getPropertyValue("--reader-text-size")).toBe("16px");
  });
});
