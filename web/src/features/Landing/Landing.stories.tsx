import type { Meta, StoryObj } from "storybook-solidjs-vite";
import Landing from "~/features/Landing";
import { withTheme } from "../../../.storybook/decorators";

const meta: Meta<typeof Landing> = {
  title: "Chat/Landing",
  component: Landing,
  parameters: {
    layout: "fullscreen",
  },
  args: {
    onSubmit: (text: string) => {
      console.debug("Landing onSubmit", text);
    },
  },
};
export default meta;

type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const Dark: Story = {
  decorators: [withTheme("dark")],
  parameters: { backgrounds: { default: "paper-dark" } },
};

// Mobile (iPhone 14, 390×844). Atlas moves to TOP per design 1a, the
// hero collapses to the Π monogram, the composer pills wrap to two
// rows, and the three-mode entry stacks vertically. Those four changes
// are the whole of what "design 1a" specified for this surface, recorded
// here because the wireframe file they came from was a local scratch file
// and never entered the repository — this story is the design of record
// (#360).
export const Mobile: Story = {
  parameters: {
    viewport: { defaultViewport: "iphone14" },
  },
};

// 375×812 narrow check per design 1b — paraphrases shorten on pills
// 2 and 4, monogram shrinks 52→44, gutters 20→16. No layout breaks.
export const MobileNarrow: Story = {
  parameters: {
    viewport: { defaultViewport: "iphoneSE" },
  },
};
