import { describe, it, expect, vi, beforeEach } from "vitest";
import { createSignal, flush } from "solid-js";
import { render, screen, waitFor } from "@solidjs/testing-library";
import { fireEvent } from "./helpers/settledFireEvent";
import type { ChunkContextResponse, MinervaTurn } from "~/utils/types";

const fetchChunkContext = vi.fn();
vi.mock("~/api/readerApi", () => ({
  fetchChunkContext: (...args: unknown[]): unknown => fetchChunkContext(...args),
}));

const { MinervaTurnView } = await import("~/Thread/components/MinervaTurnView");

type OpenReader = (workId: string, sourceLang: string | undefined, chunkId: string) => void;

const TURN: MinervaTurn = {
  role: "minerva",
  time: "09:00",
  dominant: "P",
  paragraphs: ["Justice is doing one's own [1]."],
  citations: [
    { n: 1, text: "Each part doing its own work.", src: "Rep. IV 441c", chunk_id: "rep-441c" },
  ],
};

const CONTEXT = {
  corpus: "plato",
  author: "Plato",
  work: "Republic",
  display_title: "Republic",
  lang: "grc",
  focus: { chunk_id: "rep-441c", text: "focus" },
  before: [],
  after: [],
} as unknown as ChunkContextResponse;

beforeEach(() => {
  fetchChunkContext.mockReset();
  fetchChunkContext.mockResolvedValue(CONTEXT);
});

describe("<MinervaTurnView /> open-in-reader handler reactivity", () => {
  it("invokes a handler supplied after mount, and the swapped-in one after that", async () => {
    const [handler, setHandler] = createSignal<OpenReader | undefined>(undefined);
    render(() => <MinervaTurnView msg={TURN} marginNotes onOpenReader={handler()} />);
    const link = () => screen.getByRole("button", { name: "Rep. IV 441c" });

    // No handler yet: the click is a no-op and fetches nothing.
    fireEvent.click(link());
    expect(fetchChunkContext).not.toHaveBeenCalled();

    const first = vi.fn<OpenReader>();
    setHandler(() => first);
    flush();
    fireEvent.click(link());
    await waitFor(() => {
      expect(first).toHaveBeenCalledWith("Republic", "grc", "rep-441c");
    });
    expect(fetchChunkContext).toHaveBeenCalledWith("rep-441c", 0);

    const second = vi.fn<OpenReader>();
    setHandler(() => second);
    flush();
    fireEvent.click(link());
    await waitFor(() => {
      expect(second).toHaveBeenCalledWith("Republic", "grc", "rep-441c");
    });
    expect(first).toHaveBeenCalledTimes(1);
  });

  it("opens straight from an already-expanded context without refetching", async () => {
    const onOpenReader = vi.fn<OpenReader>();
    render(() => <MinervaTurnView msg={TURN} marginNotes onOpenReader={onOpenReader} />);
    fireEvent.click(screen.getByRole("button", { name: "+ more" }));
    await screen.findByRole("button", { name: "− less" });
    // "− less" shows from the loading state on; wait for the context itself,
    // which is what "already expanded" means here. (Solid 2 commits the
    // ready write a microtask after the fetch resolves, so the toggle label
    // alone can win the race.)
    await screen.findByText("focus");
    expect(fetchChunkContext).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole("button", { name: "Rep. IV 441c" }));
    expect(onOpenReader).toHaveBeenCalledWith("Republic", "grc", "rep-441c");
    expect(fetchChunkContext).toHaveBeenCalledTimes(1);
  });

  it("enables the pull-quote locator link only once a handler exists", async () => {
    const [handler, setHandler] = createSignal<OpenReader | undefined>(undefined);
    render(() => <MinervaTurnView msg={TURN} marginNotes={false} onOpenReader={handler()} />);
    expect(screen.queryByRole("button", { name: "Rep. IV 441c" })).toBeNull();

    const onOpenReader = vi.fn<OpenReader>();
    setHandler(() => onOpenReader);
    flush();
    fireEvent.click(screen.getByRole("button", { name: "Rep. IV 441c" }));
    await waitFor(() => {
      expect(onOpenReader).toHaveBeenCalledWith("Republic", "grc", "rep-441c");
    });
  });
});
