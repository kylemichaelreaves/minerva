import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { FADE_MS, GRACE_MS, LIFT_MS, type Flight } from "~/features/LandingTransition/controller";
import {
  createReturnTransition,
  defaultReturnEnv,
  returnKeyframes,
  type ReturnEnv,
  type ReturnGeometry,
} from "~/features/LandingTransition/returnController";

const GEOMETRY: ReturnGeometry = {
  composer: { top: 760, left: 300, width: 840, height: 90 },
  box: { top: 320, left: 380, width: 680, height: 82 },
};

function deferred() {
  let resolve!: () => void;
  const promise = new Promise<void>((r) => {
    resolve = r;
  });
  return { promise, resolve };
}

function fakeEnv(over: Partial<ReturnEnv> = {}) {
  const done = deferred();
  const cancel = vi.fn();
  const flight: Flight = { finished: done.promise, cancel };
  const env = {
    reducedMotion: vi.fn<ReturnEnv["reducedMotion"]>(over.reducedMotion ?? (() => false)),
    canAnimate: vi.fn<ReturnEnv["canAnimate"]>(over.canAnimate ?? (() => true)),
    setStage: vi.fn<ReturnEnv["setStage"]>(),
    measure: vi.fn<ReturnEnv["measure"]>(over.measure ?? (() => GEOMETRY)),
    play: vi.fn<ReturnEnv["play"]>(over.play ?? (() => flight)),
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

describe("returnKeyframes", () => {
  it("moves the composer's centre and top onto the box's, and its width", () => {
    const k = returnKeyframes(GEOMETRY);
    // Centres: 300 + 420 = 720 → 380 + 340 = 720; tops 760 → 320.
    expect(k.wrap).toEqual([
      { transform: "translate(0px, 0px)" },
      { transform: "translate(0px, -440px)" },
    ]);
    expect(k.box).toEqual([{ maxWidth: "840px" }, { maxWidth: "680px" }]);
  });
});

describe("createReturnTransition", () => {
  it("returns: stages the layer before measuring, then flies", () => {
    const { env } = fakeEnv();
    const go = vi.fn();
    const t = createReturnTransition(env);

    t.begin(go);
    expect(t.phase()).toBe("return");
    expect(env.setStage).toHaveBeenCalledWith("return");
    const order = (fn: { mock: { invocationCallOrder: number[] } }) =>
      fn.mock.invocationCallOrder[0] ?? Number.NaN;
    expect(order(env.setStage)).toBeLessThan(order(env.measure));
    expect(env.play).toHaveBeenCalledWith(GEOMETRY);
    // The chat stays until the flight has settled.
    expect(go).not.toHaveBeenCalled();
  });

  it("navigates once the flight finishes, then idles", async () => {
    const { env, cancel, done } = fakeEnv();
    const go = vi.fn();
    const t = createReturnTransition(env);
    t.begin(go);

    done.resolve();
    await vi.advanceTimersByTimeAsync(0);

    expect(go).toHaveBeenCalledOnce();
    expect(t.phase()).toBe("idle");
    expect(env.setStage).toHaveBeenLastCalledWith("idle");
    expect(cancel).toHaveBeenCalledOnce();
    // Navigating first, while the layer is still up: no frame with neither.
    expect(go.mock.invocationCallOrder[0]).toBeLessThan(
      env.setStage.mock.invocationCallOrder.at(-1) ?? Number.NaN,
    );
  });

  it("navigates when the flight rejects", async () => {
    const flight: Flight = { finished: Promise.reject(new Error("aborted")), cancel: vi.fn() };
    const { env } = fakeEnv({ play: vi.fn(() => flight) });
    const go = vi.fn();
    const t = createReturnTransition(env);
    t.begin(go);

    await vi.advanceTimersByTimeAsync(0);
    expect(go).toHaveBeenCalledOnce();
    expect(t.phase()).toBe("idle");
  });

  it("navigates on the grace timeout if the flight never settles", () => {
    const { env } = fakeEnv();
    const go = vi.fn();
    const t = createReturnTransition(env);
    t.begin(go);

    vi.advanceTimersByTime(LIFT_MS + GRACE_MS - 1);
    expect(go).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(go).toHaveBeenCalledOnce();
    expect(t.phase()).toBe("idle");
  });

  it("fades under reduced motion and navigates after FADE_MS", () => {
    const { env } = fakeEnv({ reducedMotion: vi.fn(() => true) });
    const go = vi.fn();
    const t = createReturnTransition(env);

    t.begin(go);
    expect(t.phase()).toBe("fade");
    expect(env.setStage).toHaveBeenCalledWith("fade");
    expect(env.play).not.toHaveBeenCalled();

    vi.advanceTimersByTime(FADE_MS);
    expect(go).toHaveBeenCalledOnce();
    expect(t.phase()).toBe("idle");
  });

  it("cuts when the browser cannot animate", () => {
    const { env } = fakeEnv({ canAnimate: vi.fn(() => false) });
    const go = vi.fn();
    const t = createReturnTransition(env);

    t.begin(go);
    expect(go).toHaveBeenCalledOnce();
    expect(t.phase()).toBe("idle");
    expect(env.setStage).not.toHaveBeenCalled();
  });

  it.each([
    ["nothing to measure", { measure: vi.fn(() => null) }],
    [
      "measure throws",
      {
        measure: vi.fn(() => {
          throw new Error("no layout");
        }),
      },
    ],
    [
      "play throws",
      {
        play: vi.fn((): Flight => {
          throw new Error("no animate");
        }),
      },
    ],
  ])("cuts when %s", (_, over) => {
    vi.spyOn(console, "warn").mockImplementation(() => undefined);
    const { env } = fakeEnv(over);
    const go = vi.fn();
    const t = createReturnTransition(env);

    t.begin(go);
    expect(go).toHaveBeenCalledOnce();
    expect(t.phase()).toBe("idle");
    expect(env.setStage).toHaveBeenLastCalledWith("idle");
  });

  it("idles even if navigating throws", () => {
    const { env } = fakeEnv({ canAnimate: vi.fn(() => true), measure: vi.fn(() => null) });
    vi.spyOn(console, "warn").mockImplementation(() => undefined);
    const t = createReturnTransition(env);
    expect(() =>
      t.begin(() => {
        throw new Error("router");
      }),
    ).toThrow("router");
    expect(t.phase()).toBe("idle");
  });

  it("cancel stops the flight without navigating", async () => {
    const { env, cancel, done } = fakeEnv();
    const go = vi.fn();
    const t = createReturnTransition(env);
    t.begin(go);

    t.cancel();
    expect(t.phase()).toBe("idle");
    expect(cancel).toHaveBeenCalledOnce();
    done.resolve();
    await vi.advanceTimersByTimeAsync(LIFT_MS + GRACE_MS);
    expect(go).not.toHaveBeenCalled();
  });

  it("cancel while idle does nothing", () => {
    const { env } = fakeEnv();
    createReturnTransition(env).cancel();
    expect(env.setStage).not.toHaveBeenCalled();
  });

  it("ignores a second begin while one is running", () => {
    const { env } = fakeEnv();
    const t = createReturnTransition(env);
    t.begin(vi.fn());
    t.begin(vi.fn());
    expect(env.play).toHaveBeenCalledOnce();
  });
});

describe("defaultReturnEnv", () => {
  const root = document.documentElement;
  afterEach(() => {
    document.body.innerHTML = "";
    delete root.dataset.ltReturn;
    root.removeAttribute("style");
    delete (Element.prototype as { animate?: unknown }).animate;
    vi.unstubAllGlobals();
  });

  function mountChatAndLanding() {
    document.body.innerHTML = `
      <main class="main">
        <div class="composer-wrap"><div class="composer"></div></div>
        <div class="landing"><div class="landing-input-wrap"></div></div>
      </main>`;
  }

  it("measures nothing until both ends are in the DOM", () => {
    expect(defaultReturnEnv().measure()).toBeNull();
    mountChatAndLanding();
    expect(defaultReturnEnv().measure()).toEqual({
      composer: { top: 0, left: 0, width: 0, height: 0 },
      box: { top: 0, left: 0, width: 0, height: 0 },
    });
  });

  it("stages the root and the composer while it runs, and clears both", () => {
    mountChatAndLanding();
    vi.stubGlobal("scrollY", 1200);
    const env = defaultReturnEnv();
    const wrap = document.querySelector(".composer-wrap");

    env.setStage("return");
    expect(root.dataset.ltReturn).toBe("return");
    expect(root.style.getPropertyValue("--lt-d")).toBe(`${LIFT_MS}ms`);
    // Where `.main` starts at scroll 0: its (here zero) top plus the scroll.
    expect(root.style.getPropertyValue("--lt-top")).toBe("1200px");
    expect(wrap).toHaveAttribute("inert");

    env.setStage("idle");
    expect(root.dataset.ltReturn).toBeUndefined();
    for (const v of ["--lt-d", "--lt-ease", "--lt-top", "--lt-left", "--lt-width"]) {
      expect(root.style.getPropertyValue(v)).toBe("");
    }
    expect(wrap).not.toHaveAttribute("inert");
  });

  it("stages without a .main, falling back to the viewport", () => {
    defaultReturnEnv().setStage("fade");
    expect(root.dataset.ltReturn).toBe("fade");
    expect(root.style.getPropertyValue("--lt-left")).toBe("0px");
    expect(root.style.getPropertyValue("--lt-width")).toBe(`${window.innerWidth}px`);
  });

  it("reports what the platform supports", () => {
    vi.stubGlobal(
      "matchMedia",
      vi.fn(() => ({ matches: true })),
    );
    const env = defaultReturnEnv();
    expect(env.reducedMotion()).toBe(true);
    expect(env.canAnimate()).toBe(false);
  });

  it("plays the composer wrap and box, and cancel undoes both", async () => {
    mountChatAndLanding();
    const cancel = vi.fn();
    const animate = vi.fn(() => ({ finished: Promise.resolve(), cancel }));
    Object.defineProperty(Element.prototype, "animate", { value: animate, configurable: true });

    const flight = defaultReturnEnv().play(GEOMETRY);
    expect(animate).toHaveBeenCalledTimes(2);
    await flight.finished;
    flight.cancel();
    expect(cancel).toHaveBeenCalledTimes(2);
  });

  it("plays nothing it cannot find", async () => {
    const animate = vi.fn();
    Object.defineProperty(Element.prototype, "animate", { value: animate, configurable: true });
    await defaultReturnEnv().play(GEOMETRY).finished;
    expect(animate).not.toHaveBeenCalled();
  });

  it("undoes a half-started flight if an animation throws", () => {
    mountChatAndLanding();
    const cancel = vi.fn();
    const animate = vi
      .fn()
      .mockReturnValueOnce({ finished: Promise.resolve(), cancel })
      .mockImplementationOnce(() => {
        throw new Error("no keyframes");
      });
    Object.defineProperty(Element.prototype, "animate", { value: animate, configurable: true });

    expect(() => defaultReturnEnv().play(GEOMETRY)).toThrow("no keyframes");
    expect(cancel).toHaveBeenCalledOnce();
  });
});
