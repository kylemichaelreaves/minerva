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

/** `opts` accepts an accessor so a test can shrink the list under the
 *  highlight; `extra` carries `filterable` (#363) without a second harness. */
function harness(
  initial: string | undefined,
  opts: SelectOption[] | (() => SelectOption[]) = OPTS,
  extra: { filterable?: boolean } = {},
) {
  const optionsOf = typeof opts === "function" ? opts : () => opts;
  const [value, setValue] = createSignal<string | undefined>(initial);
  const onChange = vi.fn((v: string) => {
    // Reflect controlled state so re-renders pick up the new value.
    setValue(v || undefined);
  });
  const result = render(() => (
    <Select
      options={optionsOf()}
      value={value()}
      onChange={onChange}
      placeholder="Pick one"
      ariaLabel="Test select"
      filterable={extra.filterable}
    />
  ));
  const trigger = () =>
    result.container.querySelector(
      ".minerva-select__trigger",
    )!;
  const listbox = () =>
    result.container.querySelector(".minerva-select__listbox");
  const filter = () =>
    result.container.querySelector<HTMLInputElement>(
      ".minerva-select__filter-input",
    );
  const optionLabels = () =>
    Array.from(
      result.container.querySelectorAll(".minerva-select__option"),
      (el) => el.textContent,
    );
  const type = (v: string) => {
    fireEvent.input(filter()!, { target: { value: v } });
  };
  return {
    ...result,
    onChange,
    value,
    trigger,
    listbox,
    filter,
    optionLabels,
    type,
  };
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
    fireEvent.pointerDown(opts[1]!); // Beta
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
  // ── filterable mode (#363) ──────────────────────────────────────────
  //
  // The concordance work picker holds ~964 options in a 320px scroll list.
  // `filterable` puts a field at the top of the panel and narrows the list as
  // the reader types. Everything above this comment is the `filterable`-off
  // baseline and must keep passing unchanged — it is the only proof the five
  // other call sites are untouched.

  it("renders no filter field by default", () => {
    // Regression guard for the other call sites rather than a red-first test:
    // it passes before the feature exists, and would fail if `filterable`
    // defaulted on.
    const { trigger, filter } = harness(undefined);
    fireEvent.click(trigger());
    expect(filter()).toBeNull();
  });

  it("renders a filter field and focuses it when the panel opens", () => {
    const { trigger, filter } = harness(undefined, OPTS, { filterable: true });
    fireEvent.click(trigger());
    expect(filter()).not.toBeNull();
    expect(document.activeElement).toBe(filter());
  });

  it("moves the combobox role to the field while open, and back on close", () => {
    // `aria-activedescendant` is only announced on the element that has real
    // focus, so leaving `role="combobox"` on the trigger while the field is
    // focused would announce nothing as the highlight moved. Two elements
    // claiming the role at once is also invalid — hence exactly one.
    const { container, trigger, filter } = harness(undefined, OPTS, {
      filterable: true,
    });
    fireEvent.click(trigger());
    expect(container.querySelectorAll('[role="combobox"]').length).toBe(1);
    expect(filter()!.getAttribute("role")).toBe("combobox");
    expect(trigger().getAttribute("role")).toBe("button");

    fireEvent.keyDown(filter()!, { key: "Escape" });
    expect(trigger().getAttribute("role")).toBe("combobox");
  });

  it("puts aria-activedescendant on the field, not the trigger", () => {
    const { container, trigger, filter } = harness(undefined, OPTS, {
      filterable: true,
    });
    fireEvent.click(trigger());
    fireEvent.keyDown(filter()!, { key: "ArrowDown" });
    const active = container.querySelector(".minerva-select__option.is-active");
    expect(filter()!.getAttribute("aria-activedescendant")).toBe(active!.id);
    expect(trigger().getAttribute("aria-activedescendant")).toBeNull();
  });

  it("narrows the option list as the query is typed", () => {
    const { trigger, type, optionLabels } = harness(undefined, OPTS, {
      filterable: true,
    });
    fireEvent.click(trigger());
    expect(optionLabels().length).toBe(3);
    type("gam");
    expect(optionLabels()).toEqual(["Gamma"]);
  });

  it("commits the option the reader clicked, not the one at that row before filtering", () => {
    // The obstacle this feature had to clear: `commit(i)`, `activeIdx`,
    // `optionId(i)` and the scroll effect all indexed `props.options`
    // positionally. Filtered to Gamma alone, DOM row 0 is options[2] — before
    // the re-base, clicking it committed "a".
    const { container, trigger, type, onChange } = harness(undefined, OPTS, {
      filterable: true,
    });
    fireEvent.click(trigger());
    type("gam");
    fireEvent.pointerDown(container.querySelector(".minerva-select__option")!);
    expect(onChange).toHaveBeenCalledWith("c");
  });

  it("Enter commits the highlighted row of the filtered list", () => {
    const { trigger, filter, type, onChange } = harness(undefined, OPTS, {
      filterable: true,
    });
    fireEvent.click(trigger());
    type("bet");
    fireEvent.keyDown(filter()!, { key: "Enter" });
    expect(onChange).toHaveBeenCalledWith("b");
  });

  it("NEVER commits the raw query when nothing matches", () => {
    // PickerShell's rule, ported (`Syntax/components/PickerShell.tsx`): the
    // field filters, it never accepts. An accepted non-existent work title
    // would go into the URL, look valid, and return an empty concordance.
    const { container, trigger, filter, type, onChange } = harness(
      undefined,
      OPTS,
      { filterable: true },
    );
    fireEvent.click(trigger());
    type("zzz");
    fireEvent.keyDown(filter()!, { key: "Enter" });
    expect(onChange).not.toHaveBeenCalled();
    expect(
      container.querySelector(".minerva-select__empty")?.textContent,
    ).toContain("zzz");
  });

  it("says there are no options at all, rather than no match for an empty query", () => {
    // Reachable in the concordance: `addWorkOptions` returns [] once every
    // work is already chosen, and `No match for ""` would be nonsense there.
    const { container, trigger } = harness(undefined, [], {
      filterable: true,
    });
    fireEvent.click(trigger());
    expect(container.querySelector(".minerva-select__empty")?.textContent).toBe(
      "No options",
    );
  });

  it("keeps showing a selected option that the query excludes", () => {
    // `selected` resolves against the full list, not the filtered view — a
    // filtered-out option is still the selected one.
    const { container, trigger, type } = harness("b", OPTS, {
      filterable: true,
    });
    fireEvent.click(trigger());
    type("gam");
    expect(
      container.querySelector(".minerva-select__primary")?.textContent,
    ).toBe("Beta");
  });

  it("opens with the highlight on the current selection", () => {
    const { container, trigger } = harness("b", OPTS, { filterable: true });
    fireEvent.click(trigger());
    expect(
      container.querySelector(".minerva-select__option.is-active")?.textContent,
    ).toContain("Beta");
  });

  it("wraps the arrow keys within the filtered list", () => {
    const { container, trigger, filter, type } = harness(undefined, OPTS, {
      filterable: true,
    });
    fireEvent.click(trigger());
    type("a"); // Alpha + Gamma
    fireEvent.keyDown(filter()!, { key: "ArrowUp" });
    expect(
      container.querySelector(".minerva-select__option.is-active")?.textContent,
    ).toContain("Gamma");
  });

  it("clamps the highlight when the option list shrinks under it", () => {
    // Not only a keystroke: the caller shrinks the list too — picking a work
    // removes it from `addWorkOptions`, and a language switch replaces the
    // list wholesale. An activeIdx past the end makes Enter a silent no-op.
    const [opts, setOpts] = createSignal<SelectOption[]>(OPTS);
    const { trigger, filter, onChange } = harness(undefined, opts, {
      filterable: true,
    });
    fireEvent.click(trigger());
    fireEvent.keyDown(filter()!, { key: "ArrowDown" });
    fireEvent.keyDown(filter()!, { key: "ArrowDown" }); // → Gamma, index 2
    setOpts([{ value: "a", label: "Alpha" }]);
    fireEvent.keyDown(filter()!, { key: "Enter" });
    expect(onChange).toHaveBeenCalledWith("a");
  });

  it("resets the highlight to the first match on each keystroke", () => {
    const { trigger, filter, type, onChange } = harness(undefined, OPTS, {
      filterable: true,
    });
    fireEvent.click(trigger());
    fireEvent.keyDown(filter()!, { key: "ArrowDown" });
    fireEvent.keyDown(filter()!, { key: "ArrowDown" });
    type("alp");
    fireEvent.keyDown(filter()!, { key: "Enter" });
    expect(onChange).toHaveBeenCalledWith("a");
  });

  it("counts matches against the whole list in the footer", () => {
    const { container, trigger, type } = harness(undefined, OPTS, {
      filterable: true,
    });
    fireEvent.click(trigger());
    const foot = () =>
      container.querySelector(".minerva-select__foot")?.textContent;
    expect(foot()).toContain("3 of 3");
    type("gam");
    expect(foot()).toContain("1 of 3");
  });

  it("seeds the field with the first character typed on a closed select", () => {
    // The bug class: the field does not exist yet when this key arrives, so
    // without seeding the character is silently swallowed and the reader's
    // first keystroke does nothing.
    const { trigger, filter, optionLabels } = harness(undefined, OPTS, {
      filterable: true,
    });
    fireEvent.keyDown(trigger(), { key: "g" });
    expect(filter()).not.toBeNull();
    expect(filter()!.value).toBe("g");
    expect(optionLabels()).toEqual(["Gamma"]);
  });

  it("filters rather than prefix-jumping in filterable mode", () => {
    // "m" is the discriminator: it is a substring of Gamma and a prefix of
    // nothing. Type-ahead would find no match and leave all three rendered;
    // filtering narrows to the one that contains it. (A letter like "a" cannot
    // tell the two apart — every label here contains one, Beta included.)
    const { trigger, optionLabels } = harness(undefined, OPTS, {
      filterable: true,
    });
    fireEvent.keyDown(trigger(), { key: "m" });
    expect(optionLabels()).toEqual(["Gamma"]);
  });

  it("opens on Space without seeding a leading space", () => {
    const { trigger, filter } = harness(undefined, OPTS, { filterable: true });
    fireEvent.keyDown(trigger(), { key: " " });
    expect(filter()).not.toBeNull();
    expect(filter()!.value).toBe("");
  });

  it("Escape from the field closes the panel and returns focus to the trigger", () => {
    const { trigger, filter, listbox } = harness(undefined, OPTS, {
      filterable: true,
    });
    fireEvent.click(trigger());
    fireEvent.keyDown(filter()!, { key: "Escape" });
    expect(listbox()).toBeNull();
    expect(document.activeElement).toBe(trigger());
  });

  it("reopens with an empty query, so the full list is back", () => {
    const { trigger, filter, type, optionLabels } = harness(undefined, OPTS, {
      filterable: true,
    });
    fireEvent.click(trigger());
    type("gam");
    fireEvent.keyDown(filter()!, { key: "Escape" });
    fireEvent.click(trigger());
    expect(filter()!.value).toBe("");
    expect(optionLabels().length).toBe(3);
  });

  it("labels the filter field even when the caller gives no ariaLabel", () => {
    // The field is the combobox while open, so an unlabelled one is an
    // unlabelled combobox. `RefsFilterField` wraps Select in a visible
    // <label> and passes no ariaLabel, so this fallback is the reachable path
    // for any caller that does the same and opts into filtering.
    const [value] = createSignal<string | undefined>(undefined);
    const { container } = render(() => (
      <Select
        options={OPTS}
        value={value()}
        onChange={() => undefined}
        filterable
      />
    ));
    fireEvent.click(container.querySelector(".minerva-select__trigger")!);
    expect(
      container
        .querySelector(".minerva-select__filter-input")
        ?.getAttribute("aria-label"),
    ).toBe("Filter options");
  });

  it("Tab from the field closes the panel", () => {
    const { trigger, filter, listbox } = harness(undefined, OPTS, {
      filterable: true,
    });
    fireEvent.click(trigger());
    fireEvent.keyDown(filter()!, { key: "Tab" });
    expect(listbox()).toBeNull();
  });
});
