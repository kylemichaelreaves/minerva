// RailContent tab behavior — specifically the auto-flip to the Lemma
// tab when a word lookup arrives (design 3c → 3d: long-press a word →
// the bottom sheet opens on the lemma).

import { describe, expect, it } from "vitest";
import { createSignal, flush } from "solid-js";
import { render } from "@solidjs/testing-library";
import { RailContent } from "~/Reader/components/Rail";
import type { WordLookup } from "~/api/types/reader";
import type { RailState, WordInfoState } from "~/Reader/types";
import { must } from "./helpers/must";

const RAIL_READY: RailState = {
  kind: "ready",
  lang: "eng",
  source: "Der Geist",
  ref: "¶1",
  response: {
    translated_text: "The spirit",
    literal_text: "The spirit",
    model: "stub",
    cached: false,
  },
};

const GEIST: WordLookup = {
  surface: "Geist",
  lemma: "Geist",
  lang: "deu",
  edition_id: 1,
  work_id: 1,
  work_title: "Phänomenologie des Geistes",
  occurrence_count: 0,
  samples_offset: 0,
  next_samples_offset: null,
  pos: "NOUN",
  gender: null,
  number: null,
  feats: null,
  samples: [],
};

function setup(initialWordInfo: WordInfoState = { kind: "idle" }) {
  const [wordInfo, setWordInfo] = createSignal<WordInfoState>(initialWordInfo);
  const utils = render(() => (
    <RailContent
      state={RAIL_READY}
      wordInfo={wordInfo()}
      target="eng"
      onRetry={() => undefined}
      onDismiss={() => undefined}
      onLoadMoreSamples={() => undefined}
    />
  ));
  const activeTab = () =>
    utils.container.querySelector('[role="tab"][aria-selected="true"]')?.textContent ?? "";
  const clickTab = (label: string) => {
    const tabs = Array.from(utils.container.querySelectorAll<HTMLButtonElement>('[role="tab"]'));
    must(tabs.find((t) => t.textContent.includes(label))).click();
  };
  return { ...utils, setWordInfo, activeTab, clickTab };
}

describe("<RailContent /> tabs", () => {
  it("defaults to the Translation tab", () => {
    const { activeTab } = setup();
    expect(activeTab()).toContain("Translation");
  });

  it("auto-flips to the Lemma tab when a word lookup starts", () => {
    const { activeTab, setWordInfo } = setup();
    setWordInfo({ kind: "loading" });
    flush();
    expect(activeTab()).toContain("Lemma");
  });

  it("honors a later manual pick, then flips again on the NEXT lookup", () => {
    const { activeTab, setWordInfo, clickTab } = setup();
    setWordInfo({ kind: "loading" });
    flush();
    expect(activeTab()).toContain("Lemma");
    // User flips back to Translation while the lookup is live.
    clickTab("Translation");
    flush();
    expect(activeTab()).toContain("Translation");
    // loading → ready is the SAME lookup — no auto-flip.
    setWordInfo({ kind: "ready", info: GEIST, loadingMore: false });
    flush();
    expect(activeTab()).toContain("Translation");
    // A fresh lookup (idle → loading) flips again. Two separate updates, as
    // in the app: writes in one frame batch, and the effect would see only
    // ready → loading.
    setWordInfo({ kind: "idle" });
    flush();
    setWordInfo({ kind: "loading" });
    flush();
    expect(activeTab()).toContain("Lemma");
  });
});
