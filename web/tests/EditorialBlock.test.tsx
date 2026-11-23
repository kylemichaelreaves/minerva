import { render, screen, fireEvent } from "@solidjs/testing-library";
import { describe, expect, it } from "vitest";
import { flush } from "solid-js";
import { EditorialBlock } from "~/Reader/components/EditorialBlock";

describe("EditorialBlock", () => {
  it("is closed on first render", () => {
    render(() => (
      <EditorialBlock label="Editorial Introduction" count={3}>
        <p>Hegel delivered these lectures five times.</p>
      </EditorialBlock>
    ));
    expect(screen.queryByText(/delivered these lectures/)).toBeNull();
  });

  it("names what is hidden, so the reader can decide", () => {
    render(() => (
      <EditorialBlock label="Editorial Introduction" count={3}>
        <p>body</p>
      </EditorialBlock>
    ));
    const summary = screen.getByRole("button");
    expect(summary.textContent).toContain("Editorial Introduction");
    expect(summary.textContent).toContain("3");
  });

  it("expands on click and collapses again", () => {
    const { container } = render(() => (
      <EditorialBlock label="Editorial Introduction" count={1}>
        <p>Hegel delivered these lectures five times.</p>
      </EditorialBlock>
    ));
    const summary = screen.getByRole("button");
    const block = container.querySelector(".editorial-block");
    expect(block?.hasAttribute("data-open")).toBe(false);
    fireEvent.click(summary);
    flush();
    expect(screen.queryByText(/delivered these lectures/)).not.toBeNull();
    expect(block?.hasAttribute("data-open")).toBe(true);
    fireEvent.click(summary);
    flush();
    expect(screen.queryByText(/delivered these lectures/)).toBeNull();
    expect(block?.hasAttribute("data-open")).toBe(false);
  });
});
