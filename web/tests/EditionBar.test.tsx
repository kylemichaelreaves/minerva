import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, cleanup } from "@solidjs/testing-library";
import { EditionBar } from "~/Reader/components/EditionBar";
import type { EditionOption } from "~/utils/types";
import { must } from "./helpers/must";

const EDITIONS: EditionOption[] = [
  {
    selector: "e34",
    lang: "grc",
    is_original: true,
    translator: "Burnet",
    year: 1903,
    label: "Platonis Opera, ed. Burnet · Greek · 1903",
    short: "Greek",
    n_chunks: 6,
  },
  {
    selector: "t12",
    lang: "eng",
    is_original: false,
    translator: "Benjamin Jowett",
    year: 1892,
    label: "Benjamin Jowett · 1892",
    short: "Jowett",
    n_chunks: 8,
  },
];

describe("<EditionBar />", () => {
  it("renders a tab per edition and marks the current one", () => {
    render(() => <EditionBar editions={EDITIONS} current="t12" onSwitch={vi.fn()} />);
    const tabs = screen.getAllByRole("tab");
    expect(tabs).toHaveLength(2);
    const jowett = screen.getByRole("tab", { name: /Jowett/ });
    expect(jowett.getAttribute("aria-selected")).toBe("true");
    expect(screen.getByRole("tab", { name: /Greek/ }).getAttribute("aria-selected")).toBe("false");
    cleanup();
  });

  it("fires onSwitch with the selector when another edition is clicked", () => {
    const onSwitch = vi.fn();
    render(() => <EditionBar editions={EDITIONS} current="t12" onSwitch={onSwitch} />);
    fireEvent.click(screen.getByRole("tab", { name: /Greek/ }));
    expect(onSwitch).toHaveBeenCalledWith("e34");
    cleanup();
  });

  it("does not fire onSwitch when the current edition is re-clicked", () => {
    const onSwitch = vi.fn();
    render(() => <EditionBar editions={EDITIONS} current="t12" onSwitch={onSwitch} />);
    fireEvent.click(screen.getByRole("tab", { name: /Jowett/ }));
    expect(onSwitch).not.toHaveBeenCalled();
    cleanup();
  });

  it("renders nothing when a work has a single edition", () => {
    render(() => <EditionBar editions={[must(EDITIONS[0])]} current="e34" onSwitch={vi.fn()} />);
    expect(screen.queryByRole("tablist")).toBeNull();
    cleanup();
  });
});
