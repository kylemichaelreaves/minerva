import type { Route } from "~/routing";

export type RouteRefs = Extract<Route, { kind: "refs" }>;
export type RouteRefsReview = Extract<Route, { kind: "refs-review" }>;
export type RouteNetwork = Extract<Route, { kind: "network" }>;
export type RouteNetworkArc = Extract<Route, { kind: "network-arc" }>;
export type RouteNetworkCoverage = Extract<Route, { kind: "network-coverage" }>;
export type RouteConcordance = Extract<Route, { kind: "concordance" }>;
export type RouteLemma = Extract<Route, { kind: "concordance-lemma" }>;

export function isRefsRoute(r: Route): r is RouteRefs {
  return r.kind === "refs";
}

export function isRefsReviewRoute(r: Route): r is RouteRefsReview {
  return r.kind === "refs-review";
}

export function isNetworkRoute(r: Route): r is RouteNetwork {
  return r.kind === "network";
}

export function isNetworkArcRoute(r: Route): r is RouteNetworkArc {
  return r.kind === "network-arc";
}

export function isNetworkCoverageRoute(r: Route): r is RouteNetworkCoverage {
  return r.kind === "network-coverage";
}

export function isConcordanceRoute(r: Route): r is RouteConcordance {
  return r.kind === "concordance";
}

export function isLemmaRoute(r: Route): r is RouteLemma {
  return r.kind === "concordance-lemma";
}

export interface NetworkFilterFields {
  minConfidence?: number;
  sourceAuthors?: string[];
  corpora?: string[];
  sourceMethods?: string[];
}

/** Shared network filter fields from any network-related route. */
export function networkFiltersFromRoute(
  r: Extract<
    Route,
    { kind: "network" | "network-arc" | "network-coverage" }
  >,
): NetworkFilterFields {
  return {
    minConfidence: r.minConfidence,
    sourceAuthors: r.sourceAuthors,
    corpora: r.corpora,
    sourceMethods: r.sourceMethods,
  };
}

export function networkRouteFromFilters(
  kind: "network" | "network-arc" | "network-coverage",
  filters: NetworkFilterFields,
): Route {
  return { kind, ...filters };
}

/** Merge patch into base; `undefined` in patch means preserve base value. */
export function mergeRoutePatch<T extends object>(
  base: T,
  patch: Partial<T>,
): T {
  const out = { ...base };
  for (const key of Object.keys(patch) as (keyof T)[]) {
    if (patch[key] !== undefined) {
      out[key] = patch[key];
    }
  }
  return out;
}

/** Merge patch allowing explicit `undefined` clears (uses `in` check). */
export function mergeRoutePatchAllowClear<T extends object>(
  base: T,
  patch: Partial<T>,
): T {
  const out = { ...base };
  for (const key of Object.keys(patch) as (keyof T)[]) {
    if (key in patch) {
      out[key] = patch[key] as T[keyof T];
    }
  }
  return out;
}
