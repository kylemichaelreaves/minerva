import type { Meta, StoryObj } from "storybook-solidjs-vite";
import { MinervaTurnView } from "~/Thread/components/MinervaTurnView";
import type { MinervaTurn } from "~/utils/types";
import { withTheme } from "../../../.storybook/decorators";

const POIETES_TURN: MinervaTurn = {
  role: "minerva",
  time: "11:42",
  dominant: "P",
  paragraphs: [
    "The analogy is the architecture of the entire argument [1].",
    "But the structure is doing real work [2].",
  ],
  citations: [
    {
      n: 1,
      text: "Soul read in larger letters.",
      src: "Republic II, 368d",
      chunk_id: "abc1234567890abc1234",
    },
    {
      n: 2,
      text: "Each part doing its own work.",
      src: "Republic IV, 441c",
      chunk_id: "def1234567890def1234",
      speaker: "Socrates",
    },
  ],
};

const meta: Meta<typeof MinervaTurnView> = {
  title: "Chat/MinervaTurn",
  component: MinervaTurnView,
  parameters: {
    layout: "padded",
  },
  args: {
    msg: POIETES_TURN,
    marginNotes: true,
    onOpenReader: (workId: string, lang: string | undefined, chunkId: string) => {
      console.debug("onOpenReader", workId, lang, chunkId);
    },
  },
};
export default meta;

type Story = StoryObj<typeof meta>;

export const WithMarginNotes: Story = {};

export const PullQuotes: Story = {
  args: {
    marginNotes: false,
  },
  parameters: {
    docs: {
      description: {
        story: "When marginNotes=false, citations render as pull-quotes below the body.",
      },
    },
  },
};

export const Streaming: Story = {
  args: {
    msg: {
      role: "minerva",
      time: "12:00",
      dominant: "P",
      paragraphs: [],
      citations: [{ n: 1, text: "passage", src: "Republic 509d" }],
      streaming: true,
      streamText: "The cave allegory suggests that ",
    },
  },
};

export const Abstained: Story = {
  args: {
    msg: {
      ...POIETES_TURN,
      abstained: true,
    },
  },
};

export const AristotleDominant: Story = {
  args: {
    msg: {
      ...POIETES_TURN,
      dominant: "A",
    },
  },
};

export const Dark: Story = {
  decorators: [withTheme("dark")],
  parameters: { backgrounds: { default: "paper-dark" } },
};
