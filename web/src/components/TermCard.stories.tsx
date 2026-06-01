// Stories for TermCard — the flagship seed story.
//
// TermCard fetches `/api/terms/:id` via `fetchTermDetail` in chat.ts.
// In Storybook there's no server, so the story-file decorator
// monkey-patches `globalThis.fetch` to return a curated `TermDetail`
// payload for any URL beginning with `/api/terms/`. Other URLs fall
// through to the original `fetch`, so co-existing stories that fetch
// elsewhere remain unaffected.
//
// This story exercises the popover positioning machinery (TermCard
// anchors to a DOMRect; the decorator renders a visible trigger and
// passes its bounding rect as the anchor), the renderings grid,
// the "why this rendering?" disclosure, the related-terms chips, and
// the external-links row. Use the theme toolbar (top right) to flip
// between light and dark.

import type { Component } from "solid-js";
import type { Meta, StoryObj } from "storybook-solidjs-vite";
import TermCard from "~/components/TermCard";
import type { TermDetail } from "~/utils/types";
import { withTheme } from "../../.storybook/decorators";

// ---- mock data ----

const phantasiaTerm: TermDetail = {
  id: 1,
  source_form: "φαντασία",
  source_language: "grc",
  transliteration: "phantasia",
  lemma: "φαντασία",
  short_gloss: "imagination · appearance",
  long_description:
    "In De anima III.3, Aristotle distinguishes phantasia from aisthesis and " +
    "noesis as the faculty by which images persist after perception.",
  renderings: [
    {
      id: 1,
      translation_id: 1,
      translator_name: "Hett",
      year: 1936,
      language: "eng",
      work_title: "De anima",
      default_rendering: "imagination",
      translator_note:
        "Hett keeps 'imagination' even where the active sense (image-making) " +
        "would read more naturally as 'representation'.",
    },
    {
      id: 2,
      translation_id: 2,
      translator_name: "Reeve",
      year: 2017,
      language: "eng",
      work_title: "De anima",
      default_rendering: "appearance",
      translator_note: null,
    },
    {
      id: 3,
      translation_id: 3,
      translator_name: "Polansky",
      year: 2007,
      language: "eng",
      work_title: "De anima",
      default_rendering: "imagination",
      translator_note: "Tracks Hett, with a footnoted caveat in II.3.",
    },
  ],
  occurrences_by_edition: [
    {
      edition_id: 1,
      name: "Bekker",
      language: "grc",
      is_canonical: 1,
      work_title: "De anima",
      occurrences: 42,
    },
  ],
  related: [
    {
      id: 11,
      source_form: "αἴσθησις",
      source_language: "grc",
      short_gloss: "perception",
      relation_kind: "contrasted-with",
      notes: null,
    },
    {
      id: 12,
      source_form: "νόησις",
      source_language: "grc",
      short_gloss: "intellection",
      relation_kind: "contrasted-with",
      notes: null,
    },
  ],
};

const ergonTerm: TermDetail = {
  ...phantasiaTerm,
  id: 2,
  source_form: "ἔργον",
  transliteration: "ergon",
  lemma: "ἔργον",
  short_gloss: "function · proper work",
  long_description: "The Ergon Argument: NE I.7, 1097b22 ff.",
  renderings: [
    {
      id: 21,
      translation_id: 1,
      translator_name: "Ross",
      year: 1925,
      language: "eng",
      work_title: "Nicomachean Ethics",
      default_rendering: "function",
      translator_note: null,
    },
  ],
  occurrences_by_edition: [
    {
      edition_id: 2,
      name: "Bekker",
      language: "grc",
      is_canonical: 1,
      work_title: "Nicomachean Ethics",
      occurrences: 18,
    },
  ],
  related: [],
};

// Partial<Record<...>> so index access returns `TermDetail | undefined`,
// keeping `@typescript-eslint/no-unnecessary-condition` happy and the
// runtime safety honest if a story asks for a termId we haven't mocked.
const TERMS_BY_ID: Partial<Record<string, TermDetail>> = {
  "1": phantasiaTerm,
  "2": ergonTerm,
};

// ---- fetch interceptor ----
//
// Install once at module load. Stories that render TermCard will hit
// this interceptor; the original `fetch` is preserved for any future
// story (e.g. Composer) that calls other endpoints.

const originalFetch = globalThis.fetch.bind(globalThis);
globalThis.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
  const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
  const m = /^\/api\/terms\/(\d+)$/.exec(url);
  if (m) {
    const term = TERMS_BY_ID[m[1]];
    if (term) {
      return new Response(JSON.stringify(term), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    }
  }
  return originalFetch(input, init);
};

// ---- anchor harness ----
//
// TermCard needs a DOMRect for its anchor (the clicked word). The
// harness renders a visible "trigger" span; on mount it reads the
// span's bounding rect and renders the card pinned to that rect.

interface HarnessProps {
  termId: number;
  triggerLabel: string;
}

const Harness: Component<HarnessProps> = (props) => {
  // We can't read the rect at JSX-time; defer via a ref + signal.
  // Simpler: render the card with a manually-built rect that places
  // it in the visible area. This avoids the empty-first-render flash
  // that a ref-based path would cause.
  const anchor = new DOMRect(120, 200, 80, 24);
  return (
    <>
      <div
        style={{
          position: "fixed",
          top: `${anchor.top}px`,
          left: `${anchor.left}px`,
          width: `${anchor.width}px`,
          height: `${anchor.height}px`,
          "font-family": "var(--r-greek, GFS Didot, serif)",
          "font-size": "20px",
          color: "var(--ink)",
          "border-bottom": "1px dotted var(--ink-faint)",
        }}
      >
        {props.triggerLabel}
      </div>
      <TermCard
        termId={props.termId}
        anchor={anchor}
        onClose={() => {
          /* dismissal: no-op in story */
        }}
      />
    </>
  );
};

// ---- meta ----

const meta: Meta<typeof Harness> = {
  title: "Reader/TermCard",
  component: Harness,
  parameters: {
    layout: "fullscreen",
  },
};
export default meta;

type Story = StoryObj<typeof meta>;

export const Phantasia: Story = {
  args: {
    termId: 1,
    triggerLabel: "φαντασία",
  },
};

export const SingleRendering: Story = {
  args: {
    termId: 2,
    triggerLabel: "ἔργον",
  },
  parameters: {
    docs: {
      description: {
        story:
          "Term with exactly one translator rendering — exercises the " +
          "single-rendering flat one-liner path, not the multi-translator " +
          "grid.",
      },
    },
  },
};

export const DarkTheme: Story = {
  args: {
    termId: 1,
    triggerLabel: "φαντασία",
  },
  decorators: [withTheme("dark")],
  parameters: {
    backgrounds: { default: "paper-dark" },
    docs: {
      description: {
        story:
          "Pinned to dark theme regardless of the toolbar global. Use " +
          "this for side-by-side variant comparison in design review.",
      },
    },
  },
};
