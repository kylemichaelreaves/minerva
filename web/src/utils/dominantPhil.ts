// Glyphs for single-letter dominant codes from the API (`corpus_registry`).
// Display names come from the server via each turn's `dominant` code; unknown
// codes fall back to "${code} dominant".

/** Gutter / sidebar glyphs for dominant codes. */
export const PHIL_DOMINANT_GLYPH: Record<string, string> = {
  P: "Π",
  A: "Α",
  H: "H",
  K: "K",
  O: "Ο",
  D: "D",
  S: "S",
  B: "B",
  N: "N",
  M: "M",
  Q: "ق",
  J: "ת",
  F: "F",
  I: "I",
  L: "L",
  R: "R",
  U: "U",
  T: "T",
  E: "E",
  X: "X",
  Y: "Y",
  G: "G",
  W: "W",
  V: "V",
  Z: "Z",
  Ω: "Ω",
  Æ: "Æ",
  a: "α",
  s: "σ",
  e: "ε",
  b: "b",
  c: "c",
  g: "g",
  h: "h",
};

export function dominantGlyph(code: string | null | undefined): string {
  if (!code) return "Π";
  return PHIL_DOMINANT_GLYPH[code] ?? code;
}

export function dominantName(code: string | null | undefined): string {
  if (!code) return "Plato dominant";
  return `${code} dominant`;
}
