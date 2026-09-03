// Story for the three-dot bouncing loader. Trivial component, used
// here to validate that the global CSS (which owns the `.dots`
// keyframes) is loaded by `.storybook/preview.tsx`. If the dots are
// stationary in the canvas, the styles.css import is wrong.

import type { Meta, StoryObj } from "storybook-solidjs-vite";
import { LoadingDots } from "~/components/primitives/LoadingDots";

const meta: Meta<typeof LoadingDots> = {
  title: "Primitives/LoadingDots",
  component: LoadingDots,
};
export default meta;

type Story = StoryObj<typeof meta>;

export const Default: Story = {};
