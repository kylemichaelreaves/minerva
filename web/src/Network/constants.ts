export const VERIFICATION_METHODS = [
  "manual",
  "rule_strong",
  "rule+embed",
  "rule+embed+llm",
  "rule_weak",
] as const;

export const CORPUS_BUCKETS: { key: string; label: string }[] = [
  { key: "scrip", label: "Scripture" },
  { key: "class", label: "Classical" },
  { key: "med", label: "Medieval" },
  { key: "em", label: "Early Modern" },
  { key: "mod", label: "Modern" },
];

export const SOURCE_METHODS = [...VERIFICATION_METHODS];

/** The confidence-floor chip label, shared by the desktop header and
 *  the mobile filters bar. It was four byte-identical lines in both
 *  (#507) — the kind of duplication that lets one surface drift from
 *  the other while both claim to render the same filter state.
 *
 *  `undefined` means "no explicit floor", which the API treats as 0.8;
 *  a floor of exactly 0 is a real value and renders as such rather
 *  than falling back. One decimal below 1, none at or above it. */
export function confLabel(minConfidence: number | undefined): string {
  return minConfidence === undefined
    ? "≥0.8"
    : `≥${minConfidence.toFixed(minConfidence >= 1 ? 0 : 1)}`;
}
