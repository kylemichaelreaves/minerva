"""Load author mention rules from YAML specs (optional migration path)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import AuthorMentionRule, Rule
from .scripture_cite import default_scripture_rules

_SPECS_DIR = Path(__file__).resolve().parent / "specs"


def load_author_rules_from_yaml(spec_path: Path, *, prefix: str) -> tuple[Rule, ...]:
    """Parse a minimal YAML author spec into rule instances."""
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError as exc:
        raise RuntimeError("PyYAML required for YAML rule specs") from exc

    data: dict[str, Any] = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    rules: list[Rule] = list(default_scripture_rules(prefix))
    for entry in data.get("mentions") or []:
        target = entry["target_author"]
        slug = target.lower().replace(" ", "_")
        rules.append(
            AuthorMentionRule(
                name=entry.get("name") or f"{prefix}_{slug}",
                target_author=target,
                target_work=entry.get("target_work", ""),
                forms=tuple(entry.get("forms") or ()),
                langs=tuple(entry.get("langs") or ()),
                confidence=float(entry.get("confidence", 0.45)),
                note=entry.get("note"),
            )
        )
    return tuple(rules)


def spec_path_for_author(author: str) -> Path:
    """Resolve ``refs/rules/specs/{module}.yaml`` for a chunk author name."""
    module_name = author.lower().replace(" ", "_")
    return _SPECS_DIR / f"{module_name}.yaml"
