import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@solidjs/testing-library";
import Monogram, { ROSE_LOGO_PROBABILITY } from "~/features/Landing/Monogram";

describe("<Monogram />", () => {
  afterEach(() => vi.restoreAllMocks());

  it("is the owl, with the dusk epigraph, on most mounts", () => {
    vi.spyOn(Math, "random").mockReturnValue(ROSE_LOGO_PROBABILITY);
    render(() => <Monogram />);
    expect(screen.getByAltText("Minerva")).toHaveAttribute("src", "/owl.png");
    const tip = screen.getByRole("tooltip", { hidden: true });
    expect(tip).not.toHaveClass("landing-monogram-tooltip-long");
    expect(tip).toHaveTextContent("The owl of Minerva spreads its wings");
  });

  it("is the rose, with the long Hic Rhodus epigraph, below the threshold", () => {
    vi.spyOn(Math, "random").mockReturnValue(ROSE_LOGO_PROBABILITY - 0.01);
    render(() => <Monogram />);
    expect(screen.getByAltText("Minerva")).toHaveAttribute("src", "/rose-cross.png");
    const tip = screen.getByRole("tooltip", { hidden: true });
    expect(tip).toHaveClass("landing-monogram-tooltip-long");
    expect(tip).toHaveTextContent("Hic Rhodus, hic salta.");
  });
});
