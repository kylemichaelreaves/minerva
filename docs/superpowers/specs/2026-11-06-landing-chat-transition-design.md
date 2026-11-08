# Landing → Chat transition — design

Status: draft for approval · 2026-11-06
Prototype (Claude Design, private to the owner):
https://claude.ai/artifact/9ncmqZZtnib3WrKGQaP7aM — press **Begin**; the
Tweaks panel has duration, easing, reduced motion and theme.

## Intent

Pressing **Begin** on the landing currently hard-cuts to the conversation:
`ChatRoute` unmounts `<Landing>` and mounts the topbar, thread and bottom
composer in one frame. The question you just typed vanishes and reappears
somewhere else, and the landing's furniture disappears with no sense of
where you went.

The transition should make the move legible: **the chatbox you typed into is
the same chatbox you keep talking in, and the question you asked is the
first thing on the page.** The approved prototype is the reference for feel
and choreography; this document is the reference for everything the
prototype cannot say.

## Goals

1. **The chatbox travels.** The landing composer box moves from its centred
   position to the chat composer's position at the bottom of the column,
   widening to the column width on the way. It reads as one object, not a
   fade between two.
2. **The question lifts out.** The submitted text leaves the box and settles
   as the first user turn at the top of the thread, growing from the
   landing's 17px italic to the user turn's 18px italic. The user turn's
   left rule (`2px solid var(--ink)`) draws in as it lands, and the turn's
   meta label appears after it.
3. **The landing clears out of the way.** The owl, the mode row (and the
   Request-timing aside), and the atlas fade out in the first half of the
   movement, with a small drift (owl up, everything below it down) — not a
   slide off-screen.
4. **Chat furniture arrives late.** The topbar fades in during the second
   half; the composer's footer and placeholder switch from the landing
   copy (`↵ begin`, *Begin →*, "What would you like to consider?") to the
   chat copy (`Enter send`, *Send*, "Continue the enquiry…" /
   "Reply to Minerva…" on mobile) partway through. (As built since the
   composer card, the footer does not fade: it has the same shape on both
   ends and rides in the box, so its copy is the chat's from the swap; only
   the placeholder is held transparent until the flight ends.)
5. **No added latency.** The request to the server goes out the moment
   Begin is pressed, exactly as today (`startFromLanding` →
   `askMinerva`). "considering…" and the streamed reply render whenever
   they arrive; the animation never holds them back, and they never cut the
   animation short.

Approved timing: **~650ms total, a "settle" curve
(`cubic-bezier(.2,.7,.1,1)`)** — fast start, soft landing. Within that:
landing furniture fades over the first ~45%; the topbar fades in from
~55%; the user-turn rule draws in over the last ~35%. (The prototype also
faded the chat footer in from ~50%; as built since the composer card, both
footers have the same shape, scope pill included, and the footer rides in
the box instead — see the composer-card addendum below.)

### The prototype's choreography, in numbers

The prototype is private, so these are its values (D = 650ms, E = the
settle curve); they are the acceptance reference for "feel":

| Element | Moves | Opacity | Timing |
|---|---|---|---|
| Composer box | straight down to the chat composer's slot; widens to it, and takes its height (built: the landing box is 86px for one line and up to 376px for a long question, the composer 109px; #854) | — | top/left/width/height over D, E |
| Question text | from the textarea's text origin straight to the first user turn's body; 17px/1.45 → 18px/1.55, `--ink` → `--ink-soft`; **reflows live as its width changes** (it is real text, not a scaled image) | shown at its origin on frame 0 | over D, E |
| User-turn left rule | — | transparent → `--ink` | 0.35D, starting at 0.65D |
| User-turn meta label | — | 0 → 1 | 0.35D, starting at 0.65D (built; the prototype's "240ms at 0.8D" ends at 1.17D, after the flight, and popped to full opacity when it did — #854) |
| Owl | up 18px, scale .96 | 1 → 0 | opacity 0.45D ease; transform 0.7D E |
| Mode row (+ aside) | down 28px | 1 → 0 | same |
| Atlas | down 44px | 1 → 0 | same |
| Topbar | down from −6px | 0 → 1 | 0.4D, starting at 0.55D |
| Composer footer | rides in the box with the scope pill (built since the composer card; the prototype crossfaded landing → chat copy over 0.35D from 0.5D) | stays visible | with the box |
| Thinking row / Minerva turn | — | 0 → 1 | from ~D (see "Calls made") |

The box and the text cross paths: the text starts inside the box and rises
as the box descends.

## Non-goals

- **Redesigning the chatbox itself.** It was raised at the start of the
  conversation and set aside; the box looks as it does today on both ends.
- **The reverse journey.** "New question" (and any other route back to the
  landing) returns with a short plain fade, not the movement in reverse —
  watching your question fly back into the box reads as undoing, not
  starting over.
- **Other routes into Chat.** Opening a conversation from the sidebar, or
  arriving at `#/c/<id>` directly, keeps today's behaviour. Only the
  landing's Begin/Enter submit animates.
- **The sidebar.** Whether and when the new conversation appears under
  Recent is the sidebar's existing behaviour; this work does not touch it.
- **Changing how Landing and Chat mount** (e.g. hoisting one persistent
  composer above both views). See "How", below.
- **Moving Minerva's replies or the margin notes.** The one layout change
  in scope is the user turn's column (see "How — decided"); replies keep
  their 720px column at the left of the wide thread.

## Anti-goals — it fails even if it "works" if:

- the reply is delayed by the animation, or first tokens arriving
  mid-animation cause a jump, re-layout or restart;
- the question is ever visible twice (in the box *and* the thread), or
  visibly blinks out between them;
- the user can type into a box that is mid-flight and lose what they typed;
- someone with OS-level reduced motion sees anything travel;
- the existing unit, e2e or Playwright suites become flaky because they now
  race an animation.

## Constraints (measured, with where)

- **The swap is synchronous.** `showLanding()` is
  `route().kind === "landing" && messages().length === 0`
  (`features/conversations/conversationsCtrl.ts:84`), and
  `startFromLanding` calls `setMessages([turn])` before `askMinerva`
  (`conversationsCtrl.ts:207–227`). The first user turn is in the DOM in
  the same tick the landing leaves it.
- **The route changes again mid-flight, possibly.** When the stream's meta
  arrives, `applyStreamMeta` navigates to `{kind: "conversation", id}`
  (`features/conversations/conversationsSend.ts:61–64`). On a fast server
  this can land inside the 650ms. `ChatRoute` stays mounted across that
  navigation (it is the `<Switch>` fallback in `AppRoutes.tsx`), so the
  thread should not remount — but the builder must confirm nothing
  restarts.
- **The topbar title is the server's, not the question.** `Topbar` gets
  `conversationTitle()`, which comes from stream meta. It is usually empty
  for the first few hundred ms. The prototype shows the question as the
  title immediately; the real topbar fades in with whatever title it has
  and fills in when the server provides one. (This is a known difference
  from the prototype, not a defect.)
- **Two different composers.** The landing uses `ComposeField
  variant="landing"` with `createComposer({minPx:30,maxPx:320,
  clearOnSend:false})` (`features/Landing/index.tsx`); the chat uses
  `features/Composer/index.tsx` with `{minPx:28,maxPx:180,clearOnSend:true}`.
  Different classes, widths (landing 680px, `landing.css:303`; chat tracks
  `--col`) and footers.
- **A multi-line question.** The landing box grows up to 320px; the user
  turn wraps at the column width. The lift must look right for a long
  question, not just the one-liner in the prototype.
- **Scope chip.** When a work scope is set, a `WorkScopeControl` chip sits
  above the input on both ends (`routes/ChatRoute.tsx`). It should travel
  with the composer. (Since the composer card it is an always-on pill
  inside the box's footer on both ends; see the addendum below.)
- **Reduced motion is a per-file `@media (prefers-reduced-motion: reduce)`
  convention** (`styles/styles.css:360`, `Reader/reader.css:621`, …).
- **Mobile is a different layout** (`styles/mobile.css`: landing at
  ~L349–620; chat has `MobileTopBar` and the "Reply to Minerva…"
  placeholder). Same movement, mobile geometry.
- **Tests.** `tests/Landing.test.tsx` and `tests/conversationsCtrl.test.ts`
  (vitest/jsdom) cover the landing and the handoff; Playwright runs Chromium
  only (`playwright.config.ts`). jsdom has no layout and no View
  Transitions.
- **Repo gates** (CLAUDE.md): ≥80% changed-line coverage *including
  branches*, cognitive complexity ≤15 per function, frontend tests in
  `web/tests/` (not colocated).

## How — decided

- **User turns sit above the composer (the user's decision).** On wide
  screens the chat has three unaligned columns today: the composer is
  centred at `--col` (`features/Composer/composer.css:9`); Minerva's prose
  is capped at `min(--col, 720px)` and pinned left inside
  `.thread.has-margin`, which is `clamp(1100px, 82vw, 1800px)` wide
  (`Thread/thread.css:25–35`); and the user turn has no `.turn-inner`, so
  it spans the whole wide thread (`Thread/components/UserTurnView.tsx:5`).
  **Every user turn** — not only the first — moves into the composer's
  column: `--col` wide, centred in the thread, so its left edge lines up
  with the composer's. The question then lifts straight up, as in the
  prototype. Minerva's replies stay where they are, so on wide screens a
  question is indented (~120px at a 1440px window, read from the CSS, not
  measured) from the reply beneath it; the user accepted that over moving
  the composer. Below 1100px the thread already collapses to one centred
  `--col` column (`styles/styles.css:367`) and nothing changes.
- **Reduced motion:** under `prefers-reduced-motion: reduce`, nothing
  travels; the landing crossfades to chat (~180ms).
- **Back to the landing:** a short plain fade.
- **Technique:** do *not* restructure Landing/Chat mounting. Animate between
  where the elements are before the swap and where they are after it.

  - **The question text** cannot be a snapshot. View Transitions and FLIP
    both scale an *image* of the old element, and the question re-wraps
    between the two ends (the landing wraps at ~648px; the user turn wraps
    at `--col` minus its 20px rule-and-padding, at 18px). So the text
    travels as a **live overlay**: before the swap, measure the textarea's
    text origin and the question; after it, measure the first user turn's
    body; animate a positioned clone of the text between the two rects
    (top/left/width/font-size, so it reflows), hide the real user-turn body
    until the clone lands, then remove the clone. This is what the
    prototype does. Measure the full question, not the textarea's visible
    scroll window — a question over 320px tall is clipped in the textarea.
  - **Everything else** (the box, fades, drift, topbar) may use the
    browser's same-document **View Transitions API**
    (`document.startViewTransition` around the state change, a shared
    `view-transition-name` on the two composer boxes,
    `::view-transition-*` CSS for the rest) or a hand-rolled FLIP on the
    real chat elements. Where View Transitions is missing, fall back to
    today's instant swap. Note that a running view transition swallows
    pointer input but not keystrokes.

  *The technique is the author's call, not the user's; any of these is
  acceptable if the result matches the table above.*

## Calls made (the author's, not the user's — check these)

- **Focus.** Focus moves into the chat composer at the moment of the swap,
  so keystrokes typed during the flight land in the box they will stay in,
  and on mobile the soft keyboard stays up (if it dropped, the viewport
  would grow mid-flight and move the composer's destination). Today focus
  is simply lost after submit: the landing textarea has `autofocus`, the
  chat composer has none, and nothing calls `.focus()`.
- **The thinking row.** `askMinerva` calls `setThinking(true)` in the same
  tick, so the "considering" turn exists from frame 0, under the slot the
  question has not reached yet. It fades in with the late chrome (from
  ~0.5D), not at frame 0. It is an indicator, not the reply; reply *text*
  is never held back — if stream tokens arrive mid-flight they render
  immediately.
- **Existing `fade-in` on `UserTurnView`** (`Thread/components/UserTurnView.tsx:5`)
  is suppressed for the first turn of a landing submit; it would fight the
  lift.
- **Scope pill.** It sits in the footer inside the box on both ends, so it
  rides with the box (superseded the earlier "inside the box on the landing,
  above `.composer` in chat" placement; see the composer-card addendum).
- **Below 1280px**, `--col` is 680px. (This used to be "the same as the
  landing box, so the box does not widen there; it only moves". Since the
  composer card the landing box is `min(720px, 100%)`, so below 1280px the
  box *narrows* to the chat column as it moves — 720 → 680px — and between
  the phone breakpoint and ~1064px, with the sidebar open, it is narrower
  still, sized to the landing's column.)
- **Mobile.** The atlas sits *above* the owl in the mobile layout, and
  `MobileTopBar` replaces the landing header; "owl up, rest down" is
  re-tuned for that order rather than copied.

## Left to the builder

- Exact keyframes and per-element delays, within the timing above.
- Whether the footer/placeholder switch is a crossfade or a cut at the
  midpoint (the prototype crossfades).
- How to make the tests deterministic — e.g. Playwright's
  `reducedMotion: "reduce"` for existing specs, plus one spec that asserts
  the transition starts and ends in the right state.
- Mobile tuning of distances and timing.

## Done looks like

- On desktop Chromium and Safari, Begin plays the prototype's movement:
  one box travelling down, one question lifting up, landing furniture
  fading, topbar arriving late — with no flash, double, or jump.
- Long (multi-line) questions and a set work scope look right.
- On wide screens every user turn's left edge lines up with the
  composer's; replies and margin notes are where they were.
- Reduced motion crossfades; unsupported browsers swap instantly as today.
- The reply's first tokens are never delayed by, nor disturb, the
  animation.
- `make check` green; Sonar's new-code gates green.

## Addendum: the inverse, Escape → landing (2026-11-06)

Escape in a settled chat plays the transition backwards and lands on an
empty landing, the same destination as "New conversation"
(`returnController.ts`, `escapeToLanding.ts`).

- **When.** Only a plain Escape (no modifiers, not repeating, not while
  composing with an IME) that no other surface claimed. Popovers, the scope
  menu, dialogs and sheets claim Escape with `preventDefault()` and mostly
  register after the chat, so the decision waits until dispatch ends and
  then reads `defaultPrevented`. It is ignored while Minerva is considering
  or still streaming (leaving would abort the reply), while a conversation
  hydrates, during either transition, over an unsent draft in the chat
  composer, and while any other field has focus.
- **Choreography** (fractions of D = 650ms). The thread fades out over
  0–.45, the topbar over 0–.35. The composer's footer and scope pill ride
  down inside the box (as built since the composer card; they used to fade
  out over 0–.35).
  The real composer slides down into the landing box (translate,
  `max-width` and `height`, the inverse of the forward FLIP). The landing mounts at
  once as an inert layer and its furniture drifts back from the offsets it
  left by: fade .55–1, drift .3–1. Nothing flies back with the question.
- **The layer is `position: fixed`** at the spot where `.main` starts at
  scroll 0, not `absolute` on `.main`: the document is the scroller (#851), and a
  long chat may be scrolled far down. On arrival the page scrolls to the
  top, where the landing now sits in flow, so nothing jumps.
- **Focus** follows into the landing box on arrival.
- **Reduced motion:** the landing fades in over the chat as the chat
  fades out (180ms). **No WAAPI / nothing to measure:** an instant swap.
- A sidebar pick or New conversation mid-return ends it without
  navigating on top.

## Addendum: frame-level polish (#854, 2026-11-07)

- **The composer FLIP carries height too,** and its translate aligns
  *bottoms*: the composer wrap is pinned to the bottom of the page, so a
  height change moves the box's top. (Aligning tops with a height animation
  put the box 22–268px off on frame 0.) Both directions.
- **The leaving layer keeps the landing's height,** measured in flow before
  the swap (`--lt-leave-h`). As `inset: 0` alone it took `.main`'s post-swap
  height and a landing taller than the viewport reflowed on frame 0.
- **A resize or a theme change mid-flight cuts** to the landed chat. The
  flight's ends are measured once, in px and computed colours.
- **A scoped landing's chip travels:** the chat's chip starts on the
  landing's (inside the box, painted over it) and slides to its place above
  the composer. An unscoped landing still fades the chat's "scope to a work"
  control in from 0.5D. *(Superseded by the composer card: the pill rides
  inside the box — see the addendum below.)*
- **Phone:** the composer wrap's top rule fades in with the footer, and out
  with it on the return, instead of travelling as a full-width hairline.

## Addendum: the pill rides inside the box (composer card, 2026-11-07)

The composer card gave the landing and the chat one footer shape, with the
scope control as an always-on pill in it ("All works" unscoped, the work's
title scoped). That replaces the chip choreography above:

- **The pill rides inside the box.** It sits in `.compose-foot` on both
  ends, so it moves with the composer's `max-width`/`height` FLIP and the
  wrap's translate. It has no animation of its own: the old separate chip
  leg offset it twice once it lived in the box (`composerKeyframes` returns
  only `wrap` and `box`).
- **The footer stays visible** through the lift and the return; there is no
  footer or chip fade. Only the placeholder still goes transparent while the
  ghost leaves through the box.
- **Both pills read "All works" for the whole return.** "New conversation"
  clears the scope on arrival, so showing the scoped title on the way would
  flip at the end. That goes for the chat composer's pill above all: it is
  the one the user sees travel, since the landing box is hidden throughout
  (`.landing.is-arriving .landing-input-wrap`). One accessor in
  `ChatRoute.tsx` (`shownScope`) feeds both.
- **The return cuts the copy at the end,** as the lift cuts it at the start.
  What travels is the chat composer, so it carries the chat's copy (*Send*,
  `Enter send` / `⇧ Enter new line`) all the way down; the landing's
  (*Begin*, `↵ begin` / `⇧ ↵ new line`, its placeholder) appears in one frame
  when the chat unmounts and the landing box takes its place. There is no
  crossfade in either direction.
