import type { Meta, StoryObj } from "storybook-solidjs-vite";
import MobileTopBar from "~/components/MobileTopBar";

// MobileTopBar lives at the top of every non-landing mobile surface.
// The three stories below mirror the three contextual right-actions
// App.tsx dispatches per route:
//   - Chat     → theme toggle (interactive, onAction wires up)
//   - Reader   → "Aa" type-controls placeholder (non-interactive
//                in v1; the chip will gain a sheet later)
//   - Refs /   → "Filters" affordance (non-interactive; the chip
//     Network    strip below carries the real filter actions)
//
// Locked at iPhone 14 viewport (390×844) so the layout reads the same
// as the wireframes' design 2a/3a/4a/5a topbar strip.

const meta: Meta<typeof MobileTopBar> = {
  title: "Shell/MobileTopBar",
  component: MobileTopBar,
  parameters: {
    layout: "fullscreen",
    viewport: { defaultViewport: "iphone14" },
  },
  args: {
    onOpenDrawer: () => {
      console.debug("MobileTopBar onOpenDrawer");
    },
  },
};
export default meta;

type Story = StoryObj<typeof meta>;

export const ChatWithTheme: Story = {
  args: {
    title: <em>Chat</em>,
    action: "☼",
    onAction: () => {
      console.debug("MobileTopBar onAction");
    },
  },
};

export const ReaderWithAa: Story = {
  args: {
    title: (
      <>
        Plato · <em>Republic</em>
      </>
    ),
    action: "Aa",
    onAction: () => {
      console.debug("MobileTopBar onAction — open reader settings");
    },
  },
};

export const RefsWithFilters: Story = {
  args: {
    title: "Cross-references",
    action: "Filters",
    onAction: () => {
      console.debug("MobileTopBar onAction — open filters");
    },
  },
};

export const NetworkWithFilters: Story = {
  args: {
    title: "Network",
    action: "Filters",
    onAction: () => {
      console.debug("MobileTopBar onAction — open filters");
    },
  },
};

export const TitleOnly: Story = {
  args: {
    title: "Citation network",
  },
};
