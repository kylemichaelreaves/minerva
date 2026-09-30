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
import ReferenceCard from "~/components/cards/ReferenceCard";
import TermCard from "~/components/cards/TermCard";
import { useMobileShell } from "~/components/shell/MobileShellContext";
import { useEscape } from "~/hooks/useEscape";
import { useInfiniteScrollSentinel } from "~/hooks/useInfiniteScrollSentinel";
import { routeHash } from "~/routing";
import { slugify } from "~/slug";
import { Chrome } from "~/Reader/components/Chrome";
import { EditionBar } from "~/Reader/components/EditionBar";
import { ReaderHead } from "~/Reader/components/ReaderHead";
import { useSelectionToolbar } from "~/Reader/useSelectionToolbar";
import { useTermCard } from "~/Reader/useTermCard";
import { useTranslateRail } from "~/Reader/useTranslateRail";
import { useWordHoverTranslations } from "~/Reader/useWordHoverTranslations";
import { useWordLookup } from "~/Reader/useWordLookup";
import { useWorkRange } from "~/Reader/useWorkRange";
import { useXrefCard } from "~/Reader/useXrefCard";
import { escapeExitsReader, isSyntaxLangEnabled, type ReaderSurfaces } from "~/Reader/utils";
import { Lines, type XrefMap } from "~/Reader/components/Lines";
import { RailContent } from "~/Reader/components/Rail";
import { ReaderMobileSettingsSheet } from "~/Reader/components/ReaderMobileSettingsSheet";
import { SelectionToolbar } from "~/Reader/components/SelectionToolbar";
import "~/Reader/reader.css";

interface ReaderProps {
  /** Title slug from the route (#602). The Reader never receives a title —
   *  `workTitle()` below derives it from the loaded range instead, which is
   *  what keeps the title-keyed localStorage and API surfaces working
   *  without a migration. */
  workSlug: string;
  /** ISO 639-3. Defaults to "grc" for Plato/Aristotle; caller can hint
   *  "deu" for Hegel/Kant. The reader exposes a lang chip in the
   *  chrome for the TARGET (translation) language, not the source. */
  sourceLang?: string;
  /** Author slug. Disambiguates same-titled works (Luther 1912 vs 1545
   *  share every book title AND lang). Optional — a citation deep-link
   *  carries no author and the server resolves off `around=<chunk>`. */
  authorSlug?: string;
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
  /** Called with the loaded range's author slug when the route carried none
   *  — a citation deep-link's one-segment `#/r/<titleSlug>` — so the caller
   *  can grow the URL to its canonical two-segment form (#611). */
  onAuthorResolved?: (authorSlug: string) => void;
  onClose?: () => void;
  /** True while the syntax overlay is layered over this Reader
   *  (`?syntax=<chunk>`). The Reader stays mounted underneath it (#342),
   *  so it has to know not to take an Escape the overlay owns. */
  syntaxOpen?: boolean;
  /** Leave the Reader entirely — Escape, when nothing else is open.
   *  Distinct from `onClose`, which is the back arrow and resumes the
   *  last conversation; this one goes to the landing. */
  onExit?: () => void;
  /** True while the Reader is retained but off-screen — the route has stepped
   *  out to a concordance and `AppRoutes` is holding this instance mounted so
   *  the passage survives the round trip (#348).
   *
   *  Distinct from `syntaxOpen`, which is the Reader still being the route.
   *  The wrapper carries `hidden` and `inert`, but neither reaches a listener
   *  bound to `window` or `document`: without this flag the retained Reader
   *  would answer the concordance's Escape and exit to the landing, and its
   *  selection-toolbar hotkeys would fire on a toolbar nobody can see. */
  suspended?: boolean;
}

export default function Reader(props: ReaderProps) {
  let stageRef: HTMLDivElement | undefined;
  const shell = useMobileShell();

  onMount(() => {
    shell.registerSurfaceActions({
      openReaderSettings: () => shell.setReaderSettingsOpen(true),
    });
  });

  const { range, occMap, refsMap, loadError, loadMore, hasMore, loadingMore, switchEdition } =
    useWorkRange(
      {
        get workSlug() {
          return props.workSlug;
        },
        get sourceLang() {
          return props.sourceLang;
        },
        get authorSlug() {
          return props.authorSlug;
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

  // A one-segment route has no author; the range names it (#611). Only when
  // the range is the work the slug names: the server resolves a focus link
  // off `around=` whatever the title segment says, and pairing that work's
  // author with a title slug it does not own would build a URL that 404s.
  createEffect(() => {
    const r = range();
    if (r === null || props.authorSlug !== undefined) return;
    if (slugify(r.work) !== props.workSlug) return;
    props.onAuthorResolved?.(slugify(r.author));
  });

  const railApi = useTranslateRail();

  // Auto-shift the rail's target language away from the source's
  // language. Avoids landing on a disabled chip when reading an
  // English text (default target is also "eng"). Greek/Latin/Hebrew
  // sources never collide with the three target options, so no shift.
  createEffect(() => {
    const src = props.sourceLang;
    // promote:false — this only adjusts the DEFAULT target so a chip
    // isn't disabled; it must not open an empty rail on load (#63).
    if (src === "eng" && railApi.target() === "eng") {
      railApi.setTargetLang("deu", { promote: false });
    } else if (src === "fra" && railApi.target() === "fra") {
      railApi.setTargetLang("eng", { promote: false });
    } else if (src === "deu" && railApi.target() === "deu") {
      railApi.setTargetLang("eng", { promote: false });
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

  // The dependency parser is German-only (`syntax/parse.py:_LANG = "de"`),
  // so the action is offered only on a German edition. Gated on the
  // loaded range's own `lang` (falling back to `props.sourceLang` before
  // the range has loaded) rather than `sourceLang` alone: `sourceLang` is
  // `undefined` on citation deep-links (`App.tsx`'s `openAtChunk`) and on a
  // cold load of the legacy `#/syntax/<chunk>?work=` hash, which carries no
  // lang and so resolves the edition off `around=<chunk>` instead — either
  // would otherwise hide the action from German text. This also makes the gate
  // true to the spec's claim that it's keyed on the chunk's language, not
  // the work's. The server refuses non-German independently (400) — this
  // keeps a dead button off screen, it is not the safety property.
  const syntaxEnabled = () => isSyntaxLangEnabled(range()?.lang, props.sourceLang);

  // The route carries slugs, so the canonical title arrives with the DATA
  // (#602). Three things downstream are title-keyed and stay that way: the
  // saved-highlight localStorage key (no migration — the key is simply
  // computed a beat later, once the range resolves, which is already when
  // highlights can be applied to rendered text), the displayed title, and the
  // concordance scope filter, whose API matches on `works.title`.
  //
  // Empty string until the range lands. `useSelectionToolbar` reloads its
  // layer whenever this changes, so the highlights appear with the text.
  const workTitle = () => range()?.work ?? "";

  const selection = useSelectionToolbar({
    getStage: () => stageRef,
    workId: () => workTitle(),
    onTranslateRequest: (source, ref) => {
      hoverTranslations.clearPending();
      railApi.runTranslate(source, ref);
    },
    onLookupRequest: (word, chunkId, offset, lineEl) => {
      hoverTranslations.registerWordClick(chunkId, offset, word);
      wordLookup.onWordClick(word, chunkId, offset, lineEl);
    },
    syntaxEnabled,
    // `Boolean`, not `?? false`: the hook already treats a missing accessor
    // and an `undefined` result the same way, so the default would be a
    // branch that no test can reach without opening a selection toolbar
    // inside a full Reader mount.
    suspended: () => Boolean(props.suspended),
    onSyntaxRequest: (chunkId: string) => {
      // Build the hash through the router's own serializer rather than
      // by hand, so this link can't drift from `readRoute`'s parser in
      // routing.ts. `routeHash` is a pure function — no need to thread
      // the full routing controller through readerCtrl for this
      // single-purpose CTA.
      //
      // The whole current reader location goes back into the hash, with
      // `syntax=<chunk>` added: the overlay is a modifier on this route now
      // (#342), and the Reader stays mounted underneath it only as long as
      // every field the window is keyed on comes back unchanged. Dropping
      // `lang` here would re-resolve the edition and reload the window —
      // which is the failure the old peer route caused by unmounting.
      window.location.hash = routeHash({
        kind: "reader",
        workSlug: props.workSlug,
        sourceLang: props.sourceLang,
        authorSlug: props.authorSlug,
        focusChunkId: props.focusChunkId,
        openTermId: props.openTermId,
        syntaxChunkId: chunkId,
      });
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

  /** Section locator of the chunk currently at the top of the viewport,
   *  so an edition switch can keep the reader's place (#50). Returns
   *  undefined when nothing's resolvable — the switch then starts the
   *  new edition at the top. */
  function topVisibleSection(): string | undefined {
    const stage = stageRef;
    const r = range();
    if (!stage || !r) return undefined;
    const stageTop = stage.getBoundingClientRect().top;
    for (const el of stage.querySelectorAll("[data-chunk-id]")) {
      if (el.getBoundingClientRect().bottom >= stageTop + 4) {
        const id = el.getAttribute("data-chunk-id");
        return r.chunks.find((c) => c.chunk_id === id)?.section ?? undefined;
      }
    }
    return undefined;
  }

  function onSwitchEdition(selector: string) {
    dismiss();
    switchEdition(selector, topVisibleSection());
  }

  // Esc dismisses the rail whenever it's open. Gated on `kind !==
  // "idle"` so a stray Esc-press without an open drawer doesn't
  // intercept anything else (e.g. TermCard's own Esc listener — which
  // uses the same useEscape helper).
  useEscape(dismiss, () => !props.suspended && railApi.rail().kind !== "idle");

  // …and Esc with nothing open leaves the Reader. Last resort, not first:
  // every surface below answers Escape itself, so the gate is what makes a
  // press close the card the user meant to close and the NEXT press leave.
  // `useEscape` registers no listener at all while the gate is false, which
  // is what keeps this out of the way of the surfaces that own the key.
  const surfaces = (): ReaderSurfaces => ({
    rail: railApi.rail().kind !== "idle",
    termCard: term.openCard() !== null,
    xrefCard: xref.openRefCard() !== null,
    selectionToolbar: selection.selToolbar() !== null,
    settingsSheet: shell.readerSettingsOpen(),
    syntaxLayer: props.syntaxOpen ?? false,
  });
  useEscape(
    () => props.onExit?.(),
    () => !props.suspended && props.onExit !== undefined && escapeExitsReader(surfaces()),
  );

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
                <EditionBar
                  editions={r().editions}
                  current={r().edition}
                  onSwitch={onSwitchEdition}
                />
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
            // Through the router's own serializer, like the syntax CTA above
            // and for the same reason: routing.ts owns this format at both
            // ends, and a second hand-written copy of it drifts silently.
            // `routeHash` is pure, so this still needs no routing controller
            // threaded through readerCtrl.
            window.location.hash = routeHash({ kind: "concordance-lemma", lemma, lang });
          }}
          workTitle={workTitle()}
          onOpenWorkConcordance={() => {
            // The hand-built version of this one had already drifted. It
            // single-encoded the title into `&work=`, so `URLSearchParams.get`
            // handed a literal comma to `decodeCsv` and "Das Kapital, Band I"
            // arrived as two scope entries — 26 of 866 work titles contain a
            // comma. `routeHash` goes through `encodeCsv`, which survives the
            // extra decode (#236).
            window.location.hash = routeHash({
              kind: "concordance",
              lang: props.sourceLang ?? "deu",
              scope: "work",
              scopeWorks: [workTitle()],
            });
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
            onSyntax={
              syntaxEnabled() ? () => { selection.commitSyntax(t()); } : undefined
            }
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
            direction={c().direction}
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
