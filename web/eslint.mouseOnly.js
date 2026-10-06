// A lint rule for controls only a mouse can reach (#773).
//
// Matches the `onClick` attribute of a lowercase (intrinsic) JSX element that
// is not natively interactive and carries none of `role`, `tabindex`/`tabIndex`
// or `href`. Such an element is not in the tab order and has no keyboard
// activation, so the action it carries is unreachable without a pointer. This
// is what the issue's AST sweep counted: 35 in `web/src` before #726, 23 after.
//
// `eslint-plugin-jsx-a11y` would be the usual answer, but it targets React's
// attribute names and is unverified against Solid's (`class`, lowercase
// `tabindex`), so the rule here is a selector rather than a dependency.
//
// A site that is mouse-only on purpose, because the same action has a keyboard
// path elsewhere or because the click only dismisses something, carries
// `// eslint-disable-next-line minerva/no-mouse-only-click -- <the keyboard path>`
// above its `onClick`. The report lands on the attribute for that reason.
//
// A rule of its own rather than a `no-restricted-syntax` entry: the config
// already uses that key for the SFC-migration guard, and flat config lets a
// later block replace an earlier block's options for the same key outright, so
// the two would silently disable each other on any file both matched.
//
// Kept out of eslint.config.js so tests/mouseOnlyControls.test.ts can pin the
// selector's edges: a selector that is merely wrong reports nothing at all.

const NATIVELY_INTERACTIVE = ["button", "input", "select", "textarea", "option", "summary"];

export const MOUSE_ONLY_SELECTOR =
  "JSXOpeningElement[name.type='JSXIdentifier']" +
  `[name.name=/^(?!(?:${NATIVELY_INTERACTIVE.join("|")})$)[a-z]/]` +
  ":not(:has(JSXAttribute[name.name=/^(?:role|tabindex|tabIndex|href)$/]))" +
  " > JSXAttribute[name.name='onClick']";

export const MOUSE_ONLY_MESSAGE =
  'onClick on a non-interactive element is mouse-only (#773). Use <button type="button">, ' +
  "or role + tabindex + a key handler; if a keyboard path to the same action exists " +
  "elsewhere, disable this line and name that path.";

/** @type {import("eslint").ESLint.Plugin} */
export const minervaPlugin = {
  rules: {
    "no-mouse-only-click": {
      meta: {
        type: "problem",
        docs: { description: "Disallow onClick on an element no keyboard can reach (#773)." },
        messages: { mouseOnly: MOUSE_ONLY_MESSAGE },
        schema: [],
      },
      create(context) {
        return {
          [MOUSE_ONLY_SELECTOR](node) {
            context.report({ node, messageId: "mouseOnly" });
          },
        };
      },
    },
  },
};
