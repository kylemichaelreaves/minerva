import { fireEvent, render, screen } from "@solidjs/testing-library";
import { describe, expect, it, vi } from "vitest";
import { MobileFooterLinks } from "~/Network/components/MobileFooterLinks";

describe("<MobileFooterLinks />", () => {
  it("routes each footer link to its own handler", () => {
    const onOpenArc = vi.fn();
    const onOpenCoverage = vi.fn();
    const onOpenMore = vi.fn();
    render(() => (
      <MobileFooterLinks
        onOpenArc={onOpenArc}
        onOpenCoverage={onOpenCoverage}
        onOpenMore={onOpenMore}
      />
    ));

    fireEvent.click(screen.getByRole("button", { name: /View as timeline/ }));
    expect(onOpenArc).toHaveBeenCalledTimes(1);
    expect(onOpenCoverage).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: /Verification coverage/ }));
    expect(onOpenCoverage).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole("button", { name: /More views/ }));
    expect(onOpenMore).toHaveBeenCalledTimes(1);
    expect(onOpenArc).toHaveBeenCalledTimes(1);
  });
});
