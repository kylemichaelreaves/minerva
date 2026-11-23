import { For } from "solid-js";
import type { SyntaxSentence } from "~/api/syntaxApi";

// Navigation between the sentences of one chunk, not a dashboard. Length,
// correction count, and the opening words — enough to find the sentence you
// were working on, and nothing else.

export interface SentenceListProps {
  sentences: SyntaxSentence[];
  current: number;
  onPick: (sentOrd: number) => void;
}

/** The first few words, for recognition rather than reading. */
function opening(sent: SyntaxSentence, max = 90): string {
  const text = sent.tokens
    .map((t) => t.form)
    .join(" ")
    .replace(/\s+([.,;:!?])/g, "$1");
  return text.length > max ? `${text.slice(0, max).trimEnd()}…` : text;
}

export function SentenceList(props: SentenceListProps) {
  return (
    <nav class="syn-slist" aria-label="Sentences in this passage">
      <div class="syn-slh">
        <div class="t">Passage · {props.sentences.length} sentences</div>
      </div>
      <For each={props.sentences}>
        {(sent) => {
          const corrected = () => sent.tokens.filter((t) => t.corrected).length;
          return (
            <button
              type="button"
              class={["syn-sitem", { on: sent.sent_ord === props.current }]}
              aria-current={sent.sent_ord === props.current ? "true" : undefined}
              onClick={() => props.onPick(sent.sent_ord)}
            >
              <div class="syn-sn">
                <span>
                  {String(sent.sent_ord + 1).padStart(2, "0")} · {sent.tokens.length} tokens
                </span>
                <span class={["syn-chip", { c: corrected() > 0 }]}>
                  {corrected() ? `${String(corrected())} corrected` : "machine"}
                </span>
              </div>
              <div class="syn-sx">{opening(sent)}</div>
            </button>
          );
        }}
      </For>
    </nav>
  );
}
