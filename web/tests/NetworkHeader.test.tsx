import { render } from "@solidjs/testing-library";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MobileShellProvider } from "~/components/shell/MobileShellContext";
import { CORPUS_YEAR_SPAN_LABEL } from "~/features/Landing/corpusFacts";
import { NetworkHeader } from "~/Network/components/Header";
import { fakeMediaQueryList } from "./helpers/matchMedia";
import { must } from "./helpers/must";

const totals = { xrefs: 12345, authors: 48, works: 312 };

function mount(opts: { mobile: boolean; totals?: typeof totals }) {
  vi.spyOn(window, "matchMedia").mockImplementation((query: string) =>
    fakeMediaQueryList(query, opts.mobile),
  );
  const { container } = render(() => (
    <MobileShellProvider>
      <NetworkHeader
        minConfidence={0.8}
        totals={opts.totals}
        authorOptions={[]}
        onPatch={vi.fn()}
      />
    </MobileShellProvider>
  ));
  return must(container.querySelector(".net-totals"), ".net-totals");
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("<NetworkHeader /> totals", () => {
  it("desktop: renders citations · authors · works inline", () => {
    const el = mount({ mobile: false, totals });
    const bigs = [...el.querySelectorAll(".big")].map((s) => s.textContent);
    expect(bigs).toEqual([(12345).toLocaleString(), "48", "312"]);
    expect(el.textContent).toContain("citations");
    expect(el.textContent).toContain("works");
    expect(el.querySelector(".net-hero-num")).toBeNull();
    expect(el.querySelector(".crumbs")?.textContent).toContain("filter: conf");
  });

  it("mobile: renders the hero number and the authors · works · span byline", () => {
    const el = mount({ mobile: true, totals });
    expect(el.querySelector(".net-hero-num")?.textContent).toBe((12345).toLocaleString());
    expect(el.querySelector(".net-hero-what")?.textContent).toContain("verified cross-references");
    const nums = [...el.querySelectorAll(".net-hero-meta .num")].map((s) => s.textContent);
    expect(nums).toEqual(["48", "312", CORPUS_YEAR_SPAN_LABEL]);
    // The desktop confidence crumb is suppressed on mobile.
    expect(el.querySelector(".crumbs")).toBeNull();
  });

  it.each([false, true])("shows only the dash placeholder without totals (mobile=%s)", (mobile) => {
    const el = mount({ mobile });
    expect(el.querySelector(".big")).toBeNull();
    expect(el.querySelector(".net-hero-num")).toBeNull();
    expect(el.textContent).toContain("—");
  });
});
