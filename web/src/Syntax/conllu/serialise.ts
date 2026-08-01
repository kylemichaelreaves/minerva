import type { Document, Sentence, Token } from "./types";

// The canonical CoNLL-U writer. Every line is terminated by `\n` and every
// sentence is followed by one blank line, including the last — so a document
// ends `\n\n` and two documents concatenate into a valid third.
//
// This is the export path for hand corrections, so it must not normalise
// anything it was not asked to: comments go out verbatim, untouched columns
// go out unchanged, and skipped rows are restored to the exact position they
// held. `writeConllu(parseConllu(x)) === x` is asserted on the fixture bytes.

function writeToken(t: Token): string {
  return [
    String(t.id),
    t.form,
    t.lemma,
    t.upos,
    t.xpos,
    t.feats,
    // `null` is the format's `_` — an unparsed token, not a second root.
    t.head === null ? "_" : String(t.head),
    t.deprel,
    t.deps,
    t.misc,
  ].join("\t");
}

function writeSentence(sent: Sentence): string {
  // Interleave tokens and skipped rows back into source order. Skipped rows
  // know the slot they occupied; tokens fill the gaps in sequence.
  const total = sent.tokens.length + sent.skipped.length;
  const slots = new Array<string | undefined>(total);
  for (const s of sent.skipped) slots[s.lineIndex] = s.raw;

  let next = 0;
  for (let i = 0; i < total; i += 1) {
    if (slots[i] !== undefined) continue;
    const tok = sent.tokens[next];
    next += 1;
    if (tok !== undefined) slots[i] = writeToken(tok);
  }

  const body = slots.filter((line): line is string => line !== undefined);
  return [...sent.comments, ...body].map((line) => `${line}\n`).join("") + "\n";
}

export function writeConllu(doc: Document): string {
  return doc.sentences.map(writeSentence).join("");
}
