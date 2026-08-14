// "Is the subtree I am in currently suspended?" — for listeners bound to
// `window` or `document`, which no DOM attribute can reach (#352).
//
// #342 and then #348 made "mounted but not on screen" a normal state: the
// Reader now survives a step-out to the syntax layer and to the concordance
// instead of being destroyed on the way out. Before that, a Reader that left
// the route took every listener in its subtree with it, so the question never
// arose. `hidden` and `inert` govern painting, focus and pointer events; they
// do nothing about a handler registered on `window`.
//
// #348 threaded a `suspended` prop by hand to the two listeners whose misfire
// it had measured. That does not scale — it protects the listeners someone
// remembered, and the Reader's card subtree binds four more. This context is
// the part that generalises: a hook consults it and registers nothing while
// its subtree is suspended, including hooks added later.
//
// SCOPE, which is the whole reason a context works here rather than a global
// flag: the value is provided around the Reader subtree only, so
// `useContext` answers "am I inside the suspended subtree?" and not "does the
// app have a suspended subtree somewhere?". Everything outside — the
// concordance's own `Select`, its `useListKeyboardNav`, every hook on a
// destination route — reads the default and stays live. That distinction is
// what #352 flagged as the hard part of this approach; provider placement is
// what supplies it.
//
// Deliberately NOT consulted by `useClickOutside`. That hook is genuinely
// shared with a surface that must stay live while the Reader is suspended
// (`components/Select.tsx`, rendered by the concordance's own FilterBar), and
// keeping it out of the context makes `Select` provably unaffected no matter
// where a future provider lands. Its popover caller folds the flag into the
// `isActive` accessor the hook already takes instead — `useTermCard` did until
// #356 moved the listener to the shell both cards share, and
// `components/PopoverCard.tsx` does now, by reading this context directly.

import { createContext, useContext, type Accessor, type JSX } from "solid-js";

/** Default `false`: a subtree with no provider above it is never suspended,
 *  which is the correct answer for every route that is actually on screen. */
const SuspendedSubtreeContext = createContext<Accessor<boolean>>(() => false);

export function SuspendedSubtreeProvider(props: {
  suspended: Accessor<boolean>;
  children: JSX.Element;
}): JSX.Element {
  // Wrapped rather than passed through so the provider's value is a stable
  // reference while the accessor stays reactive.
  return (
    <SuspendedSubtreeContext.Provider value={() => props.suspended()}>
      {props.children}
    </SuspendedSubtreeContext.Provider>
  );
}

/** True while the calling component's subtree is mounted but stepped out of.
 *  Read it inside a tracking scope — it is an accessor, not a boolean. */
export function useSuspendedSubtree(): Accessor<boolean> {
  return useContext(SuspendedSubtreeContext);
}
