// Segmented control listing every edition/translation of the work, so
// the reader can switch which text it renders (#50). Shown only when a
// work actually has more than one edition. The original-language
// edition and translations sit side by side as peers; the design
// (issue #50) is built to grow into a side-by-side compare mode.

import { For, Show } from "solid-js";
import type { EditionOption } from "~/utils/types";

export function EditionBar(props: {
  // Optional so a partial range (older mocks, a degraded response) just
  // renders nothing rather than throwing; the live API always sends it.
  editions?: EditionOption[];
  current: string;
  onSwitch: (selector: string) => void;
}) {
  return (
    <Show when={(props.editions?.length ?? 0) > 1}>
      <div class="edition-bar" role="tablist" aria-label="Edition">
        <For each={props.editions}>
          {(ed) => (
            <button
              type="button"
              class="edition-seg"
              classList={{ original: ed.is_original }}
              role="tab"
              aria-selected={ed.selector === props.current ? "true" : "false"}
              title={ed.label}
              onClick={() => {
                if (ed.selector !== props.current) props.onSwitch(ed.selector);
              }}
            >
              {ed.short}
              <Show when={ed.year}>
                <span class="yr">{ed.year}</span>
              </Show>
            </button>
          )}
        </For>
      </div>
    </Show>
  );
}
