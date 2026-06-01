// Stories for the XrefMarker gutter glyph.
//
// Four states × two themes (eight cells), then a ten-row page-density
// mockup at the bottom. Faithful port of
// project/reference-card/ReferenceMarker.html — the storybook canvas
// is the production-grade visual review surface, replacing the
// design-bundle's static HTML once the component ships.
//
// The marker is intentionally inert in stories: `onOpen` is a no-op,
// and the "active" state is rendered via the `active` prop rather
// than by triggering a real ReferenceCard. The Reader's integration
// (Reader/index.tsx) is where the marker's open-card cycle actually
// runs.

import type { Component, JSX } from "solid-js";
import { For } from "solid-js";
import type { Meta, StoryObj } from "storybook-solidjs-vite";
import { XrefMarker } from "~/components/XrefMarker";
import { withTheme } from "../../.storybook/decorators";

// ─── line-row primitive ───────────────────────────────────────────
//
// Mirrors the .line grid in reader.css — `36px 1fr 24px` flex/grid
// row with line number on the left, body text in the middle, marker
// (or empty cell) in the right gutter. The story uses inline styles
// keyed off the same `--r-*` tokens reader.css declares, so light
// and dark cascade automatically from the toolbar global theme via
// the preview.tsx decorator (or via withTheme for pinned variants).

interface LineProps {
  num: string;
  text: string;
  marker?: JSX.Element;
}
const Line: Component<LineProps> = (props) => (
  <div
    style={{
      display: "grid",
      "grid-template-columns": "64px 1fr 24px",
      "column-gap": "22px",
      "align-items": "baseline",
      padding: "2px 0",
      "font-family": "var(--r-serif)",
      "font-size": "17px",
      "line-height": "1.7",
      color: "var(--r-ink)",
      "letter-spacing": "0.005em",
    }}
  >
    <span
      style={{
        "text-align": "right",
        "padding-right": "8px",
        "font-family": "var(--r-sans)",
        "font-size": "10.5px",
        "font-variant-numeric": "tabular-nums",
        color: "var(--r-ink-faint)",
        "letter-spacing": "0.04em",
        "user-select": "none",
      }}
    >
      {props.num}
    </span>
    <span>{props.text}</span>
    <span style={{ "text-align": "left", "font-family": "var(--r-sans)" }}>
      {props.marker}
    </span>
  </div>
);

// The story stage: paper background card with three adjacent lines.
// Mirrors the design's `.stage` block (paper background, paper-deep
// 1px border, ~22px vertical padding) so each state cell reads as
// the same "scene" the production reader will use.
interface StageProps {
  tag: string;
  children: JSX.Element;
}
const Stage: Component<StageProps> = (props) => (
  <div
    class="reader"
    style={{
      background: "var(--r-paper)",
      border: "1px solid var(--r-paper-deep)",
      padding: "22px 0",
      position: "relative",
      overflow: "hidden",
    }}
  >
    <span
      style={{
        position: "absolute",
        top: "10px",
        right: "14px",
        "font-family": "var(--r-sans)",
        "font-size": "9.5px",
        "letter-spacing": "0.14em",
        "text-transform": "uppercase",
        color: "var(--r-ink-faint)",
      }}
    >
      {props.tag}
    </span>
    {props.children}
  </div>
);

// ─── shared sample text ───────────────────────────────────────────
//
// Latin from Aquinas (ST I, q. 6, a. 3 — "de bonitate dei"). One
// sentence per line, broken at natural caesurae so the lines are
// visibly similar to the production reader. Used in all four state
// rows — the marker placement on the middle line is what changes.

const LINES_LATIN: { num: string; text: string }[] = [
  { num: "§43.2", text: "Quemadmodum enim non est verum esse omnium quae sunt, ita" },
  { num: "§43.3", text: "non est unum quod omnia sunt; sed est aliquid quod magis est et" },
  { num: "§43.4", text: "magis unum quam cetera. Hoc autem est ipsum esse subsistens." },
];

// Density sample — Augustine, Confessiones X.6.4–13. Real Latin from
// the corpus's _smoke.yaml seed — same passage the design's density
// mockup used. Three markers across ten rows demonstrates ~30%
// density without crowding.

interface DensityRow {
  num: string;
  text: string;
  count?: number;
}
const DENSITY: DensityRow[] = [
  { num: "x.6.4", text: "Et quid est hoc? Interrogavi terram et dixit: «Non sum ego». Et quae-" },
  { num: "x.6.5", text: "cumque in eadem sunt, idem confessa sunt. Interrogavi mare et abys-", count: 1 },
  { num: "x.6.6", text: "sos et reptilia animarum vivarum, et responderunt: «Non sumus deus" },
  { num: "x.6.7", text: "tuus; quaere super nos». Interrogavi auras flabiles, et inquit universus", count: 2 },
  { num: "x.6.8", text: "aer cum incolis suis: «Fallitur Anaximenes; non sum ego deus»." },
  { num: "x.6.9", text: "Interrogavi caelum, solem, lunam, stellas: «Neque nos sumus deus," },
  { num: "x.6.10", text: "quem quaeris», inquiunt. Et dixi omnibus his, quae circumstant fores", count: 3 },
  { num: "x.6.11", text: "carnis meae: «Dicite mihi de deo meo, quod vos non estis: dicite mihi" },
  { num: "x.6.12", text: "de illo aliquid». Et exclamaverunt voce magna: «Ipse fecit nos». In-", count: 1 },
  { num: "x.6.13", text: "terrogatio mea, intentio mea, et responsio eorum, species eorum." },
];

const noop = (_rect: DOMRect): void => {
  /* no-op: stories don't open a real ReferenceCard. */
};

// ─── story harnesses ──────────────────────────────────────────────
//
// Each story renders a Stage with three adjacent rows. The middle
// row has the marker; the other two leave the gutter empty so the
// page-density argument is visible — the marker must NOT pull the
// eye when reading the surrounding prose.

interface StateHarnessProps {
  state: "default" | "hover" | "focus" | "active";
}
const StateHarness: Component<StateHarnessProps> = (props) => {
  // For hover and focus we fake the pseudo-states with className
  // overrides on the marker so the visual still reads correctly in a
  // story. The real button's :hover and :focus-visible rules in
  // reader.css drive the live component.
  const markerClassExtra =
    props.state === "hover"
      ? " is-hover"
      : props.state === "focus"
        ? " is-focus"
        : "";
  return (
    <Stage tag={props.state}>
      <Line num={LINES_LATIN[0].num} text={LINES_LATIN[0].text} />
      <Line
        num={LINES_LATIN[1].num}
        text={LINES_LATIN[1].text}
        marker={
          // Render the XrefMarker directly for `default` and `active`;
          // overlay the .is-hover / .is-focus class via a wrapper for
          // visual-only states. Wrapper carries the same className the
          // real button picks up from CSS pseudo-classes.
          props.state === "default" || props.state === "active" ? (
            <XrefMarker
              count={1}
              active={props.state === "active"}
              onOpen={noop}
            />
          ) : (
            <PseudoStateMarker className={markerClassExtra} />
          )
        }
      />
      <Line num={LINES_LATIN[2].num} text={LINES_LATIN[2].text} />
    </Stage>
  );
};

// Visual-only marker for hover / focus stories. The production
// component picks these up via CSS pseudo-classes; here we paint the
// equivalent state via an explicit className so the story doesn't
// require simulating a real hover or keyboard-focus interaction.
const PseudoStateMarker: Component<{ className: string }> = (props) => (
  <button
    type="button"
    class={`xref-pin${props.className}`}
    aria-label="Cross-reference on this passage"
  >
    ▸
  </button>
);

// The `.is-hover` and `.is-focus` class hooks the visual-only stories
// rely on are defined alongside the :hover / :focus-visible pseudo-
// classes in reader.css — no story-level <style> tag needed.

// Density harness — 10 lines with markers on a subset (rows 2, 4, 7, 9)
// echoing the design's distribution. Counts 1, 2, 3 appear across the
// span so the count rendering is exercised at all three plausible
// magnitudes.
const DensityHarness: Component = () => (
  <Stage tag="density · ~30%">
    <For each={DENSITY}>
      {(row) => (
        <Line
          num={row.num}
          text={row.text}
          marker={
            row.count ? (
              <XrefMarker count={row.count} onOpen={noop} />
            ) : undefined
          }
        />
      )}
    </For>
  </Stage>
);

// ─── meta ─────────────────────────────────────────────────────────

const meta: Meta = {
  title: "Reader/XrefMarker",
  parameters: {
    layout: "padded",
  },
};
export default meta;

type Story = StoryObj<typeof meta>;

// ─── state stories (4 × 2 themes) ─────────────────────────────────

export const Default: Story = {
  render: () => <StateHarness state="default" />,
  parameters: {
    docs: {
      description: {
        story:
          "Idle marker in ink-faint. Sits in the 24px right gutter, " +
          "baseline-aligned to the first text line. Reads as a " +
          "scholarly footnote indicator — visible on intentional " +
          "scan, invisible in peripheral vision.",
      },
    },
  },
};
export const DefaultDark: Story = {
  render: () => <StateHarness state="default" />,
  decorators: [withTheme("dark")],
  parameters: { backgrounds: { default: "paper-dark" } },
};

export const Hover: Story = {
  render: () => <StateHarness state="hover" />,
  parameters: {
    docs: {
      description: {
        story:
          "Glyph color shifts to accent. No underline, no background " +
          "fill, no scale. Cursor: pointer (live in the production " +
          "component; story shows the visual state only).",
      },
    },
  },
};
export const HoverDark: Story = {
  render: () => <StateHarness state="hover" />,
  decorators: [withTheme("dark")],
  parameters: { backgrounds: { default: "paper-dark" } },
};

export const FocusVisible: Story = {
  render: () => <StateHarness state="focus" />,
  parameters: {
    docs: {
      description: {
        story:
          "Keyboard focus — 1px accent outline at 2px offset, traced " +
          "around the glyph's bounding box. Mouse focus suppresses " +
          "the ring (CSS `:focus-visible`, not `:focus`).",
      },
    },
  },
};
export const FocusVisibleDark: Story = {
  render: () => <StateHarness state="focus" />,
  decorators: [withTheme("dark")],
  parameters: { backgrounds: { default: "paper-dark" } },
};

export const Active: Story = {
  render: () => <StateHarness state="active" />,
  parameters: {
    docs: {
      description: {
        story:
          "ReferenceCard is anchored to this row. Glyph stays in " +
          "accent until the card closes — the persistence comes from " +
          "the card itself, not from the marker.",
      },
    },
  },
};
export const ActiveDark: Story = {
  render: () => <StateHarness state="active" />,
  decorators: [withTheme("dark")],
  parameters: { backgrounds: { default: "paper-dark" } },
};

// ─── density story (10 rows, ~30% with markers) ───────────────────

export const PageDensity: Story = {
  render: () => <DensityHarness />,
  parameters: {
    docs: {
      description: {
        story:
          "Ten rows of Augustine, Confessiones X.6.4–13, with " +
          "markers on roughly a third of the lines (rows 2, 4, 7, 9). " +
          "Counts of 1, 2, 3 appear so the superscript count " +
          "rendering is exercised at all three magnitudes. The " +
          "gutter should feel calm — no marker should pull the eye " +
          "while reading the surrounding prose.",
      },
    },
  },
};
export const PageDensityDark: Story = {
  render: () => <DensityHarness />,
  decorators: [withTheme("dark")],
  parameters: { backgrounds: { default: "paper-dark" } },
};
