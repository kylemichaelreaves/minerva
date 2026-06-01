import type { Meta, StoryObj } from "storybook-solidjs-vite";
import { SelectionToolbar } from "~/Reader/components/SelectionToolbar";
import { withTheme } from "../../../.storybook/decorators";

const ANCHOR = {
  rect: new DOMRect(200, 280, 120, 22),
};

const meta: Meta<typeof SelectionToolbar> = {
  title: "Reader/SelectionToolbar",
  component: SelectionToolbar,
  parameters: {
    layout: "fullscreen",
  },
  args: {
    anchor: ANCHOR,
    count: "4 words · 22 chars",
    singleWord: false,
    onTranslate: () => {
      console.debug("SelectionToolbar onTranslate");
    },
    onCopy: () => {
      console.debug("SelectionToolbar onCopy");
    },
    onDismiss: () => {
      console.debug("SelectionToolbar onDismiss");
    },
  },
};
export default meta;

type Story = StoryObj<typeof meta>;

export const MultiWord: Story = {};

export const SingleWord: Story = {
  args: {
    singleWord: true,
    count: "1 word · 8 chars",
    onLookup: () => {
      console.debug("SelectionToolbar onLookup");
    },
  },
};

export const Dark: Story = {
  decorators: [withTheme("dark")],
  parameters: { backgrounds: { default: "paper-dark" } },
};
