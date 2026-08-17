/** Blank out JS/TS comments while preserving every character position.
 *
 *  Written for `routeConstruction.test.ts` (#349), whose guards decide
 *  whether a route is reachable by regex over source text. With no notion
 *  of what is live code, a **commented-out** constructor satisfies the
 *  reachability half — the exact state #232 was filed on, one comment
 *  marker away, and the guard stayed green through it.
 *
 *  Comment bytes become spaces; newlines are kept as newlines. That is the
 *  whole reason this blanks rather than strips: `constructorsOf` reports
 *  `file:line` derived from a character offset
 *  (`text.slice(0, m.index).split("\n").length`), so a transform that
 *  changed length or line count would corrupt every location the guard
 *  prints — turning a true failure into a wild-goose chase.
 *
 *  Scope, deliberately: this is a scanner, not a parser. It tracks string
 *  and template literals so a `//` inside `"https://…"` is not read as a
 *  comment, and it does **not** track regex literals. A regex containing
 *  `//` therefore blanks the rest of its line. That direction is safe: the
 *  worst case is a constructor going unseen, which fails the guard loudly,
 *  rather than a commented-out one being counted, which is the silent
 *  failure this exists to stop. The alternative — a real TS AST walk — is
 *  option 2 in #349 and buys precision this property does not need.
 */
export function blankComments(text: string): string {
  const out = text.split("");
  const n = text.length;

  const blank = (from: number, to: number): void => {
    for (let k = from; k < to; k++) {
      if (out[k] !== "\n") out[k] = " ";
    }
  };

  let i = 0;
  while (i < n) {
    const c = text[i];
    const d = text[i + 1];

    if (c === "/" && d === "/") {
      let j = i;
      while (j < n && text[j] !== "\n") j++;
      blank(i, j);
      i = j;
      continue;
    }

    if (c === "/" && d === "*") {
      let j = i + 2;
      while (j < n && !(text[j] === "*" && text[j + 1] === "/")) j++;
      j = Math.min(j + 2, n);
      blank(i, j);
      i = j;
      continue;
    }

    if (c === '"' || c === "'" || c === "`") {
      const quote = c;
      let j = i + 1;
      while (j < n) {
        if (text[j] === "\\") {
          j += 2;
          continue;
        }
        if (text[j] === quote) {
          j++;
          break;
        }
        // An unterminated single/double-quoted string cannot span lines;
        // bail at the newline so one stray quote does not swallow the
        // rest of the file.
        if (quote !== "`" && text[j] === "\n") break;
        j++;
      }
      i = j;
      continue;
    }

    i++;
  }

  return out.join("");
}
