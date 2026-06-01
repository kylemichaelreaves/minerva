import type { Meta, StoryObj } from "storybook-solidjs-vite";
import { UserTurnView } from "~/Thread/components/UserTurnView";
import type { UserTurn } from "~/utils/types";

const SAMPLE: UserTurn = {
  role: "user",
  text: "Is justice the same in soul and city?",
  time: "11:41",
};

const meta: Meta<typeof UserTurnView> = {
  title: "Chat/UserTurn",
  component: UserTurnView,
  parameters: {
    layout: "padded",
  },
  args: {
    msg: SAMPLE,
  },
};
export default meta;

type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const LongQuestion: Story = {
  args: {
    msg: {
      ...SAMPLE,
      text:
        "How does Aristotle's distinction between phantasia and noesis in De anima III.7 " +
        "bear on Aquinas's account of the intellect's operation without phantasms?",
    },
  },
};
