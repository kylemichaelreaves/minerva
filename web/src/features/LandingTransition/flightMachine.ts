// What the landing → chat lift (`controller.ts`) and the chat → landing
// return (`returnController.ts`) share: the timing, the platform probes, the
// animation start/undo, the interrupt watch, and the state machine that
// owns a running flight (#882).
//
// They used to be two copies, and the copies drifted: only the lift watched
// for a resize or theme change mid-flight, so a resize mid-return left the
// landing layer pinned at the old width and its furniture jumped 170px on
// arrival (#865). The watch now lives in `fly`, so neither direction can
// start a flight without it.
//
// What stays in each controller is what genuinely differs: what is measured,
// what is played, the order of `enter` and `setStage`, and what "done"
// means. The lift's done is `end`; the return's is to navigate, then `end`.

import { createSignal, type Accessor } from "solid-js";

export const LIFT_MS = 650;
export const FADE_MS = 180;
export const SETTLE_EASE = "cubic-bezier(.2,.7,.1,1)";
/** How long past LIFT_MS a flight may run before it is ended regardless —
 *  a `finished` promise that never settles must not strand the phase. */
export const GRACE_MS = 200;

/** Sets the CSS timing both directions read: the lift's duration and ease,
 *  and the fade's duration, so `FADE_MS` is the one number that ends the
 *  fade in JS and in CSS (#882). */
export function setTiming(s: CSSStyleDeclaration) {
  s.setProperty("--lt-d", `${LIFT_MS}ms`);
  s.setProperty("--lt-fade-d", `${FADE_MS}ms`);
  s.setProperty("--lt-ease", SETTLE_EASE);
}
export const TIMING_VARS = ["--lt-d", "--lt-fade-d", "--lt-ease"] as const;

export interface Flight {
  finished: Promise<unknown>;
  cancel(): void;
}

/** The platform probes both directions branch on. */
export const motionProbes = {
  reducedMotion: (): boolean => matchMedia("(prefers-reduced-motion: reduce)").matches,
  canAnimate: (): boolean => typeof Element.prototype.animate === "function",
};

/** One animation to start: skipped when its element is missing. */
export type AnimationStep = readonly [
  el: Element | null,
  keyframes: Keyframe[],
  options: KeyframeAnimationOptions,
];

/** Starts every step whose element exists, as one Flight.
 *
 *  If a start throws, the animations already started are cancelled and
 *  `cleanup` runs before the error propagates: the controller will cut, and
 *  nothing of the half-started flight may stay behind. `cancel` is also the
 *  normal end — cancelling a finished `fill: "both"` animation drops its
 *  held last frame, which is where the element sits anyway. */
export function animateAll(steps: readonly AnimationStep[], cleanup?: () => void): Flight {
  const anims: Animation[] = [];
  const undo = () => {
    for (const a of anims) a.cancel();
    cleanup?.();
  };
  try {
    for (const [el, keyframes, options] of steps) {
      if (el) anims.push(el.animate(keyframes, options));
    }
  } catch (err) {
    undo();
    throw err;
  }
  return { finished: Promise.all(anims.map((a) => a.finished)), cancel: undo };
}

/** Calls `interrupted` when a flight's measurements go stale, until the
 *  returned function is called.
 *
 *  A flight's ends are measured once, in px and computed colours, so a
 *  resize leaves it aimed at the old target (and the return's layer pinned
 *  at the old width), and a theme toggle leaves it in the old theme. Both
 *  are rare mid-flight; the caller cuts. Width only: a phone's keyboard
 *  opening or closing changes the height alone, which moves nothing a
 *  flight is aimed at — and cutting there would cut most phone flights. */
export function watchViewport(interrupted: () => void): () => void {
  const width = window.innerWidth;
  const onResize = () => {
    if (window.innerWidth !== width) interrupted();
  };
  const themes = new MutationObserver(interrupted);
  themes.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  window.addEventListener("resize", onResize);
  return () => {
    themes.disconnect();
    window.removeEventListener("resize", onResize);
  };
}

/** Runs `fn`; on a throw, logs `"<what> skipped"` and returns null so the
 *  caller can cut. */
export function attempt<T>(what: string, fn: () => T): T | null {
  try {
    return fn();
  } catch (err) {
    console.warn(`${what} skipped`, err);
    return null;
  }
}

export interface FlightMachine<P extends string> {
  phase: Accessor<P | "idle">;
  /** Enters a running phase. The caller orders this against its own
   *  `setStage`: the lift enters first, the return stages first. */
  enter: (p: P) => void;
  /** Back to idle: stops the timer and the watch, drops the phase, unstages,
   *  then cancels the flight — in that order, in one task, so the phase drop
   *  reveals the real elements as the animated ones go. */
  end: () => void;
  /** Owns a started flight. `done` runs once: when the flight settles, when
   *  it overruns LIFT_MS + GRACE_MS, or when the viewport interrupts it —
   *  and not at all if `end` got there first. */
  fly: (started: Flight, done: () => void) => void;
  /** No flight to own, only a duration (the reduced-motion fade). */
  after: (ms: number, done: () => void) => void;
  /** `end`, unless already idle. */
  cancel: () => void;
}

export function createFlightMachine<P extends string>(opts: {
  /** Clears whatever the controller staged. */
  unstage(): void;
  watchInterrupts(interrupted: () => void): () => void;
}): FlightMachine<P> {
  const [phase, setPhase] = createSignal<P | "idle">("idle");
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
    setPhase("idle");
    opts.unstage();
    running?.cancel();
  }

  function fly(started: Flight, done: () => void) {
    flight = started;
    const settle = () => {
      if (flight === started) done();
    };
    unwatch = opts.watchInterrupts(settle);
    timer = setTimeout(settle, LIFT_MS + GRACE_MS);
    started.finished.then(settle, settle);
  }

  return {
    phase,
    enter: (p) => setPhase(() => p),
    end,
    fly,
    after: (ms, done) => {
      timer = setTimeout(done, ms);
    },
    cancel: () => {
      if (phase() !== "idle") end();
    },
  };
}
