import type { Meta, StoryObj } from "storybook-solidjs-vite";
import Topbar from "~/components/Topbar";
import { withTheme } from "../../.storybook/decorators";

const meta: Meta<typeof Topbar> = {
  title: "Shell/Topbar",
  component: Topbar,
  parameters: {
    layout: "fullscreen",
  },
  args: {
    scrolled: false,
    sidebarCollapsed: false,
    onToggleSidebar: () => {
      console.debug("Topbar onToggleSidebar");
    },
    theme: "light",
    onToggleTheme: () => {
      console.debug("Topbar onToggleTheme");
    },
    conversationTitle: "On the divided line",
  },
};
export default meta;

type Story = StoryObj<typeof meta>;

export const WithTitle: Story = {};

export const Untitled: Story = {
  args: {
    conversationTitle: null,
  },
};

export const CollapsedSidebar: Story = {
  args: {
    sidebarCollapsed: true,
    scrolled: true,
  },
};

export const Dark: Story = {
  args: {
    theme: "dark",
  },
  decorators: [withTheme("dark")],
  parameters: { backgrounds: { default: "paper-dark" } },
};
