// F2 unified-rail filter UI. Top-down: Scope segmented control →
// applied-filters card (chips + reset) → Work checkbox list with
// search + "+N more" → Case → Number → Gender (prose lock-state when
// single-valued) → Surface form chips with "+N more".

import { For, Show, createMemo, createSignal } from "solid-js";
import type { ConcScope, LemmaDetailResponse } from "~/api/concordanceApi";
import {
  abbrevWork,
  caseLabelFor,
  CASES_ORDER,
  GENDER_LABEL,
  GENDERS_ORDER,
  numberLabelFor,
  NUMBERS_ORDER,
  sortBucketsByOrder,
} from "~/Concordance/constants";
import { FilterChipGroup } from "~/Concordance/components/FilterChipGroup";

const WORK_CAP = 8;
const SURFACE_CAP = 6;

export function FilterRail(props: {
  data: LemmaDetailResponse;
  scope: ConcScope;
  scopeAuthor?: string;
  scopeWork?: string;
  caseFilter?: string;
  numberFilter?: string;
  surface?: string;
  currentWorkScope?: string;
  onSetScope: (patch: { scope: ConcScope; scopeAuthor?: string; scopeWork?: string }) => void;
  onSetCase: (v: string | undefined) => void;
  onSetNumber: (v: string | undefined) => void;
  onSetSurface: (v: string | undefined) => void;
  onSetWork: (w: string) => void;
  onResetAll: () => void;
}) {
  // Morphology abbreviations are language-specific: German uses Akk/Vok,
  // Greek & Latin the classical Acc/Voc (+ a dual number). Drive both
  // off the response's ``lang`` so the detail rail matches the data.
  const caseLabel = createMemo(() => caseLabelFor(props.data.lang));
  const numberLabel = createMemo(() => numberLabelFor(props.data.lang));

  const orderedCases = createMemo(() => sortBucketsByOrder(props.data.case_breakdown, CASES_ORDER));
  const orderedNumbers = createMemo(() =>
    sortBucketsByOrder(props.data.number_breakdown, NUMBERS_ORDER),
  );
  const orderedGenders = createMemo(() =>
    sortBucketsByOrder(props.data.gender_breakdown, GENDERS_ORDER),
  );

  /** Single-attested gender — pulled into the lemma identity card so
   *  the rail's Gender section can switch to the locked-prose state.
   *  Returns null when the lemma has multiple genders (rare but real:
   *  some Latin nouns alternate, e.g. ``dies`` masc/fem).
   *
   *  spaCy occasionally mislabels gender on a handful of tokens — a
   *  long-tail "Fem 38" alongside "Masc 4494" for Geist is noise, not
   *  evidence of a genuinely ambiguous lemma. Treat any gender that
   *  accounts for >95% of the total as the locked value. */
  const lockedGender = createMemo(() => {
    const gs = orderedGenders();
    const top = gs[0];
    if (top === undefined) return null;
    if (gs.length === 1) return top.value;
    const total = gs.reduce((s, b) => s + b.count, 0);
    return top.count / total > 0.95 ? top.value : null;
  });

  const [workSearch, setWorkSearch] = createSignal("");
  const [workExpanded, setWorkExpanded] = createSignal(false);
  const [surfaceExpanded, setSurfaceExpanded] = createSignal(false);

  /** Work list, filtered by the in-rail search field. Substring match
   *  on the displayed work title (post-abbreviation). */
  const visibleWorks = createMemo(() => {
    const all = props.data.work_breakdown;
    const q = workSearch().trim().toLowerCase();
    const filtered = q
      ? all.filter(
          (b) => abbrevWork(b.value).toLowerCase().includes(q) || b.value.toLowerCase().includes(q),
        )
      : all;
    return workExpanded() || q ? filtered : filtered.slice(0, WORK_CAP);
  });
  const workOverflow = createMemo(() => props.data.work_breakdown.length - WORK_CAP);

  const visibleSurfaces = createMemo(() =>
    surfaceExpanded()
      ? props.data.surface_breakdown
      : props.data.surface_breakdown.slice(0, SURFACE_CAP),
  );
  const surfaceOverflow = createMemo(() => props.data.surface_breakdown.length - SURFACE_CAP);

  /** Pills shown in the applied-filters card. Each carries its own
   *  remove behaviour so the card never needs to know the filter kind. */
  const appliedPills = createMemo(() => {
    const pills: { k: string; v: string; italic?: boolean; onRemove: () => void }[] = [];
    if (props.scope === "work" && props.scopeWork) {
      pills.push({
        k: "work",
        v: abbrevWork(props.scopeWork),
        onRemove: () =>
          props.onSetScope({
            scope: "corpus",
            scopeAuthor: undefined,
            scopeWork: undefined,
          }),
      });
    } else if (props.scope === "author" && props.scopeAuthor) {
      pills.push({
        k: "author",
        v: props.scopeAuthor,
        onRemove: () =>
          props.onSetScope({
            scope: "corpus",
            scopeAuthor: undefined,
            scopeWork: undefined,
          }),
      });
    }
    if (props.caseFilter) {
      pills.push({
        k: "case",
        v: caseLabel()[props.caseFilter] ?? props.caseFilter,
        onRemove: () => props.onSetCase(undefined),
      });
    }
    if (props.numberFilter) {
      pills.push({
        k: "num",
        v: numberLabel()[props.numberFilter] ?? props.numberFilter,
        onRemove: () => props.onSetNumber(undefined),
      });
    }
    if (props.surface) {
      pills.push({
        k: "surface",
        v: props.surface,
        italic: true,
        onRemove: () => props.onSetSurface(undefined),
      });
    }
    return pills;
  });

  return (
    <div class="filter-rail">
      {/* Scope segmented control sits at the top — replaces the header
          pill duplicate on F2's LIVE design. The Author/Work segments
          are only active when we already have a value for them; the
          ScopePillDetail in the page header still drives the user into
          those scopes via keyboard shortcuts and the work-list. */}
      <div class="fr-group">
        <div class="fr-label">
          <span>Scope</span>
        </div>
        <div class="fr-scope">
          <span
            class={"seg" + (props.scope === "corpus" ? " on" : "")}
            onClick={() => {
              if (props.scope !== "corpus") {
                props.onSetScope({
                  scope: "corpus",
                  scopeAuthor: undefined,
                  scopeWork: undefined,
                });
              }
            }}
          >
            Corpus
          </span>
          <span
            class={"seg" + (props.scope === "author" ? " on" : "")}
            onClick={() => {
              // Only navigable when we already have an author to scope
              // to — the work-list click below sets one, as does the
              // index page when the user clicks a lemma from an author
              // scope. Otherwise the segment is a no-op (cursor stays
              // pointer so the click target is still discoverable).
              if (props.scope !== "author" && props.scopeAuthor) {
                props.onSetScope({ scope: "author" });
              }
            }}
          >
            {props.scopeAuthor ?? "Author"}
          </span>
          <span
            class={"seg" + (props.scope === "work" ? " on" : "")}
            onClick={() => {
              if (props.scope !== "work" && props.scopeWork) {
                props.onSetScope({ scope: "work" });
              }
            }}
          >
            {props.scopeWork ? abbrevWork(props.scopeWork) : "Work"}
          </span>
        </div>
      </div>

      <Show when={appliedPills().length > 0}>
        <div class="applied-filters">
          <div class="hd">
            <span>
              {appliedPills().length} filter{appliedPills().length === 1 ? "" : "s"} applied
            </span>
            <span class="reset" onClick={() => props.onResetAll()}>
              ↺ reset
            </span>
          </div>
          <div class="pills">
            <For each={appliedPills()}>
              {(p) => (
                <span class="pill">
                  <span class="k">{p.k}</span>
                  <span class={"v" + (p.italic ? "" : "")}>{p.v}</span>
                  <span
                    class="x"
                    onClick={(e) => {
                      e.stopPropagation();
                      p.onRemove();
                    }}
                  >
                    ×
                  </span>
                </span>
              )}
            </For>
          </div>
        </div>
      </Show>

      <Show when={props.data.work_breakdown.length > 0}>
        <div class="fr-group">
          <div class="fr-label">
            <span>
              Work
              <Show when={props.currentWorkScope}>
                <span class="applied">· {abbrevWork(props.currentWorkScope!)}</span>
              </Show>
            </span>
            <Show when={props.currentWorkScope}>
              <span class="clr" onClick={() => props.onSetWork("")}>
                clear
              </span>
            </Show>
          </div>
          <Show when={props.data.work_breakdown.length > WORK_CAP}>
            <div class="fr-search">
              <span class="ico">⌕</span>
              <input
                type="text"
                placeholder="Find work…"
                value={workSearch()}
                onInput={(e) => setWorkSearch(e.currentTarget.value)}
              />
            </div>
          </Show>
          <For each={visibleWorks()}>
            {(b) => (
              <div
                class={"fr-check" + (props.currentWorkScope === b.value ? " on" : "")}
                onClick={() => props.onSetWork(b.value)}
                title={b.value}
              >
                <span class="box" />
                <span>{abbrevWork(b.value)}</span>
                <span class="ct">{b.count.toLocaleString()}</span>
              </div>
            )}
          </For>
          <Show when={!workExpanded() && !workSearch() && workOverflow() > 0}>
            <span class="fr-more" onClick={() => setWorkExpanded(true)}>
              + {workOverflow()} more work{workOverflow() === 1 ? "" : "s"} ▾
            </span>
          </Show>
        </div>
      </Show>

      <Show when={orderedCases().length > 0}>
        <FilterChipGroup
          label="Case"
          applied={
            props.caseFilter ? (caseLabel()[props.caseFilter] ?? props.caseFilter) : undefined
          }
          onClear={() => props.onSetCase(undefined)}
          buckets={orderedCases()}
          selected={props.caseFilter}
          labelFor={(v) => caseLabel()[v] ?? v}
          titleFor={(b) => `${b.count.toLocaleString()} occurrence${b.count === 1 ? "" : "s"}`}
          onToggle={props.onSetCase}
        />
      </Show>

      <Show when={orderedNumbers().length > 0}>
        <FilterChipGroup
          label="Number"
          applied={
            props.numberFilter
              ? (numberLabel()[props.numberFilter] ?? props.numberFilter)
              : undefined
          }
          onClear={() => props.onSetNumber(undefined)}
          buckets={orderedNumbers()}
          selected={props.numberFilter}
          labelFor={(v) => numberLabel()[v] ?? v}
          titleFor={(b) => b.count.toLocaleString()}
          onToggle={props.onSetNumber}
        />
      </Show>

      <Show when={orderedGenders().length > 0}>
        <div class="fr-group">
          <div class="fr-label">
            <span>Gender</span>
          </div>
          <Show
            when={lockedGender()}
            fallback={
              <div class="fr-opts">
                <For each={orderedGenders()}>
                  {(b) => (
                    <span class="fr-opt muted" title={b.count.toLocaleString()}>
                      {GENDER_LABEL[b.value] ?? b.value}
                    </span>
                  )}
                </For>
              </div>
            }
          >
            {/* Single attested gender — render as prose. The lemma
                identity card carries this fact too; the rail slot stays
                so the IA doesn't shift between lemmas. */}
            <div class="fr-locked">
              <span>
                <b>{GENDER_LABEL[lockedGender()!] ?? lockedGender()}</b> only — single attested
                gender for this lemma.
              </span>
            </div>
          </Show>
        </div>
      </Show>

      <Show when={props.data.surface_breakdown.length > 0}>
        <FilterChipGroup
          label="Surface form"
          applied={props.surface}
          onClear={() => props.onSetSurface(undefined)}
          buckets={visibleSurfaces()}
          selected={props.surface}
          labelFor={(v) => v}
          titleFor={(b) => b.count.toLocaleString()}
          onToggle={props.onSetSurface}
        >
          <Show when={!surfaceExpanded() && surfaceOverflow() > 0}>
            <span class="fr-more" onClick={() => setSurfaceExpanded(true)}>
              + {surfaceOverflow()} more form{surfaceOverflow() === 1 ? "" : "s"} ▾
            </span>
          </Show>
        </FilterChipGroup>
      </Show>
    </div>
  );
}
