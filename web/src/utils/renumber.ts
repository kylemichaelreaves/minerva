// Renumber an LLM response's citations into the order they're first
// mentioned in the prose. The server returns citations in retrieval-rank
// order (`[1]` = best match), but the LLM cites them in whatever order
// best supports its argument — so the prose often opens with `[3]` while
// the margin column starts at `[1]`. Footnote tradition is "N is the Nth
// citation encountered in the text," and that's what readers expect.
//
// Pure function, side-effect free. Citations not referenced in the prose
// (e.g. retrieval matches the LLM chose not to use) keep their relative
// order and trail the cited ones.

import type { Citation } from "~/utils/types";

export interface RenumberInput {
  paragraphs: string[];
  citations: Citation[];
}

export function renumberCitations({ paragraphs, citations }: RenumberInput): RenumberInput {
  if (!citations.length) return { paragraphs, citations };

  // First, scan paragraphs left-to-right and record the order of first
  // appearance for each numeric marker.
  const firstSeen: number[] = [];
  const seen = new Set<number>();
  const cite = /\[(\d+)\]/g;
  for (const p of paragraphs) {
    for (const m of p.matchAll(cite)) {
      const n = Number(m[1]);
      if (Number.isFinite(n) && !seen.has(n)) {
        seen.add(n);
        firstSeen.push(n);
      }
    }
  }

  // Append uncited citations in their original order (preserves the
  // retrieval-rank tail behavior — they're still useful as evidence even
  // if the LLM didn't quote them directly).
  const finalOrder: number[] = [...firstSeen];
  for (const c of citations) {
    if (!seen.has(c.n)) finalOrder.push(c.n);
  }

  // Build the old→new mapping. Drop unknowns (cite refers to a citation
  // that doesn't exist in the list — shouldn't happen but be defensive).
  const valid = new Set(citations.map((c) => c.n));
  const remap = new Map<number, number>();
  let next = 1;
  for (const oldN of finalOrder) {
    if (valid.has(oldN) && !remap.has(oldN)) {
      remap.set(oldN, next++);
    }
  }

  // Rewrite prose markers using the mapping. Markers that don't resolve
  // (orphan references) are left as-is so the corruption is visible
  // rather than silently dropped.
  const newParagraphs = paragraphs.map((p) =>
    p.replace(cite, (whole, digits) => {
      const mapped = remap.get(Number(digits));
      return mapped === undefined ? whole : `[${mapped}]`;
    }),
  );

  // Reorder citations to match and rewrite `.n` in place.
  const byOldN = new Map(citations.map((c) => [c.n, c]));
  const newCitations: Citation[] = [];
  for (const oldN of finalOrder) {
    const c = byOldN.get(oldN);
    const newN = remap.get(oldN);
    if (c && newN !== undefined) {
      newCitations.push({ ...c, n: newN });
    }
  }

  return { paragraphs: newParagraphs, citations: newCitations };
}
