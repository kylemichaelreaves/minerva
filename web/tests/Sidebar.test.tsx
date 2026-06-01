import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@solidjs/testing-library";
import Sidebar from "~/Sidebar";
import type { HistoryItem, Work } from "~/utils/types";

function makeWork(author: string, work: string, lang = "grc"): Work {
  return {
    corpus: author.toLowerCase(),
    author,
    work,
    lang,
    chunks: 1,
    display_title: work,
  };
}

const HISTORY: HistoryItem[] = [
  { id: "a", title: "On the divided line", meta: "Today", dominant: "P" },
  { id: "b", title: "Phronesis vs sophia", meta: "Yesterday", dominant: "A" },
  { id: "c", title: "Sittlichkeit", meta: "2d ago", dominant: "H" },
  { id: "d", title: "Synthetic a priori", meta: "Last week", dominant: "K" },
  { id: "e", title: "Phaedo", meta: "April", dominant: "P" },
];

function renderSidebar(
  overrides: Partial<{
    history: HistoryItem[];
    activeId: string | null;
    onRequestDelete: (item: HistoryItem) => void;
    mode: "chat" | "reader";
  }> = {},
) {
  const onPick = vi.fn();
  const onNew = vi.fn();
  const onToggle = vi.fn();
  const onRequestDelete = overrides.onRequestDelete ?? vi.fn();
  const utils = render(() => (
    <Sidebar
      collapsed={false}
      onToggle={onToggle}
      history={overrides.history ?? HISTORY}
      activeId={overrides.activeId ?? null}
      onPick={onPick}
      onNew={onNew}
      onRequestDelete={onRequestDelete}
      mode={overrides.mode ?? "chat"}
    />
  ));
  return { onPick, onNew, onToggle, onRequestDelete, ...utils };
}

describe("<Sidebar /> — delete affordance", () => {
  it("renders a delete button for every history item when handler is provided", () => {
    const { container } = renderSidebar();
    const buttons = container.querySelectorAll(".history-delete");
    expect(buttons).toHaveLength(HISTORY.length);
  });

  it("omits the delete button entirely when no handler is provided", () => {
    const onPick = vi.fn();
    const onNew = vi.fn();
    const onToggle = vi.fn();
    const { container } = render(() => (
      <Sidebar
        collapsed={false}
        onToggle={onToggle}
        history={HISTORY}
        activeId={null}
        onPick={onPick}
        onNew={onNew}
        mode="chat"
      />
    ));
    expect(container.querySelectorAll(".history-delete")).toHaveLength(0);
  });

  it("clicking the delete button calls onRequestDelete with the item", () => {
    const { onRequestDelete, container } = renderSidebar();
    const firstDelete = container.querySelector(".history-delete")!;
    fireEvent.click(firstDelete);
    expect(onRequestDelete).toHaveBeenCalledTimes(1);
    expect(onRequestDelete).toHaveBeenCalledWith(HISTORY[0]);
  });

  it("clicking the delete button does NOT also pick the conversation", () => {
    const { onRequestDelete, onPick, container } = renderSidebar();
    const firstDelete = container.querySelector(".history-delete")!;
    fireEvent.click(firstDelete);
    expect(onRequestDelete).toHaveBeenCalledTimes(1);
    expect(onPick).not.toHaveBeenCalled();
  });

  it("clicking the conversation row still calls onPick", () => {
    const { onPick, onRequestDelete, container } = renderSidebar();
    // The row is the .history-item button (the trash button shares part of
    // its aria-label, so role-name lookup is ambiguous — query the row directly).
    const row = container.querySelectorAll(".history-item")[0] as HTMLElement;
    fireEvent.click(row);
    expect(onPick).toHaveBeenCalledWith("a");
    expect(onRequestDelete).not.toHaveBeenCalled();
  });

  it("delete button has an aria-label naming the conversation it targets", () => {
    renderSidebar();
    expect(
      screen.getByRole("button", { name: /Delete conversation: On the divided line/ }),
    ).toBeInTheDocument();
  });

  it("does not render a hardcoded identity footer", () => {
    const { container } = renderSidebar();
    expect(container.querySelector(".sidebar-foot")).toBeNull();
  });

  it("marks the active item via .history-item-wrap.active", () => {
    const { container } = renderSidebar({ activeId: "b" });
    const wraps = container.querySelectorAll(".history-item-wrap");
    expect(wraps).toHaveLength(HISTORY.length);
    const active = container.querySelectorAll(".history-item-wrap.active");
    expect(active).toHaveLength(1);
  });

  it("renders Recent and Earlier section labels when both have items", () => {
    renderSidebar();
    expect(screen.getByText("Recent")).toBeInTheDocument();
    expect(screen.getByText("Earlier")).toBeInTheDocument();
  });

  it("hides the Earlier label when there are 4 or fewer conversations", () => {
    renderSidebar({ history: HISTORY.slice(0, 3) });
    expect(screen.getByText("Recent")).toBeInTheDocument();
    expect(screen.queryByText("Earlier")).toBeNull();
  });

  it("hides both labels when the history is empty", () => {
    renderSidebar({ history: [] });
    expect(screen.queryByText("Recent")).toBeNull();
    expect(screen.queryByText("Earlier")).toBeNull();
  });
});

// Mode-tab tests removed — the Chat/Read/Refs/Network strip is no
// longer rendered. Mode switching happens via the landing page's
// mode entry row; see Landing.test.tsx.

describe("<Sidebar /> — works list ordering", () => {
  // Regression test for the duplicate-AUTHOR_ORDER bug. The Sidebar
  // used to maintain its own hand-coded ordering table that didn't
  // include the Pre-Socratics, so adding them to the corpus landed
  // them AFTER Hegel via the "unknown authors fall through" branch.
  // The fix is to trust the backend's chronological order: Map
  // iteration is insertion-order, so first-appearance grouping
  // preserves whatever order /api/works returned.
  it("preserves the order in which authors first appear in props.works", () => {
    // Simulate a backend response with the canonical chronological
    // order — Pre-Socratics between Homer and Plato.
    const works: Work[] = [
      makeWork("Homer", "Iliad"),
      makeWork("Heraclitus", "Fragments (DK 22)"),
      makeWork("Plato", "Republic"),
      makeWork("Aristotle", "Nicomachean Ethics"),
      makeWork("Hegel", "Phenomenology of Spirit", "deu"),
    ];
    const utils = render(() => (
      <Sidebar
        collapsed={false}
        onToggle={() => undefined}
        history={[]}
        activeId={null}
        onPick={() => undefined}
        onNew={() => undefined}
        mode="reader"
        works={works}
      />
    ));
    // Toggle buttons render as `.history-label-toggle` with children
    // [caret, author-name span (no class), count badge]; grab the
    // middle child's text content to read the author name.
    const headers = Array.from(
      utils.container.querySelectorAll(".history-label-toggle"),
    ).map((el) => el.children[1].textContent.trim());
    expect(headers).toEqual([
      "Homer",
      "Heraclitus",
      "Plato",
      "Aristotle",
      "Hegel",
    ]);
  });

  it("groups consecutive works by the same author into one section", () => {
    const works: Work[] = [
      makeWork("Plato", "Republic"),
      makeWork("Plato", "Phaedo"),
      makeWork("Plato", "Symposium"),
      makeWork("Aristotle", "Nicomachean Ethics"),
    ];
    const utils = render(() => (
      <Sidebar
        collapsed={false}
        onToggle={() => undefined}
        history={[]}
        activeId={null}
        onPick={() => undefined}
        onNew={() => undefined}
        mode="reader"
        works={works}
      />
    ));
    // Toggle buttons render as `.history-label-toggle` with children
    // [caret, author-name span (no class), count badge]; grab the
    // middle child's text content to read the author name.
    const headers = Array.from(
      utils.container.querySelectorAll(".history-label-toggle"),
    ).map((el) => el.children[1].textContent.trim());
    expect(headers).toEqual(["Plato", "Aristotle"]);
  });
});
