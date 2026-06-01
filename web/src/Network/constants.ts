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
