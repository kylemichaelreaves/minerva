// #690: switching the target language while the rail shows a finished
// translation must not cache the old language's text under the new one.
// Driven through both real hooks so the ordering inside setTargetLang
// (flip target, then re-run) is the one under test.

import { describe, it, expect, vi, beforeEach } from "vitest";
import { createRoot } from "solid-js";

const translate = vi.fn();
vi.mock("~/api/readerApi", () => ({
  translate: (...args: unknown[]) => translate(...args) as never,
}));

import { useTranslateRail } from "~/Reader/useTranslateRail";
import { useWordHoverTranslations } from "~/Reader/useWordHoverTranslations";

function response(text: string) {
  return { translated_text: text, literal_text: text, model: "m", cached: false };
}

function setup() {
  let dispose: () => void = () => undefined;
  const { railApi, hover } = createRoot((d) => {
    dispose = d;
    const railApi = useTranslateRail();
    const hover = useWordHoverTranslations({
      rail: railApi.rail,
      target: railApi.target,
    });
    return { railApi, hover };
  });
  return { railApi, hover, dispose };
}

const settle = () => new Promise((r) => setTimeout(r, 0));

describe("translate rail → hover cache language (#690)", () => {
  beforeEach(() => translate.mockReset());

  it("records the language a ready response was produced for", async () => {
    translate.mockResolvedValueOnce(response("and the man"));
    const { railApi, dispose } = setup();
    railApi.runTranslate("virumque", "c1");
    await settle();
    const r = railApi.rail();
    expect(r.kind).toBe("ready");
    expect(r.kind === "ready" && r.lang).toBe("eng");
    dispose();
  });

  it("does not cache the old language's text under the new one when the re-translation fails", async () => {
    translate
      .mockResolvedValueOnce(response("and the man"))
      .mockRejectedValueOnce(new Error("boom"));
    const { railApi, hover, dispose } = setup();

    hover.registerWordClick("c1", 4, "virumque");
    railApi.runTranslate("virumque", "c1");
    await settle();
    expect(hover.lookup("c1", 4)).toBe("and the man");

    railApi.setTargetLang("deu");
    await settle();
    expect(railApi.rail().kind).toBe("error");
    expect(hover.lookup("c1", 4)).toBeUndefined();

    // The English entry is still there, under English.
    railApi.setTargetLang("eng", { promote: false });
    expect(hover.lookup("c1", 4)).toBe("and the man");
    dispose();
  });
});
