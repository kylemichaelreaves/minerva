// ESLint v9 flat config. Strict baseline: typescript-eslint's
// `strictTypeChecked` (semantic rules that require the type-checker)
// plus the Solid plugin for JSX-reactivity gotchas, and the Prettier
// config last to disable any formatting rules we'd let Prettier handle.
import js from "@eslint/js";
import solid from "eslint-plugin-solid/configs/typescript";
import prettier from "eslint-config-prettier";
import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  {
    ignores: ["dist/**", "node_modules/**", "vite.config.ts.*", "eslint.config.js"],
  },
  js.configs.recommended,
  ...tseslint.configs.strictTypeChecked,
  ...tseslint.configs.stylisticTypeChecked,
  {
    files: ["src/**/*.{ts,tsx}", "tests/**/*.{ts,tsx}"],
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
      "@typescript-eslint/no-confusing-void-expression": [
        "error",
        { ignoreArrowShorthand: true },
      ],
    },
  },
  // SFC migration: forbid new hooks/*.ts and utils/*.ts under feature surfaces.
  {
    files: [
      "src/Reader/hooks/**/*.ts",
      "src/Reader/utils/**/*.ts",
      "src/Concordance/hooks/**/*.ts",
      "src/Concordance/utils/**/*.ts",
      "src/Network/hooks/**/*.ts",
      "src/Network/utils/**/*.ts",
      "src/Refs/hooks/**/*.ts",
      "src/Refs/utils/**/*.ts",
      "src/Thread/hooks/**/*.ts",
      "src/Thread/utils/**/*.ts",
      "src/Landing/hooks/**/*.ts",
      "src/Landing/utils/**/*.ts",
    ],
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
  // Prettier config disables ESLint rules that would conflict with
  // Prettier's formatting decisions. Must run LAST.
  prettier,
);
