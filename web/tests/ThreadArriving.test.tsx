import { describe, it, expect } from "vitest";
import { render } from "@solidjs/testing-library";
import Thread from "~/Thread";
import type { Phase } from "~/features/LandingTransition/controller";

function renderThread(arriving?: Phase) {
  return render(() => (
    <Thread
      messages={[{ role: "user", text: "What is Geist?", time: "10:00" }]}
      thinking
      marginNotes
      arriving={arriving}
    />
  ));
}

describe("<Thread arriving>", () => {
  it("marks the thread while the question lifts in", () => {
    const { container } = renderThread("lift");
    expect(container.querySelector(".thread")).toHaveClass("lt-arriving");
  });

  it("marks the thread while it fades in under reduced motion", () => {
    const { container } = renderThread("fade");
    expect(container.querySelector(".thread")).toHaveClass("lt-fading");
  });

  it("carries neither mark at rest", () => {
    for (const arriving of [undefined, "idle"] as const) {
      const { container, unmount } = renderThread(arriving);
      const thread = container.querySelector(".thread");
      expect(thread).not.toHaveClass("lt-arriving");
      expect(thread).not.toHaveClass("lt-fading");
      unmount();
    }
  });
});
