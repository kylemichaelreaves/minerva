import type { SyntaxSentence } from "~/api/syntaxApi";
import type { Document, Sentence, Token } from "~/Syntax/conllu/types";
import { writeConllu } from "~/Syntax/conllu/serialise";
import type { Correction, CorrectionPatch } from "./apply";

// Getting a corrected tree out of the tool, two ways.
//
// CoNLL-U is the interchange format: a treebank, a parser evaluation, a
// colleague's pipeline. An export only this app can read is not an export, so
// the test that matters is that it reparses.
//
// The JSON patch is the correction log itself, portable. It is what makes the
// machine parse safe to discard and recompute — reapplied to a fresh parse of
// the same text, it reproduces the edited tree. `fromVal` rides along because
// it is what a reviewer checks the claim against.

/** The format's "empty" — a column with no value is `_`, never blank. */
const or_ = (value: string | null | undefined): string => value ?? "_";

/**
 * The reading text of a sentence, reconstructed from its tokens.
 *
 * Approximate on purpose: the API gives character offsets into the chunk but
 * not the chunk text, so this joins forms with spaces and tucks punctuation
 * back against the word before it. `# text` is a convenience comment, not
 * data anything reads back — the tokens are the payload.
 */
function sentenceText(sentence: SyntaxSentence): string {
  return sentence.tokens
    .map((t) => t.form)
    .join(" ")
    .replace(/ ([,.;:!?)\]}»])/g, "$1")
    .replace(/([([{«]) /g, "$1");
}

/** One API sentence as a CoNLL-U sentence. */
function toSentence(chunkId: string, sentence: SyntaxSentence): Sentence {
  const sentId = `${chunkId}-${String(sentence.sent_ord)}`;
  const text = sentenceText(sentence);

  const tokens: Token[] = sentence.tokens.map((t) => ({
    id: t.id,
    form: t.form,
    lemma: or_(t.lemma),
    upos: or_(t.upos),
    xpos: or_(t.xpos),
    feats: or_(t.feats),
    // Not `or_`: `null` is the format's `_` for an unparsed token and `0` is
    // "attaches to the root". Collapsing them invents a second root.
    head: t.head,
    deprel: or_(t.deprel),
    deps: "_",
    misc: or_(t.misc),
  }));

  return {
    sentId,
    text,
    comments: [`# sent_id = ${sentId}`, `# text = ${text}`],
    tokens,
    // Multiword ranges and empty nodes are dropped by the parse pipeline
    // before they reach the API, so there is nothing to restore here.
    skipped: [],
  };
}

/** The whole chunk as a CoNLL-U document. */
export function toConlluDocument(chunkId: string, sentences: readonly SyntaxSentence[]): Document {
  return { sentences: sentences.map((s) => toSentence(chunkId, s)) };
}

/**
 * The corrected tree as CoNLL-U text.
 *
 * Pass the *materialised* sentences — the ones with corrections already
 * replayed. This function has no opinion about provenance; it writes what it
 * is given.
 */
export function exportConllu(chunkId: string, sentences: readonly SyntaxSentence[]): string {
  return writeConllu(toConlluDocument(chunkId, sentences));
}

/**
 * The correction log as a portable patch.
 *
 * Sorted by id so replay order is stable across exports, and stamped so two
 * patches of the same chunk can be told apart.
 */
export function exportPatch(chunkId: string, corrections: readonly Correction[]): CorrectionPatch {
  return {
    chunkId,
    exportedAt: new Date().toISOString(),
    corrections: [...corrections].sort((a, b) => a.id - b.id),
  };
}

/** A filename that sorts and does not collide. */
export function exportFilename(chunkId: string, extension: "conllu" | "json"): string {
  const stamp = new Date().toISOString().slice(0, 10);
  return `${chunkId}-syntax-${stamp}.${extension}`;
}
