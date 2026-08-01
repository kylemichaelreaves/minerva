"""Runtime guards for the ``perseus/download_*.py`` family (issue #116).

Sixteen downloaders referenced module globals that were never defined
— extractor skip-sets, wikitext regexes, a missing ``urllib`` import.
They all *imported* cleanly (the names are only touched inside function
bodies) and raised ``NameError`` the moment the relevant path ran, so
neither the test suite nor a successful download noticed. Several of
the breaks were on error paths only: a 404 turned into a ``NameError``
instead of the intended "[WORK SKIPPED]" message.

Ruff's F821 gate over ``perseus/`` (issue #117) is the static half of
the fix. These tests are the behavioural half — they actually *call*
the repaired functions, which is what the lint gate cannot do.

Network is never touched: every test feeds bytes in directly.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

PERSEUS = Path(__file__).resolve().parents[1] / "perseus"

# Downloaders whose `except urllib.error.HTTPError:` handler used to
# raise NameError because the refactor dropped `import urllib.request`.
_URLLIB_USERS = [
    "download_cicero_wikisource",
    "download_ica_aristotle",
    "download_kjv_en",
    "download_luther_1545_de",
    "download_luther_1912_de",
    "download_marx_archive",
    "download_marx_pgde",
    "download_sacy_fr",
    "download_sblgnt_nt",
    "download_spinoza_ttp",
    "download_vulgate",
]

# Downloaders that build a paragraph extractor from module-level
# skip-sets. Each must survive being handed real markup.
_EXTRACTOR_USERS = [
    "download_cicero_wikisource",
    "download_descartes_wikisource",
    "download_marx_archive",
    "download_marx_pgde",
    "download_pascal_fr",
    "download_rousseau_fr",
]

_CHROME_HTML = b"""<html><head><title>Page Title</title></head><body>
<script>tracker()</script>
<div class="headertemplate">WIKISOURCE CHROME</div>
<div class="site-header">WORDPRESS CHROME</div>
<div class="wm-ipp">WAYBACK TOOLBAR</div>
<p>Prima sententia operis.</p>
<p>Secunda sententia operis.</p>
<table><tr><td>navigation table</td></tr></table>
</body></html>"""


@pytest.fixture(autouse=True)
def _perseus_on_path():
    """`perseus/` has no __init__.py; the scripts import each other by
    bare module name, exactly as Python does when you run one directly.
    """

    sys.path.insert(0, str(PERSEUS))
    try:
        yield
    finally:
        sys.path.remove(str(PERSEUS))
        for name in list(sys.modules):
            if name.startswith("download_") or name in {"_download", "_gutenberg"}:
                del sys.modules[name]


@pytest.mark.parametrize("modname", _URLLIB_USERS)
def test_urllib_error_is_resolvable(modname):
    """The HTTPError handlers must be able to resolve `urllib.error`.

    Regression: `_fetch = make_fetcher()` replaced the inline urlopen
    call and `import urllib.request` went with it, but the
    `except urllib.error.HTTPError:` below it stayed.
    """

    mod = importlib.import_module(modname)
    urllib_mod = getattr(mod, "urllib", None)
    assert urllib_mod is not None, f"{modname} references urllib but never imports it"
    assert hasattr(urllib_mod, "error"), f"{modname}: urllib.error not reachable"
    assert issubclass(urllib_mod.error.HTTPError, Exception)


@pytest.mark.parametrize("modname", _EXTRACTOR_USERS)
def test_extractor_runs_and_keeps_body_text(modname):
    """`_extract_paragraphs` must run (it used to raise NameError on
    `_SKIP_TAGS`) and return the prose while dropping script/table.

    Each scraper only strips its *own* site's class chrome, so this
    asserts on tag-level stripping and body survival — the parts every
    variant shares.
    """

    mod = importlib.import_module(modname)
    paragraphs = mod._extract_paragraphs(_CHROME_HTML)

    assert "Prima sententia operis." in paragraphs
    assert "Secunda sententia operis." in paragraphs
    joined = " ".join(paragraphs)
    assert "tracker()" not in joined
    assert "navigation table" not in joined


def test_marx_pgde_strips_wordpress_chrome():
    """PG-DE serves WordPress chrome; its class tokens must drop it."""

    mod = importlib.import_module("download_marx_pgde")
    joined = " ".join(mod._extract_paragraphs(_CHROME_HTML))
    assert "WORDPRESS CHROME" not in joined


def test_marx_archive_strips_wayback_toolbar():
    """Die deutsche Ideologie comes via a web.archive.org wrapper."""

    mod = importlib.import_module("download_marx_archive")
    joined = " ".join(mod._extract_paragraphs(_CHROME_HTML))
    assert "WAYBACK TOOLBAR" not in joined


@pytest.mark.parametrize("modname", ["download_pascal_fr", "download_rousseau_fr"])
def test_wikisource_scrapers_strip_apparatus(modname):
    """Editorial-apparatus classes must not bleed into corpus text —
    that bleed is what causes spurious cross-references downstream.
    """

    mod = importlib.import_module(modname)
    joined = " ".join(mod._extract_paragraphs(_CHROME_HTML))
    assert "WIKISOURCE CHROME" not in joined


def test_clean_wikitext_strips_markup():
    """The exact reproduction from issue #116, plus the other five
    patterns `clean_wikitext` applies.
    """

    mod = importlib.import_module("download_spinoza_ttp")

    assert mod.clean_wikitext("hello <ref>x</ref> world") == "hello  world"
    assert mod.clean_wikitext("a <ref name='n'/> b") == "a  b"
    # Templates nest one level; the caller iterates to unwrap them.
    assert mod.clean_wikitext("{{outer{{inner}}}}text") == "text"
    assert mod.clean_wikitext("<div>x</div>") == "x"
    # Piped wikilink keeps the display half; plain link keeps the target.
    assert mod.clean_wikitext("[[Deus|Dei]] et [[Natura]]") == "Dei et Natura"
    assert mod.clean_wikitext("a '''bold''' and ''italic''") == "a bold and italic"
    assert mod.clean_wikitext("trailing   \nnext") == "trailing\nnext"
    assert mod.clean_wikitext("a\n\n\n\n\nb") == "a\n\nb"


def test_cicero_subpage_discovery():
    """Sub-page links are the `<work>/<part>` titles Parsoid emits as
    `href="./De_officiis/Liber_I"`; siblings and anchors must not match.
    """

    mod = importlib.import_module("download_cicero_wikisource")
    html = (
        b'<a href="./De_officiis/Liber_I">I</a>'
        b'<a href="./De_officiis/Liber_II">II</a>'
        b'<a href="./De_officiis/Liber_I#anchor">dup</a>'
        b'<a href="./De_officiis">self</a>'
        b'<a href="./De_amicitia/Liber_I">other work</a>'
    ).decode()
    subs = mod._subpage_titles(html.encode(), "De officiis")

    assert subs == ["De_officiis/Liber_I", "De_officiis/Liber_II"]


def test_cicero_extractor_drops_breadcrumb_and_page_title():
    """la.wikisource opens each work with a `< Author / < Collection`
    breadcrumb, and the REST endpoint returns a full document whose
    `<title>` would otherwise lead the output.
    """

    mod = importlib.import_module("download_cicero_wikisource")
    html = (
        b"<html><head><title>De fato (Marcus Tullius Cicero)</title></head>"
        b"<body><p>&lt; Marcus Tullius Cicero<br/>&lt; Opera philosophica</p>"
        b"<p>[1] Cum multae res in philosophia.</p></body></html>"
    )
    paragraphs = mod._extract_paragraphs(html)

    assert paragraphs == ["[1] Cum multae res in philosophia."]


def test_descartes_reuses_shared_gutenberg_helpers():
    """`download_descartes` duplicated `_gutenberg`'s boilerplate
    stripper minus its `_PG_START`/`_PG_END` constants. It now imports
    them, so the two can't drift apart again.
    """

    mod = importlib.import_module("download_descartes")
    gutenberg = importlib.import_module("_gutenberg")

    assert mod._strip_pg_boilerplate is gutenberg.strip_pg_boilerplate
    assert mod._verify_language is gutenberg.verify_language

    raw = (
        "front matter\n"
        "*** START OF THE PROJECT GUTENBERG EBOOK MEDITATIONES ***\n"
        "Ego cogito.\n"
        "*** END OF THE PROJECT GUTENBERG EBOOK MEDITATIONES ***\n"
        "license blurb\n"
    )
    assert mod._strip_pg_boilerplate(raw) == "Ego cogito.\n"


def test_every_perseus_module_imports():
    """Blanket guard: no downloader may fail at import time."""

    failures = []
    for path in sorted(PERSEUS.glob("*.py")):
        try:
            importlib.import_module(path.stem)
        except Exception as exc:  # reporting, not handling
            failures.append(f"{path.name}: {type(exc).__name__}: {exc}")

    assert not failures, "modules failed to import:\n" + "\n".join(failures)
