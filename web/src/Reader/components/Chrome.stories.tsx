import type { Meta, StoryObj } from "storybook-solidjs-vite";
import { Chrome } from "~/Reader/components/Chrome";
import type { TargetLang, WorkRange } from "~/utils/types";
import { withTheme } from "../../../.storybook/decorators";

const META: WorkRange = {
  work_id: 81,
  corpus: "greek",
  author: "Plato",
  work: "*politei/a",
  display_title: "Πολιτεία",
  lang: "grc",
  total: 412,
  offset: 0,
  limit: 40,
  edition: "e81",
  editions: [
    { selector: "e81", lang: "grc", is_original: true, translator: "OCT", year: 1903,
      label: "OCT · Greek · 1903", short: "Greek", n_chunks: 412 },
    { selector: "t12", lang: "eng", is_original: false, translator: "Benjamin Jowett", year: 1892,
      label: "Benjamin Jowett · 1892", short: "Jowett", n_chunks: 388 },
  ],
  chunks: [],
};

const meta: Meta<typeof Chrome> = {
  title: "Reader/Chrome",
  component: Chrome,
  parameters: {
    layout: "fullscreen",
  },
  args: {
    target: "eng",
    onTarget: (t: TargetLang) => {
      console.debug("Chrome onTarget", t);
    },
    meta: META,
    onBack: () => {
      console.debug("Chrome onBack");
    },
  },
  decorators: [
    (Story) => (
      <div class="reader">
        <Story />
      </div>
    ),
  ],
};
export default meta;

type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const FrenchTarget: Story = {
  args: {
    target: "fra",
  },
};

export const NoMeta: Story = {
  args: {
    meta: null,
    onBack: undefined,
  },
};

export const Dark: Story = {
  decorators: [withTheme("dark")],
  parameters: { backgrounds: { default: "paper-dark" } },
};
