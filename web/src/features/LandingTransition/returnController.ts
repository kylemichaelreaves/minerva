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

import { createSignal, type Accessor } from "solid-js";
import type { Rect } from "~/features/LandingTransition/flight";
import {
  FADE_MS,
  GRACE_MS,
  LIFT_MS,
  SETTLE_EASE,
  type Flight,
} from "~/features/LandingTransition/controller";
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
}

/** Keyframes for the chat composer's slide into the landing box: its centre
 *  onto the box's centre, its top onto the box's top, its width onto the
 *  box's. The inverse of `composerKeyframes`. */
export function returnKeyframes(g: ReturnGeometry): { wrap: Keyframe[]; box: Keyframe[] } {
  const dx = g.box.left + g.box.width / 2 - (g.composer.left + g.composer.width / 2);
  const dy = g.box.top - g.composer.top;
  return {
    wrap: [{ transform: "translate(0px, 0px)" }, { transform: `translate(${dx}px, ${dy}px)` }],
    box: [{ maxWidth: `${g.composer.width}px` }, { maxWidth: `${g.box.width}px` }],
  };
}

function rectOf(el: Element): Rect {
  const r = el.getBoundingClientRect();
  return { top: r.top, left: r.left, width: r.width, height: r.height };
}

const STAGE_VARS = ["--lt-d", "--lt-ease", "--lt-top", "--lt-left", "--lt-width"] as const;

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
  root.style.setProperty("--lt-d", `${LIFT_MS}ms`);
  root.style.setProperty("--lt-ease", SETTLE_EASE);
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
  const wrap = document.querySelector<HTMLElement>(".composer-wrap");
  const composer = document.querySelector<HTMLElement>(".composer");
  const anims: Animation[] = [];
  const undo = () => {
    for (const a of anims) a.cancel();
  };
  try {
    if (wrap) anims.push(wrap.animate(k.wrap, travel));
    if (composer) anims.push(composer.animate(k.box, travel));
  } catch (err) {
    undo();
    throw err;
  }
  return { finished: Promise.all(anims.map((a) => a.finished)), cancel: undo };
}

export function defaultReturnEnv(): ReturnEnv {
  return {
    reducedMotion: () => matchMedia("(prefers-reduced-motion: reduce)").matches,
    canAnimate: () => typeof Element.prototype.animate === "function",
    setStage,
    measure: () => {
      const composer = document.querySelector<HTMLElement>(".composer");
      const box = document.querySelector<HTMLElement>(".landing-input-wrap");
      return composer && box ? { composer: rectOf(composer), box: rectOf(box) } : null;
    },
    play: playReturn,
  };
}

function attempt<T>(fn: () => T): T | null {
  try {
    return fn();
  } catch (err) {
    console.warn("return transition skipped", err);
    return null;
  }
}

export function createReturnTransition(env: ReturnEnv = defaultReturnEnv()): {
  phase: Accessor<ReturnPhase>;
  begin(go: () => void): void;
  cancel(): void;
} {
  const [phase, setPhase] = createSignal<ReturnPhase>("idle");
  let flight: Flight | null = null;
  let timer: ReturnType<typeof setTimeout> | undefined;

  function end() {
    clearTimeout(timer);
    timer = undefined;
    const running = flight;
    flight = null;
    setPhase("idle");
    env.setStage("idle");
    running?.cancel();
  }

  /** `go` first, while the layer is still up: the landing it navigates to
   *  is the layer itself (same instance), so there is no frame with neither. */
  function finish(go: () => void) {
    try {
      go();
    } finally {
      end();
    }
  }

  function beginReturn(go: () => void) {
    env.setStage("return");
    setPhase("return");
    const g = attempt(() => env.measure());
    const started = g && attempt(() => env.play(g));
    if (!started) {
      finish(go);
      return;
    }
    flight = started;
    timer = setTimeout(() => finish(go), LIFT_MS + GRACE_MS);
    const settle = () => {
      if (flight === started) finish(go);
    };
    started.finished.then(settle, settle);
  }

  function begin(go: () => void) {
    if (phase() !== "idle") return;
    if (env.reducedMotion()) {
      env.setStage("fade");
      setPhase("fade");
      timer = setTimeout(() => finish(go), FADE_MS);
    } else if (env.canAnimate()) {
      beginReturn(go);
    } else {
      go();
    }
  }

  /** Something else moved the page mid-flight (a sidebar pick, New
   *  conversation): stop, and do not navigate on top of it. */
  function cancel() {
    if (phase() !== "idle") end();
  }

  return { phase, begin, cancel };
}
