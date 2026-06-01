import type { Meta, StoryObj } from "storybook-solidjs-vite";
import { MarginNote } from "~/Thread/components/MarginNote";
import type { Citation } from "~/utils/types";

const CITATION: Citation = {
  n: 1,
  text: "Soul read in larger letters.",
  src: "Republic II, 368d",
  chunk_id: "abc1234567890abc1234",
  speaker: "Socrates",
};

const meta: Meta<typeof MarginNote> = {
  title: "Chat/MarginNote",
  component: MarginNote,
  parameters: {
    layout: "padded",
  },
  args: {
    citation: CITATION,
    state: undefined,
    onToggleExpand: () => {
      console.debug("MarginNote onToggleExpand");
    },
    onOpenReader: () => {
      console.debug("MarginNote onOpenReader");
    },
    onTogglePin: (chunkId: string) => {
      console.debug("MarginNote onTogglePin", chunkId);
    },
    pinnedChunkIds: [],
  },
};
export default meta;

type Story = StoryObj<typeof meta>;

export const Collapsed: Story = {};

export const Loading: Story = {
  args: {
    state: { status: "loading" },
  },
};

const chunk = (text: string, ord: number) => ({
  chunk_id: `chunk-${ord}`,
  section: "II.368d",
  book: null,
  page: null,
  speaker: "Socrates",
  text,
  ord,
});

export const Expanded: Story = {
  args: {
    state: {
      status: "ready",
      context: {
        corpus: "greek",
        author: "Plato",
        work: "*politei/a",
        display_title: "Πολιτεία",
        lang: "grc",
        before: [chunk("And so, Glaucon, we have arrived at the image of the soul.", 1)],
        focus: chunk("We must read the soul in larger letters, as it were.", 2),
        after: [chunk("What is true of the one will be true of the other.", 3)],
      },
    },
  },
};

export const Error: Story = {
  args: {
    state: { status: "error", message: "network timeout" },
  },
};

export const Pinned: Story = {
  args: {
    citation: { ...CITATION, pinned: true },
    pinnedChunkIds: ["abc1234567890abc1234"],
  },
};
