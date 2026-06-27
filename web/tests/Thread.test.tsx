import { describe, it, expect, vi } from "vitest";
import { createSignal } from "solid-js";
import { render, screen } from "@solidjs/testing-library";
import Thread from "~/Thread";
import type { MinervaTurn, Turn, UserTurn } from "~/utils/types";

const POIETES_TURN: MinervaTurn = {
  role: "minerva",
  time: "11:42",
  dominant: "P",
  paragraphs: [
    "The analogy is the architecture of the entire argument [1].",
    "But the structure is doing real work [2].",
  ],
  citations: [
    { n: 1, text: "Soul read in larger letters.", src: "Republic II, 368d" },
    { n: 2, text: "Each part doing its own work.", src: "Republic IV, 441c" },
  ],
};

const USER_TURN: UserTurn = {
  role: "user",
  text: "Is justice the same in soul and city?",
  time: "11:41",
};

describe("<Thread />", () => {
  it("renders user and minerva turns with their text", () => {
    render(() => (
      <Thread messages={[USER_TURN, POIETES_TURN]} thinking={false} marginNotes={true} />
    ));
    expect(screen.getByText(USER_TURN.text)).toBeInTheDocument();
    expect(screen.getByText(/architecture of the entire argument/)).toBeInTheDocument();
    expect(screen.getByText(/structure is doing real work/)).toBeInTheDocument();
  });

  it('renders [N] markers as <sup class="cite-mark"> superscripts', () => {
    const { container } = render(() => (
      <Thread messages={[POIETES_TURN]} thinking={false} marginNotes={true} />
    ));
    const cites = container.querySelectorAll("sup.cite-mark");
    expect(cites).toHaveLength(2);
    // The [N] marker is in its own .cite-mark-n child (sibling of the
    // mobile-only .cite-mark-chip with source+locator inline).
    expect(cites[0]!.querySelector(".cite-mark-n")?.textContent).toBe("[1]");
    expect(cites[1]!.querySelector(".cite-mark-n")?.textContent).toBe("[2]");
  });

  it("shows margin notes when marginNotes=true and pull-quotes when false", () => {
    const { container, unmount } = render(() => (
      <Thread messages={[POIETES_TURN]} thinking={false} marginNotes={true} />
    ));
    expect(container.querySelectorAll(".margin-note")).toHaveLength(2);
    expect(container.querySelectorAll(".pull-quote")).toHaveLength(0);
    unmount();
    const { container: c2 } = render(() => (
      <Thread messages={[POIETES_TURN]} thinking={false} marginNotes={false} />
    ));
    expect(c2.querySelectorAll(".margin-note")).toHaveLength(0);
    expect(c2.querySelectorAll(".pull-quote")).toHaveLength(2);
  });

  it("renders plain streaming text and a cursor while streaming", () => {
    const streaming: MinervaTurn = {
      role: "minerva",
      time: "12:00",
      dominant: "P",
      paragraphs: [],
      citations: [{ n: 1, text: "passage", src: "Republic 509d" }],
      streaming: true,
      streamText: "The cave ",
    };
    const { container } = render(() => (
      <Thread messages={[streaming]} thinking={false} marginNotes={true} />
    ));
    expect(container.querySelector(".turn-body-streaming")?.textContent).toContain("The cave");
    expect(container.querySelector(".stream-cursor")).not.toBeNull();
    expect(container.querySelector("sup.cite-mark")).toBeNull();
    expect(container.querySelectorAll(".margin-note")).toHaveLength(1);
  });

  it("keeps the same minerva turn DOM node across streaming deltas and finalize", () => {
    const base: MinervaTurn = {
      role: "minerva",
      time: "12:00",
      dominant: "P",
      paragraphs: [],
      citations: [],
      streaming: true,
      streamText: "The cave ",
    };
    const [msgs, setMsgs] = createSignal<Turn[]>([base]);
    const { container } = render(() => (
      <Thread messages={msgs()} thinking={false} marginNotes={true} />
    ));
    const node = container.querySelector(".turn-minerva");
    expect(node).not.toBeNull();

    // SSE delta: same row, more streamText — must NOT recreate the view.
    setMsgs([{ ...base, streamText: "The cave is an image " }]);
    expect(container.querySelector(".turn-minerva")).toBe(node);
    expect(container.querySelector(".turn-body-streaming")?.textContent).toContain("is an image");

    // Finalize: streaming flips off, paragraphs arrive — still the same node,
    // so useCitationExpand state inside the view survives the transition.
    setMsgs([
      {
        ...base,
        streaming: false,
        streamText: undefined,
        paragraphs: ["The cave is an image of education."],
      },
    ]);
    expect(container.querySelector(".turn-minerva")).toBe(node);
    expect(container.querySelector(".turn-body")?.textContent).toContain("image of education");
  });

  it("reveals streamed text as per-character spans, appending only new ones per delta", () => {
    const base: MinervaTurn = {
      role: "minerva",
      time: "12:00",
      dominant: "P",
      paragraphs: [],
      citations: [],
      streaming: true,
      streamText: "The cave",
    };
    const [msgs, setMsgs] = createSignal<Turn[]>([base]);
    const { container } = render(() => (
      <Thread messages={msgs()} thinking={false} marginNotes={true} />
    ));
    // Each character is its own animated span, and together they
    // reproduce the full streamed text.
    const firstSpans = [...container.querySelectorAll(".turn-body-streaming .tok-reveal")];
    expect(firstSpans).toHaveLength("The cave".length);
    expect(firstSpans.map((s) => s.textContent).join("")).toBe("The cave");

    // A delta appends pieces for the new tail only — the already-revealed
    // spans keep their identity so the glow animation never re-fires on
    // text the reader has already seen.
    setMsgs([{ ...base, streamText: "The cave is dark" }]);
    const nextSpans = [...container.querySelectorAll(".turn-body-streaming .tok-reveal")];
    expect(nextSpans.length).toBeGreaterThan(firstSpans.length);
    expect(nextSpans.map((s) => s.textContent).join("")).toBe("The cave is dark");
    // The original spans are the very same DOM nodes (reused, not rebuilt).
    firstSpans.forEach((node, i) => {
      expect(nextSpans[i]).toBe(node);
    });
  });

  it("shows the thinking indicator only when thinking=true", () => {
    const { container, unmount } = render(() => (
      <Thread messages={[USER_TURN]} thinking={true} marginNotes={false} />
    ));
    expect(container.querySelector(".thinking")).not.toBeNull();
    unmount();
    const { container: c2 } = render(() => (
      <Thread messages={[USER_TURN]} thinking={false} marginNotes={false} />
    ));
    expect(c2.querySelector(".thinking")).toBeNull();
  });

  it("renders the speaker before the locator when present (margin notes)", () => {
    const turn: MinervaTurn = {
      ...POIETES_TURN,
      citations: [
        {
          n: 1,
          text: "Reason rules in the just soul.",
          src: "Republic IV, 441c",
          speaker: "Socrates",
        },
      ],
    };
    const { container } = render(() => (
      <Thread messages={[turn]} thinking={false} marginNotes={true} />
    ));
    const src = container.querySelector(".margin-note .src");
    expect(src?.textContent).toMatch(/Socrates · Republic IV, 441c/);
  });

  it("renders speaker in pull-quotes when marginNotes=false", () => {
    const turn: MinervaTurn = {
      ...POIETES_TURN,
      citations: [{ n: 1, text: "Reply.", src: "Theaetetus 151b", speaker: "Theaetetus" }],
    };
    const { container } = render(() => (
      <Thread messages={[turn]} thinking={false} marginNotes={false} />
    ));
    const src = container.querySelector(".pull-quote .src");
    expect(src?.textContent).toMatch(/Theaetetus · Theaetetus 151b/);
  });

  it("omits the speaker prefix when speaker is null", () => {
    const turn: MinervaTurn = {
      ...POIETES_TURN,
      citations: [{ n: 1, text: "Narrator.", src: "Republic VI, 504a", speaker: null }],
    };
    const { container } = render(() => (
      <Thread messages={[turn]} thinking={false} marginNotes={true} />
    ));
    const src = container.querySelector(".margin-note .src");
    expect(src?.textContent).toBe("— Republic VI, 504a");
  });

  it('marks abstained turns with the .turn-abstain class and a "no evidence" badge', () => {
    const abstain: MinervaTurn = {
      role: "minerva",
      time: "11:00",
      dominant: "P",
      paragraphs: ["I could not find enough evidence in the indexed corpus to answer that."],
      citations: [],
      abstained: true,
    };
    const { container } = render(() => (
      <Thread messages={[abstain]} thinking={false} marginNotes={true} />
    ));
    expect(container.querySelector(".turn-abstain")).not.toBeNull();
    expect(screen.getByText(/no evidence in corpus/i)).toBeInTheDocument();
    // Philosopher tag should NOT show on abstained turns.
    expect(screen.queryByText(/plato dominant/i)).toBeNull();
  });

  it("skips citation rendering on abstained turns even if citations are present", () => {
    const abstain: MinervaTurn = { ...POIETES_TURN, abstained: true };
    const { container } = render(() => (
      <Thread messages={[abstain]} thinking={false} marginNotes={true} />
    ));
    expect(container.querySelectorAll(".margin-note")).toHaveLength(0);
    expect(container.querySelectorAll(".pull-quote")).toHaveLength(0);
  });

  it("renders a pin button when onTogglePin is provided", () => {
    const turn: MinervaTurn = {
      ...POIETES_TURN,
      citations: [{ n: 1, text: "x", src: "Republic 509d", chunk_id: "rep-509d" }],
    };
    const onTogglePin = vi.fn();
    const { container } = render(() => (
      <Thread messages={[turn]} thinking={false} marginNotes={true} onTogglePin={onTogglePin} />
    ));
    const pin = container.querySelector<HTMLElement>(".cite-pin")!;
    expect(pin).not.toBeNull();
    pin.click();
    expect(onTogglePin).toHaveBeenCalledWith("rep-509d");
  });

  it("shows an active pin glyph when the citation is pinned", () => {
    const turn: MinervaTurn = {
      ...POIETES_TURN,
      citations: [{ n: 1, text: "x", src: "Republic 509d", chunk_id: "rep-509d", pinned: true }],
    };
    const { container } = render(() => (
      <Thread messages={[turn]} thinking={false} marginNotes={true} onTogglePin={() => undefined} />
    ));
    const pin = container.querySelector(".cite-pin");
    expect(pin?.classList.contains("is-pinned")).toBe(true);
    expect(container.querySelector(".margin-note.is-pinned")).not.toBeNull();
  });

  it("omits the pin button when no onTogglePin handler is wired", () => {
    const turn: MinervaTurn = {
      ...POIETES_TURN,
      citations: [{ n: 1, text: "x", src: "Republic 509d", chunk_id: "rep-509d" }],
    };
    const { container } = render(() => (
      <Thread messages={[turn]} thinking={false} marginNotes={true} />
    ));
    expect(container.querySelector(".cite-pin")).toBeNull();
  });

  it("renders the dominant glyph (Π for Plato, Α for Aristotle)", () => {
    const aristoTurn: MinervaTurn = { ...POIETES_TURN, dominant: "A" };
    const { unmount } = render(() => (
      <Thread messages={[POIETES_TURN]} thinking={false} marginNotes={false} />
    ));
    expect(screen.getByText(/P dominant/i)).toBeInTheDocument();
    unmount();
    render(() => <Thread messages={[aristoTurn]} thinking={false} marginNotes={false} />);
    expect(screen.getByText(/A dominant/i)).toBeInTheDocument();
  });
});
