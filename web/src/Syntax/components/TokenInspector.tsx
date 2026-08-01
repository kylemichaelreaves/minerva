import { For, Show } from "solid-js";
import type { SyntaxToken } from "~/api/syntaxApi";
import { POS_LABEL } from "~/Reader/wordInfoMorph";

// What one token is: lemma, part of speech, morphology, and where it attaches.
// The provenance line at the bottom is the point of the panel — it says
// whether you are looking at a person's judgement or a parser's guess.

/** `Case=Nom|Gender=Masc` → `[["Case","Nom"],["Gender","Masc"]]`. */
function parseFeats(feats: string | null): [string, string][] {
  if (!feats || feats === "_") return [];
  return feats
    .split("|")
    .map((pair) => pair.split("=", 2))
    .filter((kv): kv is [string, string] => kv.length === 2);
}

export interface TokenInspectorProps {
  token: SyntaxToken;
  /** The token this one attaches to; absent when it is the root. */
  head: SyntaxToken | undefined;
  onClose: () => void;
  /** Open the relation picker on this token. */
  onRelabel?: () => void;
  /** Drop the correction on this token, if it has one. */
  onRevert?: () => void;
  /** What the parser said before a human changed it — the "was obj". */
  wasDeprel?: string | null;
}

export function TokenInspector(props: TokenInspectorProps) {
  const feats = () => parseFeats(props.token.feats);

  // Returns the tag itself, never a boolean. `<Show when={x && x !== "_"}>`
  // hands the *condition* to the child callback, so the callback would
  // receive `true` and Solid renders that as nothing — a labelled row with an
  // empty value. Narrow to the value here instead.
  const xpos = (): string | undefined => {
    const tag = props.token.xpos;
    return tag !== null && tag !== "" && tag !== "_" ? tag : undefined;
  };

  return (
    <aside class="syn-panel" aria-label={`Token ${String(props.token.id)}`}>
      <div class="syn-ph">
        <span class="t">{props.token.form}</span>
        <span class="s">token {props.token.id}</span>
      </div>
      <div class="syn-rows">
        <div class="syn-kv">
          <span class="k">Lemma</span>
          <span class="v serif">{props.token.lemma ?? "—"}</span>
        </div>
        <div class="syn-kv">
          <span class="k">UPOS</span>
          <span class="v">
            {props.token.upos ?? "—"}
            <Show when={props.token.upos && POS_LABEL[props.token.upos]}>
              {(label) => <span style={{ color: "var(--syn-ink-4)" }}> · {label()}</span>}
            </Show>
          </span>
        </div>
        <Show when={xpos()}>
          {(tag) => (
            <div class="syn-kv">
              {/* The German tagset draws distinctions UPOS cannot — PRF for a
                  reflexive, which is exactly what an expl:pv correction is about. */}
              <span class="k">XPOS</span>
              <span class="v syn-mono">{tag()}</span>
            </div>
          )}
        </Show>
        <div class="syn-kv">
          <span class="k">Head</span>
          <span class="v">
            <Show
              when={props.head}
              fallback={<span>{props.token.head === 0 ? "root of the sentence" : "unparsed"}</span>}
            >
              {(h) => (
                <>
                  <span class="serif" style={{ "font-family": "var(--syn-tok)" }}>
                    {h().form}
                  </span>
                  <span style={{ color: "var(--syn-ink-4)" }}> · {h().id}</span>
                </>
              )}
            </Show>
          </span>
        </div>
        <div class="syn-kv">
          <span class="k">Relation</span>
          <span class="v" style={props.token.corrected ? { color: "var(--syn-corr)" } : undefined}>
            {props.token.deprel ?? "—"}
          </span>
        </div>
        <Show when={feats().length > 0}>
          <div class="syn-kv" style={{ "align-items": "start" }}>
            <span class="k">Feats</span>
            <span class="syn-feats">
              <For each={feats()}>
                {([k, v]) => (
                  <span class="syn-feat">
                    <b>{k}</b>={v}
                  </span>
                )}
              </For>
            </span>
          </div>
        </Show>
      </div>
      <div class="syn-prov">
        <span class={`syn-dot${props.token.corrected ? " c" : ""}`} />
        {props.token.corrected ? "Hand-corrected" : "Machine-parsed · uncorrected"}
        {/* The "was obj" the design asks for. No author: this is a
            single-operator tool and there is no user to name. */}
        <Show when={props.token.corrected && props.wasDeprel}>
          {(was) => (
            <>
              {" · was "}
              <span class="syn-was">{was()}</span>
            </>
          )}
        </Show>
      </div>

      <Show when={props.onRelabel ?? props.onRevert}>
        <div class="syn-pact">
          <Show when={props.onRelabel}>
            <button type="button" class="pri" onClick={() => props.onRelabel?.()}>
              Relabel <span class="syn-kbd">L</span>
            </button>
          </Show>
          <Show when={props.token.corrected && props.onRevert}>
            <button type="button" onClick={() => props.onRevert?.()}>
              Revert
            </button>
          </Show>
        </div>
      </Show>
    </aside>
  );
}
