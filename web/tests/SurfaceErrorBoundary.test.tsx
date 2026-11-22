import { beforeEach, describe, it, expect, vi } from "vitest";
import { render } from "@solidjs/testing-library";
import { createMemo, createSignal, flush } from "solid-js";
import SurfaceErrorBoundary from "~/routes/SurfaceErrorBoundary";
import { must } from "./helpers/must";
import { expectSurfaceFailures } from "./surfaceFailures";

// #426. The app mounted no `ErrorBoundary` anywhere, so anything that threw
// during a render escaped the tree entirely: no fallback, no message, and
// whatever was on screen frozen where it stood. Solid rethrows on reading an
// errored resource, which made that reachable from any failed fetch.
//
// The per-site guards (#235, #361, #426) stop the three known throws. This is
// the net under everything else — including throws that are not about
// resources at all.

function Boom(): never {
  throw new Error("kaboom");
}

describe("<SurfaceErrorBoundary />", () => {
  // Every test here crashes a surface on purpose.
  beforeEach(expectSurfaceFailures);

  it("renders children when nothing throws", () => {
    const { container } = render(() => (
      <SurfaceErrorBoundary label="Test surface">
        <div class="ok">fine</div>
      </SurfaceErrorBoundary>
    ));
    expect(container.querySelector(".ok")).not.toBeNull();
    expect(container.querySelector(".surface-error")).toBeNull();
  });

  it("catches a throw and renders a fallback instead of propagating", () => {
    // Without a boundary this render call itself throws.
    expect(() =>
      render(() => (
        <SurfaceErrorBoundary label="Test surface">
          <Boom />
        </SurfaceErrorBoundary>
      )),
    ).not.toThrow();
  });

  it("names the surface that failed, so the message is not generic", () => {
    const { container } = render(() => (
      <SurfaceErrorBoundary label="Concordance">
        <Boom />
      </SurfaceErrorBoundary>
    ));
    const box = container.querySelector(".surface-error");
    expect(box).not.toBeNull();
    expect(must(box).textContent).toMatch(/Concordance/);
  });

  it("surfaces the underlying message rather than swallowing it", () => {
    // A boundary that hides the reason is how a frozen surface becomes a
    // silent one — the failure mode #426 was filed about.
    const { container } = render(() => (
      <SurfaceErrorBoundary label="Test surface">
        <Boom />
      </SurfaceErrorBoundary>
    ));
    expect(must(container.querySelector(".surface-error")).textContent).toMatch(/kaboom/);
  });

  it("offers a retry that re-renders the subtree", () => {
    // `reset()` clears the error and re-runs children. The failure here is not
    // reactive (a plain counter, like a transient fetch failure the graph
    // cannot see change), so nothing but the retry can bring the subtree back.
    let attempts = 0;
    const Child = () => {
      attempts += 1;
      if (attempts === 1) throw new Error("transient");
      return <div class="recovered">back</div>;
    };
    const { container } = render(() => (
      <SurfaceErrorBoundary label="Test surface">
        <Child />
      </SurfaceErrorBoundary>
    ));
    expect(container.querySelector(".surface-error")).not.toBeNull();

    must(container.querySelector<HTMLButtonElement>(".surface-error__retry")).click();
    flush();

    expect(container.querySelector(".recovered")).not.toBeNull();
    expect(container.querySelector(".surface-error")).toBeNull();
  });

  it("heals on its own when the reactive value that threw changes", () => {
    // Solid 2 boundaries re-run the failed branch when anything it read
    // changes, with no retry click. The throw is in a memo read from JSX, not
    // at the top of the component: a component body is untracked in Solid 2,
    // so a bare `fail()` there would never see the flip.
    const [fail, setFail] = createSignal(true);
    const Child = () => {
      const ok = createMemo(() => {
        if (fail()) throw new Error("transient");
        return "back";
      });
      return <div class="recovered">{ok()}</div>;
    };
    const { container } = render(() => (
      <SurfaceErrorBoundary label="Test surface">
        <Child />
      </SurfaceErrorBoundary>
    ));
    expect(container.querySelector(".surface-error")).not.toBeNull();

    setFail(false);
    flush();

    expect(container.querySelector(".recovered")).not.toBeNull();
    expect(container.querySelector(".surface-error")).toBeNull();
  });

  it("reports the error so a failure is not silent in the console", () => {
    const warn = vi.spyOn(console, "error").mockImplementation(() => undefined);
    try {
      render(() => (
        <SurfaceErrorBoundary label="Test surface">
          <Boom />
        </SurfaceErrorBoundary>
      ));
      expect(warn).toHaveBeenCalled();
    } finally {
      warn.mockRestore();
    }
  });

  describe("the message it shows for a non-Error throw", () => {
    // JS lets you throw anything, and a boundary whose detail line reads
    // "Unknown error" or "[object Object]" is barely better than one that hides
    // the reason.
    //
    // Solid 2's `<Errored>` passes the thrown value through unchanged (Solid 1's
    // `castError` wrapped it in an `Error` with the value on `.cause`), so these
    // assert that the raw payloads are described rather than stringified.
    const detailFor = (thrown: unknown): string => {
      const Thrower = (): never => {
        throw thrown;
      };
      const { container } = render(() => (
        <SurfaceErrorBoundary label="Test surface">
          <Thrower />
        </SurfaceErrorBoundary>
      ));
      return must(container.querySelector(".surface-error__detail")).textContent;
    };

    it("shows a thrown string as itself", () => {
      expect(detailFor("plain string failure")).toBe("plain string failure");
    });

    it("serializes a thrown object", () => {
      // Server error payloads arrive this shape often enough to matter.
      expect(detailFor({ status: 503, detail: "index rebuilding" })).toMatch(/"status":\s*503/);
    });

    it("falls back to String() when the value cannot be serialized", () => {
      // A circular object makes `JSON.stringify` throw — inside the fallback of
      // an error boundary, which is the worst place to throw again.
      const circular: Record<string, unknown> = { name: "loop" };
      circular.self = circular;
      expect(() => detailFor(circular)).not.toThrow();
      expect(detailFor(circular)).toBe("[object Object]");
      // And the placeholder is not what surfaced.
      expect(detailFor(circular)).not.toBe("Unknown error");
    });

    it("falls back to the placeholder when there is nothing to describe", () => {
      // A thrown `undefined` carries nothing, and there is genuinely nothing
      // better to say.
      expect(() => detailFor(undefined)).not.toThrow();
      expect(detailFor(undefined)).toBe("Unknown error");
    });

    it("keeps a real Error's own message rather than looking at cause", () => {
      const withCause = new Error("the real reason", { cause: { noise: true } });
      expect(detailFor(withCause)).toBe("the real reason");
    });
  });
});
