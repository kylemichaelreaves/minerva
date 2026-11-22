// Shared empty/error states for the concordance (F1 index + F2 detail).
// Both pages render the same `.conc-empty` block, and three call sites
// repeated the identical "lemma cache missing → run the lemmatizer" hint
// (title + body + `$ minerva terms lemmatize` command + footer). Factored
// here so the instructional copy and markup live in one place.

import type { JSX } from "@solidjs/web";

/** Generic centered empty/error panel: an icon glyph, a title, and
 *  caller-supplied body content. */
export function ConcEmpty(props: { icon: string; title: JSX.Element; children?: JSX.Element }) {
  return (
    <div class="conc-empty">
      <div class="icon">{props.icon}</div>
      <div class="ttl">{props.title}</div>
      {props.children}
    </div>
  );
}

/** The "no lemma cache for <lang>" hint, shown whenever spaCy hasn't
 *  lemmatised an edition yet. `body` explains the consequence for the
 *  current page; `footer` is the `.broaden` line (a retry link on the
 *  index, a timing note on the detail page). */
export function LemmaCacheEmpty(props: {
  lang: string;
  title: JSX.Element;
  body: JSX.Element;
  footer: JSX.Element;
}) {
  return (
    <ConcEmpty icon="!" title={props.title}>
      <div>{props.body}</div>
      <div class="cmd">$ minerva terms lemmatize --lang {props.lang}</div>
      <div class="broaden" style={{ "margin-top": "4px" }}>
        {props.footer}
      </div>
    </ConcEmpty>
  );
}
