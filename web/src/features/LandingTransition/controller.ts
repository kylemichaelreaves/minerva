// The landing → chat transition's state machine. On Begin it picks one of
// three paths and always sends the question exactly once:
//
//   lift — the real chat composer slides from the landing box into place and
//          the question flies as a ghost into the first user turn (650ms);
//   fade — `prefers-reduced-motion`: nothing travels, the landing crossfades
//          out (180ms);
//   cut  — no Web Animations, or anything failed to measure: today's
//          instant swap.
//
// `phase()` drives the CSS (Landing `leaving`, Thread `arriving`, Topbar and
// Composer `entering`). Every DOM read and animation goes through
// `TransitionEnv`, so tests can drive each path without a layout engine.

import type { Accessor } from "solid-js";
import {
  composerKeyframes,
  FRAME_PROPS,
  ghostKeyframes,
  measureOrigin,
  measureTarget,
  type FlightOrigin,
  type FlightTarget,
} from "~/features/LandingTransition/flight";
import {
  animateAll,
  attempt,
  createFlightMachine,
  FADE_MS,
  LIFT_MS,
  motionProbes,
  setTiming,
  SETTLE_EASE,
  TIMING_VARS,
  watchViewport,
  type Flight,
} from "~/features/LandingTransition/flightMachine";
import "~/features/LandingTransition/landingTransition.css";

// Re-exported: the timing and the Flight shape are shared with the return
// and live in flightMachine.ts, but this module is where callers find them.
export {
  FADE_MS,
  GRACE_MS,
  LIFT_MS,
  SETTLE_EASE,
  type Flight,
} from "~/features/LandingTransition/flightMachine";

export type Phase = "idle" | "lift" | "fade";

export interface TransitionEnv {
  reducedMotion(): boolean;
  canAnimate(): boolean;
  measureOrigin(): FlightOrigin | null;
  measureTarget(): FlightTarget | null;
  play(o: FlightOrigin, t: FlightTarget): Flight;
  /** Before the swap: sets the timing, and pins the leaving layer to the
   *  landing's height (or clears both). */
  setStage(on: boolean): void;
  /** Calls `interrupted` when the flight's measurements go stale — the
   *  viewport resizes or the theme changes — until the returned function is
   *  called. */
  watchInterrupts(interrupted: () => void): () => void;
}

function playFlight(o: FlightOrigin, t: FlightTarget): Flight {
  const ghost = document.createElement("p");
  ghost.className = "lift-ghost";
  ghost.setAttribute("aria-hidden", "true");
  ghost.textContent = o.text;
  for (const p of FRAME_PROPS) ghost.style[p] = t.style[p];
  document.body.appendChild(ghost);

  const g = ghostKeyframes(o, t);
  const c = composerKeyframes(o, t);
  const travel: KeyframeAnimationOptions = { duration: LIFT_MS, easing: SETTLE_EASE, fill: "both" };
  const chrome: KeyframeAnimationOptions = {
    duration: LIFT_MS * 0.35,
    delay: LIFT_MS * 0.65,
    easing: "ease",
    fill: "both",
  };
  // On a failed start, and at the end, the ghost goes too — least of all may
  // a fixed ghost holding the question stay behind.
  return animateAll(
    [
      [ghost, g.move, travel],
      [ghost, g.chrome, chrome],
      [document.querySelector(".composer-wrap"), c.wrap, travel],
      [document.querySelector(".composer"), c.box, travel],
    ],
    () => ghost.remove(),
  );
}

export function defaultEnv(): TransitionEnv {
  return {
    ...motionProbes,
    measureOrigin: () => {
      const ta = document.querySelector<HTMLTextAreaElement>(".landing-input");
      const box = document.querySelector<HTMLElement>(".landing-input-wrap");
      return ta && box ? measureOrigin(ta, box) : null;
    },
    measureTarget: () => {
      // The landing submit makes a one-turn thread, so the first match is
      // the turn the question lands in.
      const body = document.querySelector<HTMLElement>(".turn-user-inner .turn-body");
      const composer = document.querySelector<HTMLElement>(".composer");
      return body && composer ? measureTarget(body, composer) : null;
    },
    play: playFlight,
    setStage: (on) => {
      const s = document.documentElement.style;
      if (on) {
        setTiming(s);
        // Still in flow, before the swap. As a layer it is `inset: 0` on
        // `.main`, which shrinks to the chat's height the moment the chat
        // mounts; a landing taller than the viewport would reflow and its
        // lower parts jump up on frame 0.
        const landing = document.querySelector(".landing");
        if (landing) s.setProperty("--lt-leave-h", `${landing.getBoundingClientRect().height}px`);
      } else {
        for (const v of [...TIMING_VARS, "--lt-leave-h"]) s.removeProperty(v);
      }
    },
    watchInterrupts: watchViewport,
  };
}

export function createLandingTransition(env: TransitionEnv = defaultEnv()): {
  phase: Accessor<Phase>;
  begin(text: string, send: (text: string) => void): void;
  cancel(): void;
} {
  const m = createFlightMachine<"lift" | "fade">({
    unstage: () => env.setStage(false),
    watchInterrupts: (cb) => env.watchInterrupts(cb),
  });

  /** The question is sent at the START of the flight, exactly once; if
   *  sending throws, nothing is left staged. */
  function sendOrEnd(text: string, send: (text: string) => void) {
    try {
      send(text);
    } catch (err) {
      m.end();
      throw err;
    }
  }

  function beginFade(text: string, send: (text: string) => void) {
    m.enter("fade");
    env.setStage(true);
    sendOrEnd(text, send);
    m.after(FADE_MS, m.end);
  }

  function beginLift(text: string, send: (text: string) => void) {
    const origin = attempt("landing transition", () => env.measureOrigin());
    if (!origin) {
      send(text);
      return;
    }
    m.enter("lift");
    env.setStage(true);
    sendOrEnd(text, send);

    const target = attempt("landing transition", () => env.measureTarget());
    const started = target && attempt("landing transition", () => env.play(origin, target));
    if (!started) {
      m.end();
      return;
    }
    m.fly(started, m.end);
  }

  function begin(text: string, send: (text: string) => void) {
    if (m.phase() !== "idle") return;
    if (env.reducedMotion()) beginFade(text, send);
    else if (env.canAnimate()) beginLift(text, send);
    else send(text);
  }

  return { phase: m.phase, begin, cancel: m.cancel };
}
