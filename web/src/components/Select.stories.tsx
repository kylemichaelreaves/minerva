// Stories for the minerva-select dropdown component.
//
// Coverage:
//   - Default (closed) with placeholder
//   - With a selection (no sublabel)
//   - With a selection (with sublabel — the design's headline scenario)
//   - Long list (exercises the listbox scroll + scrollbar tint)
//   - Disabled options interleaved (exercises arrow-key skip)
//   - Whole select disabled
//   - Pinned-dark theme for visual diffing
//
// Each story drives its own controlled `value` via createSignal so the
// trigger -> commit -> trigger cycle is exercisable in the canvas
// without external state plumbing.

import { createSignal } from "solid-js";
import type { Meta, StoryObj } from "storybook-solidjs-vite";
import { Select, type SelectOption } from "~/components/Select";
import { withTheme } from "../../.storybook/decorators";

// ─── fixtures ──────────────────────────────────────────────────────

const AUTHORS_SIMPLE: SelectOption[] = [
  { value: "", label: "— any —" },
  { value: "Aquinas", label: "Aquinas" },
  { value: "Augustine", label: "Augustine" },
  { value: "Hegel", label: "Hegel" },
  { value: "Kant", label: "Kant" },
  { value: "Spinoza", label: "Spinoza" },
];

const REF_TYPES: SelectOption[] = [
  { value: "", label: "— any —" },
  { value: "cites", label: "cites" },
  { value: "quotes", label: "quotes" },
  { value: "paraphrases", label: "paraphrases" },
  { value: "alludes", label: "alludes" },
  { value: "comments_on", label: "comments on" },
  { value: "translates", label: "translates" },
  { value: "disputes", label: "disputes" },
  { value: "corrects", label: "corrects" },
];

// The headline scenario from the design sketch: a translator picker
// where each option carries an edition-year + publisher sublabel.
const TRANSLATORS: SelectOption[] = [
  {
    value: "jowett-1871",
    label: "Benjamin Jowett",
    sublabel: "1871 · Oxford",
  },
  {
    value: "bloom-1968",
    label: "Allan Bloom",
    sublabel: "1968 · Basic Books",
  },
  {
    value: "grube-1974",
    label: "G. M. A. Grube",
    sublabel: "1974 · Hackett · rev. Reeve 1992",
  },
  {
    value: "shorey-1937",
    label: "Paul Shorey",
    sublabel: "1937 · Loeb Classical Library",
    disabled: true,
  },
  {
    value: "lee-1955",
    label: "Desmond Lee",
    sublabel: "1955 · Penguin",
  },
];

// A long list — exercises the listbox scroll + the tinted scrollbar.
const LONG_AUTHORS: SelectOption[] = Array.from({ length: 30 }, (_, i) => ({
  value: `auth-${i}`,
  label: `Author ${String(i).padStart(2, "0")} — long name to test ellipsis behavior`,
}));

// ─── meta ──────────────────────────────────────────────────────────

const meta: Meta<typeof Select> = {
  title: "Lib/Select",
  component: Select,
  parameters: {
    layout: "centered",
  },
};
export default meta;

type Story = StoryObj<typeof meta>;

// Tiny harness that wraps Select with a controlled signal so each story
// is interactive (no external state plumbing required). Width clamps
// to a realistic single-field column so the stories render close to
// production proportions.
function Harness(props: {
  options: SelectOption[];
  initial?: string;
  placeholder?: string;
  disabled?: boolean;
  clearable?: boolean;
  ariaLabel: string;
}): ReturnType<typeof Select> {
  const [value, setValue] = createSignal<string | undefined>(props.initial);
  return (
    <div style={{ width: "280px" }}>
      <Select
        options={props.options}
        value={value()}
        onChange={(v) => { setValue(v ? v : undefined); }}
        placeholder={props.placeholder}
        disabled={props.disabled}
        clearable={props.clearable}
        ariaLabel={props.ariaLabel}
      />
    </div>
  );
}

// ─── stories ───────────────────────────────────────────────────────

export const Default: Story = {
  render: () => (
    <Harness
      options={AUTHORS_SIMPLE}
      placeholder="Select an author…"
      ariaLabel="Source author"
    />
  ),
  parameters: {
    docs: {
      description: {
        story:
          "Closed trigger with placeholder text. The placeholder uses " +
          "the serif italic treatment to telegraph that the field has " +
          "no value yet without being visually loud.",
      },
    },
  },
};

export const Selected: Story = {
  render: () => (
    <Harness
      options={AUTHORS_SIMPLE}
      initial="Aquinas"
      placeholder="Select an author…"
      ariaLabel="Source author"
    />
  ),
  parameters: {
    docs: {
      description: {
        story:
          "Trigger with a selection. The primary value is the serif " +
          "treatment used throughout the reader, matching the body-text " +
          "voice of the corpus.",
      },
    },
  },
};

export const WithSublabel: Story = {
  render: () => (
    <Harness
      options={TRANSLATORS}
      initial="grube-1974"
      placeholder="Select a translation…"
      ariaLabel="Translation"
    />
  ),
  parameters: {
    docs: {
      description: {
        story:
          "Two-line value: translator name (serif) above edition-year " +
          "+ publisher (sans-muted). The design's headline scenario — " +
          "none of the project's existing selects use sublabels yet, " +
          "but the prop is optional and ready when needed.",
      },
    },
  },
};

export const ReferenceTypeFilter: Story = {
  render: () => (
    <Harness
      options={REF_TYPES}
      initial="quotes"
      placeholder="Filter by type"
      ariaLabel="Reference type"
    />
  ),
  parameters: {
    docs: {
      description: {
        story:
          "Closer to how the Refs filter bar actually uses the " +
          "component: short single-line options, an explicit " +
          "empty-sentinel option at the top (\"— any —\") to clear the " +
          "filter without a separate clear button.",
      },
    },
  },
};

export const LongList: Story = {
  render: () => (
    <Harness
      options={LONG_AUTHORS}
      placeholder="Pick from many…"
      ariaLabel="Long author list"
    />
  ),
  parameters: {
    docs: {
      description: {
        story:
          "Thirty options, exercising the listbox's max-height scroll " +
          "+ tinted scrollbar. Long option labels exercise the ellipsis " +
          "behavior on the primary line.",
      },
    },
  },
};

export const WithDisabledOptions: Story = {
  render: () => (
    <Harness
      options={TRANSLATORS}
      initial="bloom-1968"
      placeholder="Select…"
      ariaLabel="Translation"
    />
  ),
  parameters: {
    docs: {
      description: {
        story:
          "Translators fixture with one disabled option (Shorey). " +
          "Disabled options skip during arrow-key navigation and " +
          "pointer-down clicks; visually they dim to 40% opacity.",
      },
    },
  },
};

export const ClearableHasValue: Story = {
  render: () => (
    <Harness
      options={TRANSLATORS}
      initial="grube-1974"
      placeholder="Select a translation…"
      ariaLabel="Translation"
    />
  ),
  parameters: {
    docs: {
      description: {
        story:
          "When a value is selected and `clearable` defaults to true, " +
          "a small × button appears between the value and the caret. " +
          "Clicking it calls `onChange(\"\")`. The harness clears the " +
          "controlled signal back to undefined so the placeholder " +
          "shows again.",
      },
    },
  },
};

export const NotClearable: Story = {
  render: () => (
    <Harness
      options={TRANSLATORS}
      initial="grube-1974"
      placeholder="Select a translation…"
      clearable={false}
      ariaLabel="Translation"
    />
  ),
  parameters: {
    docs: {
      description: {
        story:
          "Same as WithSublabel but `clearable={false}` — for selects " +
          "where a value is required and dropping back to the placeholder " +
          "would be invalid. The clear button is hidden; the user can " +
          "only switch between options.",
      },
    },
  },
};

export const Disabled: Story = {
  render: () => (
    <Harness
      options={AUTHORS_SIMPLE}
      initial="Hegel"
      placeholder="Select…"
      disabled
      ariaLabel="Source author"
    />
  ),
  parameters: {
    docs: {
      description: {
        story:
          "Whole select disabled — trigger dims to 55% opacity, click " +
          "and keyboard interactions are no-ops, and the panel cannot " +
          "be opened.",
      },
    },
  },
};

export const Dark: Story = {
  render: () => (
    <Harness
      options={TRANSLATORS}
      initial="grube-1974"
      placeholder="Select a translation…"
      ariaLabel="Translation"
    />
  ),
  decorators: [withTheme("dark")],
  parameters: {
    backgrounds: { default: "paper-dark" },
    docs: {
      description: {
        story:
          "Same WithSublabel story under the pinned dark theme. The " +
          "accent shifts to terracotta and the paper goes near-black; " +
          "all other tokens cascade from --r-* declared in " +
          "Reader/reader.css.",
      },
    },
  },
};
