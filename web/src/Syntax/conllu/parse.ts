import type { Document, Sentence, SkippedLine, Token } from "./types";

// A CoNLL-U reader. Written rather than installed: the format is ten
// tab-separated columns, sentences separated by a blank line, `#` comment
// lines carrying metadata. A dependency would be more indirection than code.
//
// Parsing is deliberately tolerant — real treebanks arrive with stray blank
// lines and missing terminators — while `writeConllu` emits one canonical
// form. Tolerant in, canonical out.

/** `# sent_id = proj-1` → `["sent_id", "proj-1"]`. Tolerates missing spaces. */
const META_RE = /^#\s*([^=\s]+)\s*=\s*(.*)$/;

function metaValue(comments: string[], key: string): string | undefined {
  for (const line of comments) {
    const m = META_RE.exec(line);
    if (m?.[1] === key) return m[2];
  }
  return undefined;
}

function toToken(cols: string[]): Token {
  const at = (i: number): string => cols[i] ?? "_";
  const head = at(6);
  return {
    id: Number.parseInt(at(0), 10),
    form: at(1),
    lemma: at(2),
    upos: at(3),
    xpos: at(4),
    feats: at(5),
    head: head === "_" ? null : Number.parseInt(head, 10),
    deprel: at(7),
    deps: at(8),
    misc: at(9),
  };
}

/**
 * Parse a CoNLL-U document.
 *
 * Multiword ranges and empty nodes are diverted to `Sentence.skipped` with the
 * position they held, so `writeConllu` can put them back. Sentences without a
 * `# sent_id` are keyed by ordinal, since corrections are addressed by
 * sentence id and an empty key would collide across sentences.
 */
export function parseConllu(text: string): Document {
  const sentences: Sentence[] = [];

  let comments: string[] = [];
  let tokens: Token[] = [];
  let skipped: SkippedLine[] = [];
  let lineIndex = 0;
  let started = false;

  const flush = (): void => {
    if (!started) return;
    sentences.push({
      sentId: metaValue(comments, "sent_id") ?? String(sentences.length),
      text: metaValue(comments, "text"),
      comments,
      tokens,
      skipped,
    });
    comments = [];
    tokens = [];
    skipped = [];
    lineIndex = 0;
    started = false;
  };

  for (const rawLine of text.split("\n")) {
    // Tolerate CRLF without carrying the \r into any column value.
    const line = rawLine.endsWith("\r") ? rawLine.slice(0, -1) : rawLine;

    if (line === "") {
      // A run of blank lines is one separator, not several empty sentences.
      flush();
      continue;
    }
    started = true;

    if (line.startsWith("#")) {
      comments.push(line);
      continue;
    }

    const cols = line.split("\t");
    const id = cols[0] ?? "";
    if (id.includes("-") || id.includes(".")) {
      skipped.push({
        kind: id.includes("-") ? "multiword" : "empty",
        id,
        lineIndex,
        raw: line,
      });
    } else {
      tokens.push(toToken(cols));
    }
    lineIndex += 1;
  }

  // A final sentence with no terminating blank line still counts.
  flush();

  return { sentences };
}
