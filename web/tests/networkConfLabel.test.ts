// @vitest-environment node
import { describe, expect, it } from "vitest";

import { confLabel } from "~/Network/constants";

/** #507: `confLabel` was four byte-identical lines in both
 *  `Network/components/Header.tsx` and `NetworkFiltersBar.tsx`, which
 *  is how a filter chip and the header can drift apart on the same
 *  filter state. These cases pin the behaviour the two copies shared. */
describe("confLabel", () => {
  it("falls back to the default floor when no minimum is set", () => {
    expect(confLabel(undefined)).toBe("≥0.8");
  });

  it("renders one decimal below 1", () => {
    expect(confLabel(0.65)).toBe("≥0.7");
    expect(confLabel(0.9)).toBe("≥0.9");
  });

  it("drops the decimal at 1 and above", () => {
    expect(confLabel(1)).toBe("≥1");
  });

  it("renders a floor of 0 rather than treating it as unset", () => {
    expect(confLabel(0)).toBe("≥0.0");
  });
});
