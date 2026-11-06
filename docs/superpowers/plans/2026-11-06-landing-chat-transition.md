# Landing → Chat Transition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pressing Begin on the landing plays one movement into Chat: the box slides down into the chat composer, the question lifts into the first user turn, the landing furniture fades away and the chat furniture arrives late.

**Architecture:** No View Transitions. The landing stays mounted as a fading, inert layer above Chat for the duration of the flight. The *real* chat composer is FLIP-animated from the landing box's rect. The question flies as an imperative overlay "ghost" `<p>` whose position, size and font animate live, so it reflows. The real first-turn body stays hidden until the ghost lands. A small controller owns the phase (`idle | lift | fade`) and picks among lift, crossfade (reduced motion) and cut (no `Element.prototype.animate`). Every DOM read and every animation goes through an injectable environment, so the controller and geometry are unit-testable in jsdom.

**Tech Stack:** SolidJS, TypeScript, CSS animations, the Web Animations API (`element.animate`), vitest + @solidjs/testing-library (jsdom), Playwright (Chromium).

**Spec:** `docs/superpowers/specs/2026-11-06-landing-chat-transition-design.md`. Read it first; its choreography table is the acceptance reference.

**Working copy:** worktree `/Users/kreaves/src/minerva-landing-transition`, branch `landing-chat-transition` (off `origin/main` at `b428619`). It has no `node_modules` or `.venv` yet. Before the first test run, do `cd web && npm ci` and `uv sync --locked` at the root, or `make check` will fail for the wrong reason.

## Global Constraints

- Lift duration **D = 650ms**; easing **`cubic-bezier(.2,.7,.1,1)`** ("settle"). Reduced-motion crossfade **180ms**.
- Choreography fractions, verbatim from the spec's table:
  - landing furniture: opacity over 0.45D (`ease`), drift over 0.7D (settle);
  - owl −18px and scale .96; mode row and aside +28px; atlas +44px;
  - topbar from −6px, 0.4D, starting at 0.55D;
  - chat composer footer fades in over 0.35D, starting at 0.5D;
  - user-turn chrome (rule, background) over 0.35D, starting at 0.65D;
  - user-turn meta label: 240ms, starting at 0.8D;
  - thinking row: from 0.5D.
- The request to the server goes out on Begin exactly as today. `startFromLanding(text)` is called **exactly once** per submit, in every mode, including when measuring or animating throws.
- Reply text is never held back by the animation.
- Only the landing's Begin/Enter submit animates. Sidebar picks and direct `#/c/<id>` loads do not.
- Going back to the landing ("New question") is the existing `.fade-in` (480ms, `landing.css:680`). Nothing to build; don't change it.
- Repo gates (CLAUDE.md):
  - `make check` must be green;
  - ≥80% changed-line coverage *including branches* on `web/src/`;
  - Sonar cognitive complexity ≤15 per function;
  - tests live in `web/tests/` (never colocated);
  - `attr:inert`, not the `inert` prop (`AppRoutes.tsx` explains why).
- CSS lives in `web/src/features/LandingTransition/landingTransition.css`, imported by the controller module, except for the user-turn column rule, which belongs in `thread.css`. Durations come from two custom properties that the controller sets on `document.documentElement` while a transition runs and removes afterwards: `--lt-d: 650ms` and `--lt-ease: cubic-bezier(.2,.7,.1,1)`. CSS expresses every delay and duration as `calc(var(--lt-d) * <fraction>)`.

## Review Focus

1. **The stream's meta arrives mid-flight.** On a fast server, `applyStreamMeta` navigates to `{kind:"conversation"}` and appends the Minerva placeholder inside the 650ms. The flight should play once, to the end, without restarting, and the first delta should render immediately. Pinned by the Task 5 Playwright test "fast server".
2. **"New question" (or a sidebar pick) mid-flight.** The flight should be cancelled, no ghost left in the DOM, `--lt-*` removed, and the landing rendered normally. Pinned by the Task 3 unit test `cancel` and the Task 5 Playwright test "new question mid-flight".
3. **A long question.** Six or more lines, so the textarea scrolls past `maxPx: 320`. The ghost should carry the *whole* text and the landed turn should show all of it. Pinned by the Task 2 unit test (origin offset by `scrollTop`) and the Task 5 Playwright test "long question".
4. **Typing straight after Enter.** Keystrokes typed during the flight should land in the chat composer. Pinned by the Task 4 unit test (`focusOnMount`) and the Task 5 Playwright test "type during flight".
5. **Measuring or animating fails.** A missing element, `animate` throwing, or `finished` never settling should still send the message once, end with phase `idle` and leave no ghost, with a 200ms grace timeout after D. Pinned by Task 3 unit tests.

---

### Task 1: User turns sit in the composer's column

The spec's "How — decided" bullet. Independent of the animation; ship-able alone.

**Files:**
- Modify: `web/src/Thread/components/UserTurnView.tsx` (wrap meta and body in `<div class="turn-user-inner">`)
- Modify: `web/src/Thread/thread.css`:
  - add `.thread.has-margin .turn-user-inner { max-width: var(--col); margin: 0 auto; }`;
  - add `scrollbar-gutter: stable both-edges` to `.scroll`, so a classic scrollbar can't shift the thread's centre away from the sticky composer's.
- Test: `web/tests/UserTurnView.test.tsx` (create)
- Test: `web/tests/browser/landingTransition.spec.ts` (create; later tasks add to it)

**Interfaces:**
- Produces: the class `.turn-user-inner`. Task 4's CSS and Task 5's spec target `.turn-user-inner .turn-body`.

- [ ] **Step 1: Write the failing unit test.** `UserTurnView` renders `.turn.turn-user > .turn-user-inner`, and `.turn-user-inner` contains both `.turn-meta` (text `You · 10:00` for `time: "10:00"`) and `.turn-body` (the message text).
- [ ] **Step 2: Run it.** Command: `cd web && npx vitest run tests/UserTurnView.test.tsx`. Expected: FAIL (no `.turn-user-inner`).
- [ ] **Step 3: Implement the wrapper and both CSS rules.** Check `styles/mobile.css:701–712`: the mobile bubble rules target `.turn-user .turn-body` and must still apply unchanged.
- [ ] **Step 4: Run it.** Expected: PASS.
- [ ] **Step 5: Write the Playwright spec "user turn lines up with the composer".**
  - Viewport 1440×900. `page.route("**/api/chat", () => {})` (never fulfilled, so the thread stays in "thinking").
  - Fill the landing textarea (placeholder "What would you like to consider?") with `What does Hegel mean by the owl of Minerva?` and press Enter.
  - Wait for `.turn-user-inner .turn-body` to be visible.
  - With `innerBox` as `.turn-user-inner`'s bounding box and `composerBox` as `.composer`'s, assert `|innerBox.x − composerBox.x| ≤ 1` and `|innerBox.width − composerBox.width| ≤ 1`.
- [ ] **Step 6: Run it.** Command: `make test-browser`. Expected: the new test PASSES and the existing specs still pass. If the 1px check fails by about half a scrollbar width, the `scrollbar-gutter` rule isn't applying. Fix that rather than loosening the tolerance.
- [ ] **Step 7: Commit.** Message: `feat(chat): user turns sit in the composer's column on wide screens`.

### Task 2: Flight geometry (pure, measured)

**Files:**
- Create: `web/src/features/LandingTransition/flight.ts`
- Test: `web/tests/landingTransitionFlight.test.ts`

**Interfaces:**
- Produces:
  - `interface Rect { top: number; left: number; width: number; height: number }`
  - `const MORPH_PROPS = ["fontSize","lineHeight","color","fontStyle"] as const`. These animate over D.
  - `const CHROME_PROPS = ["backgroundColor","borderTopColor","borderRightColor","borderBottomColor","borderLeftColor"] as const`. These animate over 0.35D, starting at 0.65D.
  - `const FRAME_PROPS = ["paddingTop","paddingRight","paddingBottom","paddingLeft","borderTopWidth","borderRightWidth","borderBottomWidth","borderLeftWidth","borderTopStyle","borderRightStyle","borderBottomStyle","borderLeftStyle"] as const`. These are copied from the target and fixed for the whole flight.
  - `interface FlightOrigin { text: string; textTop: number; textLeft: number; textWidth: number; style: Record<MorphProp,string>; box: Rect }`
  - `interface FlightTarget { body: Rect; style: Record<MorphProp|ChromeProp|FrameProp,string>; composer: Rect }`
  - `measureOrigin(textarea: HTMLTextAreaElement, box: HTMLElement): FlightOrigin`
    - `textTop = rect.top + borderTop + paddingTop − textarea.scrollTop`;
    - `textLeft = rect.left + borderLeft + paddingLeft`;
    - `textWidth = clientWidth − paddingLeft − paddingRight`;
    - `text = textarea.value.trim()`, matching what `createComposer.send` submits.
  - `measureTarget(body: HTMLElement, composer: HTMLElement): FlightTarget`
  - `ghostKeyframes(o: FlightOrigin, t: FlightTarget): { move: Keyframe[]; chrome: Keyframe[] }`. The ghost has the target's frame (padding and border widths) throughout, so its *outer* box at the origin is the text origin pushed out by those insets:
    - origin `left = textLeft − padL − borderL`, `top = textTop − padT − borderT`, `width = textWidth + padL + padR + borderL + borderR`;
    - target = `t.body`, as given;
    - `move` animates `top/left/width` (px strings) plus `MORPH_PROPS`, from origin style to target style;
    - `chrome` animates `CHROME_PROPS` from `transparent` to the target values.
  - `composerKeyframes(o: FlightOrigin, t: FlightTarget): { wrap: Keyframe[]; box: Keyframe[] }`:
    - `wrap` goes from `translate(dx, dy)` to `translate(0px, 0px)`, where dx and dy are the centre-x and top differences between `o.box` and `t.composer`;
    - `box` goes from `maxWidth: ${o.box.width}px` to `maxWidth: ${t.composer.width}px`.

- [ ] **Step 1: Write the failing tests.** Stub `getBoundingClientRect`, `getComputedStyle` and `scrollTop`/`clientWidth` on jsdom elements with `vi.spyOn`. Assert these exact values:
  - `measureOrigin`:
    - Inputs: a textarea with rect `{top:300,left:200,width:648,height:26}`, padding 0, border 0, `scrollTop` 40, `clientWidth` 648, value `"  Why?  "`.
    - Expected: `textTop 260`, `textLeft 200`, `textWidth 648`, `text "Why?"`.
  - `ghostKeyframes`:
    - Inputs: that origin (17px/24.65px, `italic`, `rgb(26, 23, 20)`) and a target body rect `{top:118,left:280,width:880,height:28}` with `paddingLeft 18px`, `borderLeftWidth 2px` and other insets 0.
    - Expected: `move[0]` has `left "180px"`, `top "260px"`, `width "668px"`, `fontSize "17px"`; `move[1]` has `left "280px"`, `top "118px"`, `width "880px"`, `fontSize "18px"`; `chrome[0].borderLeftColor` is `"transparent"` and `chrome[1].borderLeftColor` is the target colour.
  - `composerKeyframes`:
    - Inputs: an origin box `{top:304,left:300,width:680}` and a target composer `{top:688,left:280,width:880}`.
    - Expected: `wrap[0].transform` is `"translate(-80px, -384px)"`, because the centre x goes 640 → 720 and the top goes 304 → 688. `box[0].maxWidth` is `"680px"`.
- [ ] **Step 2: Run it.** Command: `cd web && npx vitest run tests/landingTransitionFlight.test.ts`. Expected: FAIL (module missing).
- [ ] **Step 3: Implement `flight.ts`** to those signatures. No DOM writes.
- [ ] **Step 4: Run it.** Expected: PASS.
- [ ] **Step 5: Commit.** Message: `feat(landing): flight geometry for the landing → chat transition`.

### Task 3: Transition controller

**Files:**
- Create: `web/src/features/LandingTransition/controller.ts`
- Create: `web/src/features/LandingTransition/landingTransition.css` (ghost style only in this task: `.lift-ghost { position: fixed; margin: 0; pointer-events: none; z-index: 50; white-space: pre-wrap; overflow-wrap: anywhere; font-family: var(--serif); box-sizing: border-box; }`)
- Test: `web/tests/landingTransitionController.test.ts`

**Interfaces:**
- Consumes: everything Task 2 produces.
- Produces:
  - `type Phase = "idle" | "lift" | "fade"`
  - `const LIFT_MS = 650; const FADE_MS = 180; const SETTLE_EASE = "cubic-bezier(.2,.7,.1,1)"; const GRACE_MS = 200`
  - `interface Flight { finished: Promise<unknown>; cancel(): void }`
  - `interface TransitionEnv { reducedMotion(): boolean; canAnimate(): boolean; measureOrigin(): FlightOrigin | null; measureTarget(): FlightTarget | null; play(o: FlightOrigin, t: FlightTarget): Flight; setTiming(on: boolean): void }`
  - `defaultEnv(): TransitionEnv`:
    - `reducedMotion`: `matchMedia("(prefers-reduced-motion: reduce)").matches`;
    - `canAnimate`: `typeof Element.prototype.animate === "function"`;
    - `measureOrigin`: queries `.landing-input` and `.landing-input-wrap`, and returns null if either is missing;
    - `measureTarget`: queries `.turn-user-inner .turn-body`, `.composer-wrap` and `.composer`, and returns null if any is missing;
    - `play`: creates the `<p class="lift-ghost" aria-hidden="true">` on `document.body`, sets the target's `FRAME_PROPS` on it inline, and runs four animations:
      - the ghost's `move`, over `LIFT_MS` with `SETTLE_EASE`;
      - the ghost's `chrome`, over `0.35·LIFT_MS` with `0.65·LIFT_MS` delay;
      - `wrap` on `.composer-wrap`;
      - `box` on `.composer`.
      
      Every animation uses `fill: "both"`. `finished` is `Promise.all` of the four; `cancel` cancels all four and removes the ghost. The ghost is removed when the flight finishes, too.
    - `setTiming(true)` sets `--lt-d` and `--lt-ease` on `document.documentElement`; `setTiming(false)` removes them.
  - `createLandingTransition(env?: TransitionEnv): { phase: Accessor<Phase>; begin(text: string, send: (t: string) => void): void; cancel(): void }`

Controller rules. These are the decisions; the tests below pin each one.
- `begin` while the phase isn't `idle` is a no-op (double Enter).
- **Reduced motion:**
  1. phase `fade`;
  2. `setTiming(true)`;
  3. `send(text)`;
  4. after `FADE_MS`, phase `idle` and `setTiming(false)`.
- **`!canAnimate()`:** `send(text)` only; the phase stays `idle`. This is the cut, today's behaviour.
- **Lift:**
  1. `origin = measureOrigin()` **before** `send`;
  2. phase `lift` and `setTiming(true)`;
  3. `send(text)`;
  4. `target = measureTarget()` synchronously after `send` (Solid has updated the DOM by then);
  5. `flight = play(origin, target)`.
  
  End the flight on `flight.finished` *or* on a `LIFT_MS + GRACE_MS` timeout, whichever comes first. Ending sets phase `idle`, then `setTiming(false)`, then `flight.cancel()`, all in the same task. This removes the ghost in the same task that reveals the real body, so the user never sees a blink.
- Any of `measureOrigin()` returning null, `measureTarget()` returning null, or `measureOrigin`/`measureTarget`/`play` throwing degrades to the cut. `send` must still have been called exactly once, the phase ends `idle` and `setTiming(false)` runs. Write `try/finally`, not a catch that swallows silently: rethrowing isn't wanted, so log with `console.warn("landing transition skipped", err)`.
- `cancel()` cancels a running flight and clears the timers, then sets phase `idle` and calls `setTiming(false)`. It's idempotent.
- Keep `begin` under cognitive complexity 15. Split it into `beginFade`, `beginLift` and `endFlight`.

- [ ] **Step 1: Write the failing tests.** Use a fake env built from `vi.fn`s and `vi.useFakeTimers()`. One test per rule:
  - `reduced motion fades`: `send` is called once with `"Q"`; the phase is `"fade"` and then `"idle"` after `advanceTimersByTime(180)`; `setTiming` was called with `true` and then `false`.
  - `no animate cuts`: `send` is called once; the phase is `"idle"` throughout; `play` is never called.
  - `lift measures origin before send and target after`: the `vi.fn` call orders are `measureOrigin < send < measureTarget < play`; the phase is `"lift"`.
  - `lift ends when finished resolves`: resolve `finished` and flush microtasks. The phase is `"idle"`, `setTiming(false)` was called and `flight.cancel` was called.
  - `lift ends on grace timeout`: `finished` never settles; after `advanceTimersByTime(850)` the phase is `"idle"`.
  - `double begin is ignored`: `send` was called exactly once.
  - `null target degrades to cut`: `send` was called once, the phase is `"idle"` and `play` was never called.
  - `play throws degrades to cut`: same assertions, and `console.warn` was called.
  - `cancel mid-flight`: `flight.cancel` was called, the phase is `"idle"`, and advancing the timers later changes nothing.
  - `defaultEnv`:
    - stub `Element.prototype.animate` to return `{ finished: Promise.resolve(), cancel: vi.fn() }`, and render the landing and target DOM fixtures by hand;
    - assert that `play` appends exactly one `.lift-ghost` containing the question text, and that it's removed after `finished` resolves;
    - assert that `setTiming(true)` sets `--lt-d` to `650ms` on `document.documentElement` and that `setTiming(false)` removes it;
    - assert that `measureOrigin()` returns null when `.landing-input` is absent.
- [ ] **Step 2: Run them.** Command: `cd web && npx vitest run tests/landingTransitionController.test.ts`. Expected: FAIL (module missing).
- [ ] **Step 3: Implement `controller.ts`** and the ghost CSS.
- [ ] **Step 4: Run them.** Expected: PASS. Then run `cd web && npx vitest run --coverage tests/landingTransition*.test.ts` and check the branch coverage of `controller.ts` and `flight.ts` is at least 80%.
- [ ] **Step 5: Commit.** Message: `feat(landing): transition controller — lift, reduced-motion fade, cut fallback`.

### Task 4: Leaving landing and arriving chat (props and CSS)

**Files:**
- Modify: `web/src/features/Landing/index.tsx`:
  - new prop `leaving?: Phase`;
  - the root gets class `is-leaving` when it's `"lift"` and `is-fading` when it's `"fade"`;
  - while either applies, the root gets `attr:inert=""` and `aria-hidden="true"`.
- Modify: `web/src/components/shell/Topbar.tsx`: new prop `entering?: boolean`, which adds class `lt-entering`.
- Modify: `web/src/features/Composer/index.tsx`:
  - new prop `focusOnMount?: boolean`, which focuses the textarea in `onMount` with `{ preventScroll: true }`;
  - new prop `entering?: boolean`, passed down to `ComposeField`.
- Modify: `web/src/components/cards/ComposeField.tsx`: new prop `entering?: boolean`, which adds class `lt-entering` to the wrap (`composer-wrap`).
- Modify: `web/src/Thread/index.tsx`: new prop `arriving?: Phase`, which adds class `lt-arriving` (lift) or `lt-fading` (fade) to `.thread`.
- Modify: `web/src/features/LandingTransition/landingTransition.css`. Every rule is scoped to the classes above; nothing applies when they're absent:
  - **`.landing.is-leaving`:**
    - `position: absolute; inset: 0; z-index: 40; pointer-events: none`. `.main` is already `position: relative`, at `styles.css:239`.
    - `.landing-input-wrap` gets `visibility: hidden`.
    - Two animations per piece of furniture: `lt-out` (opacity 1→0, `calc(var(--lt-d)*.45)`, `ease`, `both`) and `lt-drift` (`translate: 0 var(--lt-dy)`, `scale: var(--lt-scale, 1)`, `calc(var(--lt-d)*.7)`, `var(--lt-ease)`, `both`). Use the individual `translate`/`scale` properties so the two don't fight.
    - Per element: `.landing-monogram-wrap` (`--lt-dy: -18px; --lt-scale: .96`), `.landing-modes` and `.landing-modes-aside` (`--lt-dy: 28px`), `.landing-atlas` (`--lt-dy: 44px`), `.landing-header` (`--lt-dy: 0`).
  - **Mobile.** In `@media (max-width: 768px)`, inside the same file, the atlas sits above the owl. Give `.landing-atlas` `--lt-dy: -28px` and `.landing-header` `--lt-dy: -12px`.
  - **`.landing.is-fading`:** the same layer rules, plus `lt-out` over `180ms` on the whole root and no drift.
  - **`.lt-arriving`:**
    - `.turn-user` gets `animation: none`, which suppresses `fade-in`.
    - The first turn's `.turn-user-inner .turn-body` gets `visibility: hidden`.
    - `.turn-meta` gets `lt-in` (opacity 0→1) over `240ms`, delayed `calc(var(--lt-d)*.8)`, `both`.
    - The thinking row gets `lt-in` over `calc(var(--lt-d)*.3)`, delayed `calc(var(--lt-d)*.5)`, `both`. Select it as **`.thread.lt-arriving > .turn-minerva`**: the thinking row is a direct child of `.thread`, while reply turns sit inside `div[data-turn-id]`. A reply that streams in mid-flight must not pick up the delay, because that would hold reply text back, which is an anti-goal.
  - **`.topbar.lt-entering`:** `lt-in`, plus `translate` from `0 -6px` to none, over `calc(var(--lt-d)*.4)`, delayed `calc(var(--lt-d)*.55)`, `both`.
  - **`.landing.is-leaving` background:** confirm the `.landing` root paints no background, so the chat underneath shows through the fading layer. If it does paint one, set `background: transparent` here.
  - **`.composer-wrap.lt-entering`:**
    - `z-index: 45`, so the descending box passes *over* the fading mode row. The wrap is `position: sticky`, so `z-index` applies.
    - `.composer-foot` gets `lt-in` over `calc(var(--lt-d)*.35)`, delayed `calc(var(--lt-d)*.5)`, `both`;
    - `.composer-input::placeholder` gets `color: transparent`. It switches back when the class drops at the end; that's a cut, which the spec allows.
  - **`.lt-fading`, `.topbar.lt-entering` (fade) and `.composer-wrap.lt-entering` (fade):** only `lt-in` over 180ms. In fade the controller still sets `--lt-d`, so either reuse `--lt-d` with a literal `180ms` or add a `.lt-fade` variant; pick one and keep it consistent.
  - **`@media (prefers-reduced-motion: reduce)`:** strip every `lt-drift` and `translate`, as a belt-and-braces guard. The controller already picks fade.
- Test: `web/tests/Landing.test.tsx`, `web/tests/Topbar.test.tsx`, `web/tests/Composer.test.tsx` (extend); `web/tests/ThreadArriving.test.tsx` (create)

**Interfaces:**
- Consumes: `Phase` from Task 3.
- Produces these props, which Task 5 passes:
  - `Landing.leaving`
  - `Topbar.entering`
  - `Composer.focusOnMount`
  - `Composer.entering`
  - `Thread.arriving`

- [ ] **Step 1: Write the failing tests.**
  - Landing with `leaving="lift"`: the root has `is-leaving` and the attribute `inert`. With `"fade"`: it has `is-fading`. With no prop: neither, and no `inert`.
  - Topbar with `entering`: the class is `lt-entering`.
  - Composer with `focusOnMount`: `document.activeElement` is its textarea after render. Without it, focus is not moved.
  - Composer with `entering`: `.composer-wrap` has `lt-entering`.
  - Thread with `arriving="lift"`: `.thread` has `lt-arriving`; with `"fade"`, `lt-fading`.
- [ ] **Step 2: Run them.** Command: `cd web && npx vitest run tests/Landing.test.tsx tests/Topbar.test.tsx tests/Composer.test.tsx tests/ThreadArriving.test.tsx`. Expected: the new cases FAIL.
- [ ] **Step 3: Implement** the props and the CSS.
- [ ] **Step 4: Run them.** Expected: PASS, with the existing cases in those files still passing.
- [ ] **Step 5: Commit.** Message: `feat(landing): leaving/arriving states for the landing → chat transition`.

### Task 5: Wire it into ChatRoute, plus the browser specs

**Files:**
- Modify: `web/src/routes/ChatRoute.tsx`
- Test: `web/tests/browser/landingTransition.spec.ts` (extend)

**Interfaces:**
- Consumes:
  - `createLandingTransition` and `Phase` (Task 3);
  - the Task 4 props;
  - `props.conversations.startFromLanding` and `showLanding`.

ChatRoute decisions:
- Create `const transition = createLandingTransition()` once per ChatRoute instance.
- Replace the single `<Show when={showLanding()} fallback={chat}>` with two siblings:
  - chat under `<Show when={!showLanding()}>`, which already guards the Topbar;
  - the landing under `<Show when={showLanding() || transition.phase() !== "idle"}>`.
  
  Keep the chat markup first and the landing second in the DOM, so the leaving layer paints on top.
- Landing `onSubmit={(text) => transition.begin(text, props.conversations.startFromLanding)}`. Landing `leaving={showLanding() ? undefined : transition.phase()}`.
- Chat parts:
  - `Topbar entering={transition.phase() !== "idle"}`
  - `Thread arriving={transition.phase()}`
  - `Composer entering={transition.phase() !== "idle"}`
  - `Composer focusOnMount={fromLanding}`. `fromLanding` is a plain `let`, not a signal. The landing's `onSubmit` sets it to `true`, calls `transition.begin(...)` and sets it back to `false`. The chat branch, and so the Composer, is created synchronously inside `send`, so the Composer reads `true` at creation in every mode, including the cut. Sidebar picks and direct loads read `false` and don't steal focus.
- Add a `createEffect` that calls `transition.cancel()` when `showLanding()` is true and the phase isn't `idle` (New question mid-flight), and an `onCleanup(transition.cancel)`.

- [ ] **Step 1: Write the failing Playwright specs** in `landingTransition.spec.ts`. Use viewport 1440×900, `page.route("**/api/chat", () => {})` unless a test says otherwise, and submit with Enter from the landing textarea.
  - **"lifts the question into the first turn":**
    - right after Enter, `.lift-ghost` is attached and has the question text;
    - `.landing.is-leaving` is attached;
    - the textarea with placeholder "Continue the enquiry…" is focused;
    - then `.lift-ghost` is detached within 1500ms;
    - `.landing` is detached;
    - `.turn-user-inner .turn-body` is visible with the question text;
    - `document.documentElement.style.getPropertyValue("--lt-d")` is `""`.
  - **"reduced motion crossfades":** a context with `reducedMotion: "reduce"`. `.lift-ghost` never attaches; check this with a `MutationObserver` installed via `page.addInitScript` that records any `.lift-ghost` insertion. `.landing` is detached within 600ms, and the question is visible.
  - **"long question":** a question of 12 lines joined by `\n` (Shift+Enter or `fill`). The ghost text equals the full trimmed question. After landing, the body's `innerText` equals the full question.
  - **"type during flight":** right after Enter, `page.keyboard.type("and Kant?")`. After the ghost detaches, the chat composer's value is `"and Kant?"`.
  - **"new question mid-flight":**
    - after Enter, wait 100ms and click the sidebar's "New question" control (the one that calls `newConversation`; find its accessible name in `features/Sidebar/index.tsx`);
    - `.lift-ghost` count is 0;
    - `.landing` is visible without `is-leaving`;
    - `--lt-d` is `""`.
  - **"fast server":**
    - fulfil `/api/chat` at once, with `content-type: text/event-stream` and a body containing an `event: meta` block (`conversation_id: "c-e2e"`, `title: "Owl"`, `citations: []`, `abstained: false`, `backend: "test"`) and one `event: delta` block. Match the data shapes the parser expects at `src/api/chatApi.ts:160–185`;
    - the ghost is inserted exactly once (count insertions with the same `MutationObserver`);
    - the delta text is visible *before* the ghost detaches (reply text isn't held back);
    - the URL hash ends with `c-e2e`;
    - the delta text is visible.
- [ ] **Step 2: Run them.** Command: `make test-browser`. Expected: the new tests FAIL; Task 1's test and the existing specs pass.
- [ ] **Step 3: Implement the ChatRoute wiring.**
- [ ] **Step 4: Run them.** Command: `make test-browser`. Expected: all PASS. A flaky result is a defect, because `retries` is 0 by policy (see `playwright.config.ts`). Fix the cause: wait on DOM state, never on sleeps, except the deliberate 100ms in "new question mid-flight".
- [ ] **Step 5: Commit.** Message: `feat(landing): animate the landing → chat transition on Begin`.

### Task 6: Verify against the prototype and open the PR

- [ ] **Step 1: Run `make check`** in the worktree and read the output. Every gate should be green, including `check-diff-coverage`. If it's red, fix and re-run; per CLAUDE.md, re-run after *any* edit.
- [ ] **Step 2: Look at it.** Start the dev server with `preview_start` (add a `.claude/launch.json` entry if there isn't one) and play the transition at:
  - 1440×900, light and dark;
  - 1180×800 (below 1280px, where the box doesn't widen);
  - 375×812 (mobile; the question lands as the right-aligned bubble).
  
  Compare each against the prototype (https://claude.ai/artifact/9ncmqZZtnib3WrKGQaP7aM) at the same duration. Take a screenshot at about 0.5D (temporarily set `--lt-d` to 5000ms from DevTools to catch the mid-flight frame) and the end state for the PR.
- [ ] **Step 3: Record what you find.** Per CLAUDE.md, anything noticed and not fixed gets a GitHub issue with `## Measured` and `## Hypothesis`. Known candidates:
  - the cut fallback is untested in a real browser, because Chromium always has `animate`;
  - "Request timing" aside behaviour on mobile, if it looks wrong.
- [ ] **Step 4: Push and open the PR against `main`.**
  - There is no tracked issue for this feature, so either file one first and put `Closes #N` in the PR body, or write that there's no issue.
  - Run `make check-pr-link PR=<n> ISSUES="<n>"` if an issue exists.
  - The body names the spec and plan paths, links the prototype (private: say so), and lists what was deliberately left out: the chatbox redesign and the reverse animation.
