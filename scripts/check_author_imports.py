#!/usr/bin/env python3
"""Fail if code imports deprecated root minerva.<author>_works shims."""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
AUTHORS = REPO / "src" / "minerva" / "authors"
SCAN_ROOTS = (
    REPO / "src",
    REPO / "tests",
    REPO / "perseus",
    REPO / "scripts",
)

# minerva.foo_works where foo_works.py lives under authors/
AUTHOR_MODULES = {p.stem for p in AUTHORS.glob("*_works.py") if p.name != "__init__.py"}

PATTERNS = (
    re.compile(r"from\s+minerva\.(\w+_works)\s+import"),
    re.compile(r"import\s+minerva\.(\w+_works)\b"),
    re.compile(r"import_module\(\s*[\"']minerva\.(\w+_works)"),
    re.compile(r"from\s+\.(\w+_works)\s+import"),
    re.compile(r"from\s+\.\.(\w+_works)\s+import"),
    re.compile(r"from\s+\.\.\.(\w+_works)\s+import"),
)


def _scan_file(path: Path) -> list[str]:
    if path.name == "check_author_imports.py":
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    hits: list[str] = []
    for i, line in enumerate(text.splitlines(), 1):
        if "corpus_works" in line:
            continue
        for pat in PATTERNS:
            m = pat.search(line)
            if m and m.group(1) in AUTHOR_MODULES:
                hits.append(f"{path.relative_to(REPO)}:{i}: {line.strip()}")
    return hits


def main() -> int:
    errors: list[str] = []
    for root in SCAN_ROOTS:
        if not root.is_dir():
            continue
        for path in root.rglob("*.py"):
            if path.name.endswith("_works.py") and path.parent.name == "minerva":
                continue
            errors.extend(_scan_file(path))
    if errors:
        print("Deprecated author works imports (use minerva.authors.<module>):", file=sys.stderr)
        for e in errors:
            print(f"  {e}", file=sys.stderr)
        return 1
    print("check-author-imports: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
