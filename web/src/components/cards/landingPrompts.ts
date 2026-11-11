// The landing box opens with one of these, in one of three languages, picked
// once per page load. Add a prompt by adding a line to each language. Kept
// free of imports so the browser specs can match on it.
export const LANDING_PROMPTS: Record<string, string[]> = {
  en: [
    "What would you like to consider?",
    "Somewhere, someone said…",
    "What are you trying to recollect?",
  ],
  fr: [
    "Que voudriez-vous considérer ?",
    "Quelque part, quelqu’un a dit…",
    "Que cherchez-vous à vous rappeler ?",
  ],
  de: [
    "Was möchten Sie bedenken?",
    "Irgendwo hat jemand gesagt …",
    "Woran versuchen Sie sich zu erinnern?",
  ],
};

const all = Object.entries(LANDING_PROMPTS).flatMap(([lang, ps]) => ps.map((p) => [lang, p]));
const pick = Math.trunc(Math.random() * all.length);

// The index is in range by construction. `String()` only narrows the
// noUncheckedIndexedAccess `| undefined`: eslint rejects both `as` and `!`
// here, and a `??` fallback would add a branch no test can take.
export const LANDING_LANG = String(all.map(([lang]) => lang)[pick]);
export const LANDING_PROMPT = String(all.map(([, p]) => p)[pick]);

/** Matches whichever prompt this load picked, for `getByPlaceholder`.
 *  Whitespace matches `\s`: Testing Library normalises the narrow no-break
 *  space in the French prompts to a plain one before matching. */
export const LANDING_PROMPT_RE = new RegExp(
  `^(${all
    .map(([, p]) =>
      String(p)
        .replace(/[.*+?^${}()|[\]\\]/g, String.raw`\$&`)
        .replace(/\s/g, String.raw`\s`),
    )
    .join("|")})$`,
);
