"""The YAML rule loader's missing-PyYAML error must name the extra.

``refs/rules/specs/`` holds ``boulainvilliers.yaml`` and ``gobineau.yaml``, and
``rules.rules_for_author`` reaches ``load_author_rules_from_yaml`` on the
default ``refs build`` path for those two authors — not an opt-in one. ``pyyaml``
is declared only under the ``lemma``/``dev`` extras, so on a base install that
call is the one thing standing between the operator and a fix.

Its two siblings (``glossary_spec.load_spec``, ``refs.spec.load_spec``) already
raise a message naming the install command. This one did not, which meant the
same missing dependency produced an actionable error on two paths and a bare
"PyYAML required for YAML rule specs" on the third (#481, audit §6).
"""

from __future__ import annotations

import builtins
import re
from pathlib import Path

import pytest

from minerva.refs.rules.loader import load_author_rules_from_yaml

_REAL_IMPORT = builtins.__import__


def _without_yaml(name, *args, **kwargs):
    if name == "yaml":
        raise ImportError("No module named 'yaml'")
    return _REAL_IMPORT(name, *args, **kwargs)


def test_missing_pyyaml_error_names_the_extra_to_install(monkeypatch, tmp_path):
    spec = tmp_path / "someone.yaml"
    spec.write_text("mentions: []\n", encoding="utf-8")
    monkeypatch.setattr(builtins, "__import__", _without_yaml)

    with pytest.raises(RuntimeError) as exc:
        load_author_rules_from_yaml(spec, prefix="someone")

    message = str(exc.value)
    assert "PyYAML" in message
    # The actionable half: which extra, and how to install it.
    assert ".[lemma]" in message, message
    assert re.search(r"pip install", message), message


def test_the_three_pyyaml_errors_stay_consistent():
    """All three lazy-yaml sites name the same extra.

    Guards the drift this test was written for: the loader's message was the
    odd one out for two months.
    """

    src = Path(__file__).resolve().parents[1] / "src" / "minerva"
    sites = [
        src / "refs" / "rules" / "loader.py",
        src / "refs" / "spec.py",
        src / "glossary_spec.py",
    ]
    for path in sites:
        text = path.read_text(encoding="utf-8")
        assert "import yaml" in text, f"{path} no longer lazily imports yaml"
        assert ".[lemma]" in text, f"{path} does not name the lemma extra"
