import { For, Show } from "solid-js";
import type { TargetLang } from "~/utils/types";

export const TARGET_LANGS: TargetLang[] = ["eng", "fra", "deu"];

export const TARGET_CHIP_LABEL: Record<TargetLang, string> = {
  eng: "EN",
  fra: "FR",
  deu: "DE",
};

/** Spelled out for the chip tooltips. `EN` alone does not say what pressing
 *  it will do, and in the chrome variant that was the whole problem (#257). */
const TARGET_FULL_NAME: Record<TargetLang, string> = {
  eng: "English",
  fra: "French",
  deu: "German",
};

export function TargetLangToggle(props: {
  target: TargetLang;
  onTarget: (t: TargetLang) => void;
  /** `chrome` uses `.lang`; `rail` uses `.pill`; `sheet` uses mobile settings layout. */
  variant: "chrome" | "rail" | "sheet";
  /** When set, the chip for this lang is disabled (no-op on click,
   *  dimmed, aria-disabled). Used to grey out the target that matches
   *  the source text's language — e.g. don't offer "translate to
   *  German" while reading Nietzsche in German. */
  disabledLang?: TargetLang;
}) {
  const isDisabled = (t: TargetLang) => t === props.disabledLang;

  // One return, switching on `variant` reactively (solid/components-return-once).
  return (
    <Show
      when={props.variant !== "rail"}
      fallback={
      <div class="rail-langrow">
        <span class="label">Target</span>
        <span class="pill">
          <For each={TARGET_LANGS}>
            {(t) => (
              <button
                type="button"
                class={props.target === t ? "on" : ""}
                disabled={isDisabled(t)}
                aria-disabled={isDisabled(t) ? "true" : "false"}
                title={
                  isDisabled(t) ? "Source text is already in this language" : undefined
                }
                onClick={() => {
                  if (isDisabled(t)) return;
                  props.onTarget(t);
                }}
              >
                {TARGET_CHIP_LABEL[t]}
              </button>
            )}
          </For>
        </span>
      </div>
      }
    >
      {/* The chrome variant, with a visible "Translate" label.

          Without it this control sat immediately after the crumb naming the
          source language (`454 chunks · lat`), as a segmented control with one
          member active — the idiom for "current choice among alternatives". It
          was read as an edition switcher, and pressing it changes no language:
          it opens the translate rail. The only statement of intent was the
          non-visual `aria-label`. See #257. */}
    <span class="lang-group">
      <span class="lang-label">Translate</span>
      <span class="lang" role="tablist" aria-label="Translation language">
        <For each={TARGET_LANGS}>
          {(t) => (
            <button
              class={props.target === t ? "on" : ""}
              disabled={isDisabled(t)}
              aria-disabled={isDisabled(t) ? "true" : "false"}
              title={
                isDisabled(t)
                  ? "Source text is already in this language"
                  : `Translate selected text into ${TARGET_FULL_NAME[t]}`
              }
              onClick={() => {
                if (isDisabled(t)) return;
                props.onTarget(t);
              }}
            >
              {TARGET_CHIP_LABEL[t]}
            </button>
          )}
        </For>
      </span>
    </span>
    </Show>
  );
}

/** Map a Reader source-lang code (3-letter ISO, e.g. "grc", "lat",
 *  "fra", "deu", "heb", "ara", "eng") to the target-lang it should
 *  disable in the toggle. Languages that aren't a target option
 *  (Greek, Latin, Hebrew, Arabic, …) return `undefined` so the
 *  toggle stays fully enabled — the typical philological case. */
export function disabledLangFor(sourceLang: string | undefined): TargetLang | undefined {
  if (sourceLang === "eng" || sourceLang === "fra" || sourceLang === "deu") {
    return sourceLang;
  }
  return undefined;
}
