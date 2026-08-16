// Script-aware match folding for type-to-filter (#363).
//
// The question this answers: does what the reader typed match this option,
// allowing for diacritics they cannot easily type and scripts they may not have
// a keyboard for? `logos`, `λογος` and `λόγος` all have to find `λόγος`.
//
// Every transliterator here already existed — `romanize()` in `greek.ts`,
// `hebrew.ts` and `arabic.ts`. This module only chooses between them and folds
// the result.

import { fold } from "~/utils/fold";
import { containsArabic, romanize as romanizeArabic } from "~/utils/arabic";
import { containsGreek, romanize as romanizeGreek } from "~/utils/greek";
import { containsHebrew, romanize as romanizeHebrew } from "~/utils/hebrew";

interface Script {
  detect: (s: string) => boolean;
  romanize: (word: string) => string;
}

const SCRIPTS: Script[] = [
  { detect: containsGreek, romanize: romanizeGreek },
  { detect: containsHebrew, romanize: romanizeHebrew },
  { detect: containsArabic, romanize: romanizeArabic },
];

/** Every form `s` can be matched by: the folded original, plus a folded
 *  romanization for each non-Latin script it is written in.
 *
 *  **Detection runs on the original string.** It used to run on the
 *  mark-stripped one, because all three detectors were
 *  `/[\p{Script=X}\p{M}]/u` and that `\p{M}` arm answered `true` for any
 *  combining mark whatever its script — decomposed Latin read as Greek, Hebrew
 *  and Arabic at once and collected three junk romanizations. Stripping first
 *  meant only the `\p{Script=…}` arm could fire. #367 fixed the detectors, so
 *  the workaround is gone; the guarantee it bought is asserted in
 *  `searchFold.test.ts` rather than defended here.
 *
 *  **Romanization runs on the original, per whitespace token.** The marks carry
 *  the vowels — Greek's rough breathing becomes an `h`, Hebrew's shuruq a `u` —
 *  so romanizing a stripped form would throw them away. And `romanize()` is
 *  documented for a single *word*: its rough-breathing and initial-ρ rules are
 *  word-initial, so a whole-string call mis-transliterates every word after the
 *  first (`περὶ ῥητορικῆς` → `peri retorikes`, losing the `rh`). */
export function foldForms(s: string): string[] {
  const forms = [fold(s)];
  for (const script of SCRIPTS) {
    if (!script.detect(s)) continue;
    forms.push(
      fold(s.split(/(\s+)/).map((tok) => script.romanize(tok)).join("")),
    );
  }
  return forms;
}

/** True when `query` matches any of `fields`, each field folded to every form
 *  it has. An empty or whitespace-only query matches everything.
 *
 *  Fields are alternatives, not a phrase: a query cannot span the join between
 *  two of them. (`WorkScopeControl` concatenates author and title into one
 *  haystack and so allows that; it reads as a match with no visible cause.) */
export function matchesQuery(
  query: string,
  fields: (string | undefined)[],
): boolean {
  const q = fold(query.trim());
  if (q === "") return true;
  return fields.some(
    (field) =>
      field !== undefined && foldForms(field).some((form) => form.includes(q)),
  );
}
