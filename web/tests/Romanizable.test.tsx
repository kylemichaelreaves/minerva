import { describe, expect, it } from "vitest";
import { render, screen } from "@solidjs/testing-library";
import { Romanizable } from "~/Concordance/components/Romanizable";

describe("<Romanizable />", () => {
  it("wraps a Greek word in a hover tooltip carrying its romanization", () => {
    const { container } = render(() => <Romanizable text="λόγος" />);
    // The Greek word itself is still shown as the trigger.
    expect(screen.getByText("λόγος")).toBeInTheDocument();
    // …inside a HoverTip whose tooltip body is the Latin transliteration.
    const wrap = container.querySelector(".hovertip-wrap");
    expect(wrap).not.toBeNull();
    expect(container.querySelector(".hovertip-text")?.textContent).toBe("logos");
  });

  it("romanizes rough breathing and proper-noun capitalization", () => {
    const { container } = render(() => <Romanizable text="Ἀθηνᾶ" />);
    expect(container.querySelector(".hovertip-text")?.textContent).toBe("Athena");
  });

  it("renders non-Greek text untouched — no tooltip wrapper", () => {
    const { container } = render(() => <Romanizable text="Geist" />);
    expect(screen.getByText("Geist")).toBeInTheDocument();
    expect(container.querySelector(".hovertip-wrap")).toBeNull();
  });
});
