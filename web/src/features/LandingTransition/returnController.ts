// The chat → landing transition, the inverse of `controller.ts`'s lift. On
// Escape in a settled chat it picks one of three paths and always leaves for
// the landing exactly once:
//
//   return — the landing mounts as a layer over the chat; its furniture
//            drifts back into place while the thread and topbar fade out,
//            and the real chat composer slides down into the landing box
//            (LIFT_MS);
//   fade   — `prefers-reduced-motion`: nothing travels, the landing fades in
//            over the chat as the chat fades out (FADE_MS);
//   cut    — no Web Animations, or anything failed to measure: an instant
//            swap, which is what "New conversation" does.
//
// Nothing flies back with the question: the landing it returns to is empty.
// The chat stays mounted until the end — `go` (which navigates, and so
// clears the thread) runs only once the flight has settled.

import type { Accessor } from "solid-js";
import { rectOf, settleOffset, type Rect } from "~/features/LandingTransition/flight";
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

export type ReturnPhase = "idle" | "return" | "fade";

export interface ReturnGeometry {
  /** The chat composer's box, where the flight starts. */
  composer: Rect;
  /** The landing box it settles into. */
  box: Rect;
}

export interface ReturnEnv {
  reducedMotion(): boolean;
  canAnimate(): boolean;
  /** Before the landing layer mounts: pins the layer to where the landing
   *  will sit once it is in flow, and sets the timing (or clears both). */
  setStage(phase: ReturnPhase): void;
  /** After it mounts. */
  measure(): ReturnGeometry | null;
  play(g: ReturnGeometry): Flight;
  /** As the lift's: calls `interrupted` when the viewport width or the theme
   *  changes, until the returned function is called. The layer is pinned
   *  in px at the start, so a resize mid-return leaves it at the old width
   *  (#865). */
  watchInterrupts(interrupted: () => void): () => void;
}

/** Keyframes for the chat composer's slide into the landing box: its centre
 *  onto the box's centre, its width and height onto the box's, and — the
 *  wrap being bottom-pinned — its bottom onto the box's bottom. The inverse
 *  of `composerKeyframes`. */
export function returnKeyframes(g: ReturnGeometry): { wrap: Keyframe[]; box: Keyframe[] } {
  const { dx, dy } = settleOffset(g.box, g.composer);
  return {
    wrap: [{ transform: "translate(0px, 0px)" }, { transform: `translate(${dx}px, ${dy}px)` }],
    box: [
      { maxWidth: `${g.composer.width}px`, height: `${g.composer.height}px` },
      { maxWidth: `${g.box.width}px`, height: `${g.box.height}px` },
    ],
  };
}

const STAGE_VARS = [...TIMING_VARS, "--lt-top", "--lt-left", "--lt-width"] as const;

function setStage(phase: ReturnPhase) {
  const root = document.documentElement;
  // The composer is on its way out: nothing typed or clicked into it now
  // would survive the arrival. (A cancel hands it back.)
  document.querySelector(".composer-wrap")?.toggleAttribute("inert", phase !== "idle");
  if (phase === "idle") {
    delete root.dataset.ltReturn;
    for (const v of STAGE_VARS) root.style.removeProperty(v);
    return;
  }
  // The document is the scroller (#851), so a long chat may be scrolled far
  // down `.main`. The layer is `position: fixed` at the spot `.main` starts
  // when scrolled to the top — where the landing will sit in flow, once the
  // chat is gone and the page is that short again.
  const main = document.querySelector<HTMLElement>(".main");
  const r = main?.getBoundingClientRect();
  setTiming(root.style);
  root.style.setProperty("--lt-top", `${(r?.top ?? 0) + window.scrollY}px`);
  root.style.setProperty("--lt-left", `${r?.left ?? 0}px`);
  root.style.setProperty("--lt-width", `${r?.width ?? window.innerWidth}px`);
  // The chat's parts — thread, topbar, composer — all leave together, so
  // they key on one attribute rather than a prop each.
  root.dataset.ltReturn = phase;
}

function playReturn(g: ReturnGeometry): Flight {
  const k = returnKeyframes(g);
  const travel: KeyframeAnimationOptions = { duration: LIFT_MS, easing: SETTLE_EASE, fill: "both" };
  return animateAll([
    [document.querySelector(".composer-wrap"), k.wrap, travel],
    [document.querySelector(".composer"), k.box, travel],
  ]);
}

export function defaultReturnEnv(): ReturnEnv {
  return {
    ...motionProbes,
    setStage,
    measure: () => {
      const composer = document.querySelector<HTMLElement>(".composer");
      const box = document.querySelector<HTMLElement>(".landing-input-wrap");
      return composer && box ? { composer: rectOf(composer), box: rectOf(box) } : null;
    },
    play: playReturn,
    watchInterrupts: watchViewport,
  };
}

export function createReturnTransition(env: ReturnEnv = defaultReturnEnv()): {
  phase: Accessor<ReturnPhase>;
  begin(go: () => void): void;
  cancel(): void;
} {
  const m = createFlightMachine<"return" | "fade">({
    unstage: () => env.setStage("idle"),
    watchInterrupts: (cb) => env.watchInterrupts(cb),
  });

  /** `go` first, while the layer is still up: the landing it navigates to
   *  is the layer itself (same instance), so there is no frame with neither.
   *  This is the return's "done" for every path — settle, timeout and
   *  interrupt alike: an interrupted return arrives at once rather than
   *  abandoning the reader mid-way back. */
  function finish(go: () => void) {
    try {
      go();
    } finally {
      m.end();
    }
  }

  function beginReturn(go: () => void) {
    // Staged BEFORE the phase: the layer must be pinned before it mounts.
    env.setStage("return");
    m.enter("return");
    const g = attempt("return transition", () => env.measure());
    const started = g && attempt("return transition", () => env.play(g));
    if (!started) {
      finish(go);
      return;
    }
    m.fly(started, () => finish(go));
  }

  function begin(go: () => void) {
    if (m.phase() !== "idle") return;
    if (env.reducedMotion()) {
      env.setStage("fade");
      m.enter("fade");
      m.after(FADE_MS, () => finish(go));
    } else if (env.canAnimate()) {
      beginReturn(go);
    } else {
      go();
    }
  }

  /** Something else moved the page mid-flight (a sidebar pick, New
   *  conversation): stop, and do not navigate on top of it. */
  return { phase: m.phase, begin, cancel: m.cancel };
}
