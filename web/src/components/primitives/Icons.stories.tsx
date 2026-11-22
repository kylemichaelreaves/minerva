import type { Component } from "solid-js";
import type { JSX } from "@solidjs/web";
import { For } from "solid-js";
import type { Meta, StoryObj } from "storybook-solidjs-vite";
import {
  MoonIcon,
  PlusIcon,
  SendIcon,
  SidebarIcon,
  SunIcon,
  TrashIcon,
} from "~/components/primitives/Icons";

const ICONS: { label: string; Icon: (props: JSX.SvgSVGAttributes<SVGSVGElement>) => JSX.Element }[] =
  [
    { label: "Sidebar", Icon: SidebarIcon },
    { label: "Plus", Icon: PlusIcon },
    { label: "Sun", Icon: SunIcon },
    { label: "Moon", Icon: MoonIcon },
    { label: "Send", Icon: SendIcon },
    { label: "Trash", Icon: TrashIcon },
  ];

const IconGrid: Component = () => (
  <div
    style={{
      display: "grid",
      "grid-template-columns": "repeat(3, 1fr)",
      gap: "24px",
      padding: "16px",
    }}
  >
    <For each={ICONS}>
      {({ label, Icon }) => (
        <div style={{ "text-align": "center" }}>
          <button class="icon-btn" aria-label={label}>
            <Icon />
          </button>
          <div style={{ "margin-top": "8px", "font-size": "12px", color: "var(--ink-faint)" }}>
            {label}
          </div>
        </div>
      )}
    </For>
  </div>
);

const meta: Meta = {
  title: "Primitives/Icons",
  component: IconGrid,
};
export default meta;

type Story = StoryObj<typeof meta>;

export const All: Story = {
  render: () => <IconGrid />,
};
