// Tests for `<Select>` — the keyboard-friendly combobox + listbox in
// lib/Select.tsx. Covers the click + keyboard interaction surfaces
// the FiltersBar (in /refs) and other call sites depend on.

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
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
  // `filterable` makes the trigger itself a text input that narrows the list as
  // the reader types — the ARIA combobox pattern, one element rather than a
  // button plus a second field inside the panel.
  //
  // The exception is mobile: `styles/mobile.css` turns the panel into a
  // full-screen sheet at `z-index: 80` while the sheet holding the trigger is
  // at 71, so an editable trigger would be typed into blind. There the trigger
  // stays a button and the field renders at the top of the panel. `setup.ts`
  // stubs `matchMedia` to `matches: false`, so everything below is the desktop
  // shape unless it overrides it.
  //
  // Everything ABOVE this comment is the `filterable`-off baseline and must keep
  // passing unchanged — it is the only proof the five other call sites are
  // untouched.

  it("renders a button trigger, not an input, when filterable is off", () => {
    const { trigger, filter } = harness(undefined);
    expect(trigger().tagName).toBe("BUTTON");
    expect(filter()).toBeNull();
  });

  it("wraps the field trigger in a label, and only when filterable", () => {
    // The <label> is what makes clicking the trigger's padding focus the input,
    // natively — it replaced an `onClick` on a bare <div>, which Sonar flagged
    // as a non-native interactive element (S6848 + S1082) and which was doing
    // by hand what a label does for free.
    //
    // The "only when filterable" half is a guard, not decoration:
    // `RefsFilterField` already wraps Select in a bare <label class="refs-filter">,
    // and nested labels are invalid HTML. Setting `filterable` there must fail
    // here rather than ship the nesting.
    const plain = harness(undefined);
    expect(plain.trigger().tagName).toBe("BUTTON");
    expect(plain.container.querySelector("label")).toBeNull();

    const field = harness(undefined, OPTS, { filterable: true });
    expect(field.trigger().tagName).toBe("LABEL");
  });

  it("makes the trigger itself a text input when filterable", () => {
    // The field exists before the panel opens — it *is* the trigger, so there
    // is nothing to reveal.
    const { trigger, filter } = harness(undefined, OPTS, { filterable: true });
    expect(trigger().tagName).not.toBe("BUTTON");
    expect(filter()).not.toBeNull();
    expect(filter()!.tagName).toBe("INPUT");
  });

  it("opens the panel when the input is clicked, and does not toggle shut", () => {
    // Clicking the input opens; clicking again must NOT close, because placing
    // the caret in a text field cannot be allowed to dismiss the list under it.
    //
    // Focus is deliberately not asserted here. The enclosing <label> is what
    // carries a click on the trigger's padding to the input, and that is the
    // browser's behaviour rather than ours — jsdom does not reproduce it, so
    // asserting it here would test jsdom. What is ours is the label itself,
    // pinned by the tagName test above.
    const { filter, listbox } = harness(undefined, OPTS, { filterable: true });
    fireEvent.click(filter()!);
    expect(listbox()).not.toBeNull();
    fireEvent.click(filter()!);
    expect(listbox()).not.toBeNull();
  });

  it("makes the input the one and only combobox", () => {
    // `aria-activedescendant` is only announced on the element that holds real
    // focus, which is why the role belongs on the input rather than on a
    // wrapper the user never focuses. Two elements claiming it is invalid.
    const { container, trigger, filter } = harness(undefined, OPTS, {
      filterable: true,
    });
    expect(filter()!.getAttribute("role")).toBe("combobox");
    expect(trigger().getAttribute("role")).toBeNull();
    fireEvent.click(trigger());
    expect(container.querySelectorAll('[role="combobox"]').length).toBe(1);
  });

  it("puts aria-activedescendant on the input as the highlight moves", () => {
    const { container, trigger, filter } = harness(undefined, OPTS, {
      filterable: true,
    });
    fireEvent.click(trigger());
    fireEvent.keyDown(filter()!, { key: "ArrowDown" });
    const active = container.querySelector(".minerva-select__option.is-active");
    expect(filter()!.getAttribute("aria-activedescendant")).toBe(active!.id);
  });

  it("carries the caller's ariaLabel on the input", () => {
    // No `?? "Filter options"` fallback: the input is the trigger, so the
    // label the caller gave the control is the label the control needs.
    const { filter } = harness(undefined, OPTS, { filterable: true });
    expect(filter()!.getAttribute("aria-label")).toBe("Test select");
  });

  it("opens the panel and narrows the list as the trigger is typed into", () => {
    // Native: the character lands in the input because the input is what the
    // reader is focused on. No seeding, and nothing to swallow.
    const { type, listbox, optionLabels } = harness(undefined, OPTS, {
      filterable: true,
    });
    expect(listbox()).toBeNull();
    type("gam");
    expect(listbox()).not.toBeNull();
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

  it("Space does not commit — in a text field a space is text", () => {
    const { trigger, filter, onChange } = harness(undefined, OPTS, {
      filterable: true,
    });
    fireEvent.click(trigger());
    fireEvent.keyDown(filter()!, { key: "ArrowDown" });
    fireEvent.keyDown(filter()!, { key: " " });
    expect(onChange).not.toHaveBeenCalled();
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

  it("shows the query while open and the selected label once closed", () => {
    // The input does double duty. `selected` still resolves against the full
    // list, so a query that excludes the selection does not erase it.
    const { trigger, filter, type } = harness("b", OPTS, { filterable: true });
    expect(filter()!.value).toBe("Beta");

    fireEvent.click(trigger());
    type("gam");
    expect(filter()!.value).toBe("gam");

    fireEvent.keyDown(filter()!, { key: "Escape" });
    expect(filter()!.value).toBe("Beta");
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
    type("a"); // every label contains an "a"
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

  it("filters rather than prefix-jumping in filterable mode", () => {
    // "m" is the discriminator: it is a substring of Gamma and a prefix of
    // nothing. Type-ahead would find no match and leave all three rendered;
    // filtering narrows to the one that contains it. (A letter like "a" cannot
    // tell the two apart — every label here contains one, Beta included.)
    const { type, optionLabels } = harness(undefined, OPTS, {
      filterable: true,
    });
    type("m");
    expect(optionLabels()).toEqual(["Gamma"]);
  });

  it("does not open a disabled filterable select", () => {
    const [value] = createSignal<string | undefined>(undefined);
    const { container } = render(() => (
      <Select
        options={OPTS}
        value={value()}
        onChange={() => undefined}
        filterable
        disabled
      />
    ));
    fireEvent.click(container.querySelector(".minerva-select__trigger")!);
    expect(container.querySelector(".minerva-select__listbox")).toBeNull();
  });

  it("falls back to a default placeholder when the caller gives none", () => {
    const [value] = createSignal<string | undefined>(undefined);
    const { container } = render(() => (
      <Select
        options={OPTS}
        value={value()}
        onChange={() => undefined}
        filterable
      />
    ));
    expect(
      container
        .querySelector(".minerva-select__filter-input")
        ?.getAttribute("placeholder"),
    ).toBe("Select…");
  });

  it("Escape closes the panel and leaves focus in the input", () => {
    const { trigger, filter, listbox } = harness(undefined, OPTS, {
      filterable: true,
    });
    fireEvent.click(trigger());
    fireEvent.keyDown(filter()!, { key: "Escape" });
    expect(listbox()).toBeNull();
    expect(document.activeElement).toBe(filter());
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

  it("Tab from the input closes the panel", () => {
    const { trigger, filter, listbox } = harness(undefined, OPTS, {
      filterable: true,
    });
    fireEvent.click(trigger());
    fireEvent.keyDown(filter()!, { key: "Tab" });
    expect(listbox()).toBeNull();
  });

  describe("on mobile", () => {
    // `styles/mobile.css:1119-1134` makes the panel `position: fixed; inset:
    // 44px 0 0 0; z-index: 80` while `.mobile-sheet` is `z-index: 71`, so the
    // panel covers its own trigger. An editable trigger would be invisible
    // while the list is open, so the field moves into the panel and the
    // trigger stays a button. Overriding `matchMedia` follows the precedent in
    // `App.test.tsx:115-116`.
    const realMatchMedia = window.matchMedia.bind(window);
    beforeEach(() => {
      window.matchMedia = vi.fn().mockImplementation((query: string) => ({
        matches: true,
        media: query,
        onchange: null,
        addListener: () => undefined,
        removeListener: () => undefined,
        addEventListener: () => undefined,
        removeEventListener: () => undefined,
        dispatchEvent: () => false,
      }));
    });
    afterEach(() => {
      window.matchMedia = realMatchMedia;
    });

    it("keeps a button trigger and puts the field inside the panel", () => {
      const { container, trigger, filter } = harness(undefined, OPTS, {
        filterable: true,
      });
      expect(trigger().tagName).toBe("BUTTON");
      // Closed: no field anywhere, because the panel is not rendered.
      expect(filter()).toBeNull();

      fireEvent.click(trigger());
      expect(filter()).not.toBeNull();
      expect(
        container
          .querySelector(".minerva-select__panel")!
          .contains(filter()),
      ).toBe(true);
    });

    it("returns focus to the button trigger when Escape closes the sheet", () => {
      const { trigger, filter, listbox } = harness(undefined, OPTS, {
        filterable: true,
      });
      fireEvent.click(trigger());
      fireEvent.keyDown(filter()!, { key: "Escape" });
      expect(listbox()).toBeNull();
      // The button is the control here, so that is where focus belongs — the
      // mirror of the desktop case, where focus stays in the input.
      expect(document.activeElement).toBe(trigger());
    });

    it("narrows the list from the panel's field", () => {
      const { trigger, type, optionLabels } = harness(undefined, OPTS, {
        filterable: true,
      });
      fireEvent.click(trigger());
      type("gam");
      expect(optionLabels()).toEqual(["Gamma"]);
    });
  });
});
