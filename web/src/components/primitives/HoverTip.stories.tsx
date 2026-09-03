// Stories for HoverTip — the paper-popover tooltip used by inline
// citations and Greek-romanization hovers. The trigger element is
// whatever's passed as children; we render an inline span as the
// trigger in each story. To see the tip, hover the trigger.

import type { Meta, StoryObj } from "storybook-solidjs-vite";
import { HoverTip } from "~/components/HoverTip";

const meta: Meta<typeof HoverTip> = {
  title: "Primitives/HoverTip",
  component: HoverTip,
};
export default meta;

type Story = StoryObj<typeof meta>;

export const RomanizationTip: Story = {
  args: {
    body: "phantasia · imagination, appearance",
    children: "φαντασία",
  },
  parameters: {
    docs: {
      description: {
        story:
          "Greek word with romanization + gloss on hover. The pattern " +
          "the Reader uses for non-curated Greek words.",
      },
    },
  },
};

export const CitationTip: Story = {
  args: {
    label: "PLATO · REPUBLIC 509D",
    body: "The Good is beyond being in dignity and power.",
    children: "[1]",
  },
  parameters: {
    docs: {
      description: {
        story:
          "Citation hover from a chat response. The small-caps eyebrow " +
          "shows the locator; the body shows the supporting quote. " +
          "Used by `renderMarkdown.tsx`.",
      },
    },
  },
};

export const InlineChip: Story = {
  args: {
    body: "Bekker 1098b22 — the Nicomachean Ethics' function argument.",
    children: <span style={{ "text-decoration": "underline dotted" }}>ergon</span>,
  },
};
