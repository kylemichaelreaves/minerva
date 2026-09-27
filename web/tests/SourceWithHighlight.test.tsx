import { describe, it, expect } from "vitest";
import { createSignal } from "solid-js";
import { render } from "@solidjs/testing-library";
import { SourceWithHighlight } from "~/features/Refs/components/SourceWithHighlight";
import { must } from "./helpers/must";

const TEXT = "arma virumque cano";

describe("<SourceWithHighlight />", () => {
  it("wraps exactly the [start, end) span in a <mark>", () => {
    const { container } = render(() => <SourceWithHighlight text={TEXT} start={5} end={13} />);
    const mark = must(container.querySelector("mark.review-hit"), "mark");
    expect(mark.textContent).toBe("virumque");
    const spans = [...container.querySelectorAll("span")].map((s) => s.textContent);
    expect(spans).toEqual(["arma ", " cano"]);
    expect(container.textContent).toBe(TEXT);
  });

  it.each([
    ["start null", null, 4],
    ["end null", 0, null],
    ["negative start", -1, 4],
    ["empty span", 4, 4],
    ["inverted span", 6, 2],
    ["end past text", 0, TEXT.length + 1],
  ])("renders plain text with no <mark> for %s", (_name, start, end) => {
    const { container } = render(() => <SourceWithHighlight text={TEXT} start={start} end={end} />);
    expect(container.querySelector("mark")).toBeNull();
    expect(container.textContent).toBe(TEXT);
  });

  it("drops the <mark> when a reused instance advances to a row with no span (#61)", () => {
    const [span, setSpan] = createSignal<[number | null, number | null]>([0, 4]);
    const { container } = render(() => (
      <SourceWithHighlight text={TEXT} start={span()[0]} end={span()[1]} />
    ));
    expect(container.querySelector("mark")?.textContent).toBe("arma");
    setSpan([null, null]);
    expect(container.querySelector("mark")).toBeNull();
    expect(container.textContent).toBe(TEXT);
  });
});
