import type { Meta, StoryObj } from "storybook-solidjs-vite";
import { SourceWithHighlight } from "~/features/Refs/components/SourceWithHighlight";

const TEXT =
  "Tertia via est sumpta ex possibili et necessario. Philosophus probat hoc in XII Metaphysicae.";

const meta: Meta<typeof SourceWithHighlight> = {
  title: "Refs/SourceWithHighlight",
  component: SourceWithHighlight,
  parameters: {
    layout: "padded",
  },
  args: {
    text: TEXT,
    start: 24,
    end: 35,
  },
  decorators: [
    (Story) => (
      <blockquote class="review-source-text" style={{ "max-width": "560px" }}>
        <Story />
      </blockquote>
    ),
  ],
};
export default meta;

type Story = StoryObj<typeof meta>;

export const Highlighted: Story = {};

export const NoHighlight: Story = {
  args: {
    start: null,
    end: null,
  },
};

export const InvalidSpan: Story = {
  args: {
    start: 100,
    end: 200,
  },
  parameters: {
    docs: {
      description: {
        story: "Out-of-range span falls back to plain text with no mark.",
      },
    },
  },
};
