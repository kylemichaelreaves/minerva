import { render, screen } from "@solidjs/testing-library";
import { describe, expect, it } from "vitest";
import { ApparatusPanel } from "~/Network/components/ApparatusPanel";

// #710: a citation in an editor's or translator's note is credited to that
// person. They are off the author axis, so this list is where the page
// shows them — with the author whose work hosts their notes.
describe("<ApparatusPanel />", () => {
  it("names each editor, the host author, and the count", () => {
    render(() => (
      <ApparatusPanel
        rows={[
          { name: "Allen W. Wood", host_author: "Hegel", n: 170 },
          { name: "Paul Shorey", host_author: "Plato", n: 144 },
        ]}
      />
    ));
    const rows = screen.getAllByTestId("apparatus-row").map((el) => el.textContent);
    expect(rows).toEqual(["Allen W. Wood in Hegel170", "Paul Shorey in Plato144"]);
  });

  it("renders nothing when no editor is cited", () => {
    const { container } = render(() => <ApparatusPanel rows={[]} />);
    expect(container.textContent).toBe("");
  });
});
