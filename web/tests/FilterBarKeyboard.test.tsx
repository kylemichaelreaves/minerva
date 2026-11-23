// The Concordance filter bar's Language, Sort and POS controls, from the
// keyboard (#364).
//
// All three were a local `Dropdown` in FilterBar.tsx: a `<span>` trigger with
// no `tabindex`, `<span>` options with no roles, no `aria-expanded`, and the
// only key handled anywhere in the component was Escape — which could fire
// only for a dropdown the reader had already opened with a mouse. So they were
// unreachable, not merely awkward.
//
// The component's own comment gave the reason: it skipped the shared `Select`
// because it needed "no keyboard nav beyond what native focus already gives
// us". That is true of a `<button>`; it is not true of the `<span>` that was
// actually written. Two `Select`s sat in the same bar with a full keyboard
// model, so the bar was split — two controls operable, three not.
//
// These tests assert the behaviour, not the port: any implementation that
// makes them pass is one a keyboard can drive.

import { render, screen } from "@solidjs/testing-library";
import { fireEvent } from "./helpers/settledFireEvent";
import { describe, expect, it, vi } from "vitest";
import { FilterBar } from "~/Concordance/components/FilterBar";

function renderBar(overrides: Record<string, unknown> = {}) {
  const handlers = {
    onSetLang: vi.fn(),
    onSetSort: vi.fn(),
    onSetPos: vi.fn(),
    onSetFreqRange: vi.fn(),
    onSetQ: vi.fn(),
    onPickAuthor: vi.fn(),
    onPickWork: vi.fn(),
  };
  render(() => (
    <FilterBar
      lang="deu"
      sort="freq"
      freqCeil={1000}
      scope="corpus"
      authorOptions={[]}
      workOptions={[]}
      {...handlers}
      {...overrides}
    />
  ));
  return handlers;
}

/** The three controls under test, by their visible group label. */
const CONTROLS = ["Language", "Sort", "POS"] as const;

function triggerFor(label: string): HTMLElement {
  // Each control sits in a `.grp` beside a `.lab` naming it.
  const groups = Array.from(document.querySelectorAll(".fbar .grp"));
  const group = groups.find((g) => g.querySelector(".lab")?.textContent === label);
  if (!group) throw new Error(`no filter-bar group labelled ${label}`);
  const trigger = group.querySelector("button");
  if (!trigger) throw new Error(`${label} has no button trigger — nothing to focus`);
  return trigger;
}

describe("Concordance filter bar — keyboard reachability (#364)", () => {
  it.each(CONTROLS)("%s's trigger is a focusable button", (label) => {
    renderBar();
    const trigger = triggerFor(label);

    trigger.focus();
    expect(document.activeElement).toBe(trigger);
  });

  it.each(CONTROLS)("%s announces its expanded state", (label) => {
    renderBar();
    const trigger = triggerFor(label);

    // The old markup had no `aria-expanded` at all, so assistive tech was
    // never told the popover had opened.
    expect(trigger.getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(trigger);
    expect(trigger.getAttribute("aria-expanded")).toBe("true");
  });

  it.each(CONTROLS)("%s opens from the keyboard alone", (label) => {
    renderBar();
    const trigger = triggerFor(label);
    trigger.focus();

    fireEvent.keyDown(trigger, { key: "ArrowDown" });

    expect(trigger.getAttribute("aria-expanded")).toBe("true");
    expect(document.querySelector('[role="listbox"]')).not.toBeNull();
  });

  it("picks a Sort option with arrows and Enter, never touching the mouse", () => {
    const { onSetSort } = renderBar();
    const trigger = triggerFor("Sort");
    trigger.focus();

    fireEvent.keyDown(trigger, { key: "ArrowDown" }); // open, cursor on Frequency
    fireEvent.keyDown(trigger, { key: "ArrowDown" }); // → A→Z
    fireEvent.keyDown(trigger, { key: "Enter" });

    expect(onSetSort).toHaveBeenCalledWith("alpha");
  });

  it("picks a Language option with arrows and Enter", () => {
    const { onSetLang } = renderBar();
    const trigger = triggerFor("Language");
    trigger.focus();

    fireEvent.keyDown(trigger, { key: "ArrowDown" });
    fireEvent.keyDown(trigger, { key: "ArrowDown" });
    fireEvent.keyDown(trigger, { key: "Enter" });

    expect(onSetLang).toHaveBeenCalledTimes(1);
  });

  it("exposes the options as listbox options, not bare spans", () => {
    renderBar();
    const trigger = triggerFor("POS");
    fireEvent.click(trigger);

    const options = document.querySelectorAll('[role="option"]');
    expect(options.length).toBeGreaterThan(0);
  });

  it("still closes on Escape, which was the one key the old markup handled", () => {
    renderBar();
    const trigger = triggerFor("Sort");
    trigger.focus();
    fireEvent.keyDown(trigger, { key: "ArrowDown" });
    expect(trigger.getAttribute("aria-expanded")).toBe("true");

    fireEvent.keyDown(trigger, { key: "Escape" });
    expect(trigger.getAttribute("aria-expanded")).toBe("false");
  });

  it("keeps the current value visible on the trigger", () => {
    // The old `Dropdown` showed the active label on its span. Whatever the
    // control is, the reader must still be able to see what is selected
    // without opening it.
    renderBar({ sort: "alpha" });
    expect(triggerFor("Sort").textContent).toContain("A→Z");
    expect(screen.getByText("Sort")).toBeTruthy();
  });
});
