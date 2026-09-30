// The target-language chips inside the translation rail.
//
// They render only once there is a source selection and the caller has wired
// `onTarget`; the chip matching the source language is disabled, since
// translating German into German is a no-op.

import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@solidjs/testing-library";
import { RailContent } from "~/Reader/components/Rail";
import type { RailState } from "~/Reader/types";

const RAIL_READY: RailState = {
  kind: "ready",
  lang: "eng",
  source: "Der Geist",
  ref: "¶1",
  response: {
    translated_text: "The spirit",
    literal_text: null,
    model: "stub",
    cached: false,
  } as never,
};

function renderRail(props: Partial<Parameters<typeof RailContent>[0]> = {}) {
  return render(() => (
    <RailContent
      state={RAIL_READY}
      wordInfo={{ kind: "idle" }}
      target="eng"
      onRetry={() => undefined}
      onDismiss={() => undefined}
      onLoadMoreSamples={() => undefined}
      {...props}
    />
  ));
}

describe("<RailContent /> target-language chips", () => {
  it("calls onTarget with the picked language and disables the source language", () => {
    const onTarget = vi.fn();
    renderRail({ onTarget, sourceLang: "deu" });

    const fr = screen.getByRole("button", { name: "FR" });
    const de = screen.getByRole("button", { name: "DE" });
    expect(screen.getByRole("button", { name: "EN" }).className).toBe("on");
    expect(de).toBeDisabled();

    fireEvent.click(fr);
    expect(onTarget).toHaveBeenCalledWith("fra");
    fireEvent.click(de);
    expect(onTarget).toHaveBeenCalledTimes(1);
  });

  it("renders no chips when the caller did not wire onTarget", () => {
    renderRail({ sourceLang: "deu" });
    expect(screen.queryByRole("button", { name: "FR" })).toBeNull();
  });
});
