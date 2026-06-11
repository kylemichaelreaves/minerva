import type { Citation, CitationFragment } from "~/utils/types";

/**
 * Split a paragraph string into a list of fragments where citation
 * markers `[N]` are surfaced as `{kind: 'cite', n}` objects and
 * everything else is left as a string. The caller decides how to
 * render each fragment (Thread.tsx wraps cites in <sup>).
 *
 *   splitCitations('foo [1] bar [12].') ===
 *     ['foo ', {kind:'cite', n:1}, ' bar ', {kind:'cite', n:12}, '.']
 *
 * Only digit-only `[N]` tags match. Locator-style `[Plato, Republic 514a]`
 * is left as text so cite_style='locator' answers don't get mangled.
 */
export function splitCitations(text: unknown): CitationFragment[] {
  if (typeof text !== "string" || !text) return [];
  return text.split(/(\[\d+\])/g).map<CitationFragment>((part) => {
    const digits = /^\[(\d+)\]$/.exec(part)?.[1];
    return digits !== undefined ? { kind: "cite", n: parseInt(digits, 10) } : part;
  });
}

// Note: the corpus → dominant mapping lives server-side in
// `_CORPUS_TO_DOMINANT` (src/minerva/server.py) and is delivered to the
// client via the `dominant` field on each chat response. There is no
// frontend copy — having one was a drift hazard and nothing in
// production consumed it.

// Re-export for convenience.
export type { Citation };
