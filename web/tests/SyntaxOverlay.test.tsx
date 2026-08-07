import { fireEvent, render, screen } from "@solidjs/testing-library";
import { createSignal } from "solid-js";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ChunkSyntax, SyntaxToken } from "~/api/syntaxApi";
import { SyntaxOverlay } from "~/Syntax";

// What survives a chunk change.
//
// `SyntaxRoute` re-fetches instead of re-mounting when the chunk changes, so
// every signal in the overlay outlives the passage it was set on. State that
// does not honour that reads as a broken parse: a sentence index the new
// chunk does not have renders "No syntax for this passage" over a chunk that
// parsed perfectly well (#141).

const tok = (id: number, form: string, head: number | null, deprel: string): SyntaxToken => ({
  id,
  form,
  lemma: null,
  upos: null,
  xpos: null,
  feats: null,
  misc: null,
  head,
  deprel,
  start: id,
  end: id + 1,
  corrected: false,
});

/** Three sentences, so the reader can be somewhere other than the first. */
const long: ChunkSyntax = {
  chunk_id: "long",
  sentences: [
    { sent_ord: 0, tokens: [tok(1, "erste", 0, "root")] },
    { sent_ord: 1, tokens: [tok(1, "zweite", 0, "root")] },
    { sent_ord: 2, tokens: [tok(1, "dritte", 0, "root")] },
  ],
  corrections: [],
};

/** One sentence — so sentence 3 does not exist here. */
const short: ChunkSyntax = {
  chunk_id: "short",
  sentences: [{ sent_ord: 0, tokens: [tok(1, "allein", 0, "root")] }],
  corrections: [],
};

const chunks: Record<string, ChunkSyntax> = { long, short };

vi.mock("~/api/syntaxApi", async (importOriginal) => ({
  ...(await importOriginal<typeof import("~/api/syntaxApi")>()),
  fetchChunkSyntax: vi.fn((id: string) => {
    const doc = chunks[id];
    return doc
      ? Promise.resolve(doc)
      : Promise.reject(new Error(`no fixture for ${id}`));
  }),
}));

/** Mount the overlay on a chunk the test can change under it. */
function mount(): { goTo: (id: string) => void } {
  const [chunkId, setChunkId] = createSignal("long");
  render(() => <SyntaxOverlay chunkId={chunkId()} onClose={() => undefined} />);
  return {
    goTo: (id) => {
      setChunkId(id);
    },
  };
}

/** A token's form appears twice — once in the row, once in the hidden probe. */
const showsToken = (form: string): boolean => screen.queryAllByText(form).length > 0;

describe("<SyntaxOverlay /> across a chunk change", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("does not strand the reader on a sentence the new chunk does not have", async () => {
    const { goTo } = mount();
    await screen.findAllByText("erste");

    fireEvent.keyDown(window, { key: "ArrowDown" });
    fireEvent.keyDown(window, { key: "ArrowDown" });
    expect(showsToken("dritte")).toBe(true);

    goTo("short");
    await screen.findAllByText("allein");

    // Before the fix `sentOrd` was still 2, no sentence matched, and the
    // overlay reported a parse failure for a chunk that parsed fine.
    expect(screen.queryByText("No syntax for this passage.")).toBeNull();
  });

  it("closes the relation picker left open on the previous chunk", async () => {
    const { goTo } = mount();
    await screen.findAllByText("erste");

    fireEvent.keyDown(window, { key: "ArrowRight" }); // focus the first token
    fireEvent.keyDown(window, { key: "l" }); // open the picker on it
    expect(screen.queryByLabelText("Filter relations")).not.toBeNull();

    goTo("short");
    await screen.findAllByText("allein");

    // The picker names the word it is relabelling. Left open, it is offering
    // to relabel a word that is no longer on screen.
    expect(screen.queryByLabelText("Filter relations")).toBeNull();
  });

  it("closes the part-of-speech picker left open on the previous chunk", async () => {
    // Same hazard as the relation picker: `picker` is chunk-scoped, and one
    // signal holds both modes, so this is the other half of that guard (#253).
    const { goTo } = mount();
    await screen.findAllByText("erste");

    fireEvent.keyDown(window, { key: "ArrowRight" });
    fireEvent.keyDown(window, { key: "p" });
    expect(screen.queryByLabelText("Filter parts of speech")).not.toBeNull();

    goTo("short");
    await screen.findAllByText("allein");

    expect(screen.queryByLabelText("Filter parts of speech")).toBeNull();
  });

  it("opens only one picker at a time", async () => {
    // `picker` is a single mode rather than a boolean per picker, so the two
    // cannot both be mounted over the same token.
    mount();
    await screen.findAllByText("erste");

    fireEvent.keyDown(window, { key: "ArrowRight" });
    fireEvent.keyDown(window, { key: "l" });
    expect(screen.queryByLabelText("Filter relations")).not.toBeNull();
    expect(screen.queryByLabelText("Filter parts of speech")).toBeNull();

    // The overlay ignores shortcuts while a picker is open, so close it first —
    // which is itself the behaviour that keeps the two from stacking.
    fireEvent.keyDown(screen.getByLabelText("Filter relations"), { key: "Escape" });
    fireEvent.keyDown(window, { key: "p" });

    expect(screen.queryByLabelText("Filter parts of speech")).not.toBeNull();
    expect(screen.queryByLabelText("Filter relations")).toBeNull();
  });

  it("shows the server's own reason when it refuses the chunk", async () => {
    // The 400 `load_or_parse` raises for a non-German chunk (#231, #235).
    const { fetchChunkSyntax } = await import("~/api/syntaxApi");
    vi.mocked(fetchChunkSyntax).mockRejectedValueOnce(
      new (await import("~/api/client")).ApiError(
        "syntax parsing is deu-only; chunk 'rep-509d' is 'eng'",
        400,
      ),
    );

    render(() => <SyntaxOverlay chunkId="rep-509d" onClose={() => undefined} />);

    expect(
      await screen.findByText("syntax parsing is deu-only; chunk 'rep-509d' is 'eng'"),
    ).toBeTruthy();
  });

  it("reaches an error state at all when the fetch fails", async () => {
    // #235 assumed a failed GET rendered the generic line. It rendered
    // nothing: the header and footer read the tree unconditionally, `doc()`
    // throws on an errored resource, and the throw abandoned the update that
    // would have settled it — so the overlay sat on "Parsing…" indefinitely,
    // for a 400 and a 502 alike.
    const { fetchChunkSyntax } = await import("~/api/syntaxApi");
    vi.mocked(fetchChunkSyntax).mockRejectedValueOnce(
      new (await import("~/api/client")).ApiError("502 Bad Gateway", 502),
    );

    render(() => <SyntaxOverlay chunkId="whatever" onClose={() => undefined} />);

    expect(await screen.findByText("Could not load syntax for this passage.")).toBeTruthy();
    expect(screen.queryByText("Parsing…")).toBeNull();
  });
});
