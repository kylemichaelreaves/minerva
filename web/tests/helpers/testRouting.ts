// Shared helpers for controller and component tests that need a
// controllable RoutingApi without mounting the full hash router.

import { createSignal } from "solid-js";
import { vi } from "vitest";
import type { Route, RoutingApi } from "~/routing";

/** Wait one microtask tick so Solid createEffect callbacks flush. */
export const flush = (): Promise<void> => Promise.resolve();

export function okResponse(body: unknown): Response {
  return { ok: true, json: () => Promise.resolve(body) } as unknown as Response;
}

export function errorResponse(
  status: number,
  statusText: string,
  body?: unknown,
): Response {
  // readErrorDetail reads the body via .text(); mirror a real Response.
  return {
    ok: false,
    status,
    statusText,
    text: () => Promise.resolve(body === undefined ? "" : JSON.stringify(body)),
  } as unknown as Response;
}

export interface TestRouting extends RoutingApi {
  /** Reactive route accessor for driving navigation in tests. */
  setRoute: (r: Route) => void;
  navigateSpy: ReturnType<typeof vi.fn<(r: Route) => void>>;
  replaceSpy: ReturnType<typeof vi.fn<(r: Route) => void>>;
}

export function createTestRouting(initial: Route = { kind: "landing" }): TestRouting {
  const [route, setRoute] = createSignal<Route>(initial);
  const navigateSpy = vi.fn((r: Route) => {
    setRoute(() => r);
  });
  const replaceSpy = vi.fn((r: Route) => {
    setRoute(() => r);
  });
  return {
    route,
    navigate: navigateSpy,
    replace: replaceSpy,
    setRoute,
    navigateSpy,
    replaceSpy,
  };
}
