// ESLint v9 flat config. Strict baseline: typescript-eslint's
// `strictTypeChecked` (semantic rules that require the type-checker)
// plus the Solid plugin for JSX-reactivity gotchas, and the Prettier
// config last to disable any formatting rules we'd let Prettier handle.
import js from "@eslint/js";
import solid from "eslint-plugin-solid/configs/typescript";
import prettier from "eslint-config-prettier";
import globals from "globals";
import tseslint from "typescript-eslint";
import { minervaPlugin } from "./eslint.mouseOnly.js";

export default tseslint.config(
  {
    ignores: [
      "dist/**",
      "coverage/**",
      "node_modules/**",
      "vite.config.ts.*",
      "eslint.config.js",
      // Imported by this config and outside tsconfig, so like this file it
      // cannot be type-check linted. tests/mouseOnlyControls.test.ts covers it.
      "eslint.mouseOnly.js",
      "eslint.mouseOnly.d.ts",
    ],
  },
  js.configs.recommended,
  ...tseslint.configs.strictTypeChecked,
  ...tseslint.configs.stylisticTypeChecked,
  {
    files: [
      "src/**/*.{ts,tsx}",
      "tests/**/*.{ts,tsx}",
      "scripts/**/*.ts",
      ".storybook/**/*.{ts,tsx}",
      "vite.config.ts",
      "playwright.config.ts",
    ],
    languageOptions: {
      parserOptions: {
        project: "./tsconfig.json",
        tsconfigRootDir: import.meta.dirname,
      },
      globals: {
        ...globals.browser,
        ...globals.node,
      },
    },
    ...solid,
    rules: {
      ...(solid.rules ?? {}),
      // Allow numbers/booleans in template literals — `${count}` and
      // `${flag}` are universally readable; the rule's intent (catch
      // `${someObject}` rendering as `[object Object]`) is preserved
      // because objects/arrays still trip it.
      "@typescript-eslint/restrict-template-expressions": [
        "error",
        { allowNumber: true, allowBoolean: true },
      ],
      // Non-null assertions (`x!`) are sometimes the cleanest way to
      // express invariants the type-checker can't infer (post-length-
      // check array access, established refs in onMount, etc.). Keep
      // it as a hint rather than an error.
      "@typescript-eslint/no-non-null-assertion": "warn",
      // `bool || expr` is semantically the right choice for boolean
      // fallbacks; `bool ?? expr` only triggers on null/undefined.
      // Tell the rule to skip boolean operands.
      "@typescript-eslint/prefer-nullish-coalescing": [
        "error",
        { ignorePrimitives: { boolean: true } },
      ],
      // `_` is the conventional name for a deliberately-unused param /
      // catch variable. Let the linter recognize that.
      "@typescript-eslint/no-unused-vars": [
        "error",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_", caughtErrorsIgnorePattern: "^_" },
      ],
      // Allow `onClick={() => fn()}` — the canonical Solid pattern for
      // wrapping an event handler. The rule's real target is the
      // genuinely confusing case (`const x = (() => sideEffect())()`,
      // which makes `x` undefined) — non-arrow void returns still trip
      // it, so the footgun is preserved.
      "@typescript-eslint/no-confusing-void-expression": ["error", { ignoreArrowShorthand: true }],
      // Playwright's fixture-override signature is `({}, use) => {}` —
      // the empty pattern is the destructured-fixtures parameter, required
      // by the shape even when an override needs none of them. This option
      // exists specifically for that idiom.
      "no-empty-pattern": ["error", { allowObjectPatternsAsParameters: true }],
    },
  },
  // SFC migration: forbid new hooks/*.ts and utils/*.ts under feature surfaces.
  //
  // Matched structurally, not by enumerating the surfaces. The previous
  // version listed twelve globs naming six directories by hand, and four of
  // them went dead the moment `Refs/` and `Landing/` moved under `features/`
  // — a guard that reports zero errors because there is nothing left at the
  // paths it names (#477). Three more surfaces under `features/`, and
  // `Syntax/`, had never been named at all.
  //
  // `src/hooks/` and `src/utils/` are the two exceptions: top-level shared
  // infrastructure, which the convention puts there on purpose, rather than
  // feature subtrees. `src/Syntax/` needs no exception — its subtrees are
  // named `conllu`, `layout`, `corrections` and `components`, which is
  // precisely what clears this rule (docs/FRONTEND.md).
  {
    files: ["src/**/hooks/**/*.ts", "src/**/utils/**/*.ts"],
    ignores: ["src/hooks/**", "src/utils/**"],
    rules: {
      "no-restricted-syntax": [
        "error",
        {
          selector: "Program",
          message:
            "Use SFC .tsx colocation — do not add hooks/*.ts or utils/*.ts under feature surfaces (see docs/FRONTEND.md).",
        },
      ],
    },
  },
  // Mouse-only controls (#773): see eslint.mouseOnly.js for the selector and
  // for how a deliberate exception is written. Stories are left out, as they
  // were from the sweep that counted the population.
  {
    files: ["src/**/*.tsx"],
    ignores: ["src/**/*.stories.tsx"],
    plugins: { minerva: minervaPlugin },
    rules: {
      "minerva/no-mouse-only-click": "error",
    },
  },
  // Prettier config disables ESLint rules that would conflict with
  // Prettier's formatting decisions. Must run LAST.
  prettier,
);
