import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  createLandingTransition,
  defaultEnv,
  FADE_MS,
  GRACE_MS,
  LIFT_MS,
  type Flight,
  type TransitionEnv,
} from "~/features/LandingTransition/controller";
import { composerKeyframes } from "~/features/LandingTransition/flight";
import type { FlightOrigin, FlightTarget } from "~/features/LandingTransition/flight";

const ORIGIN = { text: "Q" } as FlightOrigin;
const TARGET = { body: { top: 0, left: 0, width: 0, height: 0 } } as FlightTarget;

function deferred() {
  let resolve!: () => void;
  const promise = new Promise<void>((r) => {
    resolve = r;
  });
  return { promise, resolve };
}

function fakeEnv(over: Partial<TransitionEnv> = {}) {
  const done = deferred();
  const cancel = vi.fn();
  const flight: Flight = { finished: done.promise, cancel };
  const interrupt: { fire: () => void } = { fire: () => undefined };
  const unwatch = vi.fn();
  const env = {
    reducedMotion: vi.fn<TransitionEnv["reducedMotion"]>(over.reducedMotion ?? (() => false)),
    canAnimate: vi.fn<TransitionEnv["canAnimate"]>(over.canAnimate ?? (() => true)),
    measureOrigin: vi.fn<TransitionEnv["measureOrigin"]>(over.measureOrigin ?? (() => ORIGIN)),
    measureTarget: vi.fn<TransitionEnv["measureTarget"]>(over.measureTarget ?? (() => TARGET)),
    play: vi.fn<TransitionEnv["play"]>(over.play ?? (() => flight)),
    setStage: vi.fn<TransitionEnv["setStage"]>(),
    watchInterrupts: vi.fn<TransitionEnv["watchInterrupts"]>((cb) => {
      interrupt.fire = cb;
      return unwatch;
    }),
  };
  return { env, cancel, done, interrupt, unwatch };
}

beforeEach(() => {
  vi.useFakeTimers();
});
afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("createLandingTransition", () => {
  it("reduced motion fades for FADE_MS, then idles", () => {
    const { env } = fakeEnv({ reducedMotion: vi.fn(() => true) });
    const send = vi.fn();
    const t = createLandingTransition(env);

    t.begin("Q", send);
    expect(send).toHaveBeenCalledExactlyOnceWith("Q");
    expect(t.phase()).toBe("fade");
    expect(env.play).not.toHaveBeenCalled();

    vi.advanceTimersByTime(FADE_MS);
    expect(t.phase()).toBe("idle");
    expect(env.setStage.mock.calls).toEqual([[true], [false]]);
  });

  it("cuts when the browser cannot animate", () => {
    const { env } = fakeEnv({ canAnimate: vi.fn(() => false) });
    const send = vi.fn();
    const t = createLandingTransition(env);

    t.begin("Q", send);
    expect(send).toHaveBeenCalledOnce();
    expect(t.phase()).toBe("idle");
    expect(env.play).not.toHaveBeenCalled();
    expect(env.setStage).not.toHaveBeenCalled();
  });

  it("lifts: measures the origin before sending and the target after", () => {
    const { env } = fakeEnv();
    const send = vi.fn();
    const t = createLandingTransition(env);

    t.begin("Q", send);

    const order = (fn: { mock: { invocationCallOrder: number[] } }) =>
      fn.mock.invocationCallOrder[0] ?? Number.NaN;
    expect(order(env.measureOrigin)).toBeLessThan(order(send));
    expect(order(send)).toBeLessThan(order(env.measureTarget));
    expect(order(env.measureTarget)).toBeLessThan(order(env.play));
    expect(env.play).toHaveBeenCalledWith(ORIGIN, TARGET);
    expect(t.phase()).toBe("lift");
    expect(env.setStage).toHaveBeenCalledWith(true);
  });

  it("ends the lift when the flight finishes", async () => {
    const { env, cancel, done } = fakeEnv();
    const t = createLandingTransition(env);
    t.begin("Q", vi.fn());

    done.resolve();
    await vi.advanceTimersByTimeAsync(0);

    expect(t.phase()).toBe("idle");
    expect(env.setStage).toHaveBeenLastCalledWith(false);
    expect(cancel).toHaveBeenCalledOnce();
  });

  it("ends the lift when the flight rejects", async () => {
    const cancel = vi.fn();
    const flight: Flight = { finished: Promise.reject(new Error("aborted")), cancel };
    const { env } = fakeEnv({ play: vi.fn(() => flight) });
    const t = createLandingTransition(env);
    t.begin("Q", vi.fn());

    await vi.advanceTimersByTimeAsync(0);

    expect(t.phase()).toBe("idle");
    expect(cancel).toHaveBeenCalledOnce();
  });

  it("ends the lift on the grace timeout if the flight never settles", () => {
    const { env, cancel } = fakeEnv();
    const t = createLandingTransition(env);
    t.begin("Q", vi.fn());

    vi.advanceTimersByTime(LIFT_MS + GRACE_MS - 1);
    expect(t.phase()).toBe("lift");
    vi.advanceTimersByTime(1);
    expect(t.phase()).toBe("idle");
    expect(cancel).toHaveBeenCalledOnce();
  });

  it("ignores a second begin while one is running", () => {
    const { env } = fakeEnv();
    const send = vi.fn();
    const t = createLandingTransition(env);

    t.begin("Q", send);
    t.begin("Q", send);
    expect(send).toHaveBeenCalledOnce();
    expect(env.play).toHaveBeenCalledOnce();
  });

  it("degrades to a cut when there is no origin to fly from", () => {
    const { env } = fakeEnv({ measureOrigin: vi.fn(() => null) });
    const send = vi.fn();
    const t = createLandingTransition(env);

    t.begin("Q", send);
    expect(send).toHaveBeenCalledOnce();
    expect(t.phase()).toBe("idle");
    expect(env.measureTarget).not.toHaveBeenCalled();
    expect(env.setStage).not.toHaveBeenCalled();
  });

  it("degrades to a cut when there is no target to land on", () => {
    const { env } = fakeEnv({ measureTarget: vi.fn(() => null) });
    const send = vi.fn();
    const t = createLandingTransition(env);

    t.begin("Q", send);
    expect(send).toHaveBeenCalledOnce();
    expect(t.phase()).toBe("idle");
    expect(env.play).not.toHaveBeenCalled();
    expect(env.setStage).toHaveBeenLastCalledWith(false);
  });

  it("degrades to a cut, sending once, when play throws", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    const { env } = fakeEnv({
      play: vi.fn(() => {
        throw new Error("no animate");
      }),
    });
    const send = vi.fn();
    const t = createLandingTransition(env);

    t.begin("Q", send);
    expect(send).toHaveBeenCalledOnce();
    expect(t.phase()).toBe("idle");
    expect(warn).toHaveBeenCalledWith("landing transition skipped", expect.any(Error));
  });

  it("degrades to a cut, sending once, when measuring the origin throws", () => {
    vi.spyOn(console, "warn").mockImplementation(() => undefined);
    const { env } = fakeEnv({
      measureOrigin: vi.fn(() => {
        throw new Error("detached");
      }),
    });
    const send = vi.fn();
    const t = createLandingTransition(env);

    t.begin("Q", send);
    expect(send).toHaveBeenCalledOnce();
    expect(t.phase()).toBe("idle");
  });

  it("idles and rethrows if sending itself throws mid-lift", () => {
    const { env } = fakeEnv();
    const t = createLandingTransition(env);

    expect(() =>
      t.begin("Q", () => {
        throw new Error("send failed");
      }),
    ).toThrow("send failed");
    expect(t.phase()).toBe("idle");
    expect(env.setStage).toHaveBeenLastCalledWith(false);
  });

  it("cancel mid-flight stops it for good", () => {
    const { env, cancel } = fakeEnv();
    const t = createLandingTransition(env);
    t.begin("Q", vi.fn());

    t.cancel();
    expect(cancel).toHaveBeenCalledOnce();
    expect(t.phase()).toBe("idle");

    vi.advanceTimersByTime(LIFT_MS + GRACE_MS);
    t.cancel();
    expect(cancel).toHaveBeenCalledOnce();
    expect(env.setStage.mock.calls).toEqual([[true], [false]]);
  });

  it("cuts when the viewport or theme changes mid-flight", () => {
    const { env, cancel, interrupt, unwatch } = fakeEnv();
    const t = createLandingTransition(env);
    t.begin("Q", vi.fn());
    expect(env.watchInterrupts).toHaveBeenCalledOnce();

    interrupt.fire();
    expect(t.phase()).toBe("idle");
    expect(cancel).toHaveBeenCalledOnce();
    expect(unwatch).toHaveBeenCalledOnce();
    expect(env.setStage.mock.calls).toEqual([[true], [false]]);
  });

  it("stops watching once the flight lands", async () => {
    const { env, done, unwatch } = fakeEnv();
    createLandingTransition(env).begin("Q", vi.fn());

    done.resolve();
    await vi.advanceTimersByTimeAsync(0);
    expect(unwatch).toHaveBeenCalledOnce();
  });

  it("watches nothing under reduced motion: nothing is aimed", () => {
    const { env } = fakeEnv({ reducedMotion: vi.fn(() => true) });
    createLandingTransition(env).begin("Q", vi.fn());
    expect(env.watchInterrupts).not.toHaveBeenCalled();
  });

  it("cancel mid-fade stops it for good", () => {
    const { env } = fakeEnv({ reducedMotion: vi.fn(() => true) });
    const t = createLandingTransition(env);
    t.begin("Q", vi.fn());

    t.cancel();
    expect(t.phase()).toBe("idle");
    vi.advanceTimersByTime(FADE_MS);
    expect(env.setStage.mock.calls).toEqual([[true], [false]]);
  });
});

describe("composerKeyframes", () => {
  it("composerKeyframes has no chip leg", () => {
    const o = {
      box: { top: 304, left: 300, width: 680, height: 88 },
    } as FlightOrigin;
    const t = {
      composer: { top: 688, left: 280, width: 880, height: 96 },
    } as FlightTarget;
    // Even handed the pill's rects on both ends — what the old chip leg
    // keyed on — there is nothing for it to animate: it rides in the box.
    const pill = { top: 360, left: 316, width: 120, height: 28 };
    const withPill = { ...o, chip: pill } as FlightOrigin;
    const toPill = { ...t, chip: { ...pill, top: 752 } } as FlightTarget;
    expect(Object.keys(composerKeyframes(withPill, toPill))).toEqual(["wrap", "box"]);
  });
});

describe("defaultEnv", () => {
  afterEach(() => {
    document.body.innerHTML = "";
    document.documentElement.style.removeProperty("--lt-d");
    document.documentElement.style.removeProperty("--lt-ease");
    document.documentElement.style.removeProperty("--lt-leave-h");
    document.documentElement.removeAttribute("data-theme");
  });

  function mountLandingAndChat() {
    document.body.innerHTML = `
      <div class="landing-input-wrap"><textarea class="landing-input">What is Geist?</textarea></div>
      <div class="thread"><div class="turn turn-user"><div class="turn-user-inner">
        <div class="turn-body">What is Geist?</div>
      </div></div></div>
      <div class="composer-wrap"><div class="composer"></div></div>`;
  }

  it("measures nothing when the landing composer is gone", () => {
    expect(defaultEnv().measureOrigin()).toBeNull();
  });

  it("measures nothing when the chat has not rendered the turn", () => {
    expect(defaultEnv().measureTarget()).toBeNull();
  });

  it("measures both ends when both are in the DOM", () => {
    mountLandingAndChat();
    const env = defaultEnv();
    expect(env.measureOrigin()?.text).toBe("What is Geist?");
    expect(env.measureTarget()).not.toBeNull();
  });

  it("sets and clears the timing custom properties on the root", () => {
    const env = defaultEnv();
    env.setStage(true);
    const s = document.documentElement.style;
    expect(s.getPropertyValue("--lt-d")).toBe(`${LIFT_MS}ms`);
    expect(s.getPropertyValue("--lt-ease")).toBe("cubic-bezier(.2,.7,.1,1)");
    // No landing to measure: the layer keeps its `inset: 0` height.
    expect(s.getPropertyValue("--lt-leave-h")).toBe("");
    env.setStage(false);
    expect(s.getPropertyValue("--lt-d")).toBe("");
    expect(s.getPropertyValue("--lt-ease")).toBe("");
  });

  it("pins the leaving layer to the landing's height before the swap", () => {
    document.body.innerHTML = `<div class="landing"></div>`;
    const landing = document.querySelector(".landing");
    if (!landing) throw new Error("no landing");
    vi.spyOn(landing, "getBoundingClientRect").mockReturnValue({
      height: 982,
    } as DOMRect);
    const env = defaultEnv();
    const s = document.documentElement.style;

    env.setStage(true);
    expect(s.getPropertyValue("--lt-leave-h")).toBe("982px");
    env.setStage(false);
    expect(s.getPropertyValue("--lt-leave-h")).toBe("");
  });

  it("reports a change of width or theme until unwatched", async () => {
    const hit = vi.fn();
    const unwatch = defaultEnv().watchInterrupts(hit);

    // Height alone (a phone keyboard) is not an interrupt.
    window.dispatchEvent(new Event("resize"));
    expect(hit).not.toHaveBeenCalled();
    vi.stubGlobal("innerWidth", window.innerWidth - 100);
    window.dispatchEvent(new Event("resize"));
    expect(hit).toHaveBeenCalledTimes(1);
    document.documentElement.setAttribute("data-theme", "dark");
    await Promise.resolve();
    expect(hit).toHaveBeenCalledTimes(2);
    // Another attribute on the root is not a theme change.
    document.documentElement.setAttribute("data-lt-return", "x");
    await Promise.resolve();
    document.documentElement.removeAttribute("data-lt-return");
    expect(hit).toHaveBeenCalledTimes(2);

    unwatch();
    window.dispatchEvent(new Event("resize"));
    document.documentElement.setAttribute("data-theme", "light");
    await Promise.resolve();
    expect(hit).toHaveBeenCalledTimes(2);
    vi.unstubAllGlobals();
  });

  it("reports what the platform supports", () => {
    vi.stubGlobal(
      "matchMedia",
      vi.fn(() => ({ matches: true })),
    );
    const env = defaultEnv();
    expect(env.reducedMotion()).toBe(true);
    expect(env.canAnimate()).toBe(typeof Element.prototype.animate === "function");
    vi.unstubAllGlobals();
  });

  it("plays: one ghost carrying the question, gone once cancelled", async () => {
    mountLandingAndChat();
    const cancel = vi.fn();
    const animate = vi.fn(() => ({ finished: Promise.resolve(), cancel }));
    Object.defineProperty(Element.prototype, "animate", { value: animate, configurable: true });
    const env = defaultEnv();
    const origin = env.measureOrigin();
    const target = env.measureTarget();
    if (!origin || !target) throw new Error("fixture did not measure");

    const flight = env.play(origin, target);
    const ghosts = document.querySelectorAll(".lift-ghost");
    expect(ghosts).toHaveLength(1);
    expect(ghosts[0]?.textContent).toBe("What is Geist?");
    expect(ghosts[0]?.getAttribute("aria-hidden")).toBe("true");
    // ghost move + ghost chrome + composer wrap + composer box
    expect(animate).toHaveBeenCalledTimes(4);

    await flight.finished;
    flight.cancel();
    expect(document.querySelectorAll(".lift-ghost")).toHaveLength(0);
    expect(cancel).toHaveBeenCalledTimes(4);
    delete (Element.prototype as { animate?: unknown }).animate;
  });

  it("plays: the scope pill inside the composer gets no animation of its own", () => {
    mountLandingAndChat();
    // Both ends carry the pill inside the box now, so it rides with the
    // box's own animation; a separate leg would offset it twice.
    document
      .querySelector(".landing-input-wrap")
      ?.insertAdjacentHTML("beforeend", `<div class="chat-scope-control"></div>`);
    document
      .querySelector(".composer")
      ?.insertAdjacentHTML("beforeend", `<div class="chat-scope-control"></div>`);
    const animate = vi.fn(() => ({ finished: Promise.resolve(), cancel: vi.fn() }));
    Object.defineProperty(Element.prototype, "animate", { value: animate, configurable: true });
    const env = defaultEnv();
    const origin = env.measureOrigin();
    const target = env.measureTarget();
    if (!origin || !target) throw new Error("fixture did not measure");

    env.play(origin, target).cancel();
    // ghost move + ghost chrome + composer wrap + composer box
    expect(animate).toHaveBeenCalledTimes(4);
    // Both pills by their own selector: a bare `.chat-scope-control` finds
    // the landing's first, and the chat's — the one a chip leg animated —
    // would go unchecked.
    const chatPill = document.querySelector(".composer .chat-scope-control");
    const landingPill = document.querySelector(".landing-input-wrap .chat-scope-control");
    expect(chatPill).not.toBeNull();
    expect(landingPill).not.toBeNull();
    expect(animate.mock.contexts).not.toContain(chatPill);
    expect(animate.mock.contexts).not.toContain(landingPill);
    delete (Element.prototype as { animate?: unknown }).animate;
  });

  it("plays: if an animation throws, the ghost and the ones already started are undone", () => {
    mountLandingAndChat();
    const cancel = vi.fn();
    let calls = 0;
    const animate = vi.fn(() => {
      calls += 1;
      if (calls === 3) throw new Error("bad keyframe");
      return { finished: Promise.resolve(), cancel };
    });
    Object.defineProperty(Element.prototype, "animate", { value: animate, configurable: true });
    const env = defaultEnv();
    const origin = env.measureOrigin();
    const target = env.measureTarget();
    if (!origin || !target) throw new Error("fixture did not measure");

    expect(() => env.play(origin, target)).toThrow("bad keyframe");
    expect(document.querySelectorAll(".lift-ghost")).toHaveLength(0);
    expect(cancel).toHaveBeenCalledTimes(2);
    delete (Element.prototype as { animate?: unknown }).animate;
  });
});
