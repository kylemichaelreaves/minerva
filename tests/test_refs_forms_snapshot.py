"""Behavior-preservation guard for the shared figure-form lexicon.

`src/minerva/refs/rules/_figures.py` centralises surface-form tuples
that were duplicated verbatim across author rule modules (issue #56).
This test freezes the COMPLETE set of (module, target_author, langs,
forms, confidence, source_method, reference_type) across every rule so
that the extraction — and any future edit to _figures or a module —
cannot silently change which forms a rule matches. If you intentionally
change a rule's forms, regenerate the snapshot:

    python -c "
    import sys, json; sys.path.insert(0, 'tests')
    from test_refs_forms_snapshot import _current_rows, SNAPSHOT
    SNAPSHOT.write_text(
        json.dumps(_current_rows(), indent=1, sort_keys=True, ensure_ascii=False) + '\\n',
        encoding='utf-8',
    )"

Keep `_current_rows()` order (module, then rule-definition order) rather than
re-sorting: the comparison below sorts before asserting, so a reordered file
still passes, but it produces a ~1900-line diff that hides the real change.

A forms change usually also needs `tests/test_refs_forms_inflection_gate.py`
to agree — that gate flags same-author/same-language inflection gaps.
"""

from __future__ import annotations

import importlib
import json
import pkgutil
from pathlib import Path

import minerva.refs.rules as R

SNAPSHOT = Path(__file__).parent / "data" / "refs_forms_snapshot.json"


def _current_rows() -> list[dict]:
    pkgdir = str(Path(R.__file__).parent)
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
