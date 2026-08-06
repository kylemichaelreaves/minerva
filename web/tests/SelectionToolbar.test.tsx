import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, fireEvent } from "@solidjs/testing-library";
import { SelectionToolbar } from "~/Reader/components/SelectionToolbar";

function renderToolbar(
  overrides: Partial<{
    singleWord: boolean;
    onLookup: () => void;
    onSyntax: () => void;
  }> = {},
) {
  const onTranslate = vi.fn();
  const onCopy = vi.fn();
  const onDismiss = vi.fn();
  const onLookup = overrides.onLookup ?? vi.fn();
  const utils = render(() => (
    <SelectionToolbar
      anchor={{ rect: new DOMRect(100, 10, 40, 20) }}
      count="4 words"
      singleWord={overrides.singleWord ?? false}
      onTranslate={onTranslate}
      onLookup={onLookup}
      onSyntax={overrides.onSyntax}
      onCopy={onCopy}
      onDismiss={onDismiss}
    />
  ));
  return { onTranslate, onCopy, onDismiss, onLookup, ...utils };
}

describe("<SelectionToolbar />", () => {
  beforeEach(() => {
    Object.defineProperty(window, "innerWidth", { value: 800, configurable: true });
    Object.defineProperty(window, "innerHeight", { value: 600, configurable: true });
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders translate and copy actions for multi-word selections", () => {
    const { container, onTranslate, onCopy } = renderToolbar();
    expect(container.textContent).toContain("Translate phrase");
    expect(container.textContent).toContain("Copy");
    fireEvent.click(container.querySelector(".st-btn")!);
    expect(onTranslate).toHaveBeenCalledTimes(1);
    const buttons = container.querySelectorAll(".st-btn");
    fireEvent.click(buttons[1]!);
    expect(onCopy).toHaveBeenCalledTimes(1);
  });

  it("renders look up and translate for single-word selections", () => {
    const { container, onLookup, onTranslate } = renderToolbar({ singleWord: true });
    expect(container.textContent).toContain("Look up");
    const buttons = container.querySelectorAll(".st-btn");
    fireEvent.click(buttons[0]!);
    fireEvent.click(buttons[1]!);
    expect(onLookup).toHaveBeenCalledTimes(1);
    expect(onTranslate).toHaveBeenCalledTimes(1);
  });

  it("adds the below class when there is little headroom above the selection", () => {
    const onTranslate = vi.fn();
    const onCopy = vi.fn();
    const { container } = render(() => (
      <SelectionToolbar
        anchor={{ rect: new DOMRect(100, 5, 40, 20) }}
        count="1 word"
        singleWord={false}
        onTranslate={onTranslate}
        onCopy={onCopy}
        onDismiss={vi.fn()}
      />
    ));
    expect(container.querySelector(".selection-toolbar.below")).not.toBeNull();
  });

  it("omits the syntax action when no handler is supplied", () => {
    const { container } = renderToolbar();
    expect(container.textContent).not.toContain("Syntax");
  });

  it("renders the syntax action and calls it on click", () => {
    const onSyntax = vi.fn();
    const { container } = renderToolbar({ onSyntax });
    expect(container.textContent).toContain("Syntax");

    const btn = Array.from(container.querySelectorAll(".st-btn")).find((b) =>
      b.textContent?.includes("Syntax"),
    );
    fireEvent.click(btn!);
    expect(onSyntax).toHaveBeenCalledTimes(1);
  });

  it("keeps the other actions working when syntax is present", () => {
    const { container, onTranslate, onCopy } = renderToolbar({ onSyntax: vi.fn() });
    const byText = (s: string) =>
      Array.from(container.querySelectorAll(".st-btn")).find((b) =>
        b.textContent?.includes(s),
      )!;
    fireEvent.click(byText("Translate"));
    fireEvent.click(byText("Copy"));
    expect(onTranslate).toHaveBeenCalledTimes(1);
    expect(onCopy).toHaveBeenCalledTimes(1);
  });
});
