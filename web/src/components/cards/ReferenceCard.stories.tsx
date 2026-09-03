// Stories for ReferenceCard — the cross-reference popover.
//
// Three variants × two themes. These stories ARE the design of record for
// the card: they began as a mirror of a static HTML design canvas that was
// never committed, and this file replaced it (#360). Each story renders the
// card pinned to a fake gutter-marker anchor at known viewport
// coordinates so the popover positioning machinery exercises but
// doesn't fall to (0, 0). The toolbar Theme global toggles light /
// dark; pinned-dark stories use the `withTheme` decorator for
// side-by-side comparison.
//
// No fetch interception — ReferenceCard is fully prop-driven. The
// mocked `Reference` objects below match the shape returned by
// `/api/chunks/:id/references` so swapping in real API data later is
// a one-line change.

import type { Component } from "solid-js";
import type { Meta, StoryObj } from "storybook-solidjs-vite";
import ReferenceCard, { type Reference } from "~/components/ReferenceCard";
import { withTheme } from "../../.storybook/decorators";

// ─── mock references ─────────────────────────────────────────────

const inCorpusRef: Reference = {
  id: 2,
  source_chunk_id: "4f1c245883e7aad638ed",
  source_span_start: null,
  source_span_end: null,
  source_form: "Philosophus",
  quoted_phrase: "νοεῖν ἄνευ φαντάσματος",
  target: {
    author: "Aristotle",
    work: "De anima",
    in_corpus_work_id: 107,
    chunk_id: "9866703703c8fff41076",
    locator: "III.7",
    locator_payload: null,
    sort_key: null,
  },
  reference_type: "cites",
  confidence: 1.0,
  source_method: "manual",
  curator_status: "manual",
  note: "the locus classicus on Aquinas's appropriation of Aristotelian cognition",
};

const inCorpusPreview =
  "The soul never thinks without an image. As in perceiving, so in " +
  "thinking — when one apprehends, the imagination presents the form " +
  "to which thought attends; without that image, the intellect has " +
  "nothing on which to fasten.";

const outOfCorpusRef: Reference = {
  id: 99,
  source_chunk_id: "d0e8b483d00fdb3b3f06",
  source_span_start: null,
  source_span_end: null,
  source_form: null,
  quoted_phrase: "iustitia erga deos religio, erga parentes pietas dicitur",
  target: {
    author: "Cicero",
    work: "De re publica",
    in_corpus_work_id: null, // <- distinguishing feature: not in corpus
    chunk_id: null,
    locator: "VI.13",
    locator_payload: null,
    sort_key: null,
  },
  reference_type: "quotes",
  confidence: 1.0,
  source_method: "manual",
  curator_status: "manual",
  note: null,
};

const pendingRef: Reference = {
  id: 100,
  source_chunk_id: "deadbeefdeadbeefdead",
  source_span_start: null,
  source_span_end: null,
  source_form: null,
  quoted_phrase: "εἰς τὸ ὅμοιον αὑτῇ",
  target: {
    author: "Plato",
    work: "Phaedo",
    in_corpus_work_id: 4,
    chunk_id: null,
    locator: "79d",
    locator_payload: null,
    sort_key: null,
  },
  reference_type: "alludes",
  confidence: 0.62,
  source_method: "rule+embed",
  // curator_status='auto' is what flips the visual state to PENDING.
  curator_status: "auto",
  note: "auto-detected via Plotinus-Augustine embedding similarity",
};

const pendingPreview =
  "When the soul investigates by itself, it passes into the realm " +
  "of what is pure, ever-existing, immortal, and unchanging; and " +
  "being akin to this, comes always to be with it, whenever it is " +
  "by itself and can be so.";

// ─── anchor harness ──────────────────────────────────────────────
//
// ReferenceCard pins itself to a DOMRect. The harness builds a fake
// gutter marker at known coordinates and passes its rect to the
// card. Same pattern as TermCard.stories.tsx.

interface HarnessProps {
  reference: Reference;
  previewText?: string;
}

const Harness: Component<HarnessProps> = (props) => {
  const anchor = new DOMRect(120, 220, 14, 18);
  return (
    <>
      {/* Pretend gutter marker — purely decorative, anchors the arrow. */}
      <div
        style={{
          position: "fixed",
          top: `${anchor.top}px`,
          left: `${anchor.left}px`,
          width: `${anchor.width}px`,
          height: `${anchor.height}px`,
          "font-family": "var(--r-sans, Geist, system-ui, sans-serif)",
          "font-size": "12px",
          color: "var(--r-accent)",
          "text-align": "center",
          "line-height": `${anchor.height}px`,
        }}
        aria-hidden="true"
      >
        ▸
      </div>
      <ReferenceCard
        reference={props.reference}
        anchor={anchor}
        previewText={props.previewText}
        onClose={() => {
          /* dismissal: no-op in story */
        }}
      />
    </>
  );
};

// ─── meta ────────────────────────────────────────────────────────

const meta: Meta<typeof Harness> = {
  title: "Reader/ReferenceCard",
  component: Harness,
  parameters: {
    layout: "fullscreen",
  },
};
export default meta;

type Story = StoryObj<typeof meta>;

// ─── variants × themes ───────────────────────────────────────────

export const InCorpus: Story = {
  args: {
    reference: inCorpusRef,
    previewText: inCorpusPreview,
  },
  parameters: {
    docs: {
      description: {
        story:
          "Target work is in our local index (Aristotle's De anima, " +
          "work_id 107). Preview block is populated from the target " +
          "chunk's text; 'Open in reader →' navigates to the Aristotle " +
          "reader at the matching Bekker passage.",
      },
    },
  },
};

export const InCorpusDark: Story = {
  args: {
    reference: inCorpusRef,
    previewText: inCorpusPreview,
  },
  decorators: [withTheme("dark")],
  parameters: {
    backgrounds: { default: "paper-dark" },
  },
};

export const OutOfCorpus: Story = {
  args: {
    reference: outOfCorpusRef,
  },
  parameters: {
    docs: {
      description: {
        story:
          "Target work isn't in the corpus (Cicero, De re publica). " +
          "Quote is required — there's no preview to fall back on. " +
          "External-link row offers Logeion / Perseus / archive.org " +
          "for further pursuit.",
      },
    },
  },
};

export const OutOfCorpusDark: Story = {
  args: {
    reference: outOfCorpusRef,
  },
  decorators: [withTheme("dark")],
  parameters: {
    backgrounds: { default: "paper-dark" },
  },
};

export const PendingApproval: Story = {
  args: {
    reference: pendingRef,
    previewText: pendingPreview,
  },
  parameters: {
    docs: {
      description: {
        story:
          "Auto-detected (rule + embedding) but the curator hasn't yet " +
          "approved. Adds an 'unverified · auto' pill top-right and " +
          "mutes the preview block. The reference-type chip drops below " +
          "the pill so they don't collide.",
      },
    },
  },
};

export const PendingApprovalDark: Story = {
  args: {
    reference: pendingRef,
    previewText: pendingPreview,
  },
  decorators: [withTheme("dark")],
  parameters: {
    backgrounds: { default: "paper-dark" },
  },
};
