// Reader chrome: the top toolbar (back button, work title,
// chunk-count crumb, EN/FR/DE translation-language pill).

import { Show } from "solid-js";
import type { TargetLang, WorkRange } from "~/utils/types";
import { TargetLangToggle } from "~/Reader/components/TargetLangToggle";

export function Chrome(props: {
  target: TargetLang;
  onTarget: (t: TargetLang) => void;
  meta: WorkRange | null;
  onBack?: () => void;
}) {
  return (
    <div class="chrome">
      <div class="chrome-l">
        <Show when={props.onBack}>
          <button class="ico-btn" aria-label="Back" onClick={() => props.onBack?.()}>
            <svg viewBox="0 0 24 24">
              <polyline points="14 6 8 12 14 18" />
            </svg>
          </button>
        </Show>
        <div class="work-title">
          <Show when={props.meta} fallback={<span class="author">Reader</span>}>
            {(m) => (
              <>
                <span class="author">{m().author}</span>
                <span class="sep">·</span>
                <span>{m().display_title || m().work}</span>
              </>
            )}
          </Show>
        </div>
      </div>
      <div class="chrome-r">
        <Show when={props.meta}>
          {(m) => (
            <span class="crumb">
              {m().total} chunks · {m().lang}
            </span>
          )}
        </Show>
        <TargetLangToggle
          variant="chrome"
          target={props.target}
          onTarget={props.onTarget}
        />
      </div>
    </div>
  );
}
