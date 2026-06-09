// F1 — Lemma frequency index. Orchestrator composes useConcordanceIndex;
// presentational pieces live in ./components.

import { For, Show, createEffect, createMemo, createResource, createSignal } from "solid-js";
import {
  fetchLemmaIndex,
  type ConcScope,
  type ConcSort,
  type LemmaIndexRow,
} from "~/api/concordanceApi";
import { ActiveFilterStrip } from "~/Concordance/components/ActiveFilterStrip";
import { ConcEmpty, LemmaCacheEmpty } from "~/Concordance/components/ConcEmpty";
import { FilterBar } from "~/Concordance/components/FilterBar";
import { LbRow } from "~/Concordance/components/LbRow";
import { LoadingSkeleton } from "~/Concordance/components/LoadingSkeleton";
import { ScopePill } from "~/Concordance/components/ScopePill";
import { alphabetFor, foldInitial } from "~/Concordance/constants";
import { useMobile } from "~/hooks/useMobile";
import { MobileSheet } from "~/components/MobileSheet";
import "~/Concordance/concordance.css";

/** Allow-clear navigation patch — explicit `undefined` clears that field
 *  from the URL. ConcordanceRoute uses `mergeRoutePatchAllowClear` so a
 *  chip's onRemove can set `pos: undefined` and we drop the param. */
export interface IndexNavPatch {
  lang?: string;
  scope?: ConcScope;
  scopeAuthor?: string;
  scopeWork?: string;
  letter?: string;
  sort?: ConcSort;
  pos?: string;
  freqMin?: number;
  freqMax?: number;
  q?: string;
}

export interface IndexPageProps {
  lang?: string;
  scope?: ConcScope;
  scopeAuthor?: string;
  scopeWork?: string;
  letter?: string;
  sort?: ConcSort;
  pos?: string;
  freqMin?: number;
  freqMax?: number;
  q?: string;
  onNavigate: (patch: IndexNavPatch) => void;
  onOpenLemma: (lemma: string, scope?: ConcScope, scopeAuthor?: string, scopeWork?: string) => void;
}

export function ConcordanceIndexPage(props: IndexPageProps) {
  const lang = () => props.lang ?? "deu";
  const scope = (): ConcScope => props.scope ?? "corpus";
  const sort = (): ConcSort => props.sort ?? "freq";
  const letter = () => props.letter;

  const { data, setRetryKey, lettersWithHits, grouped } = useConcordanceIndex({
    lang,
    scope,
    sort,
    letter,
    scopeAuthor: () => props.scopeAuthor,
    scopeWork: () => props.scopeWork,
    pos: () => props.pos,
    freqMin: () => props.freqMin,
    freqMax: () => props.freqMax,
    q: () => props.q,
  });

  const isMobile = useMobile();
  const [sheetOpen, setSheetOpen] = createSignal(false);

  /** Slider ceiling — the highest count we've seen so far for this
   *  scope. Monotonic: never shrinks during a filter session, so the
   *  slider scale doesn't jump when the user drags freq_max down and
   *  the top row's count drops along with it. Resets when the user
   *  changes scope (different scope = different unfiltered max). */
  const [freqCeil, setFreqCeil] = createSignal(10000);
  let lastScopeKey = "";
  createEffect(() => {
    const scopeKey = `${lang()}|${scope()}|${props.scopeAuthor ?? ""}|${props.scopeWork ?? ""}`;
    if (scopeKey !== lastScopeKey) {
      lastScopeKey = scopeKey;
      setFreqCeil(10000);
    }
    const top = data()?.rows[0]?.count;
    if (top && top > freqCeil()) {
      setFreqCeil(top);
    }
  });

  /** Chips shown in the active-filter strip. Each carries its own
   *  remove patch; the strip never needs to know what kind of filter
   *  the chip represents. */
  const activeChips = createMemo(() => {
    const chips: { k: string; v: string; onRemove: () => void }[] = [];
    if (props.letter) {
      chips.push({
        k: "letter",
        v: props.letter,
        onRemove: () => props.onNavigate({ letter: undefined }),
      });
    }
    if (props.pos) {
      const label = props.pos === "all" ? "all" : props.pos.toLowerCase();
      chips.push({
        k: "POS",
        v: label,
        onRemove: () => props.onNavigate({ pos: undefined }),
      });
    }
    if (props.freqMin !== undefined || props.freqMax !== undefined) {
      const lo = props.freqMin?.toLocaleString() ?? "1";
      const hi = props.freqMax?.toLocaleString() ?? "∞";
      chips.push({
        k: "freq",
        v: `${lo}–${hi}`,
        onRemove: () => props.onNavigate({ freqMin: undefined, freqMax: undefined }),
      });
    }
    if (props.q) {
      chips.push({
        k: "q",
        v: `"${props.q}"`,
        onRemove: () => props.onNavigate({ q: undefined }),
      });
    }
    return chips;
  });

  const resetAll = () =>
    props.onNavigate({
      letter: undefined,
      pos: undefined,
      freqMin: undefined,
      freqMax: undefined,
      q: undefined,
    });

  return (
    <div class="conc-stage conc-index">
      <div class="conc-head">
        <div class="conc-head-main">
          <h1 class="conc-h1">Concordance</h1>
          <div
            class="conc-sub"
            style={{ display: "flex", gap: "12px", "align-items": "center", "flex-wrap": "wrap" }}
          >
            <ScopePill
              steps={[
                { label: "Work", scope: "work", cur: scope() === "work" },
                { label: "Author", scope: "author", cur: scope() === "author" },
                {
                  label: scope() === "corpus" ? (data()?.scope_label ?? "Corpus") : "Corpus",
                  scope: "corpus",
                  cur: scope() === "corpus",
                },
              ]}
              count={data()?.total_occurrences}
              onPick={(s) =>
                props.onNavigate({ scope: s, scopeAuthor: undefined, scopeWork: undefined })
              }
            />
            <span>
              · <b>{data()?.total_lemmas.toLocaleString() ?? "—"}</b> lemmas ·{" "}
              {lang().toUpperCase()}
            </span>
          </div>
        </div>
      </div>

      {/* Desktop: header-bar filter row inline. Mobile: same controls
          rendered inside the bottom sheet (see <MobileSheet> below). */}
      <Show when={!isMobile()}>
        <FilterBar
          lang={lang()}
          sort={sort()}
          pos={props.pos}
          freqMin={props.freqMin}
          freqMax={props.freqMax}
          freqCeil={freqCeil()}
          q={props.q}
          onSetLang={(v) => props.onNavigate({ lang: v, letter: undefined })}
          onSetSort={(v) => props.onNavigate({ sort: v })}
          onSetPos={(v) => props.onNavigate({ pos: v })}
          onSetFreqRange={(lo, hi) => props.onNavigate({ freqMin: lo, freqMax: hi })}
          onSetQ={(v) => props.onNavigate({ q: v })}
        />
      </Show>

      <div class="az-rail az-rail-grid">
        <For each={alphabetFor(lang())}>
          {(L) => {
            const klass = () =>
              "l " + (L === letter() ? "cur" : lettersWithHits().has(L) ? "has" : "");
            return (
              <span
                class={klass()}
                onClick={() => props.onNavigate({ letter: L === letter() ? undefined : L })}
              >
                {L}
              </span>
            );
          }}
        </For>
        <Show when={letter()}>
          <span class="l az-all" onClick={() => props.onNavigate({ letter: undefined })}>
            all
          </span>
        </Show>
      </div>

      <ActiveFilterStrip
        items={activeChips()}
        // Show the actual page row count — this is what changes as the
        // user narrows. The header retains the unfiltered scope total
        // ("122,965 lemmas") for orientation; the strip mirrors the
        // result set the user is looking at right now. Capped at the
        // fetch limit (200), which is plenty for any narrowed filter.
        count={data()?.rows.length}
        countLabel="lemmas shown"
        onReset={resetAll}
      />

      {/* Mobile: floating Filters button — opens the bottom sheet that
          re-renders the same controls. The badge counts only the
          non-letter chips because the A-Z strip lives outside the sheet. */}
      <Show when={isMobile()}>
        <button type="button" class="conc-fab" onClick={() => setSheetOpen(true)}>
          ≡ Filters
          <Show when={activeChips().length > 0}>
            <span class="badge">{activeChips().length}</span>
          </Show>
        </button>
        <MobileSheet open={sheetOpen()} title="Filters" onClose={() => setSheetOpen(false)}>
          <div class="conc-mob-sheet">
            <FilterBar
              lang={lang()}
              sort={sort()}
              pos={props.pos}
              freqMin={props.freqMin}
              freqMax={props.freqMax}
              freqCeil={freqCeil()}
              q={props.q}
              onSetLang={(v) => props.onNavigate({ lang: v, letter: undefined })}
              onSetSort={(v) => props.onNavigate({ sort: v })}
              onSetPos={(v) => props.onNavigate({ pos: v })}
              onSetFreqRange={(lo, hi) => props.onNavigate({ freqMin: lo, freqMax: hi })}
              onSetQ={(v) => props.onNavigate({ q: v })}
            />
            <div class="conc-mob-sheet-foot">
              <span
                class="reset"
                onClick={() => {
                  resetAll();
                  setSheetOpen(false);
                }}
              >
                ↺ Reset all
              </span>
              <span class="done" onClick={() => setSheetOpen(false)}>
                <b>{data()?.total_lemmas.toLocaleString() ?? "—"}</b> lemmas →
              </span>
            </div>
          </div>
        </MobileSheet>
      </Show>

      <Show
        when={!data.error}
        fallback={
          <Show
            when={String(data.error).toLowerCase().includes("lemma cache")}
            fallback={
              <ConcEmpty icon="!" title="Couldn't load the lemma index">
                <div>{String(data.error)}</div>
                <div style={{ "margin-top": "10px" }}>
                  <span
                    style={{ color: "var(--accent)", cursor: "pointer" }}
                    onClick={() => setRetryKey((k) => k + 1)}
                  >
                    retry
                  </span>
                </div>
              </ConcEmpty>
            }
          >
            <LemmaCacheEmpty
              lang={lang()}
              title="No lemma cache"
              body={
                <>
                  spaCy hasn't lemmatised the {lang().toUpperCase()} edition yet — the concordance
                  needs a populated lemma cache to operate.
                </>
              }
              footer={
                <>
                  Runs once per edition. Re-fetch when complete:{" "}
                  <a onClick={() => setRetryKey((k) => k + 1)}>retry</a>
                </>
              }
            />
          </Show>
        }
      >
        <Show
          when={data() && (data()!.rows.length > 0 || !data.loading)}
          fallback={<LoadingSkeleton />}
        >
          <Show
            when={data()!.rows.length > 0}
            fallback={
              <Show
                when={
                  data()!.total_lemmas === 0 &&
                  data()!.total_occurrences === 0 &&
                  !letter() &&
                  scope() === "corpus"
                }
                fallback={
                  <ConcEmpty icon="∅" title="No lemmas in this scope">
                    <div>Try a different letter or change the scope.</div>
                  </ConcEmpty>
                }
              >
                <LemmaCacheEmpty
                  lang={lang()}
                  title={`No lemma cache for ${lang().toUpperCase()}`}
                  body={
                    <>
                      spaCy hasn't lemmatised this language yet. Run the lemmatizer once per edition
                      to populate the cache.
                    </>
                  }
                  footer={
                    <>
                      Re-fetch when complete: <a onClick={() => setRetryKey((k) => k + 1)}>retry</a>
                    </>
                  }
                />
              </Show>
            }
          >
            <div class="leaderboard">
              <For each={grouped()}>
                {(g) => (
                  <>
                    <Show when={g.letter}>
                      <div class="lb-letter">{g.letter}</div>
                    </Show>
                    <For each={g.rows}>
                      {(row) => (
                        <LbRow
                          row={row}
                          onOpen={() =>
                            props.onOpenLemma(
                              row.lemma,
                              scope(),
                              props.scopeAuthor,
                              props.scopeWork,
                            )
                          }
                        />
                      )}
                    </For>
                  </>
                )}
              </For>
            </div>
          </Show>
        </Show>
      </Show>
    </div>
  );
}

interface UseConcordanceIndexArgs {
  lang: () => string;
  scope: () => ConcScope;
  sort: () => ConcSort;
  letter: () => string | undefined;
  scopeAuthor: () => string | undefined;
  scopeWork: () => string | undefined;
  pos: () => string | undefined;
  freqMin: () => number | undefined;
  freqMax: () => number | undefined;
  q: () => string | undefined;
}

export function useConcordanceIndex(args: UseConcordanceIndexArgs) {
  const [retryKey, setRetryKey] = createSignal(0);

  const [data] = createResource(
    () => ({
      lang: args.lang(),
      scope: args.scope(),
      author: args.scopeAuthor(),
      work: args.scopeWork(),
      letter: args.letter(),
      sort: args.sort(),
      pos: args.pos(),
      freqMin: args.freqMin(),
      freqMax: args.freqMax(),
      q: args.q(),
      _retry: retryKey(),
    }),
    async (p) =>
      fetchLemmaIndex({
        lang: p.lang,
        scope: p.scope,
        author: p.author,
        work: p.work,
        letter: p.letter,
        sort: p.sort,
        pos_in: p.pos,
        min_count: p.freqMin,
        max_count: p.freqMax,
        q: p.q,
        limit: 200,
      }),
  );

  const lettersWithHits = createMemo<Set<string>>(() => {
    const rows = data()?.rows ?? [];
    const s = new Set<string>();
    for (const r of rows) {
      // Fold to the base capital (ASCII A–Z or Greek Α–Ω) so the rail's
      // "has hits" dots line up with the diacritic-folded backend filter.
      const c = foldInitial(r.lemma);
      if (c) s.add(c);
    }
    return s;
  });

  const grouped = createMemo<{ letter: string; rows: LemmaIndexRow[] }[]>(() => {
    const rows = data()?.rows ?? [];
    if (args.sort() !== "alpha" && !args.letter()) {
      return [{ letter: "", rows }];
    }
    const map = new Map<string, LemmaIndexRow[]>();
    for (const r of rows) {
      // Bucket alpha-sort section headers on the folded initial so
      // ἀγαθός / ἄνθρωπος / Ἀθηνᾶ all sit under a single "Α" header.
      const c = foldInitial(r.lemma) || "·";
      if (!map.has(c)) map.set(c, []);
      map.get(c)!.push(r);
    }
    return Array.from(map.entries())
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([letter, rows]) => ({ letter, rows }));
  });

  return { data, retryKey, setRetryKey, lettersWithHits, grouped };
}
