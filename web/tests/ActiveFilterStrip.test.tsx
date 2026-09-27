import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@solidjs/testing-library";
import { ActiveFilterStrip } from "~/Concordance/components/ActiveFilterStrip";
import { must } from "./helpers/must";

describe("<ActiveFilterStrip />", () => {
  it("renders nothing when items is empty", () => {
    const { container } = render(() => <ActiveFilterStrip items={[]} onReset={vi.fn()} />);
    expect(container.querySelector(".afs")).toBeNull();
  });

  it("renders one pill per item, kicker + value", () => {
    render(() => (
      <ActiveFilterStrip
        items={[
          { k: "letter", v: "H", onRemove: vi.fn() },
          { k: "POS", v: "noun", onRemove: vi.fn() },
        ]}
        onReset={vi.fn()}
      />
    ));
    expect(screen.getByText("Active · 2")).toBeInTheDocument();
    expect(screen.getByText("letter")).toBeInTheDocument();
    expect(screen.getByText("POS")).toBeInTheDocument();
    expect(screen.getByText("H")).toBeInTheDocument();
    expect(screen.getByText("noun")).toBeInTheDocument();
  });

  it("clicking the × on a pill calls onRemove for that pill only", () => {
    const removeA = vi.fn();
    const removeB = vi.fn();
    render(() => (
      <ActiveFilterStrip
        items={[
          { k: "letter", v: "H", onRemove: removeA },
          { k: "POS", v: "noun", onRemove: removeB },
        ]}
        onReset={vi.fn()}
      />
    ));
    const closers = document.querySelectorAll(".afs .afs-pill .x");
    expect(closers).toHaveLength(2);
    fireEvent.click(must(closers[0]));
    expect(removeA).toHaveBeenCalledTimes(1);
    expect(removeB).not.toHaveBeenCalled();
    fireEvent.click(must(closers[1]));
    expect(removeB).toHaveBeenCalledTimes(1);
  });

  it("clicking 'reset all' calls onReset", () => {
    const onReset = vi.fn();
    render(() => (
      <ActiveFilterStrip items={[{ k: "letter", v: "H", onRemove: vi.fn() }]} onReset={onReset} />
    ));
    fireEvent.click(screen.getByText(/reset all/));
    expect(onReset).toHaveBeenCalledTimes(1);
  });

  it("shows count and default countLabel when count is set", () => {
    render(() => (
      <ActiveFilterStrip
        items={[{ k: "letter", v: "H", onRemove: vi.fn() }]}
        count={847}
        onReset={vi.fn()}
      />
    ));
    expect(screen.getByText("847")).toBeInTheDocument();
    // Default countLabel
    expect(screen.getByText(/results/)).toBeInTheDocument();
  });

  it("honours an explicit countLabel", () => {
    render(() => (
      <ActiveFilterStrip
        items={[{ k: "letter", v: "H", onRemove: vi.fn() }]}
        count={42}
        countLabel="lemmas shown"
        onReset={vi.fn()}
      />
    ));
    expect(screen.getByText(/lemmas shown/)).toBeInTheDocument();
  });
});
