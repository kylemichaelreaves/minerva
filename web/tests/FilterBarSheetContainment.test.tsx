// The Concordance filter bar's picker panels inside the mobile sheet (#365).
//
// The sheet contains a `Select` panel by pinning it to `position: static`, so
// it cannot escape the sheet body. That rule was written for the three controls
// that were a local `Dropdown` at the time, and #364's port retargeted it from
// `.fbar-drop .menu` onto `.fbar-drop .minerva-select__panel` — keeping it on
// the `.fbar-drop` wrapper only those three controls carry.
//
// The Author and Work pickers are bare `<Select>`s in a `.grp`, so the rule
// never reached them. They are also the two `filterable` ones — the tall ones,
// with a search input above the listbox — which is the case containment matters
// most for.
//
// These tests read the selector out of the stylesheet and ask the real rendered
// panel whether it matches. Asserting the CSS text alone would pass on a rule
// that covers nothing; asserting the markup alone cannot see the rule. The
// defect lived exactly in the gap between them.

import { fireEvent, render } from "@solidjs/testing-library";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it, vi } from "vitest";
import { FilterBar } from "~/Concordance/components/FilterBar";

// Comments stripped, because a selector is scraped as "everything since the
// last brace" and a comment block sits directly above this rule.
const css = readFileSync(
  resolve(process.cwd(), "src/Concordance/concordance.css"),
  "utf8",
).replace(/\/\*[\s\S]*?\*\//g, "");

/** The selector list of the mobile-sheet containment rule — the one that pins a
 *  picker panel to `position: static`. Found by its declaration rather than by
 *  a hard-coded selector, so widening the rule is what the test sees. */
function containmentSelectors(): string[] {
  const panelRules = [...css.matchAll(/([^{}]+)\{([^{}]*)\}/g)]
    .map((m) => ({ selector: m[1] ?? "", body: m[2] ?? "" }))
    .filter(
      (r) =>
        r.selector.includes("minerva-select__panel") &&
        /position:\s*static;/.test(r.body),
    );
  const only = panelRules[0];
  if (panelRules.length !== 1 || only === undefined) {
    throw new Error(
      `expected exactly one static-position rule for a Select panel, found ${String(panelRules.length)}`,
    );
  }
  return only.selector
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

function renderBarWithPickers() {
  render(() => (
    <FilterBar
      lang="deu"
      sort="freq"
      freqCeil={1000}
      scope="work"
      authorOptions={[{ value: "hegel", label: "Hegel" }]}
      workOptions={[{ value: "pr", label: "Philosophy of Right" }]}
      onSetLang={vi.fn()}
      onSetSort={vi.fn()}
      onSetPos={vi.fn()}
      onSetFreqRange={vi.fn()}
      onSetQ={vi.fn()}
      onPickAuthor={vi.fn()}
      onPickWork={vi.fn()}
    />
  ));
}

/** Open the picker in the group carrying `label` and return its panel. */
function openPanel(label: string): HTMLElement {
  const group = Array.from(document.querySelectorAll(".fbar .grp")).find(
    (g) => g.querySelector(".lab")?.textContent === label,
  );
  if (!group) throw new Error(`no filter-bar group labelled ${label}`);
  // A plain Select's trigger is a <button>; a `filterable` one is a <label>
  // wrapping the combobox <input>, so click whichever this control has.
  const trigger = group.querySelector<HTMLElement>(".minerva-select__trigger");
  if (!trigger) throw new Error(`${label} has no trigger`);
  fireEvent.click(trigger.querySelector("input") ?? trigger);
  const panel = group.querySelector<HTMLElement>(".minerva-select__panel");
  if (!panel) throw new Error(`${label}'s panel did not open`);
  return panel;
}

describe("the mobile sheet's picker containment reaches every picker (#365)", () => {
  for (const label of ["Language", "Sort", "POS", "Author", "Work"]) {
    it(`contains the ${label} panel`, () => {
      renderBarWithPickers();

      const panel = openPanel(label);

      expect(
        containmentSelectors().some((sel) => panel.matches(sel)),
      ).toBe(true);
    });
  }
});
