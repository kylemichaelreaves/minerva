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

import { createSignal, type Accessor } from "solid-js";
import {
  composerKeyframes,
  FRAME_PROPS,
  ghostKeyframes,
  measureOrigin,
  measureTarget,
  type FlightOrigin,
  type FlightTarget,
} from "~/features/LandingTransition/flight";
import "~/features/LandingTransition/landingTransition.css";

export type Phase = "idle" | "lift" | "fade";

export const LIFT_MS = 650;
export const FADE_MS = 180;
export const SETTLE_EASE = "cubic-bezier(.2,.7,.1,1)";
/** How long past LIFT_MS a flight may run before it is ended regardless —
 *  a `finished` promise that never settles must not strand the phase. */
export const GRACE_MS = 200;

export interface Flight {
  finished: Promise<unknown>;
  cancel(): void;
}

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
  const wrap = document.querySelector<HTMLElement>(".composer-wrap");
  const composer = document.querySelector<HTMLElement>(".composer");
  const anims: Animation[] = [];
  const undo = () => {
    for (const a of anims) a.cancel();
    ghost.remove();
  };
  try {
    anims.push(
      ghost.animate(g.move, travel),
      ghost.animate(g.chrome, {
        duration: LIFT_MS * 0.35,
        delay: LIFT_MS * 0.65,
        easing: "ease",
        fill: "both",
      }),
    );
    if (wrap) anims.push(wrap.animate(c.wrap, travel));
    if (composer) anims.push(composer.animate(c.box, travel));
  } catch (err) {
    // The controller will cut; nothing of the half-started flight may stay
    // behind — least of all a fixed ghost holding the question.
    undo();
    throw err;
  }

  return {
    finished: Promise.all(anims.map((a) => a.finished)),
    // Also the normal end: cancelling a finished `fill: "both"` animation
    // drops its held last frame, which is where the element sits anyway.
    cancel: undo,
  };
}

export function defaultEnv(): TransitionEnv {
  return {
    reducedMotion: () => matchMedia("(prefers-reduced-motion: reduce)").matches,
    canAnimate: () => typeof Element.prototype.animate === "function",
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
        s.setProperty("--lt-d", `${LIFT_MS}ms`);
        s.setProperty("--lt-ease", SETTLE_EASE);
        // Still in flow, before the swap. As a layer it is `inset: 0` on
        // `.main`, which shrinks to the chat's height the moment the chat
        // mounts; a landing taller than the viewport would reflow and its
        // lower parts jump up on frame 0.
        const landing = document.querySelector(".landing");
        if (landing) s.setProperty("--lt-leave-h", `${landing.getBoundingClientRect().height}px`);
      } else {
        for (const v of ["--lt-d", "--lt-ease", "--lt-leave-h"]) s.removeProperty(v);
      }
    },
    watchInterrupts: (interrupted) => {
      // The flight's ends are measured once, in px and computed colours, so
      // a resize leaves the ghost aimed at the old target and a theme toggle
      // leaves it in the old theme. Both are rare mid-flight; cut.
      // Width only: a phone's keyboard opening or closing changes the
      // height alone, which moves nothing the ghost is aimed at (the turn
      // sits at the top, and the composer's FLIP is relative to wherever
      // its wrap now is) — and cutting there would cut most phone flights.
      const width = window.innerWidth;
      const onResize = () => {
        if (window.innerWidth !== width) interrupted();
      };
      const themes = new MutationObserver(interrupted);
      themes.observe(document.documentElement, {
        attributes: true,
        attributeFilter: ["data-theme"],
      });
      window.addEventListener("resize", onResize);
      return () => {
        themes.disconnect();
        window.removeEventListener("resize", onResize);
      };
    },
  };
}

/** Runs `fn`; on a throw, logs and returns null so the caller can cut. */
function attempt<T>(fn: () => T): T | null {
  try {
    return fn();
  } catch (err) {
    console.warn("landing transition skipped", err);
    return null;
  }
}

export function createLandingTransition(env: TransitionEnv = defaultEnv()): {
  phase: Accessor<Phase>;
  begin(text: string, send: (text: string) => void): void;
  cancel(): void;
} {
  const [phase, setPhase] = createSignal<Phase>("idle");
  let flight: Flight | null = null;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let unwatch: (() => void) | undefined;

  function end() {
    clearTimeout(timer);
    timer = undefined;
    unwatch?.();
    unwatch = undefined;
    const running = flight;
    flight = null;
    // Same task: the phase drop reveals the real body as the ghost goes.
    setPhase("idle");
    env.setStage(false);
    running?.cancel();
  }

  function sendOrEnd(text: string, send: (text: string) => void) {
    try {
      send(text);
    } catch (err) {
      end();
      throw err;
    }
  }

  function beginFade(text: string, send: (text: string) => void) {
    setPhase("fade");
    env.setStage(true);
    sendOrEnd(text, send);
    timer = setTimeout(end, FADE_MS);
  }

  function beginLift(text: string, send: (text: string) => void) {
    const origin = attempt(() => env.measureOrigin());
    if (!origin) {
      send(text);
      return;
    }
    setPhase("lift");
    env.setStage(true);
    sendOrEnd(text, send);

    const target = attempt(() => env.measureTarget());
    const started = target && attempt(() => env.play(origin, target));
    if (!started) {
      end();
      return;
    }
    flight = started;
    unwatch = env.watchInterrupts(end);
    timer = setTimeout(end, LIFT_MS + GRACE_MS);
    const settle = () => {
      if (flight === started) end();
    };
    started.finished.then(settle, settle);
  }

  function begin(text: string, send: (text: string) => void) {
    if (phase() !== "idle") return;
    if (env.reducedMotion()) beginFade(text, send);
    else if (env.canAnimate()) beginLift(text, send);
    else send(text);
  }

  function cancel() {
    if (phase() !== "idle") end();
  }

  return { phase, begin, cancel };
}
