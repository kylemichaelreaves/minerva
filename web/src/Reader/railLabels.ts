import type { TargetLang } from "~/utils/types";

// Returns the rail's "literary" sub-label. The language is already
// shown by the target-lang chip above the rail, so we drop the
// language identifier + the dot separator that used to precede this
// word ("English · literary" → "literary").
export function labelFor(t: TargetLang): string {
  if (t === "eng") return "literary";
  if (t === "fra") return "littéraire";
  return "literarisch";
}
