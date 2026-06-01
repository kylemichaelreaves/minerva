// Tiny inline-markdown parser tailored to LLM chat output. Handles
// citations `[N]`, **bold**, *italic*, and `inline code`. Block-level
// constructs (headings, lists) are detected at the paragraph level by
// the caller (`Thread.tsx`).
//
// We deliberately roll our own rather than pulling in `marked` /
// `markdown-it`: the rendering surface is small (we already split into
// paragraphs server-side) and we need cite markers (`[N]`) interleaved
// with formatting. A full parser would also have to be paired with a
// sanitizer to prevent XSS — staying inline-and-fragment-only means the
// renderer in `Thread.tsx` always wraps text in JSX nodes, never
// `innerHTML`, so script injection isn't possible by construction.

import type { Citation } from "~/utils/types";

export type RichFragment =
  | string
  | { kind: "cite"; n: number }
  | { kind: "bold"; children: RichFragment[] }
  | { kind: "italic"; children: RichFragment[] }
  | { kind: "code"; text: string };

const _MAX_DEPTH = 4;

// Order matters: bold (`**...**`) must be matched before italic (`*...*`)
// because both start with `*`, and `inline code` is independent. Each
// alternative captures content into a different group so the dispatch
// below knows which variant matched.
const PATTERN = /\[(\d+)\]|\*\*([\s\S]+?)\*\*|\*((?!\s)[\s\S]+?(?<!\s))\*|`([^`\n]+)`/g;

export function parseRichText(text: unknown, depth = 0): RichFragment[] {
  if (typeof text !== "string" || !text) return [];
  if (depth > _MAX_DEPTH) return [text];

  const out: RichFragment[] = [];
  let cursor = 0;
  // matchAll consumes the regex's lastIndex; using a single regex with
  // alternations means each match returns one group set at a time.
  for (const m of text.matchAll(PATTERN)) {
    // TS types `RegExpMatchArray` indices as `string`, but alternation
    // groups are runtime-`undefined` for the branches that didn't match —
    // hence the `(string | undefined)[]` re-cast.
    const idx = m.index;
    if (idx > cursor) out.push(text.slice(cursor, idx));
    const groups = m as unknown as (string | undefined)[];
    if (groups[1] !== undefined) {
      out.push({ kind: "cite", n: parseInt(groups[1], 10) });
    } else if (groups[2] !== undefined) {
      out.push({ kind: "bold", children: parseRichText(groups[2], depth + 1) });
    } else if (groups[3] !== undefined) {
      out.push({ kind: "italic", children: parseRichText(groups[3], depth + 1) });
    } else {
      // groups[4] is the only remaining alternative once the others
      // are undefined; the explicit check would be flagged.
      out.push({ kind: "code", text: groups[4] ?? "" });
    }
    cursor = idx + m[0].length;
  }
  if (cursor < text.length) out.push(text.slice(cursor));
  return out;
}

// Block-level: detect a paragraph that's a heading (`# `, `## `, `### `),
// a bullet list item (`- `, `* `), or a horizontal rule (`---`/`***`/
// `___`). The body of the heading / list item still goes through
// `parseRichText` for inline formatting.
export type BlockKind = "paragraph" | "h1" | "h2" | "h3" | "list-item" | "hr";

export interface Block {
  kind: BlockKind;
  body: string;
}

// CommonMark: a thematic break is a line of three or more `-`, `*`, or
// `_` (optionally interspersed with spaces). We test against the trimmed
// paragraph since the server already split on `\n\n`.
const HR_RE = /^([-*_])(?:\s*\1){2,}\s*$/;

export function parseBlock(paragraph: string): Block {
  const t = paragraph.trimStart();
  if (HR_RE.test(t.trim())) return { kind: "hr", body: "" };
  if (t.startsWith("### ")) return { kind: "h3", body: t.slice(4) };
  if (t.startsWith("## ")) return { kind: "h2", body: t.slice(3) };
  if (t.startsWith("# ")) return { kind: "h1", body: t.slice(2) };
  if (t.startsWith("- ") || t.startsWith("* ")) {
    return { kind: "list-item", body: t.slice(2) };
  }
  return { kind: "paragraph", body: paragraph };
}

// Some LLM outputs cram a heading + bullet list into a single \n\n-
// delimited paragraph (e.g. `**Sources**\n- a\n- b`). The server's
// paragraph splitter doesn't break those apart, so we line-scan here
// when we see a paragraph that contains any list-item or heading line.
// Pure prose paragraphs are left as one block so multi-sentence text
// doesn't get torn into one-line stubs.
function paragraphHasBlockMarker(paragraph: string): boolean {
  const lines = paragraph.split("\n");
  if (lines.length < 2) return false;
  return lines.some((line) => {
    const t = line.trimStart();
    return (
      t.startsWith("- ") ||
      t.startsWith("* ") ||
      t.startsWith("# ") ||
      t.startsWith("## ") ||
      t.startsWith("### ") ||
      HR_RE.test(line.trim())
    );
  });
}

export function parseBlocks(paragraph: string): Block[] {
  if (!paragraphHasBlockMarker(paragraph)) return [parseBlock(paragraph)];
  // When a paragraph mixes prose and markers, treat each non-empty line
  // as its own block. Adjacent prose lines stay separate paragraphs —
  // not perfect CommonMark but matches LLM output where line breaks
  // usually do mean separate items.
  return paragraph
    .split("\n")
    .map((line) => line)
    .filter((line) => line.trim() !== "")
    .map(parseBlock);
}

// Re-export so callers don't also need to import from `./types`.
export type { Citation };
