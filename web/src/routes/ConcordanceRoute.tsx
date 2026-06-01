import { Show } from "solid-js";
import { ConcordanceIndexPage, ConcordanceLemmaDetail } from "~/Concordance";
import type { RouteContextProps } from "~/routes/types";
import {
  isConcordanceRoute,
  isLemmaRoute,
  mergeRoutePatchAllowClear,
  type RouteConcordance,
  type RouteLemma,
} from "~/routes/routeUtils";

/**
 * Solid runs each component body once — anything captured at that
 * point is frozen for the component's lifetime. The previous shape
 * ``const r = props.routing.route()`` was a classic stale-snapshot
 * bug: it ran at first mount, then every subsequent navigation re-set
 * the URL but the captured ``r`` (and every prop derived from it —
 * ``freqMax``, ``letter``, ``q``, etc.) stayed at the initial values.
 * The slider thumbs and the reset-all chip looked "broken" because
 * their prop updates never arrived.
 *
 * Fix: keep the route as an accessor (``route()``) and read it inside
 * each JSX expression. Solid wraps every attribute in an effect, so
 * each navigation re-evaluates the per-prop reads and the child
 * components see fresh values. The ``<Show>`` wrap (non-keyed) leaves
 * the child instance in place while its props update, so the resource
 * subscription survives the navigation rather than refetching from
 * scratch on every URL change.
 */

export function ConcordanceRoute(props: RouteContextProps) {
  const route = () => props.routing.route();
  const conc = (): RouteConcordance => {
    const r = route();
    if (!isConcordanceRoute(r)) throw new Error("expected concordance route");
    return r;
  };
  const lemma = (): RouteLemma => {
    const r = route();
    if (!isLemmaRoute(r)) throw new Error("expected concordance-lemma route");
    return r;
  };

  return (
    <>
      <Show when={isConcordanceRoute(route())}>
        <ConcordanceIndexPage
          lang={conc().lang}
          scope={conc().scope}
          scopeAuthor={conc().scopeAuthor}
          scopeWork={conc().scopeWork}
          letter={conc().letter}
          sort={conc().sort}
          pos={conc().pos}
          freqMin={conc().freqMin}
          freqMax={conc().freqMax}
          q={conc().q}
          onNavigate={(patch) => {
            // Read fresh inside the callback — the closure must see
            // the LATEST route on each invocation, not the one at
            // mount time. Otherwise every navigate would base its
            // merge on stale state and silently lose just-applied
            // filters from the URL.
            const cur = conc();
            props.routing.navigate(
              mergeRoutePatchAllowClear(
                {
                  kind: "concordance" as const,
                  lang: cur.lang,
                  scope: cur.scope,
                  scopeAuthor: cur.scopeAuthor,
                  scopeWork: cur.scopeWork,
                  letter: cur.letter,
                  sort: cur.sort,
                  pos: cur.pos,
                  freqMin: cur.freqMin,
                  freqMax: cur.freqMax,
                  q: cur.q,
                },
                patch,
              ),
            );
          }}
          onOpenLemma={(lemmaName, scope, scopeAuthor, scopeWork) => {
            const cur = conc();
            props.routing.navigate({
              kind: "concordance-lemma",
              lemma: lemmaName,
              lang: cur.lang,
              scope: scope ?? cur.scope,
              scopeAuthor: scopeAuthor ?? cur.scopeAuthor,
              scopeWork: scopeWork ?? cur.scopeWork,
            });
          }}
        />
      </Show>

      <Show when={isLemmaRoute(route())}>
        <ConcordanceLemmaDetail
          lemma={lemma().lemma}
          lang={lemma().lang}
          scope={lemma().scope}
          scopeAuthor={lemma().scopeAuthor}
          scopeWork={lemma().scopeWork}
          caseFilter={lemma().caseFilter}
          numberFilter={lemma().numberFilter}
          surface={lemma().surface}
          onNavigate={(patch) => {
            const cur = lemma();
            props.routing.navigate(
              mergeRoutePatchAllowClear(
                {
                  kind: "concordance-lemma" as const,
                  lemma: cur.lemma,
                  lang: cur.lang,
                  scope: cur.scope,
                  scopeAuthor: cur.scopeAuthor,
                  scopeWork: cur.scopeWork,
                  caseFilter: cur.caseFilter,
                  numberFilter: cur.numberFilter,
                  surface: cur.surface,
                },
                patch,
              ),
            );
          }}
          onBackToIndex={() => {
            const cur = lemma();
            props.routing.navigate({
              kind: "concordance",
              lang: cur.lang,
              scope: cur.scope,
              scopeAuthor: cur.scopeAuthor,
              scopeWork: cur.scopeWork,
            });
          }}
          onOpenChunk={props.openSourceInReader}
        />
      </Show>
    </>
  );
}
