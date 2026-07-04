"""Behavior-preservation guard for the shared figure-form lexicon.

`src/minerva/refs/rules/_figures.py` centralises surface-form tuples
that were duplicated verbatim across author rule modules (issue #56).
This test freezes the COMPLETE set of (module, target_author, langs,
forms, confidence, source_method, reference_type) across every rule so
that the extraction — and any future edit to _figures or a module —
cannot silently change which forms a rule matches. If you intentionally
change a rule's forms, regenerate the snapshot:

    python - <<'PY'
    # (see tests/data/refs_forms_snapshot.json header / git history)
    PY
"""

from __future__ import annotations

import importlib
import json
import os
import pkgutil
from pathlib import Path

import minerva.refs.rules as R

SNAPSHOT = Path(__file__).parent / "data" / "refs_forms_snapshot.json"


def _current_rows() -> list[dict]:
    pkgdir = os.path.dirname(R.__file__)
    mods = [
        n
        for _, n, _ in pkgutil.iter_modules([pkgdir])
        if n not in ("__init__", "loader", "_figures")
    ]
    rows: list[dict] = []
    for m in sorted(mods):
        mod = importlib.import_module(f"minerva.refs.rules.{m}")
        for rule in getattr(mod, "RULES", ()):
            forms = getattr(rule, "forms", None)
            if not forms:
                continue
            rows.append(
                {
                    "module": m,
                    "name": getattr(rule, "name", None),
                    "target_author": getattr(rule, "target_author", None),
                    "langs": list(getattr(rule, "langs", ()) or ()),
                    "forms": sorted(forms),
                    "confidence": getattr(rule, "confidence", None),
                    "source_method": getattr(rule, "source_method", None),
                    "reference_type": getattr(rule, "reference_type", None),
                }
            )
    return rows


def test_rule_forms_match_snapshot() -> None:
    expected = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    actual = _current_rows()
    # Compare as sorted JSON so ordering differences don't matter.
    key = lambda r: (r["module"], r["name"], r["target_author"])  # noqa: E731
    assert sorted(actual, key=key) == sorted(expected, key=key)
