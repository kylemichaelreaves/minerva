// Primary-source reader. Renders a contiguous range of source-language
// chunks (Greek for Perseus, German for Hegel/Kant) with line numbers,
// and opens a right-rail translation surface when the user selects text.
// Translation requests are cache-first on the server (see
// `src/minerva/translations.py`); the client just calls /api/translate.
//
// This file is the orchestrator — it composes hooks that own each
// state machine and wires their callbacks together:
//
//   useWorkRange         — windowed range fetch + occurrence/refs maps
//   useTranslateRail     — rail signal + target lang + runTranslate
//   useWordLookup        — wordInfo + lemmaHighlights + onWordClick
//   useSelectionToolbar  — selToolbar + pinnedHighlights + commit*
//   useXrefCard          — openRefCard + toggle
//   useTermCard          — openCard + URL `?term=` bidirectionality
//
// Presentational pieces (Chrome, Lines, Rail, SelectionToolbar) live
// in their sibling files; pure helpers (inferRefFromSelection,
// occurrenceFor) live in ./utils.

import { Show, createEffect, onMount } from "solid-js";
import { classnames } from "~/utils/util";
import ReferenceCard from "~/components/ReferenceCard";
import TermCard from "~/components/TermCard";
import { useMobileShell } from "~/components/MobileShellContext";
import { useEscape } from "~/hooks/useEscape";
import { useInfiniteScrollSentinel } from "~/hooks/useInfiniteScrollSentinel";
import { Chrome } from "~/Reader/components/Chrome";
import { ReaderHead } from "~/Reader/components/ReaderHead";
import { useSelectionToolbar } from "~/Reader/useSelectionToolbar";
import { useTermCard } from "~/Reader/useTermCard";
import { useTranslateRail } from "~/Reader/useTranslateRail";
import { useWordHoverTranslations } from "~/Reader/useWordHoverTranslations";
import { useWordLookup } from "~/Reader/useWordLookup";
import { useWorkRange } from "~/Reader/useWorkRange";
import { useXrefCard } from "~/Reader/useXrefCard";
import { Lines, type XrefMap } from "~/Reader/components/Lines";
import { RailContent } from "~/Reader/components/Rail";
import { ReaderMobileSettingsSheet } from "~/Reader/components/ReaderMobileSettingsSheet";
import { SelectionToolbar } from "~/Reader/components/SelectionToolbar";
import "~/Reader/reader.css";

interface ReaderProps {
  workId: string;
  /** ISO 639-3. Defaults to "grc" for Plato/Aristotle; caller can hint
   *  "deu" for Hegel/Kant. The reader exposes a lang chip in the
   *  chrome for the TARGET (translation) language, not the source. */
  sourceLang?: string;
  /** Disambiguates same-titled works (Luther 1912 vs 1545 share every
   *  book title AND lang). Optional — the server falls back to one
   *  deterministic edition for legacy bookmarks. */
  author?: string;
  /** When set, open the reader at the window around this chunk and
   *  scroll it into view. Used by citation locator clicks from chat. */
  focusChunkId?: string;
  /** Term-card open state, mirrored from the URL (`?term=<id>`). When
   *  set on first paint, the card resumes (without a click anchor —
   *  the card falls back to viewport-corner positioning). The Reader
   *  pushes new ids back via onOpenTermIdChange so click-to-open and
   *  the URL stay in sync. */
  openTermId?: number;
  onOpenTermIdChange?: (id: number | null) => void;
  onClose?: () => void;
}

export default function Reader(props: ReaderProps) {
  let stageRef: HTMLDivElement | undefined;
  const shell = useMobileShell();

  onMount(() => {
    shell.registerSurfaceActions({
      openReaderSettings: () => shell.setReaderSettingsOpen(true),
    });
  });

  const { range, occMap, refsMap, loadError, loadMore, hasMore, loadingMore } =
    useWorkRange(
      {
        get workId() {
          return props.workId;
        },
        get sourceLang() {
          return props.sourceLang;
        },
        get author() {
          return props.author;
        },
        get focusChunkId() {
          return props.focusChunkId;
        },
      },
      () => stageRef,
    );

  // Infinite-scroll sentinel. We mount an empty <div> below the
  // rendered chunks and observe it with an IntersectionObserver
  // scoped to the scrolling `.stage` element, pre-fetching 800px
  // before the user runs out of text. ``useWorkRange`` gates against
  // re-entry while a request is in flight, so repeated observer fires
  // collapse to one network call per page.
  //
  // The shared hook's signal-based ref callback matters here: the
  // sentinel lives inside `<Show when={range()}>`, so on first run it
  // doesn't exist yet — the previous hand-rolled effect read plain
  // `let` refs, tracked zero dependencies, returned early, and never
  // re-ran; the observer was never attached and works longer than one
  // page could not be scrolled past chunk 80.
  const setSentinelEl = useInfiniteScrollSentinel(
    hasMore,
    () => void loadMore(),
    { root: () => stageRef, rootMargin: "800px 0px" },
  );

  const railApi = useTranslateRail();

  // Auto-shift the rail's target language away from the source's
  // language. Avoids landing on a disabled chip when reading an
  // English text (default target is also "eng"). Greek/Latin/Hebrew
  // sources never collide with the three target options, so no shift.
  createEffect(() => {
    const src = props.sourceLang;
    if (src === "eng" && railApi.target() === "eng") {
      railApi.setTargetLang("deu");
    } else if (src === "fra" && railApi.target() === "fra") {
      railApi.setTargetLang("eng");
    } else if (src === "deu" && railApi.target() === "deu") {
      railApi.setTargetLang("eng");
    }
  });

  const hoverTranslations = useWordHoverTranslations({
    rail: railApi.rail,
    target: railApi.target,
  });

  const wordLookup = useWordLookup({
    range,
    onTranslateRequest: railApi.runTranslate,
  });

  const selection = useSelectionToolbar({
    getStage: () => stageRef,
    workId: () => props.workId,
    onTranslateRequest: (source, ref) => {
      hoverTranslations.clearPending();
      railApi.runTranslate(source, ref);
    },
    onLookupRequest: (word, chunkId, offset, lineEl) => {
      hoverTranslations.registerWordClick(chunkId, offset, word);
      wordLookup.onWordClick(word, chunkId, offset, lineEl);
    },
  });

  const xref = useXrefCard({ refsMap });

  const term = useTermCard({
    openTermId: () => props.openTermId,
    onOpenTermIdChange: (id) => props.onOpenTermIdChange?.(id),
  });

  /** Composed dismiss: aborts the rail + word-lookup, then promotes
   *  any active pinned highlight to its saved underline marker so the
   *  user can re-open the cached translation later. The translations
   *  table is the persistence layer; the marker here is in-memory
   *  only (survives until reload). */
  function dismiss() {
    railApi.reset();
    wordLookup.reset();
    selection.markAllPinnedSaved();
  }

  // Esc dismisses the rail whenever it's open. Gated on `kind !==
  // "idle"` so a stray Esc-press without an open drawer doesn't
  // intercept anything else (e.g. TermCard's own Esc listener — which
  // uses the same useEscape helper).
  useEscape(dismiss, () => railApi.rail().kind !== "idle");

  /** Derived count-only map for Lines.tsx — the marker only needs
   *  `count` per chunk; the full `top` array is read by the click
   *  handler. */
  const xrefMapForLines = (): XrefMap | undefined => {
    const m = refsMap();
    if (!m) return undefined;
    const out: XrefMap = {};
    for (const [chunkId, entry] of Object.entries(m.by_chunk)) {
      out[chunkId] = { count: entry.count };
    }
    return out;
  };

  const hasRail = () => railApi.rail().kind !== "idle";

  return (
    <div class={classnames("reader", hasRail() && "has-rail")}>
      <Chrome
        target={railApi.target()}
        onTarget={railApi.setTargetLang}
        meta={range()}
        onBack={props.onClose}
      />

      <div class="stage" ref={stageRef} onMouseUp={selection.onMouseUp}>
        <div class="column">
          <Show when={range()}>
            {(r) => (
              <>
                <ReaderHead range={r()} />
                <Lines
                  chunks={r().chunks}
                  lang={r().lang}
                  occMap={occMap()}
                  lemmaHighlights={wordLookup.lemmaHighlights()}
                  pinnedHighlights={selection.pinnedHighlights()}
                  onPinnedClick={selection.onPinnedClick}
                  onPinnedRemove={selection.removeSavedHighlight}
                  xrefMap={xrefMapForLines()}
                  openRefChunkId={xref.openRefCard()?.chunkId ?? null}
                  onWordClick={(word, chunkId, offset, lineEl) => {
                    hoverTranslations.registerWordClick(
                      chunkId,
                      offset,
                      word,
                    );
                    wordLookup.onWordClick(word, chunkId, offset, lineEl);
                  }}
                  wordTranslation={hoverTranslations.lookup}
                  onXrefOpen={xref.onXrefOpen}
                  onTermClick={term.onTermClick}
                />
                {/* Infinite-scroll affordances. The sentinel is an
                    empty div observed by the IntersectionObserver
                    set up above — when it enters the viewport
                    (within the 800px rootMargin pre-fetch window)
                    `loadMore()` fires. The loading-more strip is
                    only visible while a fetch is in flight so
                    typical scrolling produces no visual flicker. */}
                <Show when={hasMore()}>
                  <div
                    ref={setSentinelEl}
                    aria-hidden="true"
                    style={{ height: "1px" }}
                  />
                </Show>
                <Show when={loadingMore()}>
                  <div
                    style={{
                      color: "var(--r-ink-mute)",
                      "font-style": "italic",
                      "font-size": "13px",
                      "text-align": "center",
                      padding: "12px 0",
                    }}
                  >
                    Loading more…
                  </div>
                </Show>
              </>
            )}
          </Show>
          <Show when={loadError()}>
            <div style={{ color: "var(--r-ink-mute)", "font-style": "italic" }}>
              Could not load the source: {loadError()}
            </div>
          </Show>
        </div>
      </div>

      {/* Rail is ALWAYS mounted so CSS transitions on `.rail`'s
          transform + opacity can run on close — `Show` would tear
          the element out of the DOM before any transition could
          play. The `.open` class drives the animation; when closed
          the rail is off-screen, opacity-0, and `pointer-events:
          none` (see reader.css). `aria-hidden` mirrors the state for
          screen readers. */}
      <aside
        class={classnames("rail", hasRail() && "open")}
        aria-hidden={!hasRail()}
      >
        <RailContent
          state={railApi.rail()}
          wordInfo={wordLookup.wordInfo()}
          target={railApi.target()}
          onTarget={railApi.setTargetLang}
          onRetry={railApi.retry}
          onDismiss={dismiss}
          onLoadMoreSamples={wordLookup.loadMoreSamples}
          onOpenConcordance={(lemma, lang) => {
            // Navigate via hash — routing.ts's hashchange listener
            // picks it up and renders the concordance route. We don't
            // need to thread the routing controller through readerCtrl
            // for this single-purpose CTA.
            const enc = encodeURIComponent(lemma);
            window.location.hash =
              `#/concordance/${enc}?lang=${encodeURIComponent(lang)}`;
          }}
          workTitle={props.workId}
          onOpenWorkConcordance={() => {
            const lang = props.sourceLang ?? "deu";
            window.location.hash =
              `#/concordance?lang=${encodeURIComponent(lang)}` +
              `&scope=work&work=${encodeURIComponent(props.workId)}`;
          }}
          sourceLang={props.sourceLang}
        />
      </aside>

      <Show when={selection.selToolbar()}>
        {(t) => (
          <SelectionToolbar
            anchor={{ rect: t().rect }}
            count={t().summary}
            singleWord={t().singleWord}
            onTranslate={() => { selection.commitTranslate(t()); }}
            onLookup={() => { selection.commitLookup(t()); }}
            onCopy={() => { selection.copySelection(t()); }}
            onDismiss={selection.dismissToolbar}
          />
        )}
      </Show>

      <Show when={term.openCard()}>
        {(c) => (
          <TermCard
            termId={c().termId}
            anchor={c().anchor}
            onClose={term.close}
          />
        )}
      </Show>

      <Show when={xref.openRefCard()}>
        {(c) => (
          <ReferenceCard
            reference={c().reference}
            anchor={c().anchor}
            onClose={xref.close}
          />
        )}
      </Show>

      <Show when={range()}>
        {(r) => (
          <div class="pagefoot">
            {r().author} · {r().work} · {r().total} chunks
          </div>
        )}
      </Show>

      <ReaderMobileSettingsSheet
        open={shell.isMobile() && shell.readerSettingsOpen()}
        target={railApi.target()}
        onTarget={railApi.setTargetLang}
        onClose={() => shell.setReaderSettingsOpen(false)}
      />
    </div>
  );
}
