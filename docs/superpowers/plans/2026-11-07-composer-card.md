# Composer Card (PR 1 of 5) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Landing and chat use one weighted composer card, with the scope pill in its footer and a filled accent button, on desktop and phone, and the landing ↔ chat transition still runs cleanly.

**Architecture:** `ComposeField` stays the single component behind both composers. A new shared stylesheet, `composeCard.css`, holds the card's look, and the per-variant rules in `landing.css`, `composer.css` and `mobile.css` shrink to the size differences. The variant class names that the transition and mobile CSS select on (`.landing-input-wrap`, `.landing-input`, `.composer-wrap`, `.composer`, `.composer-input`) are kept. The scope pill moves inside the card, so it rides with the box during the flight, and the flight's separate chip animation is deleted.

**Tech Stack:** SolidJS, plain CSS custom properties, vitest + @solidjs/testing-library (`web/tests/`), Playwright browser suite (`web/tests/browser/`).

**Spec:** `docs/superpowers/specs/2026-11-07-composer-redesign-design.md` (sections "The composer card", "Dark theme", "The landing → chat transition", "Mobile"; delivery step 1). Mock: <https://claude.ai/artifact/GnQKPhukfbExzueX2ixSop>, boards `A-Landing` and `A-Chat`.

**Out of scope here (PRs 2–5):** top bar, removing the landing modes row, Request timing link or Atlas, the mobile drawer nav. Leave the landing body below the composer untouched.

## Global Constraints

- Work in the worktree `/Users/kreaves/src/minerva-composer-redesign`. Create the branch `feat/composer-card` from `origin/main` before Task 1.
- Frontend tests go in `web/tests/` (unit) and `web/tests/browser/` (Playwright), never colocated under `web/src`.
- New tokens go in `web/src/styles/styles.css`, under both `:root` and `[data-theme="dark"]`. No hex literals in feature CSS.
- Card: radius `10px`; border `1px solid var(--rule)`; background `var(--paper-raised)`; shadow `var(--composer-shadow)`.
- Light values: `--paper-raised: #fbf8f2`; `--on-accent: var(--paper)`; `--composer-shadow: 0 1px 0 var(--paper-edge), 0 16px 40px rgb(26 23 20 / 8%)`.
- Dark values: `--paper-raised: #1b1713`; `--on-accent: var(--paper)` (dark text on terracotta); `--composer-shadow: 0 1px 0 var(--rule-soft)`, the hairline only.
- Input: serif, roman (not italic), `21px` landing / `19px` chat, line-height `1.45`. Resting height: landing 3 rows (`min-height: 104px`), chat 2 rows (`min-height: 64px`). Padding: landing `20px 22px 8px`, chat `16px 22px 4px`.
- Footer: no rule above it. Left side holds the scope pill, then the key hint. Right side holds the send button: filled `var(--accent)`, `var(--on-accent)` text, `40px` tall, pill radius, `13.5px` sans, weight 500, labelled "Begin" / "Send" with a trailing →.
- Placeholders are unchanged: "What would you like to consider?" / "Continue the enquiry…" / mobile "Reply to Minerva…".
- `make check` must pass before every commit that ends a task. Re-run it after any fix.
- Cognitive complexity ≤ 15 per function (Sonar). Duplication ≤ 3% on new code.

## Review Focus

1. **A long work title in the pill on a 390px phone.** The title truncates with an ellipsis, and the send button stays inside the card. Pinned in Task 6.
2. **"Awaiting reply…" (disabled) on the accent button.** It reads as disabled: `--rule` background, `--ink-mute` text, `disabled` attribute set. Pinned in Task 2.
3. **Escape back to the landing with a work scope set.** The landing's pill reads "All works" for the whole return, with no flip to it at the end. Pinned in Task 5.
4. **Keyboard order inside the card is textarea → scope pill → send**, and the card shows a visible focus state when the textarea has focus. Pinned in Task 2 (order) and Task 3 (focus ring, via `focusRing.spec.ts`).
5. **A question taller than the landing box when you press Begin** (the textarea is scrolled). The flight still starts from the box and lands in the turn. The existing browser test covers this; it must keep passing after Task 5.

---

### Task 1: Composer tokens with measured contrast

**Files:**
- Modify: `web/src/styles/styles.css` (`:root` block ~line 6, `[data-theme="dark"]` block ~line 74)
- Create: `web/tests/helpers/contrast.ts`
- Test: `web/tests/composerTokens.test.ts`

**Interfaces:**
- Produces: CSS custom properties `--paper-raised`, `--on-accent` and `--composer-shadow`, in both themes. Also `contrastRatio(fg: string, bg: string): number`, which takes `#rrggbb` and returns the WCAG 2.x ratio.

- [ ] **Step 1: Write the failing test.** `composerTokens.test.ts` reads `src/styles/styles.css` as text and extracts each theme block's declarations with a regex. Assertions:
  - Light `--on-accent` resolved (`--paper` `#f4efe6`) on `--accent` `#7b2e2a`: ratio ≥ 4.5.
  - Dark `--on-accent` resolved (`--paper` `#14110e`) on `--accent` `#c97a65`: ratio ≥ 4.5.
  - `--ink` on `--paper-raised`: ≥ 4.5 in both themes.
  - `--ink-mute` on `--paper-raised`: ≥ 4.5 in both themes (it colours the key hint).
- [ ] **Step 2: Run it.** `cd web && npx vitest run tests/composerTokens.test.ts`. Expected: FAIL, because the tokens are not defined.
- [ ] **Step 3: Add the tokens** with the values in Global Constraints. If an assertion fails on a value above, adjust that value and record the measured ratio in a comment beside it, the way the `--bad/--warn/--ok` comment does.
- [ ] **Step 4: Run it.** Expected: PASS.
- [ ] **Step 5: Commit.** `git commit -m "feat(web): composer card tokens with measured contrast"`

### Task 2: One footer for both composers (`ComposeField`)

**Files:**
- Modify: `web/src/components/cards/ComposeField.tsx`
- Test: `web/tests/Composer.test.tsx`, `web/tests/Landing.test.tsx`

**Interfaces:**
- Consumes: nothing new.
- Produces the DOM that Tasks 3–6 style and select on, the same for both variants:
  - The card element carries `compose-card` plus its variant class: `landing-input-wrap` (landing; the wrap *is* the card) or `composer` (chat, inside `.composer-wrap`).
  - The textarea carries `compose-input` plus `landing-input` / `composer-input`.
  - The footer is `div.compose-foot`, containing `div.compose-foot__left` (`props.scopeChip`, then `props.hint`) and `button.compose-send`.
  - `props.scopeChip` renders **only** inside `.compose-foot__left`, never above the input.
  - The `accessory` prop is deleted. It has no caller since #258.
  - The `send-btn` class is no longer emitted.

- [ ] **Step 1: Write the failing tests.**
  - In `Composer.test.tsx`, `it("renders scope, hint and send in one footer, in tab order")`: render `<Composer scopeChip={<button>scope</button>} …/>`. Assert `.compose-foot__left` contains the scope button, and that `[textarea, scope button, send button]` is the order of `container.querySelectorAll("textarea, button")`.
  - In `Composer.test.tsx`, `it("shows a disabled send while awaiting a reply")`: with `disabled`, the `.compose-send` button has the `disabled` attribute.
  - In `Landing.test.tsx`, replace `"puts the chip above the input, not below it"` with `"puts the scope pill in the footer, after the input"`: the chip's `compareDocumentPosition` relative to the textarea is `DOCUMENT_POSITION_FOLLOWING`, and `chip.closest(".compose-foot__left")` is not null.
- [ ] **Step 2: Run them.** `npx vitest run tests/Composer.test.tsx tests/Landing.test.tsx`. Expected: the new tests FAIL.
- [ ] **Step 3: Restructure `ComposeField`** to the DOM in Interfaces. The two variant branches in the footer collapse into one; only `sendLabel`, `hint`, placeholder and the variant classes differ. Keep `disabled` on the button, and keep the `disabled` class for `sendDisabled()`.
- [ ] **Step 4: Run them, then the rest of the unit suite** (`npx vitest run --exclude 'tests/e2e/**'`). Fix any assertion that names `.send-btn`, `.composer-foot` or `.landing-input-foot` by moving it to the new class. Don't delete an assertion's behaviour. Expected: PASS.
- [ ] **Step 5: Commit.** `git commit -m "refactor(web): one composer footer, scope pill inside it"`

### Task 3: The card stylesheet

**Files:**
- Create: `web/src/components/cards/composeCard.css`, imported from `ComposeField.tsx`
- Modify: `web/src/features/Landing/landing.css` (composer block ~lines 301–390), `web/src/features/Composer/composer.css` (`.composer`, `.composer-input`, `.composer-foot`, `.kbd`), `web/src/styles/styles.css` (`.send-btn` block ~lines 290–325: delete it, since Task 2 left it no users)
- Test: `web/tests/browser/composerCard.spec.ts` (new)

**Interfaces:**
- Consumes: the Task 1 tokens and the Task 2 class names.
- Produces: `.compose-card`, `.compose-input`, `.compose-foot`, `.compose-foot__left` and `.compose-send` (including `:hover`, `:focus-visible`, and `:disabled` / `.disabled` as `background: var(--rule)`, `color: var(--ink-mute)`, no pointer events), plus `.compose-card:focus-within`, a visible ring: border `var(--ink)` plus a `0 0 0 3px var(--selection)` ring added to the shadow.

- [ ] **Step 1: Write the failing browser test** `composerCard.spec.ts` using the fixture server (see `tests/browser/fixtures.ts`). At 1280×800:
  - `it("landing and chat cards share radius, background and border")`: read computed `border-radius`, `background-color` and `border-top-color` from `.landing-input-wrap`. Begin a question, wait for the chat, and read the same from `.composer`. Assert they are equal and that the radius is `10px`.
  - `it("send is a filled accent pill")`: on `.compose-send`, `background-color` equals the computed `--accent`, and the height is `40px`.
  - `it("rests at three lines on the landing and two in the chat")`: the `.landing-input` client height is ≥ 104 and the `.composer-input` client height is ≥ 64.
  - Run the same three assertions under `colorScheme: "dark"` (set `data-theme="dark"`).
- [ ] **Step 2: Run it.** `cd web && npx playwright test tests/browser/composerCard.spec.ts`. Expected: FAIL.
- [ ] **Step 3: Write `composeCard.css`** with the values in Global Constraints. Variant size differences (font size, min-height, padding, width) stay in `landing.css` / `composer.css`, scoped to the variant class. Delete every rule there that the shared file now owns. The landing card's width becomes `720px` (was `680px`). The chat card keeps `max-width: var(--col)`.
- [ ] **Step 4: Run** `composerCard.spec.ts` and `focusRing.spec.ts`. Expected: PASS. `focusRing.spec.ts` still finds a visible ring on the composer.
- [ ] **Step 5: Commit.** `git commit -m "feat(web): weighted composer card on landing and chat"`

### Task 4: The scope pill (`WorkScopeControl`)

**Files:**
- Modify: `web/src/features/Composer/WorkScopeControl.tsx`, the `.chat-scope*` rules in `web/src/features/Composer/composer.css`
- Test: `web/tests/WorkScopeControl.test.tsx` (new), `web/tests/browser/landingTransition.spec.ts:368`

**Interfaces:**
- Produces:
  - **Unscoped:** one `<button aria-haspopup="dialog">` with visible text "All works" and a ▾ chevron (`aria-hidden`), and accessible name `"Scope: All works"`.
  - **Scoped:** the work's title as the opener, accessible name `"Scope: <title>"`, plus the existing × clear button.
  - The drop-up picker is unchanged.
  - Pill styling: `--paper-soft` background, `1px solid var(--rule-soft)` border, pill radius, `12px` sans, `6px 12px` padding; the title is truncated at `max-width: 32ch`.

- [ ] **Step 1: Write the failing tests** in `WorkScopeControl.test.tsx`:
  - `it("offers 'All works' when unscoped")`: `getByRole("button", { name: "Scope: All works" })` exists.
  - `it("names the work when scoped and can clear it")`: given scope `{workId: 1}` and a work titled "Ethica", `getByRole("button", { name: "Scope: Ethica" })` exists. Clicking the clear button calls `onSet(null)`.
  - `it("opens the picker from the pill")`: clicking the pill renders the filter input.
- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Implement** the pill per Interfaces. Change the browser spec's `/scope to a work/i` locator (line 368) to `{ name: "Scope: All works" }`.
- [ ] **Step 4: Run** the new test, `WorkScopeControlEscape.test.tsx`, and `landingTransition.spec.ts`. Expected: PASS.
- [ ] **Step 5: Commit.** `git commit -m "feat(web): scope control as an 'All works' pill"`

### Task 5: Always-on pill and the transition

**Files:**
- Modify: `web/src/routes/ChatRoute.tsx` (landing `scopeChip`, ~lines 134–149), `web/src/features/LandingTransition/flight.ts` (`FlightOrigin.chip`, `FlightTarget.chip`, `measureOrigin`, `measureTarget`, the `composerKeyframes` chip leg), `web/src/features/LandingTransition/controller.ts` (chip queries in `playFlight`, `measureOrigin` and `measureTarget`), `web/src/features/LandingTransition/landingTransition.css` (the `.lt-entering .composer-foot`, `> :not(.composer)` and `.chat-scope-control` rules ~lines 153–166, and their `[data-lt-return="return"]` mirrors ~lines 232–233), `docs/superpowers/specs/2026-11-06-landing-chat-transition-design.md` (the chip-travel and footer-fade passages)
- Test: `web/tests/landingTransitionController.test.ts`, `web/tests/browser/landingTransition.spec.ts`

**Interfaces:**
- Consumes: the Task 2 DOM. The pill now lives inside the card, so it moves with the box's `maxWidth`/`height` animation and the wrap's translate.
- Produces:
  - `composerKeyframes(o, t): { wrap: Keyframe[]; box: Keyframe[] }` (the `chip` field is gone).
  - `measureOrigin(textarea, box)` and `measureTarget(body, composer)` (the chip parameter is gone).
  - The landing always receives a `WorkScopeControl`. Its `scope` accessor is `() => (returning() ? null : props.conversations.chatScope())`, so a return shows "All works" from its first frame.

- [ ] **Step 1: Write the failing tests.**
  - In `landingTransitionController.test.ts`: `it("composerKeyframes has no chip leg")`. Given an origin and target, `Object.keys(composerKeyframes(o, t))` equals `["wrap", "box"]`.
  - In `landingTransition.spec.ts`, replace `"a work scope's chip travels from the landing's chip"` (line 660) with `"the scope pill rides inside the box"`. On a scoped landing, press Begin, then freeze frames, snapshotting only the animations started by the trigger (see the `getAnimations` trap recorded in the #855 notes). At the midpoint, the `.composer .chat-scope-control` box is inside the `.composer` box, and its opacity is 1.
  - In `landingTransition.spec.ts`, add `"a scoped chat returns to an 'All works' landing without a flip"`. With a scope set, press Escape. Read the landing pill's accessible name **once** via `page.evaluate` at the return's first frame and once at the end; both are `"Scope: All works"`. Don't use an auto-retrying assertion; the #855 notes record why.
- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Implement.** Remove the chip leg and its parameters. Pass the pill to the landing unconditionally, with the accessor above. Delete the footer and chip fade rules: the landing and chat footers now have the same shape, so the footer stays visible through the lift and the return. Keep the placeholder-transparent rule. Update the two passages in the 2026-11-06 spec to say the pill now rides inside the box.
- [ ] **Step 4: Run** `npx vitest run tests/landingTransitionController.test.ts tests/returnTransitionController.test.ts tests/Landing.test.tsx` and `npx playwright test tests/browser/landingTransition.spec.ts`. Expected: PASS, including Review Focus 5 (the existing scrolled-question test).
- [ ] **Step 5: Commit.** `git commit -m "feat(landing): scope pill rides inside the box through the transition"`

### Task 6: The card on phones

**Files:**
- Modify: `web/src/styles/mobile.css` (`.landing-input-wrap` / `.send-btn` ~lines 466–510; chat composer ~lines 575–650), `web/src/features/LandingTransition/landingTransition.css` (the mobile top-rule rules ~lines 50 and 258–268)
- Test: `web/tests/browser/composerCard.spec.ts`

**Interfaces:**
- Consumes: the Task 3 classes.
- Produces, at ≤768px:
  - The same card (radius, raised paper, border; shadow allowed to drop) with `12px` side margins. It replaces the borderless bar.
  - Input `17px` serif roman. Landing resting 3 rows, chat 1 row.
  - `.compose-send` becomes a `44×44` accent circle showing only the arrow, `aria-label` = the send label.
  - The chat hides the key hint, as today. The landing keeps `.landing-mobile-hint`.
  - The pill title truncates at `max-width: 18ch`.

- [ ] **Step 1: Write the failing tests** in `composerCard.spec.ts`, at 390×844:
  - `it("phone: the card keeps its border and radius")`.
  - `it("phone: send is a 44px circle named by its label")`: `getByRole("button", { name: "Send" })` has a bounding box of 44×44.
  - `it("phone: a long work title truncates and send stays inside the card")` (Review Focus 1): scope the chat to the fixture's longest title, then assert the `.compose-send` box lies within the `.composer` box and that the title element's `scrollWidth > clientWidth`.
- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Rewrite the mobile composer rules** per Interfaces. Delete the borderless-bar rules and the transition's mobile top-rule rules, which no longer have a bar to draw.
- [ ] **Step 4: Run** `composerCard.spec.ts` and `landingTransition.spec.ts` (its mobile cases included). Expected: PASS.
- [ ] **Step 5: Commit.** `git commit -m "feat(web): composer card on phones"`

### Task 7: Gate, issue, PR

- [ ] **Step 1: Run `make check`** from the repo root and read the output. Expected: every stage passes, including `check-diff-coverage` ≥ 80% (branches included). Fix and re-run until it does.
- [ ] **Step 2: Take screenshots** of the landing and chat at 1280×800, light and dark, plus the phone landing and chat, from the browser-suite fixture server (not `make run`). Save them to the scratchpad for the PR body.
- [ ] **Step 3: File the issue** for this step: "Composer redesign 1/5: weighted composer card". The body has `## Measured`: today's thin box, with the `landing.css` / `composer.css` `file:line` refs. It has `## Hypothesis`: the spec's fix. It links the spec and the mock and carries the `frontend` + `enhancement` labels. Run `direnv exec . gh issue create …`.
- [ ] **Step 4: Push and open the PR** against `main`, with `Closes #<issue>` in the body and the commit trailer. The body says what is deferred to PRs 2–5. Then run `make check-pr-link PR=<n> ISSUES="<issue>"` and expect exit 0.
