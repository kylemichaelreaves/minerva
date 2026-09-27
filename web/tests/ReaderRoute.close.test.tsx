// `ReaderRoute`'s close exit (the back arrow): it seeds the chat scope with
// the work being read, then switches to chat mode. Escape (`onExit`) is
// covered end-to-end in readerEscape.test.tsx; this pins the other exit.

import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@solidjs/testing-library";

interface StubReaderProps {
  workSlug: string;
  onClose: () => void;
}

vi.mock("~/Reader", () => ({
  // Stands in for the Reader's own back arrow, which calls `onClose`.
  default: (props: StubReaderProps) => (
    <button type="button" onClick={() => props.onClose()}>
      back from {props.workSlug}
    </button>
  ),
}));

import { ReaderRoute } from "~/routes/ReaderRoute";
import type { RouteContextProps } from "~/routes/types";

const LOC = { workSlug: "das-kapital-band-i", sourceLang: "deu" };
const WORK = { work_id: 781, display_title: "Das Kapital, Band I" };

function mount(currentWork: typeof WORK | null) {
  const setChatScope = vi.fn();
  const switchMode = vi.fn().mockResolvedValue(undefined);
  const resolveWork = vi.fn().mockResolvedValue(WORK);
  const props = {
    routing: {
      route: () => ({ kind: "reader", ...LOC }),
      navigate: vi.fn(),
    },
    conversations: { setChatScope, chatScope: () => null },
    reader: {
      readerWork: () => LOC,
      retainedWork: () => null,
      currentWork: () => currentWork,
      resolveWork,
      setOpenTermId: vi.fn(),
      mode: () => "reader",
      switchMode,
    },
  } as unknown as RouteContextProps;
  const utils = render(() => <ReaderRoute {...props} />);
  return { setChatScope, switchMode, resolveWork, ...utils };
}

describe("<ReaderRoute /> onClose", () => {
  it("seeds the chat scope with the current work and switches to chat", () => {
    const { setChatScope, switchMode, resolveWork } = mount(WORK);

    fireEvent.click(screen.getByRole("button", { name: "back from das-kapital-band-i" }));

    expect(setChatScope).toHaveBeenCalledWith({ workId: 781, title: "Das Kapital, Band I" });
    expect(switchMode).toHaveBeenCalledWith("chat");
    // Warm list: nothing to resolve late.
    expect(resolveWork).not.toHaveBeenCalled();
  });

  it("switches immediately and fills the scope late when the works list is cold", async () => {
    const { setChatScope, switchMode, resolveWork } = mount(null);

    fireEvent.click(screen.getByRole("button", { name: "back from das-kapital-band-i" }));

    // The exit does not wait on the network.
    expect(switchMode).toHaveBeenCalledWith("chat");
    expect(setChatScope).toHaveBeenNthCalledWith(1, null);
    expect(resolveWork).toHaveBeenCalledWith(LOC);
    await vi.waitFor(() => {
      expect(setChatScope).toHaveBeenLastCalledWith({
        workId: 781,
        title: "Das Kapital, Band I",
      });
    });
  });
});
