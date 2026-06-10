// Hover-to-transliterate wrapper for Greek words on the Concordance
// page. Reuses the Reader's romanization scheme (utils/greek.romanize)
// and the shared HoverTip popover, so hovering a Greek lemma or surface
// form reveals its Latin transliteration — the same affordance the
// Reader gives over Greek words in running text.
//
// Non-Greek text (German / Latin / English lemmas, ASCII surface forms)
// renders untouched: no wrapper, no tooltip. The Greek test is per-word
// via `containsGreek`, so a mixed list shows tooltips only on the Greek
// rows without threading the page language down to every cell.

import { Show } from "solid-js";
import { HoverTip } from "~/components/HoverTip";
import { containsGreek, romanize } from "~/utils/greek";

export function Romanizable(props: { text: string }) {
  return (
    <Show when={containsGreek(props.text)} fallback={<>{props.text}</>}>
      <HoverTip body={romanize(props.text)}>{props.text}</HoverTip>
    </Show>
  );
}
