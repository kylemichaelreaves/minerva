import type { Meta, StoryObj } from "storybook-solidjs-vite";
import Thread from "~/Thread";
import type { MinervaTurn, UserTurn } from "~/utils/types";
import { withTheme } from "../../.storybook/decorators";

const USER: UserTurn = {
  role: "user",
  text: "Is justice the same in soul and city?",
  time: "11:41",
};

const POIETES: MinervaTurn = {
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

const meta: Meta<typeof Thread> = {
  title: "Chat/Thread",
  component: Thread,
  parameters: {
    layout: "padded",
  },
  args: {
    messages: [USER, POIETES],
    thinking: false,
    marginNotes: true,
  },
};
export default meta;

type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const Thinking: Story = {
  args: {
    messages: [USER],
    thinking: true,
  },
};

export const Dark: Story = {
  decorators: [withTheme("dark")],
  parameters: { backgrounds: { default: "paper-dark" } },
};
