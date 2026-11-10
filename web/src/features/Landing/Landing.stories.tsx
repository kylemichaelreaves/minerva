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

// Mobile (iPhone 14, 390×844). The hero collapses to the monogram, the
// composer pills wrap to two rows, and the doors (Read / Citations /
// Network / Concordance / Observability) sit under the composer as a
// 2-column grid, since the header has no room for them. Design 1a (#360)
// put the Atlas at the top here; the landing redesign moved the Atlas to the
// Network page and the doors into the desktop header. The redesign's mocks
// live on the "Minerva landing redesign" Claude Design canvas (option B).
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
