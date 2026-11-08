# Composer redesign — one weighted composer, views in a shared top bar

Date: 2026-11-07
Mock: Claude Design canvas "Minerva composer",
<https://claude.ai/artifact/GnQKPhukfbExzueX2ixSop> — row **A** (`A-Landing`,
`A-Chat`) is the chosen direction; the "Today" row is the baseline. Rows B
and C are rejected alternatives, kept for reference.

Markers used below: **(decided)** = the user's call in the design session;
**(my call)** = chosen while mocking, open to the builder or the user;
**(builder)** = left to whoever implements it.

## Why

The landing page has too much going on: owl, composer, a four-cell
destination row, a separate "Request timing" link, and the Atlas timeline.
And the **composer itself feels thin and dangles** — on the landing *and* on
the chat screen it reads as a strip hanging off the page rather than the
thing the page is for. **(decided)**

The goal is a composer with enough weight that it is clearly the primary
object on both screens, and a landing page that is little more than that
composer.

## Goals

1. **One composer, the same object on both screens.** Landing and chat use
   the same visual treatment (card, type size, footer row, button), differing
   only in height and labels. **(decided — option A)**
2. **The composer has weight.** Larger serif input, multi-line resting
   height, a raised card, a filled primary button. **(decided — option A)**
3. **The four views leave the landing body** and move to a top bar shared by
   the landing and the chat screens: Ask · Read · Citations · Network ·
   Concordance, with "Ask" as the current view. **(decided — option A)**
4. **The primary button is not black in light theme.** **(decided)** It uses
   the accent: light `--accent` `#7b2e2a` with `--paper` text (≈9:1). **(my
   call)**
5. **Every screen shares the top bar** — Reader, Refs, Network, Concordance
   and Metrics as well as landing and chat — so the nav works as tabs, with
   the current view marked wherever you are. **(decided)**
6. **Phones too.** Option A applies on mobile; there the five views live in
   the existing mobile menu drawer rather than a horizontal bar. **(decided)**
7. **The Atlas leaves the landing page but is kept**, moved to another
   screen. **(decided)** Which screen is still open — see Open questions.

## Non-goals

- Restyling the conversation thread, margin notes, or the sidebar.
- Changing what Begin/Send *do*, the composer's keyboard behaviour, autosize
  limits' purpose, or the work-scope picker's behaviour (only its placement
  and chip styling change — see below).
- Redesigning the *content* of the Reader, Refs, Network, Concordance or
  Metrics screens. They gain the shared top bar (goal 5) and, for one of
  them, the Atlas (goal 7); nothing else on them changes.

## Anti-goals (would make this a failure even if it works)

- The landing → chat Begin transition (#855) regressing to a jump or a cut.
  The redesign should make it *simpler*, not break it.
- Two composers that look alike in the mock but drift in code — the point is
  one treatment, so it must live in one place (`ComposeField` + shared CSS),
  not two hand-matched stylesheets.
- New colours that only work in light theme. The repo has both themes; the
  mocks are light-only.

## What changes

### Landing (`web/src/features/Landing/`)

Layout, top to bottom (see `A-Landing`):

- **Top bar** (the shared one, below).
- **Centred hero**, vertically centred in the remaining space:
  - Owl monogram, smaller than today (mock: 64px vs 76px), epigraph popover
    unchanged. The ~1-in-5 rose-cross variant stays. **(my call)**
  - **Composer card**, 720px wide in the mock (today 680px). **(my call —
    builder may tie it to `--col`)**
  - **One caption line** under the card, serif italic, `--ink-mute`: "Ask
    about a passage, a work, or an author — 48 authors, N works, N
    cross-references", the numbers from the existing `fetchLandingStats()`.
    **(my call)**
- **Removed:** the `.landing-modes` four-cell row, the `.landing-modes-aside`
  "Request timing" link, and the `<Atlas>` strip. The Atlas is **moved, not
  deleted** (goal 7): it leaves the landing in the same PR that lands it on
  its new screen, so there is never a build without it.

`Landing`'s `onOpenRead / onOpenRefs / onOpenNetwork / onOpenConcordance /
onOpenMetrics` props move to the top bar's wiring.

### Chat (`web/src/routes/ChatRoute.tsx`, `web/src/features/Composer/`)

- **Top bar** replaces today's `Topbar` content (below).
- The conversation title, which today sits in the top bar, moves to a small
  serif-italic line at the head of the thread column (mock: 13px,
  `--ink-mute`). **(my call)**
- **Composer card** docked at the bottom as today (sticky, gradient fade
  above it), now the same card as the landing: 2-line resting height instead
  of 1, otherwise identical.

### The composer card (`ComposeField`, shared CSS)

Measured from the mock (`A-Landing` / `A-Chat`):

| Property | Today (landing / chat) | New (both) |
|---|---|---|
| Background | `--paper` | new token, raised paper: light `#fbf8f2` |
| Border | 1px `--rule`, radius 0 / 4px | 1px `--rule`, radius 10px |
| Shadow | none | `0 1px 0 --paper-edge, 0 16px 40px rgb(26 23 20 / 8%)` |
| Input font | serif 17px italic / serif 18px | serif 21px (landing), 19px (chat), roman |
| Resting height | 1 line | landing 3 lines (~104px), chat 2 lines (~64px) |
| Input padding | 12px 16px / 14px 16px | 20px 22px 8px (landing), 16px 22px 4px (chat) |
| Footer | hint + text "Begin →" / dotted rule, hint + outlined pill | no rule; left: scope pill + hint; right: filled button |
| Primary button | text link / outlined ink pill | filled accent pill, 40px tall, 13.5px sans, `--paper` text |

- **Placeholder copy stays**: "What would you like to consider?" /
  "Continue the enquiry…" (mobile "Reply to Minerva…"). Roman, not italic, in
  the mock. **(my call)**
- **Scope moves inside the card and always shows.** Today the
  `WorkScopeControl` chip sits *above* the box (chat always; landing only
  when a scope is set, #350). In A it is a pill in the footer reading "All
  works ▾", or the work's title when scoped, on both screens — **including
  the cold landing (decided)**, which deliberately reverses #350's "cold
  landing stays uncluttered" rule. Consequence for the return transition
  (`returnController.ts`): "New conversation" clears the scope on arrival,
  and today the chip is hidden while returning so it cannot pop out at the
  end. With an always-present pill, its label changes from the work title to
  "All works" instead; the builder decides when in the return that swap
  happens so it doesn't flicker.
- Focus state: keep a visible focus ring on the card (today
  `.composer:focus-within { border-color: var(--ink) }`). **(builder)**
- Disabled/"Awaiting reply…" state keeps today's behaviour; the filled button
  needs a disabled style that still reads as disabled on the accent.
  **(builder)**

### The shared top bar

`A-Landing` and `A-Chat` show the same bar, 60px tall, hairline
`--rule-soft` bottom border:

- **Left: a nav of five links** — Ask · Read · Citations · Network ·
  Concordance — 13px sans. The current view is `--ink`, weight 500, with a
  2px `--accent` underline; the rest `--ink-soft`. It is a `<nav
  aria-label="Views">` of real links/buttons; the current one carries
  `aria-current="page"`.
- **"Ask"** goes to the current conversation, or the landing if there is
  none. Clicked while already in Ask it does nothing — it never starts a new
  conversation, so it needs none of Escape's guards (`chatIsSettled`,
  `wouldDropInput`). "+ New question" in the sidebar stays the way to start
  fresh. **(my call)**
- **The bar is one instance that stays still** through the Begin and return
  transitions: it sits outside the landing's leaving/arriving layers and
  does not fade. Today's late fade-in of the chat `Topbar` (`lt-entering`)
  and the landing's own header both go. **(my call — the #855 transition
  spec is updated in the same PR.)**
- **On every screen** (goal 5). Each screen's existing header controls that
  are not views (e.g. the Reader's own toolbar) stay where they are, below
  the bar; the builder reconciles any duplicated theme toggle.
- **Right:** "Timing" (→ `#/metrics`, replacing the landing's "Request
  timing" link) and the existing `ThemeToggle`. Small-caps labels as today.
- The sidebar-collapse button that `Topbar` shows when the sidebar is
  collapsed stays, at the far left. **(builder)**
- Where the bar lives — extending `Topbar` vs a new shared component that the
  landing header also renders — is **(builder)**, with the constraint that
  the landing and chat bars are the same component.

### Dark theme

The mocks are light-only. Dark values, **(my call)** — each must be
contrast-measured on dark `--paper` `#14110e` before shipping, as #600 did:

- Raised paper: a step lighter than `--paper` (e.g. `#1b1713`); builder
  derives and measures.
- Primary button: dark `--accent` `#c97a65` with **dark** text (`--paper`),
  since parchment text on terracotta is weaker than ink-on-terracotta.
- Card shadow: likely drop to the hairline only; a 40px blur on near-black
  reads as a smudge.

### The landing → chat transition (#855)

`web/src/features/LandingTransition/controller.ts` FLIPs the landing
composer box into the chat composer. Today the two boxes differ in width,
padding, border radius and font size, so the FLIP scales between unlike
shapes. After this change they are the same card at different heights, so
the lift becomes mostly a translate plus a height change. The ghost-question
text (`.lift-ghost`) must be retuned to the new font sizes (21px → 19px)
rather than today's 17px italic → 18px roman. The landing's leaving layer
loses the modes row and the Atlas, so their fade-out rules in
`landingTransition.css` go too. Spec of record for the transition:
`docs/superpowers/specs/2026-11-06-landing-chat-transition-design.md`.

## Constraints

- **Tests that name what is being removed:** `tests/Landing.test.tsx`,
  `tests/Atlas.test.tsx`, `tests/keyboardReachableControls.test.tsx`,
  `tests/readerEscape.test.tsx`, `tests/browser/focusRing.spec.ts`. Each
  must be updated to the new structure rather than deleted wholesale where
  it guards behaviour that survives (keyboard reachability, focus ring,
  Escape-to-landing).
- `src/data/atlasData.ts` and `src/utils/atlasGeometry.ts` are also used by
  `Network/components/NetworkArc.tsx`. Removing the landing Atlas must not
  remove them. `atlasData` is generated from `data/authors/manifest.yaml`;
  never hand-edit it.
- Frontend tests live in `web/tests/`, not colocated (Sonar gate).
- Sonar: ≤3% duplication on new code, so the composer card is one
  implementation, not a landing copy plus a chat copy.
- `make check` includes the e2e and Playwright browser suites; visual checks
  use the browser-suite fixture server, not `make run`.

### Mobile (goal 6)

- The composer card applies as on desktop, scaled for the phone (builder
  sets sizes; the mock is desktop-only).
- The landing drops the Atlas and the 2×2 views grid (`styles/mobile.css`).
- The five views plus Timing go in the existing mobile menu drawer, with the
  current one marked. `MobileTopBar` today returns no config while
  `showLanding()` is true; the landing needs a way to open the drawer.
  **(builder decides the affordance)**

## Delivery: a series, not one PR

Goals 5–7 make this several changes. Suggested order **(my call)**, each
independently shippable:

1. **Composer card** on landing and chat, scope pill inside, accent button,
   transition retuned. Desktop and mobile.
2. **Shared top bar on landing and chat**; landing modes row and "Request
   timing" link removed; bar held still through the transition.
3. **Top bar on Reader, Refs, Network, Concordance, Metrics.**
4. **Mobile drawer nav** for the views.
5. **Atlas moved** to its new screen and removed from the landing, together.

Until step 5 lands, the Atlas stays on the landing below the composer.

## Open question

1. **Where does the Atlas go?** Read (as a way into the authors) or Network
   (which already draws from the same `atlasData`) are the obvious homes.
   Only step 5 depends on this; steps 1–4 can be planned and built without
   it.
