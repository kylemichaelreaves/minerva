// Lemma identity card for F2 (KWIC detail). Carries the lemma, its
// part-of-speech, the language, the total occurrences in scope, and —
// crucially — the gender when one dominates the lemma's attested
// forms. "Exactly one attested gender" is what this comment used to
// say and what the note under the value used to claim; the threshold
// has always been >95%, and most locked lemmas carry a mislabelled
// long tail (`ratio` is Fem 17,619 / Masc 50), so the share is
// reported instead (#507). Pulling gender into the identity card
// resolves the muted-chip ambiguity from the LIVE design: gender is a
// property of the lemma, not a filter knob.

import { Show } from "solid-js";
import type { LemmaDetailResponse } from "~/api/concordanceApi";
import { Romanizable } from "~/Concordance/components/Romanizable";
import { formatGenderShare, GENDER_LABEL, lockedGender, POS_LABEL } from "~/Concordance/constants";

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
  /** The lemma's dominant gender — shared with the filter rail, which
   *  used to compute it differently and disagree (#507). */
  const locked = () => lockedGender(props.data.gender_breakdown);
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
        <Show when={locked()}>
          {(l) => (
            <>
              <span class="locked">
                {GENDER_LABEL[l().value] ?? l().value}
                <span class="note">· {formatGenderShare(l().share)} of attested forms</span>
              </span>
              {" · "}
            </>
          )}
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
