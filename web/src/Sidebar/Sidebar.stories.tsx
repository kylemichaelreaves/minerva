import type { Meta, StoryObj } from "storybook-solidjs-vite";
import type { JSX } from "solid-js";
import Sidebar from "~/Sidebar";
import type { HistoryItem, Work } from "~/utils/types";
import { withTheme } from "../../.storybook/decorators";

const HISTORY: HistoryItem[] = [
  { id: "a", title: "On the divided line", meta: "Today", dominant: "P" },
  { id: "b", title: "Phronesis vs sophia", meta: "Yesterday", dominant: "A" },
  { id: "c", title: "Sittlichkeit", meta: "2d ago", dominant: "H" },
  { id: "d", title: "Synthetic a priori", meta: "Last week", dominant: "K" },
  { id: "e", title: "Phaedo", meta: "April", dominant: "P" },
];

const WORKS: Work[] = [
  {
    work_id: 1,
    corpus: "greek",
    author: "Plato",
    work: "*politei/a",
    display_title: "Πολιτεία",
    lang: "grc",
    chunks: 412,
  },
  {
    work_id: 1,
    corpus: "greek",
    author: "Plato",
    work: "*politei/a",
    display_title: "Republic",
    lang: "eng",
    chunks: 380,
  },
  {
    work_id: 2,
    corpus: "greek",
    author: "Aristotle",
    work: "de anima",
    display_title: "Περὶ Ψυχῆς",
    lang: "grc",
    chunks: 156,
  },
  {
    work_id: 3,
    corpus: "german",
    author: "Hegel",
    work: "Phänomenologie des Geistes",
    display_title: "Phänomenologie des Geistes",
    lang: "deu",
    chunks: 890,
  },
];

const noop = (): void => {
  /* stories don't push routes */
};

const meta: Meta<typeof Sidebar> = {
  title: "Shell/Sidebar",
  component: Sidebar,
  parameters: {
    layout: "fullscreen",
  },
  args: {
    collapsed: false,
    onToggle: noop,
    history: HISTORY,
    activeId: "a",
    onPick: (id: string) => {
      console.debug("Sidebar onPick", id);
    },
    onNew: noop,
    onRequestDelete: (item: HistoryItem) => {
      console.debug("Sidebar onRequestDelete", item.id);
    },
    mode: "chat",
    works: WORKS,
    activeWorkId: "*politei/a",
    activeWorkLang: "grc",
    onPickWork: (w: Work) => {
      console.debug("Sidebar onPickWork", w.work);
    },
  },
};
export default meta;

type Story = StoryObj<typeof meta>;

export const ChatMode: Story = {};

export const ReaderMode: Story = {
  args: {
    mode: "reader",
    activeId: null,
  },
};

export const Collapsed: Story = {
  args: {
    collapsed: true,
  },
};

export const Dark: Story = {
  decorators: [withTheme("dark")],
  parameters: { backgrounds: { default: "paper-dark" } },
};

// Mobile (iPhone 14, 390×844). Sidebar slides in as a left-edge drawer
// per design 2b. The ✕ close affordance appears in the drawer header
// (passed via onCloseMobile). The decorator below flips
// body[data-mobile-drawer="open"] so the drawer is in its slid-in
// state, which is the only useful render mode at mobile width.
export const Mobile: Story = {
  args: {
    onCloseMobile: () => {
      console.debug("Sidebar onCloseMobile");
    },
  },
  parameters: {
    viewport: { defaultViewport: "iphone14" },
  },
  decorators: [
    (Story: () => JSX.Element) => {
      document.body.setAttribute("data-mobile-drawer", "open");
      return Story();
    },
  ],
};

export const MobileReaderTree: Story = {
  args: {
    mode: "reader",
    activeId: null,
    onCloseMobile: () => {
      console.debug("Sidebar onCloseMobile");
    },
  },
  parameters: {
    viewport: { defaultViewport: "iphone14" },
  },
  decorators: [
    (Story: () => JSX.Element) => {
      document.body.setAttribute("data-mobile-drawer", "open");
      return Story();
    },
  ],
};
