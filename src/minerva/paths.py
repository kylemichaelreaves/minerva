"""Repository root path — single source of truth."""

from __future__ import annotations

from pathlib import Path

# `paths.py` lives at src/minerva/paths.py → parents[2] is the repo root.
REPO_ROOT = Path(__file__).resolve().parents[2]
