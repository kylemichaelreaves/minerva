/**
 * The Reader's EN/FR/DE control (#257).
 *
 * It sets the *translation target*. In the `chrome` variant it sits directly
 * after the crumb naming the source language — `454 chunks · lat` — styled as a
 * segmented control with one member active, which is the idiom for "current
 * choice among alternatives". Read there it looks like an edition switcher, and
 * pressing it changes no language: it opens the translate rail, whose desktop
 * layout is dominated by this work's concordance.
 *
 * The `rail` variant never had the problem — it is labelled `Target`. So what
 * is under test is that the chrome variant says what it does too.
 */
import { render, screen, cleanup, fireEvent } from "@solidjs/testing-library";
import { afterEach, describe, expect, it, vi } from "vitest";
import { TargetLangToggle, disabledLangFor } from "~/Reader/components/TargetLangToggle";

afterEach(cleanup);

function mountChrome(overrides: { disabledLang?: "eng" | "fra" | "deu" } = {}) {
  const onTarget = vi.fn();
  const { container } = render(() => (
    <TargetLangToggle
      variant="chrome"
      target="eng"
      onTarget={onTarget}
      disabledLang={overrides.disabledLang}
    />
  ));
  return { onTarget, container };
}

describe("TargetLangToggle, chrome variant", () => {
  it("says in visible text that it is about translating", () => {
    // The defect: nothing on screen distinguished this from an edition
    // switcher. `aria-label="Translation language"` is not visible, and the
    // control sits beside `· lat`.
    const { container } = mountChrome();
    expect(container.textContent).toMatch(/translate/i);
  });

  it("still offers the three targets, with the current one marked", () => {
    const { container } = mountChrome();
    const chips = [...container.querySelectorAll(".lang button")];
    expect(chips.map((b) => b.textContent)).toEqual(["EN", "FR", "DE"]);
    expect(chips.filter((b) => b.className.includes("on")).map((b) => b.textContent)).toEqual([
      "EN",
    ]);
  });

  it("names the language and the action in each chip's tooltip", () => {
    // A hover explanation costs nothing and removes the last of the ambiguity
    // for anyone who reads the segmented control before the label.
    const { container } = mountChrome();
    const de = [...container.querySelectorAll(".lang button")].find(
      (b) => b.textContent === "DE",
    );
    expect(de?.getAttribute("title")).toMatch(/translate/i);
    expect(de?.getAttribute("title")).toMatch(/german/i);
  });

  it("commits a target on click", () => {
    const { onTarget, container } = mountChrome();
    const fr = [...container.querySelectorAll(".lang button")].find(
      (b) => b.textContent === "FR",
    );
    fireEvent.click(fr!);
    expect(onTarget).toHaveBeenCalledWith("fra");
  });

  it("greys out the target matching the source language, and explains why", () => {
    const { onTarget, container } = mountChrome({ disabledLang: "deu" });
    const de = [...container.querySelectorAll(".lang button")].find(
      (b) => b.textContent === "DE",
    ) as HTMLButtonElement;

    expect(de.disabled).toBe(true);
    expect(de.getAttribute("title")).toMatch(/already in this language/i);
    fireEvent.click(de);
    expect(onTarget).not.toHaveBeenCalled();
  });
});

describe("TargetLangToggle, rail variant", () => {
  it("keeps its existing Target label", () => {
    render(() => (
      <TargetLangToggle variant="rail" target="deu" onTarget={vi.fn()} />
    ));
    expect(screen.getByText("Target")).toBeTruthy();
  });
});

describe("disabledLangFor", () => {
  it("disables the target that matches an English, French or German source", () => {
    expect(disabledLangFor("eng")).toBe("eng");
    expect(disabledLangFor("fra")).toBe("fra");
    expect(disabledLangFor("deu")).toBe("deu");
  });

  it("leaves the toggle fully enabled for the philological languages", () => {
    // Greek, Latin, Hebrew, Arabic are never targets, so nothing is greyed —
    // the typical case, and the one in the issue (Aquinas, lat).
    for (const src of ["grc", "lat", "heb", "ara", undefined]) {
      expect(disabledLangFor(src)).toBeUndefined();
    }
  });
});
