// Glyphs for dominant codes from the API (`corpus_registry`). The map
// below is generated from `data/authors/manifest.yaml` by
// `scripts/generate_author_artifacts.py` — do not edit the marked block
// by hand.

/** Gutter / sidebar glyphs for dominant codes. */
// BEGIN DOMINANT_GLYPH
export const PHIL_DOMINANT_GLYPH: Record<string, string> = {
  'A': 'Α',
  'B': 'B',
  'C': 'C',
  'D': 'D',
  'E': 'E',
  'F': 'F',
  'G': 'G',
  'H': 'H',
  'I': 'I',
  'J': 'ת',
  'K': 'K',
  'L': 'L',
  'M': 'M',
  'N': 'N',
  'O': 'Ο',
  'P': 'Π',
  'Q': 'ق',
  'R': 'R',
  'S': 'S',
  'T': 'T',
  'U': 'U',
  'V': 'V',
  'W': 'W',
  'X': 'X',
  'Y': 'Y',
  'Z': 'Z',
  'a': 'α',
  'b': 'b',
  'c': 'c',
  'e': 'ε',
  'g': 'g',
  'h': 'h',
  'l': 'l',
  'o': 'o',
  'r': 'r',
  's': 'σ',
  't': 'τ',
  'v': 'v',
  'Æ': 'Æ',
  'Ω': 'Ω',
};
// END DOMINANT_GLYPH

export function dominantGlyph(code: string | null | undefined): string {
  if (!code) return "Π";
  return PHIL_DOMINANT_GLYPH[code] ?? code;
}

export function dominantName(code: string | null | undefined): string {
  if (!code) return "Plato dominant";
  return `${code} dominant`;
}
