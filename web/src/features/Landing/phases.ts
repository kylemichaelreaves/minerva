// The landing's two transitions, as data: each phase that is in flight maps
// to the class the landing wears during it. A phase missing from its map
// ("idle", or none at all) means no transition is running.

import { createEffect } from "solid-js";
import type { Phase } from "~/features/LandingTransition/controller";
import type { ReturnPhase } from "~/features/LandingTransition/returnController";

/** Landing → chat: the landing lifts away, or fades on a phone. */
export const LEAVING_CLASS: Partial<Record<Phase, string>> = {
  lift: "is-leaving",
  fade: "is-fading",
};

/** Chat → landing (Escape): the landing drifts back, or fades in. */
export const ARRIVING_CLASS: Partial<Record<ReturnPhase, string>> = {
  return: "is-arriving",
  fade: "is-arriving-fade",
};

export const inFlight = <P extends string>(
  classes: Partial<Record<P, string>>,
  phase: P | undefined,
): boolean => phase !== undefined && phase in classes;

/** Runs `fn` when a transition finishes: the phase goes from in flight to
 *  cleared. Not on "idle" — that is a flight running to its end as the
 *  landing unmounts. */
export function createPhaseEndEffect<P extends string>(
  phase: () => P | undefined,
  classes: Partial<Record<P, string>>,
  fn: () => void,
): void {
  createEffect(
    () => phase(),
    (now, was) => {
      if (inFlight(classes, was) && now === undefined) fn();
    },
  );
}
