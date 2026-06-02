// F2 — Lemma detail / KWIC grid. Orchestrator composes useLemmaDetail;
// presentational pieces live in ./components.

import {
  For,
  Show,
  createEffect,
  createMemo,
  createResource,
  createSignal,
  onCleanup,
} from "solid-js";
import { fetchLemmaDetail, type ConcScope, type KwicRow } from "~/api/concordanceApi";
import { ConcEmpty, LemmaCacheEmpty } from "~/Concordance/components/ConcEmpty";
import { FilterRail } from "~/Concordance/components/FilterRail";
import { KwicRowEl } from "~/Concordance/components/KwicRow";
import { KwicSkeleton } from "~/Concordance/components/KwicSkeleton";
import { LemmaIdentityCard } from "~/Concordance/components/LemmaIdentityCard";
import { useMobile } from "~/hooks/useMobile";
import { MobileSheet } from "~/components/MobileSheet";
import "~/Concordance/concordance.css";

export interface LemmaDetailProps {
  lemma: string;
  lang?: string;
  scope?: ConcScope;
  scopeAuthor?: string;
  scopeWork?: string;
  caseFilter?: string;
  numberFilter?: string;
  surface?: string;
  onNavigate: (patch: {
    scope?: ConcScope;
    scopeAuthor?: string;
    scopeWork?: string;
    caseFilter?: string;
    numberFilter?: string;
    surface?: string;
  }) => void;
  onBackToIndex: () => void;
  onOpenChunk: (work: string, chunkId: string) => void;
}

export function ConcordanceLemmaDetail(props: LemmaDetailProps) {
  const lang = () => props.lang ?? "deu";
  const scope = (): ConcScope => props.scope ?? "corpus";

  const { data, cursor, setCursor, morph } = useLemmaDetail({
    lemma: () => props.lemma,
    lang,
    scope,
    scopeAuthor: () => props.scopeAuthor,
    scopeWork: () => props.scopeWork,
    surface: () => props.surface,
    caseFilter: () => props.caseFilter,
    numberFilter: () => props.numberFilter,
    onNavigate: props.onNavigate,
    onBackToIndex: props.onBackToIndex,
    onOpenChunk: props.onOpenChunk,
  });

  const isMobile = useMobile();
  const [sheetOpen, setSheetOpen] = createSignal(false);

  /** Reset every URL-bound filter at once, used by the applied-
   *  filters card and the mobile sheet's Reset button. Scope is the
   *  one knob we DON'T touch — narrowing scope is a directed action
   *  the user took at the F1 page, and the back-to-index link is the
   *  right exit. */
  const resetAllFilters = () =>
    props.onNavigate({
      caseFilter: undefined,
      numberFilter: undefined,
      surface: undefined,
    });

  /** Active-filter count for the mobile FAB badge. Mirrors the
   *  applied-filters card's pill count minus the scope pill, since on
   *  mobile the scope crumb has its own visible row above the KWIC. */
  const filterCount = createMemo(() => {
    let n = 0;
    if (props.caseFilter) n += 1;
    if (props.numberFilter) n += 1;
    if (props.surface) n += 1;
    return n;
  });

  return (
    <div class="conc-stage conc-detail">
      <Show when={data()}>
        <div class="conc-head" style={{ "align-items": "flex-start" }}>
          <div style={{ flex: 1 }}>
            <LemmaIdentityCard lemma={props.lemma} lang={lang()} data={data()!} />
            <div
              style={{
                "font-family": "var(--sans)",
                "font-size": "11px",
                color: "var(--ink-mute)",
                "margin-top": "2px",
              }}
            >
              <a
                style={{ color: "var(--accent)", cursor: "pointer", "text-decoration": "none" }}
                onClick={props.onBackToIndex}
              >
                ‹ back to index
              </a>
            </div>
          </div>
        </div>
      </Show>

      <Show when={!!data.error}>
        <Show
          when={String(data.error as unknown)
            .toLowerCase()
            .includes("lemma cache")}
          fallback={
            <ConcEmpty icon="!" title="Couldn't load occurrences">
              <div>{String(data.error)}</div>
            </ConcEmpty>
          }
        >
          <LemmaCacheEmpty
            lang={lang()}
            title="No lemma cache"
            body={
              <>
                spaCy hasn't lemmatised the {lang().toUpperCase()} edition yet — the concordance
                can't key occurrences until the cache lands.
              </>
            }
            footer={<>Runs once per edition · ~3 min for ~30k chunks.</>}
          />
        </Show>
      </Show>

      <Show when={data.loading && !data()}>
        <KwicSkeleton />
      </Show>

      <Show when={data() && !data.error}>
        <Show
          when={data()!.total > 0}
          fallback={
            <ConcEmpty icon="∅" title="No occurrences with these filters">
              <div>
                <em>{props.lemma}</em>
                {Object.entries(morph())
                  .map(([k, v]) => ` · ${k}=${v}`)
                  .join("")}
                {props.surface ? ` · surface=${props.surface}` : ""} doesn't appear in{" "}
                {data()!.scope_label || "this scope"}.
              </div>
              <div class="broaden">
                <Show when={props.numberFilter}>
                  {(() => {
                    const drop = props.caseFilter
                      ? data()!.case_breakdown.find((b) => b.value === props.caseFilter)?.count
                      : data()!.case_breakdown.reduce((s, b) => s + b.count, 0);
                    return (
                      <a onClick={() => props.onNavigate({ numberFilter: undefined })}>
                        Drop Number{drop !== undefined ? ` · ${drop.toLocaleString()} hits` : ""}
                      </a>
                    );
                  })()}
                </Show>
                <Show when={props.caseFilter}>
                  {(() => {
                    const drop = props.numberFilter
                      ? data()!.number_breakdown.find((b) => b.value === props.numberFilter)?.count
                      : data()!.case_breakdown.reduce((s, b) => s + b.count, 0);
                    return (
                      <a onClick={() => props.onNavigate({ caseFilter: undefined })}>
                        Drop Case{drop !== undefined ? ` · ${drop.toLocaleString()} hits` : ""}
                      </a>
                    );
                  })()}
                </Show>
                <Show when={props.surface}>
                  <a onClick={() => props.onNavigate({ surface: undefined })}>Drop Surface form</a>
                </Show>
                <Show when={scope() !== "corpus"}>
                  <a onClick={() => props.onNavigate({ scope: "corpus" })}>Zoom to corpus</a>
                </Show>
              </div>
            </ConcEmpty>
          }
        >
          <div class="kwic-stage">
            <Show when={!isMobile()}>
              <FilterRail
                data={data()!}
                scope={scope()}
                scopeAuthor={props.scopeAuthor}
                scopeWork={props.scopeWork}
                caseFilter={props.caseFilter}
                numberFilter={props.numberFilter}
                surface={props.surface}
                onSetScope={(patch) => props.onNavigate(patch)}
                onSetCase={(v) => props.onNavigate({ caseFilter: v })}
                onSetNumber={(v) => props.onNavigate({ numberFilter: v })}
                onSetSurface={(v) => props.onNavigate({ surface: v })}
                onSetWork={(w) =>
                  // Empty string clears the work-scope back up to author
                  // (preserving the previous Author binding when there
                  // is one) or to corpus otherwise.
                  w
                    ? props.onNavigate({
                        scope: "work",
                        scopeWork: w,
                        scopeAuthor: undefined,
                      })
                    : props.onNavigate({
                        scope: props.scopeAuthor ? "author" : "corpus",
                        scopeWork: undefined,
                      })
                }
                onResetAll={resetAllFilters}
                currentWorkScope={props.scopeWork}
              />
            </Show>
            <div class="kwic-pane" classList={{ "kwic-refetching": data.loading }}>
              <div class="kwic-toolbar">
                <span class="ct">
                  Showing <b>{data()!.rows.length}</b> of <b>{data()!.total.toLocaleString()}</b>
                </span>
                <span class="kbd">
                  <kbd>j</kbd>/<kbd>k</kbd> next / prev · <kbd>↵</kbd> open chunk ·{" "}
                  <Show when={scope() !== "corpus"}>
                    <kbd>⌘↑</kbd> zoom out ·{" "}
                  </Show>
                  <Show when={scope() !== "work" && data()!.work_breakdown.length > 0}>
                    <kbd>⌘↓</kbd> zoom in ·{" "}
                  </Show>
                  <kbd>esc</kbd> back
                </span>
              </div>
              <div class="kwic-grid">
                <For each={data()!.rows}>
                  {(row, idx) => (
                    <KwicRowEl
                      row={row}
                      cur={idx() === cursor()}
                      onClick={() => {
                        setCursor(idx());
                        props.onOpenChunk(row.work, row.chunk_id);
                      }}
                      onHover={() => setCursor(idx())}
                    />
                  )}
                </For>
              </div>
            </div>
          </div>
        </Show>
      </Show>

      {/* Mobile FAB + sheet. Renders the same FilterRail inside the
          sheet body — content drives the design, not duplicated layout. */}
      <Show when={isMobile() && data() && !data.error && data()!.total > 0}>
        <button type="button" class="conc-fab" onClick={() => setSheetOpen(true)}>
          ≡ Filters
          <Show when={filterCount() > 0}>
            <span class="badge">{filterCount()}</span>
          </Show>
        </button>
        <MobileSheet
          open={sheetOpen()}
          title="Filter occurrences"
          onClose={() => setSheetOpen(false)}
        >
          <div class="conc-mob-sheet">
            <FilterRail
              data={data()!}
              scope={scope()}
              scopeAuthor={props.scopeAuthor}
              scopeWork={props.scopeWork}
              caseFilter={props.caseFilter}
              numberFilter={props.numberFilter}
              surface={props.surface}
              onSetScope={(patch) => props.onNavigate(patch)}
              onSetCase={(v) => props.onNavigate({ caseFilter: v })}
              onSetNumber={(v) => props.onNavigate({ numberFilter: v })}
              onSetSurface={(v) => props.onNavigate({ surface: v })}
              onSetWork={(w) =>
                w
                  ? props.onNavigate({
                      scope: "work",
                      scopeWork: w,
                      scopeAuthor: undefined,
                    })
                  : props.onNavigate({
                      scope: props.scopeAuthor ? "author" : "corpus",
                      scopeWork: undefined,
                    })
              }
              onResetAll={resetAllFilters}
              currentWorkScope={props.scopeWork}
            />
            <div class="conc-mob-sheet-foot">
              <span
                class="reset"
                onClick={() => {
                  resetAllFilters();
                  setSheetOpen(false);
                }}
              >
                ↺ Reset all
              </span>
              <span class="done" onClick={() => setSheetOpen(false)}>
                <b>{data()!.total.toLocaleString()}</b> occurrences →
              </span>
            </div>
          </div>
        </MobileSheet>
      </Show>
    </div>
  );
}

interface UseLemmaDetailArgs {
  lemma: () => string;
  lang: () => string;
  scope: () => ConcScope;
  scopeAuthor: () => string | undefined;
  scopeWork: () => string | undefined;
  surface: () => string | undefined;
  caseFilter: () => string | undefined;
  numberFilter: () => string | undefined;
  onNavigate: (patch: {
    scope?: ConcScope;
    scopeAuthor?: string;
    scopeWork?: string;
    caseFilter?: string;
    numberFilter?: string;
    surface?: string;
  }) => void;
  onBackToIndex: () => void;
  onOpenChunk: (work: string, chunkId: string) => void;
}

export function useLemmaDetail(args: UseLemmaDetailArgs) {
  const [cursor, setCursor] = createSignal(0);

  const morph = createMemo<Record<string, string>>(() => {
    const m: Record<string, string> = {};
    if (args.caseFilter()) m.Case = args.caseFilter()!;
    if (args.numberFilter()) m.Number = args.numberFilter()!;
    return m;
  });

  const [data] = createResource(
    () => ({
      lemma: args.lemma(),
      lang: args.lang(),
      scope: args.scope(),
      author: args.scopeAuthor(),
      work: args.scopeWork(),
      surface: args.surface(),
      morph: morph(),
    }),
    async (p) =>
      fetchLemmaDetail({
        lemma: p.lemma,
        lang: p.lang,
        scope: p.scope,
        author: p.author,
        work: p.work,
        surface: p.surface,
        morph: Object.keys(p.morph).length > 0 ? p.morph : undefined,
        limit: 100,
      }),
  );

  createEffect(() => {
    morph();
    args.surface();
    args.scope();
    setCursor(0);
  });

  function scrollRowIntoView() {
    queueMicrotask(() => {
      document.querySelector<HTMLElement>(".kwic-row.cur")?.scrollIntoView({ block: "nearest" });
    });
  }

  function onKey(e: KeyboardEvent) {
    if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
    const rows = data()?.rows ?? [];
    if (e.key === "ArrowUp" && (e.metaKey || e.ctrlKey) && args.scope() !== "corpus") {
      e.preventDefault();
      args.onNavigate({
        scope: "corpus",
        scopeAuthor: undefined,
        scopeWork: undefined,
      });
    } else if (e.key === "ArrowDown" && (e.metaKey || e.ctrlKey) && args.scope() !== "work") {
      const topWork = data()?.work_breakdown[0]?.value;
      if (topWork) {
        e.preventDefault();
        args.onNavigate({ scope: "work", scopeWork: topWork, scopeAuthor: undefined });
      }
    } else if (e.key === "j" || e.key === "ArrowDown") {
      e.preventDefault();
      setCursor((c) => Math.min(rows.length - 1, c + 1));
      scrollRowIntoView();
    } else if (e.key === "k" || e.key === "ArrowUp") {
      e.preventDefault();
      setCursor((c) => Math.max(0, c - 1));
      scrollRowIntoView();
    } else if (e.key === "Enter") {
      const r = rows[cursor()];
      // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition
      if (r) {
        e.preventDefault();
        args.onOpenChunk(r.work, r.chunk_id);
      }
    } else if (e.key === "Escape") {
      e.preventDefault();
      args.onBackToIndex();
    }
  }

  window.addEventListener("keydown", onKey);
  onCleanup(() => window.removeEventListener("keydown", onKey));

  return { data, cursor, setCursor, morph };
}

export type { KwicRow };
