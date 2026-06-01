import type { Meta, StoryObj } from "storybook-solidjs-vite";
import { RefsEmptyState } from "~/Refs/components/RefsEmptyState";

const meta: Meta<typeof RefsEmptyState> = {
  title: "Refs/RefsEmptyState",
  component: RefsEmptyState,
  parameters: {
    layout: "padded",
  },
  args: {
    onClear: () => {
      console.debug("RefsEmptyState onClear");
    },
  },
  decorators: [
    (Story) => (
      <div style={{ "max-width": "480px" }}>
        <Story />
      </div>
    ),
  ],
};
export default meta;

type Story = StoryObj<typeof meta>;

export const NoIndex: Story = {
  args: {
    hasFilters: false,
  },
};

export const NoMatches: Story = {
  args: {
    hasFilters: true,
  },
};
