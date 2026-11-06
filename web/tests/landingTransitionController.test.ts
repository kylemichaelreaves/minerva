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
  const env = {
    reducedMotion: vi.fn<TransitionEnv["reducedMotion"]>(over.reducedMotion ?? (() => false)),
    canAnimate: vi.fn<TransitionEnv["canAnimate"]>(over.canAnimate ?? (() => true)),
    measureOrigin: vi.fn<TransitionEnv["measureOrigin"]>(over.measureOrigin ?? (() => ORIGIN)),
    measureTarget: vi.fn<TransitionEnv["measureTarget"]>(over.measureTarget ?? (() => TARGET)),
    play: vi.fn<TransitionEnv["play"]>(over.play ?? (() => flight)),
    setTiming: vi.fn<TransitionEnv["setTiming"]>(),
  };
  return { env, cancel, done };
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
    expect(env.setTiming.mock.calls).toEqual([[true], [false]]);
  });

  it("cuts when the browser cannot animate", () => {
    const { env } = fakeEnv({ canAnimate: vi.fn(() => false) });
    const send = vi.fn();
    const t = createLandingTransition(env);

    t.begin("Q", send);
    expect(send).toHaveBeenCalledOnce();
    expect(t.phase()).toBe("idle");
    expect(env.play).not.toHaveBeenCalled();
    expect(env.setTiming).not.toHaveBeenCalled();
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
    expect(env.setTiming).toHaveBeenCalledWith(true);
  });

  it("ends the lift when the flight finishes", async () => {
    const { env, cancel, done } = fakeEnv();
    const t = createLandingTransition(env);
    t.begin("Q", vi.fn());

    done.resolve();
    await vi.advanceTimersByTimeAsync(0);

    expect(t.phase()).toBe("idle");
    expect(env.setTiming).toHaveBeenLastCalledWith(false);
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
    expect(env.setTiming).not.toHaveBeenCalled();
  });

  it("degrades to a cut when there is no target to land on", () => {
    const { env } = fakeEnv({ measureTarget: vi.fn(() => null) });
    const send = vi.fn();
    const t = createLandingTransition(env);

    t.begin("Q", send);
    expect(send).toHaveBeenCalledOnce();
    expect(t.phase()).toBe("idle");
    expect(env.play).not.toHaveBeenCalled();
    expect(env.setTiming).toHaveBeenLastCalledWith(false);
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
    expect(env.setTiming).toHaveBeenLastCalledWith(false);
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
    expect(env.setTiming.mock.calls).toEqual([[true], [false]]);
  });

  it("cancel mid-fade stops it for good", () => {
    const { env } = fakeEnv({ reducedMotion: vi.fn(() => true) });
    const t = createLandingTransition(env);
    t.begin("Q", vi.fn());

    t.cancel();
    expect(t.phase()).toBe("idle");
    vi.advanceTimersByTime(FADE_MS);
    expect(env.setTiming.mock.calls).toEqual([[true], [false]]);
  });
});

describe("defaultEnv", () => {
  afterEach(() => {
    document.body.innerHTML = "";
    document.documentElement.style.removeProperty("--lt-d");
    document.documentElement.style.removeProperty("--lt-ease");
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
    env.setTiming(true);
    const s = document.documentElement.style;
    expect(s.getPropertyValue("--lt-d")).toBe(`${LIFT_MS}ms`);
    expect(s.getPropertyValue("--lt-ease")).toBe("cubic-bezier(.2,.7,.1,1)");
    env.setTiming(false);
    expect(s.getPropertyValue("--lt-d")).toBe("");
    expect(s.getPropertyValue("--lt-ease")).toBe("");
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
});
