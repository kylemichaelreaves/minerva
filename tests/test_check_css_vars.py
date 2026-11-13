"""#877: `var(--x)` naming a property nothing defines.

Such a declaration is invalid at computed-value time and silently drops to
its initial value. On #877, `--paper-deep` was never defined, and the Refs
review cards computed `border-style: none` across all twelve uses.
"""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import check_css_vars as ccv  # noqa: E402


def _tree(tmp_path: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    return tmp_path


def test_a_defined_property_passes(tmp_path: Path, capsys):
    root = _tree(
        tmp_path,
        {
            "web/src/styles.css": ":root { --paper: #fff; }\n.a { color: var(--paper); }",
        },
    )
    assert ccv.main(root) == 0
    assert "ok" in capsys.readouterr().out


def test_an_undefined_property_fails_with_its_site(tmp_path: Path, capsys):
    root = _tree(
        tmp_path,
        {
            "web/src/styles.css": ":root { --paper: #fff; }",
            "web/src/review.css": ".card {\n  border: 1px solid var(--paper-deep);\n}",
        },
    )
    assert ccv.main(root) == 1
    err = capsys.readouterr().err
    assert "--paper-deep  (1 use)" in err
    assert "web/src/review.css:2" in err


def test_a_fallback_does_not_excuse_an_undefined_name(tmp_path: Path):
    # `var(--r-paper-soft, transparent)` was transparent forever.
    root = _tree(
        tmp_path, {"web/src/r.css": ".x { background: var(--r-paper-soft, transparent); }"}
    )
    assert list(ccv.undefined_uses(root)) == ["--r-paper-soft"]


def test_definitions_in_tsx_and_index_html_count(tmp_path: Path):
    root = _tree(
        tmp_path,
        {
            "web/index.html": "<style>:root { --boot: 1px; }</style>",
            "web/src/A.tsx": 'el.style.setProperty("--lt-left", x);\nconst s = { "--lt-d": "1s" };',
            "web/src/B.tsx": "const c = 'var(--boot)'; const d = 'var(--lt-left)';",
            "web/src/b.css": ".y { transition-duration: var(--lt-d); }",
        },
    )
    assert ccv.undefined_uses(root) == {}


def test_runtime_built_prefixes_are_exempt(tmp_path: Path):
    root = _tree(
        tmp_path,
        {"web/src/Atlas.tsx": "return `var(--atlas-${t})`;\nfill={`var(--net-step-${k})`}"},
    )
    assert ccv.undefined_uses(root) == {}


def test_a_missing_web_src_is_vacuously_clean(tmp_path: Path):
    (tmp_path / "web").mkdir()
    assert ccv.undefined_uses(tmp_path) == {}
