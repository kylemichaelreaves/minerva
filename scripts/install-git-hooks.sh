#!/usr/bin/env bash
# Install the project's git hooks into .git/hooks/.
#
# Re-run any time the hook scripts change — `git config core.hooksPath`
# would skip the symlink dance but adds friction for one-off
# uninstalls. We do the symlinks explicitly so `git commit --no-verify`
# still works the standard way.
#
# Hooks installed:
#   * pre-commit — runs `make lint typecheck` (see scripts/githooks/pre-commit)
#
# Role: workflow

set -e

REPO_ROOT="$(git rev-parse --show-toplevel)"
HOOKS_SRC="$REPO_ROOT/scripts/githooks"
HOOKS_DST="$REPO_ROOT/.git/hooks"

if [ ! -d "$HOOKS_SRC" ]; then
  echo "✗ Source dir missing: $HOOKS_SRC"
  exit 1
fi

for hook in "$HOOKS_SRC"/*; do
  name="$(basename "$hook")"
  target="$HOOKS_DST/$name"
  if [ -e "$target" ] && [ ! -L "$target" ]; then
    echo "⚠ $target exists and isn't a symlink — leaving alone."
    echo "  Move it aside and re-run if you want the project hook to win."
    continue
  fi
  ln -sf "$hook" "$target"
  chmod +x "$hook"
  echo "✓ installed $name"
done

echo
echo "Hooks installed. Bypass with --no-verify if you must."
