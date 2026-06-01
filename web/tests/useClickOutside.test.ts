import { afterEach, describe, expect, it, vi } from "vitest";
import { createRoot, createSignal } from "solid-js";
import { useClickOutside } from "~/hooks/useClickOutside";

const flush = (): Promise<void> => Promise.resolve();

describe("useClickOutside", () => {
  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("calls onOutside when clicking outside the root while active", async () => {
    await createRoot(async (dispose) => {
      const onOutside = vi.fn();
      const root = document.createElement("div");
      const inner = document.createElement("span");
      root.appendChild(inner);
      document.body.appendChild(root);

      const [active, setActive] = createSignal(true);
      useClickOutside(() => root, active, onOutside, { event: "mousedown" });
      await flush();

      inner.dispatchEvent(new MouseEvent("mousedown", { bubbles: true }));
      expect(onOutside).not.toHaveBeenCalled();

      document.body.dispatchEvent(new MouseEvent("mousedown", { bubbles: true }));
      expect(onOutside).toHaveBeenCalledTimes(1);

      setActive(false);
      onOutside.mockClear();
      await flush();
      document.body.dispatchEvent(new MouseEvent("mousedown", { bubbles: true }));
      expect(onOutside).not.toHaveBeenCalled();

      dispose();
    });
  });

  it("respects ignore callback", async () => {
    await createRoot(async (dispose) => {
      const onOutside = vi.fn();
      const root = document.createElement("div");
      const ignored = document.createElement("button");
      ignored.className = "ignore-me";
      document.body.append(root, ignored);

      useClickOutside(() => root, () => true, onOutside, {
        event: "mousedown",
        ignore: (t) => (t as Element).closest(".ignore-me") != null,
      });
      await flush();

      ignored.dispatchEvent(new MouseEvent("mousedown", { bubbles: true }));
      expect(onOutside).not.toHaveBeenCalled();

      document.body.dispatchEvent(new MouseEvent("mousedown", { bubbles: true }));
      expect(onOutside).toHaveBeenCalledTimes(1);

      dispose();
    });
  });
});
