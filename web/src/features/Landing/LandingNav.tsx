// The doors out of the landing. One list, placed in the header on desktop
// and under the composer on a phone (see the Landing file comment).
// Observability watches the server rather than reading the corpus, so it
// sits after a divider, muted.

import { For } from "solid-js";

export interface LandingNavProps {
  onOpenRead: () => void;
  onOpenRefs: (sourceAuthor?: string) => void;
  onOpenNetwork: () => void;
  onOpenConcordance: () => void;
  onOpenMetrics: () => void;
}

// The corpus doors, in order: label, then the prop that opens it.
const DOORS = [
  ["Read", "onOpenRead"],
  ["Citations", "onOpenRefs"],
  ["Network", "onOpenNetwork"],
  ["Concordance", "onOpenConcordance"],
] as const satisfies readonly (readonly [string, keyof LandingNavProps])[];

export default function LandingNav(props: LandingNavProps) {
  return (
    <nav class="landing-nav" aria-label="Explore the corpus">
      <For each={DOORS}>
        {([label, open]) => (
          <button type="button" class="landing-nav__link" onClick={() => props[open]()}>
            {label}
          </button>
        )}
      </For>
      <span class="landing-nav__sep" aria-hidden="true" />
      <button
        type="button"
        class="landing-nav__link landing-nav__link--util"
        onClick={() => props.onOpenMetrics()}
      >
        Observability
      </button>
    </nav>
  );
}
