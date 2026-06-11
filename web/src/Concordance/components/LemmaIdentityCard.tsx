// Lemma identity card for F2 (KWIC detail). Carries the lemma, its
// part-of-speech, the language, the total occurrences in scope, and —
// crucially — the gender when the lemma has exactly one attested
// gender. Pulling gender into the identity card resolves the muted-
// chip ambiguity from the LIVE design: gender is a property of the
// lemma, not a filter knob.

import { Show } from "solid-js";
import type { LemmaDetailResponse } from "~/api/concordanceApi";
import { Romanizable } from "~/Concordance/components/Romanizable";
import { GENDER_LABEL, POS_LABEL } from "~/Concordance/constants";

export function LemmaIdentityCard(props: {
  lemma: string;
  lang: string;
  data: LemmaDetailResponse;
  /** Optional gloss / translation. Rendered as italic prose at the
   *  right edge of the card when present. Today we don't have a gloss
   *  store wired up, so callers can omit; the slot is reserved for the
   *  next phase. */
  gloss?: string;
}) {
  const pos = () => props.data.pos_breakdown[0]?.value ?? "";
  const posLabel = () => POS_LABEL[pos()] ?? pos().toLowerCase();
  /** Treat a gender as "the lemma's gender" when one value accounts
   *  for >95% of attested forms. spaCy's mislabels generate a tiny
   *  long-tail (Geist gets Masc 4494 / Fem 38 / Neut 3) — we don't
   *  want to lose the locked card just because of three noisy tokens. */
  const lockedGender = () => {
    const buckets = props.data.gender_breakdown;
    const top = buckets[0];
    if (top === undefined) return null;
    if (buckets.length === 1) return top.value;
    const total = buckets.reduce((s, b) => s + b.count, 0);
    return top.count / total > 0.95 ? top.value : null;
  };
  return (
    <div class="lemma-id">
      <span class="lem">
        <Romanizable text={props.lemma} />
      </span>
      <span class="meta">
        <Show when={pos()}>
          {posLabel().toUpperCase()}
          {" · "}
        </Show>
        <Show when={lockedGender()}>
          <span class="locked">
            {GENDER_LABEL[lockedGender()!] ?? lockedGender()}
            <span class="note">· only attested gender</span>
          </span>
          {" · "}
        </Show>
        {props.lang.toUpperCase()}
        {" · "}
        <b>{props.data.total.toLocaleString()}</b> occurrence
        {props.data.total === 1 ? "" : "s"}
      </span>
      <Show when={props.gloss}>
        <span
          style={{
            "margin-left": "auto",
            "font-family": "var(--serif)",
            "font-style": "italic",
            "font-size": "13px",
            color: "var(--ink-mute)",
            "max-width": "360px",
            "text-align": "right",
          }}
        >
          {props.gloss}
        </span>
      </Show>
    </div>
  );
}
