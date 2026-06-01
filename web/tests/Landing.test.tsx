import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@solidjs/testing-library";
import Landing from "~/Landing";

function renderLanding() {
  const onSubmit = vi.fn();
  const onPickPrompt = vi.fn();
  const onOpenRead = vi.fn();
  const onOpenRefs = vi.fn();
  const onOpenNetwork = vi.fn();
  const onOpenConcordance = vi.fn();
  const utils = render(() => (
    <Landing
      onSubmit={onSubmit}
      onPickPrompt={onPickPrompt}
      onOpenRead={onOpenRead}
      onOpenRefs={onOpenRefs}
      onOpenNetwork={onOpenNetwork}
      onOpenConcordance={onOpenConcordance}
    />
  ));
  return {
    onSubmit,
    onPickPrompt,
    onOpenRead,
    onOpenRefs,
    onOpenNetwork,
    onOpenConcordance,
    ...utils,
  };
}

describe("<Landing />", () => {
  it("renders the monogram and the composer", () => {
    renderLanding();
    expect(screen.getByAltText("Minerva")).toBeInTheDocument();
    expect(
      screen.getByPlaceholderText(/what would you like to consider/i),
    ).toBeInTheDocument();
  });

  it("starter prompts row is hidden by default", () => {
    const { container } = renderLanding();
    expect(container.querySelector(".landing-starters")).toBeNull();
  });

  it("Enter on the textarea calls onSubmit with trimmed value", () => {
    const { onSubmit } = renderLanding();
    const ta = screen.getByPlaceholderText(/what would you like to consider/i);
    fireEvent.input(ta, { target: { value: "  on the good  " } });
    fireEvent.keyDown(ta, { key: "Enter" });
    expect(onSubmit).toHaveBeenCalledWith("on the good");
  });

  it("Shift+Enter is a newline, not a submit", () => {
    const { onSubmit } = renderLanding();
    const ta = screen.getByPlaceholderText(/what would you like to consider/i);
    fireEvent.input(ta, { target: { value: "partial" } });
    fireEvent.keyDown(ta, { key: "Enter", shiftKey: true });
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("Begin button is disabled until the user types", () => {
    renderLanding();
    const btn = screen.getByRole("button", { name: /begin/i });
    expect(btn.classList.contains("disabled")).toBe(true);
    fireEvent.input(screen.getByPlaceholderText(/what would you like/i), {
      target: { value: "x" },
    });
    expect(btn.classList.contains("disabled")).toBe(false);
  });
});
