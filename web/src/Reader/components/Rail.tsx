// Right-rail content: word info + translate states. The Reader owns
// the two state machines (`RailState`, `WordInfoState`) and passes
// them as props; everything below is presentational.
//
// On mobile (design 3d) the rail becomes a bottom sheet with three
// tabs (Translation · Lemma · Refs). On desktop everything still
// renders in vertical sequence as before — the tab UI is gated by
// `.rail-tabs` CSS, which is `display: none` outside the mobile
// media query.

import { Show, createEffect, createSignal } from "solid-js";
import { classnames } from "~/utils/util";
import { LoadingDots } from "~/components/LoadingDots";
import type { TargetLang } from "~/utils/types";
import { TargetLangToggle, disabledLangFor } from "~/Reader/components/TargetLangToggle";
import { RailDismissFooter } from "~/Reader/components/RailDismissFooter";
import { labelFor } from "~/Reader/railLabels";
import type { RailState, WordInfoState } from "~/Reader/types";
import { WordInfoBlock } from "~/Reader/components/WordInfoBlock";
import { ConcordanceTabPanel } from "~/Reader/components/ConcordanceTabPanel";

type Tab = "translation" | "lemma" | "refs" | "concord";

export function RailContent(props: {
  state: RailState;
  wordInfo: WordInfoState;
  target: TargetLang;
  onTarget?: (t: TargetLang) => void;
  onRetry: () => void;
  onDismiss: () => void;
  onLoadMoreSamples: () => void;
  /** Navigate to the corpus concordance for the clicked lemma.
   *  Optional — when absent, the rail's WordInfoBlock hides the
   *  "See all in concordance" CTA. */
  onOpenConcordance?: (lemma: string, lang: string) => void;
  /** Currently-open work's title (the URL slug). Drives the
   *  Concordance tab's work-scoped mini-leaderboard. */
  workTitle?: string;
  /** Navigate to the concordance scoped to ``workTitle``. */
  onOpenWorkConcordance?: () => void;
  /** The source text's language. Used to disable the matching
   *  target-lang chip (translating Nietzsche → German is a no-op).
   *  Non-target source langs (grc, lat, heb, ara…) leave all chips
   *  enabled. */
  sourceLang?: string;
}) {
  const sourceText = (): string | null => {
    const s = props.state;
    if (s.kind === "loading" || s.kind === "ready" || s.kind === "error") {
      return s.source;
    }
    return null;
  };
  const refText = (): string | null => {
    const s = props.state;
    if (s.kind === "loading" || s.kind === "ready" || s.kind === "error") {
      return s.ref;
    }
    return null;
  };
  const isCrossChunk = (): boolean => {
    const r = refText();
    return r?.includes("—") ?? false;
  };

  // Tab selection — mobile-only UI, but the signal lives at the
  // component level so reactivity covers desktop renders too (where
  // CSS hides the tab strip but content is still rendered serially
  // as before via `:where(.rail.mobile-tabs-on)` gating).
  const hasLemma = (): boolean =>
    props.wordInfo.kind === "ready" || props.wordInfo.kind === "loading";
  const [tab, setTab] = createSignal<Tab>("translation");
  // Auto-flip to the Lemma tab when a word lookup arrives — matches
  // the design 3c → 3d flow (long-press → bottom sheet on the lemma).
  // We flip on the *transition* into an active lookup (idle/error →
  // loading/ready): tapping a word is itself an explicit gesture, so
  // it wins over a previous manual tab pick, while later manual picks
  // are honored until the next lookup arrives.
  let prevLookupActive = hasLemma();
  createEffect(() => {
    const active = hasLemma();
    if (active && !prevLookupActive) setTab("lemma");
    prevLookupActive = active;
  });
  const activeTab = (): Tab => tab();

  return (
    <Show when={props.state.kind !== "idle"}>
      <button
        type="button"
        class="rail-close"
        aria-label="Close drawer"
        title="Close (Esc)"
        onClick={() => {
          props.onDismiss();
        }}
      >
        <svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true">
          <line x1="6" y1="6" x2="18" y2="18" />
          <line x1="18" y1="6" x2="6" y2="18" />
        </svg>
      </button>
      <div class="pin">
        <span>Selection</span>
        <span class="ref">
          <Show when={props.state.kind !== "awaiting"} fallback={"—"}>
            {(() => {
              const ref = () =>
                (props.state as Extract<
                  RailState,
                  { kind: "loading" | "ready" | "error" }
                >).ref;
              return <>{ref()}</>;
            })()}
          </Show>
        </span>
      </div>

      {/* Mobile tab strip — desktop hides via .rail-tabs { display:none }
          outside the @media (max-width: 768px) block. Order matches
          design 3d: Translation · Lemma · Refs. */}
      <div class="rail-tabs" role="tablist">
        <button
          type="button"
          role="tab"
          aria-selected={activeTab() === "translation"}
          class={classnames("rail-tab", activeTab() === "translation" && "cur")}
          onClick={() => setTab("translation")}
        >
          Translation
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={activeTab() === "lemma"}
          class={classnames("rail-tab", activeTab() === "lemma" && "cur")}
          onClick={() => setTab("lemma")}
          disabled={!hasLemma()}
        >
          Lemma <span class="rail-tab-sub">· LSJ</span>
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={activeTab() === "refs"}
          class={classnames("rail-tab", activeTab() === "refs" && "cur")}
          onClick={() => setTab("refs")}
          disabled
        >
          Refs
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={activeTab() === "concord"}
          class={classnames("rail-tab", activeTab() === "concord" && "cur")}
          onClick={() => setTab("concord")}
        >
          Concord
        </button>
      </div>

      <div class="rail-tabpanel" data-tab="lemma" aria-hidden={activeTab() !== "lemma"}>
        <WordInfoBlock
          state={props.wordInfo}
          onLoadMore={props.onLoadMoreSamples}
          onOpenConcordance={props.onOpenConcordance}
        />
      </div>

      <div class="rail-tabpanel" data-tab="translation" aria-hidden={activeTab() !== "translation"}>
        <Show
          when={
            sourceText() && props.wordInfo.kind === "idle" && isCrossChunk()
          }
        >
          <div class="rail-ribbon">
            <span class="pip" />
            <span>Selection crosses a chunk boundary · refs joined</span>
          </div>
        </Show>

        <Show when={props.onTarget && sourceText() !== null}>
          <TargetLangToggle
            variant="rail"
            target={props.target}
            onTarget={props.onTarget!}
            disabledLang={disabledLangFor(props.sourceLang)}
          />
        </Show>

        <div class="target-label">
          <span>{labelFor(props.target)}</span>
          <Show
            when={
              props.state.kind === "ready" &&
              (props.state).response.cached
            }
          >
            <span class="tag">cached</span>
          </Show>
        </div>

        <Show when={props.state.kind === "awaiting"}>
          <div class="translation translation-awaiting">
            Select Greek or German text in the passage to translate it.
          </div>
          <RailDismissFooter meta="ready" onDismiss={props.onDismiss} />
        </Show>

        <Show when={props.state.kind === "loading"}>
          <div class="translation">
            <span class="progress">
              <LoadingDots />
              Translating
            </span>
          </div>
        </Show>

        <Show when={props.state.kind === "ready"}>
          {(_) => {
            const ready = props.state as Extract<RailState, { kind: "ready" }>;
            return (
              <>
                <div class="translation">{ready.response.translated_text}</div>
                <Show when={ready.response.literal_text}>
                  <div class="translation-literal">
                    <div class="translation-literal-label">Literal</div>
                    <div class="translation-literal-text">
                      {ready.response.literal_text}
                    </div>
                  </div>
                </Show>
                <RailDismissFooter
                  meta={ready.response.cached ? "cached" : ready.response.model}
                  onDismiss={props.onDismiss}
                />
              </>
            );
          }}
        </Show>
      </div>

      <div class="rail-tabpanel" data-tab="refs" aria-hidden={activeTab() !== "refs"}>
        {/* Refs tab is a placeholder for v1 — the desktop xref-card
            popover serves the same role and is currently unreachable
            via this sheet. */}
      </div>

      <div
        class="rail-tabpanel"
        data-tab="concord"
        aria-hidden={activeTab() !== "concord"}
      >
        <ConcordanceTabPanel
          workTitle={props.workTitle ?? null}
          lang={props.sourceLang ?? "deu"}
          onOpenWorkScope={() => props.onOpenWorkConcordance?.()}
          onOpenLemma={(lemma) =>
            props.onOpenConcordance?.(lemma, props.sourceLang ?? "deu")
          }
        />
      </div>

      <Show when={props.state.kind === "error"}>
        {(_) => {
          const err = props.state as Extract<RailState, { kind: "error" }>;
          return (
            <>
              <div class="err-icon">
                <svg
                  width="14"
                  height="14"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="1.4"
                >
                  <circle cx="12" cy="12" r="9" />
                  <line x1="12" y1="8" x2="12" y2="13" />
                  <circle cx="12" cy="16.5" r="0.6" fill="currentColor" />
                </svg>
              </div>
              <div class="err-title">The translation could not be retrieved.</div>
              <div class="err-body">{err.message}</div>
              <div class="err-actions">
                <button
                  class="btn-link"
                  onClick={() => {
                    props.onRetry();
                  }}
                >
                  Retry
                </button>
                <button
                  class="btn-link ghost"
                  onClick={() => {
                    props.onDismiss();
                  }}
                >
                  Dismiss
                </button>
              </div>
            </>
          );
        }}
      </Show>
    </Show>
  );
}
