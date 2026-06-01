// Tests for `<Select>` — the keyboard-friendly combobox + listbox in
// lib/Select.tsx. Covers the click + keyboard interaction surfaces
// the FiltersBar (in /refs) and other call sites depend on.

import { describe, it, expect, vi } from "vitest";
import { render, fireEvent } from "@solidjs/testing-library";
import { createSignal } from "solid-js";
import { Select, type SelectOption } from "~/components/Select";

const OPTS: SelectOption[] = [
  { value: "a", label: "Alpha" },
  { value: "b", label: "Beta" },
  { value: "c", label: "Gamma" },
];

function harness(initial: string | undefined, opts: SelectOption[] = OPTS) {
  const [value, setValue] = createSignal<string | undefined>(initial);
  const onChange = vi.fn((v: string) => {
    // Reflect controlled state so re-renders pick up the new value.
    setValue(v || undefined);
  });
  const result = render(() => (
    <Select
      options={opts}
      value={value()}
      onChange={onChange}
      placeholder="Pick one"
      ariaLabel="Test select"
    />
  ));
  const trigger = () =>
    result.container.querySelector(
      ".minerva-select__trigger",
    )!;
  const listbox = () =>
    result.container.querySelector(".minerva-select__listbox");
  return { ...result, onChange, value, trigger, listbox };
}

describe("<Select />", () => {
  it("renders placeholder when value is undefined", () => {
    const { container } = harness(undefined);
    expect(
      container.querySelector(".minerva-select__placeholder")?.textContent,
    ).toBe("Pick one");
  });

  it("renders selected option label when value is set", () => {
    const { container } = harness("b");
    expect(
      container.querySelector(".minerva-select__primary")?.textContent,
    ).toBe("Beta");
  });

  it("clicking the trigger opens the panel", () => {
    const { trigger, listbox } = harness(undefined);
    expect(listbox()).toBeNull();
    fireEvent.click(trigger());
    expect(listbox()).not.toBeNull();
  });

  it("pointer-down on an option commits and closes", () => {
    const { container, onChange, listbox, trigger } = harness(undefined);
    fireEvent.click(trigger());
    const opts = container.querySelectorAll(".minerva-select__option");
    expect(opts.length).toBe(3);
    fireEvent.pointerDown(opts[1]); // Beta
    expect(onChange).toHaveBeenCalledWith("b");
    // Panel closes after commit.
    expect(listbox()).toBeNull();
  });

  it("arrow-down opens and lands on the first enabled option", () => {
    const { trigger, container } = harness(undefined);
    fireEvent.keyDown(trigger(), { key: "ArrowDown" });
    expect(container.querySelector(".minerva-select__listbox")).not.toBeNull();
    // Active option is the first one (no prior selection to anchor on).
    const active = container.querySelector(".minerva-select__option.is-active");
    expect(active?.textContent).toContain("Alpha");
  });

  it("Enter on an active option commits it", () => {
    const { trigger, onChange } = harness(undefined);
    // Open + advance to Beta (one ArrowDown opens to Alpha, second
    // advances to Beta).
    fireEvent.keyDown(trigger(), { key: "ArrowDown" });
    fireEvent.keyDown(trigger(), { key: "ArrowDown" });
    fireEvent.keyDown(trigger(), { key: "Enter" });
    expect(onChange).toHaveBeenCalledWith("b");
  });

  it("Escape closes without committing", () => {
    const { trigger, onChange, container } = harness(undefined);
    fireEvent.click(trigger());
    fireEvent.keyDown(trigger(), { key: "Escape" });
    expect(onChange).not.toHaveBeenCalled();
    expect(container.querySelector(".minerva-select__listbox")).toBeNull();
  });

  it("type-ahead jumps to the first option whose label starts with the buffer", () => {
    const { trigger, container } = harness(undefined);
    fireEvent.keyDown(trigger(), { key: "g" });
    const active = container.querySelector(".minerva-select__option.is-active");
    expect(active?.textContent).toContain("Gamma");
  });

  it("clear button appears when value is set and resets it", () => {
    const { container, onChange } = harness("b");
    const clear = container.querySelector(".minerva-select__clear");
    expect(clear).not.toBeNull();
    fireEvent.click(clear!);
    expect(onChange).toHaveBeenCalledWith("");
  });

  it("clearable={false} hides the clear button", () => {
    const [value] = createSignal<string | undefined>("b");
    const { container } = render(() => (
      <Select
        options={OPTS}
        value={value()}
        onChange={() => undefined}
        clearable={false}
      />
    ));
    expect(container.querySelector(".minerva-select__clear")).toBeNull();
  });

  it("disabled trigger doesn't open on click", () => {
    const [value] = createSignal<string | undefined>(undefined);
    const { container } = render(() => (
      <Select
        options={OPTS}
        value={value()}
        onChange={() => undefined}
        disabled
      />
    ));
    const trigger = container.querySelector(
      ".minerva-select__trigger",
    )!;
    fireEvent.click(trigger);
    expect(container.querySelector(".minerva-select__listbox")).toBeNull();
  });

  it("disabled options are skipped by arrow navigation", () => {
    const opts: SelectOption[] = [
      { value: "a", label: "Alpha" },
      { value: "b", label: "Beta", disabled: true },
      { value: "c", label: "Gamma" },
    ];
    const { trigger, container } = harness(undefined, opts);
    // Open and step twice — Beta is disabled, so we skip from Alpha
    // to Gamma on the second ArrowDown.
    fireEvent.keyDown(trigger(), { key: "ArrowDown" }); // open → Alpha
    fireEvent.keyDown(trigger(), { key: "ArrowDown" }); // → Gamma
    const active = container.querySelector(".minerva-select__option.is-active");
    expect(active?.textContent).toContain("Gamma");
  });
});
