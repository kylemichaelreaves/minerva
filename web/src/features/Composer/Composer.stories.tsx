import type { Meta, StoryObj } from "storybook-solidjs-vite";
import Composer from "~/features/Composer";

const meta: Meta<typeof Composer> = {
  title: "Chat/Composer",
  component: Composer,
  parameters: {
    layout: "padded",
  },
  args: {
    onSend: (text: string) => {
      console.debug("Composer onSend", text);
    },
  },
};
export default meta;

type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const Disabled: Story = {
  args: {
    disabled: true,
  },
  parameters: {
    docs: {
      description: {
        story: "Awaiting-reply state — controls grayed out, placeholder reads “Awaiting reply…”.",
      },
    },
  },
};

// Mobile composer (design 2a): pinned to the bottom edge, no border
// box, italic serif placeholder, kbd hint row hidden, 38pt outlined
// arrow send. The kbd hints disappear on mobile because virtual
// keyboards have no Enter-shortcut affordance to learn.
export const Mobile: Story = {
  parameters: {
    viewport: { defaultViewport: "iphone14" },
    layout: "fullscreen",
  },
};
