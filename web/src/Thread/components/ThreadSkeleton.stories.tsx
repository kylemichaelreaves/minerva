import type { Meta, StoryObj } from "storybook-solidjs-vite";
import { ThreadSkeleton } from "~/Thread/components/ThreadSkeleton";

const meta: Meta<typeof ThreadSkeleton> = {
  title: "Chat/ThreadSkeleton",
  component: ThreadSkeleton,
  parameters: {
    layout: "padded",
  },
};
export default meta;

type Story = StoryObj<typeof meta>;

export const Default: Story = {};
