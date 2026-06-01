// Static seed data for the prototype. SAMPLE_HISTORY and SEED_THREAD
// used to live here as fixtures for early UI work; they've been
// retired now that the real backend serves history and the Thread
// renders live turns. Likewise the bronze/lapis accents were
// alternatives never wired up — only Oxblood is selected in App.tsx.

import type { AccentDef, AccentKey, StarterPrompt } from "~/utils/types";

export const ACCENTS: Record<AccentKey, AccentDef> = {
  oxblood: {
    label: "Oxblood",
    light: { accent: "#7B2E2A", soft: "#C7A9A6", selection: "rgba(123,46,42,0.18)" },
    dark: { accent: "#C97A65", soft: "#6E3F36", selection: "rgba(201,122,101,0.22)" },
  },
};

// Starter prompts. Ethics + Ontology carried over from the prior
// product line (the canonical "what is virtue?" and "essence vs.
// existence" framings); Method + Reception adopted from the design 1a
// wireframe to broaden the doorway into modern epistemology and
// reception history. Each topic pairs with a serif-italic paraphrase
// rendered alongside the topic label inside the pill.
export const STARTER_PROMPTS: StarterPrompt[] = [
  {
    topic: "Ethics",
    paraphrase: "virtue & the soul",
    text: "Is virtue a kind of knowledge, or a habit of the soul?",
  },
  {
    topic: "Ontology",
    paraphrase: "essence & existence",
    text: "What is the difference between essence and existence?",
  },
  {
    topic: "Method",
    paraphrase: "clear & distinct",
    text: "What does it mean for an idea to be clear and distinct?",
  },
  {
    topic: "Reception",
    paraphrase: "Marx reads Hegel",
    text: "How does Marx's dialectic invert Hegel's idealism?",
  },
];
