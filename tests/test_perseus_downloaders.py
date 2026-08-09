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
<p>Prima sententia operis.</p>
<p>Secunda sententia operis.</p>
<table><tr><td>navigation table</td></tr></table>
</body></html>"""

# The wayback toolbar is keyed on `id`, never on a class — see
# `test_marx_archive_strips_wayback_toolbar`.
_WAYBACK_HTML = b"""<html><head><title>Page Title</title></head><body>
<script>tracker()</script>
<div id="wm-ipp">WAYBACK TOOLBAR</div>
<p>Prima sententia operis.</p>
<p>Secunda sententia operis.</p>
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


_PGDE_WRAPPER = "book-reader__chapter-content-wrapper"


def _pgde_page(*bodies: str) -> bytes:
    """A PG-DE chapter page: chrome, then one wrapper region per body."""

    regions = "".join(
        f'<div class="book-reader__chapter-text">'
        f'<div class="{_PGDE_WRAPPER}">{b}</div></div>'
        for b in bodies
    )
    return (
        '<html><body><header class="site-header">Zum Inhalt springen</header>'
        '<p class="gb-text">Bei Amazon Bei Thalia Lokale Buchhandlung</p>'
        f"{regions}"
        '<div class="gbp-section__inner">Nutzungsbedingungen Datenschutz</div>'
        "</body></html>"
    ).encode()


def test_marx_pgde_takes_only_the_content_container():
    """Enumerating chrome classes left four paragraphs behind; taking the
    body's own container leaves none."""

    mod = importlib.import_module("download_marx_pgde")
    html = _pgde_page("<p>Hegel bemerkte irgendwo.</p>")
    paragraphs = mod._extract_paragraphs(html)

    assert paragraphs == ["Hegel bemerkte irgendwo."]


def test_marx_pgde_deduplicates_the_twice_rendered_body():
    """PG-DE renders the chapter body twice — text-identical, differing
    markup. Parsing the whole document emitted every Marx paragraph
    twice; taking the first region is the dedup.
    """

    mod = importlib.import_module("download_marx_pgde")
    html = _pgde_page("<p>Hegel bemerkte irgendwo.</p>", "<p>Hegel bemerkte irgendwo.</p>")
    assert mod._extract_paragraphs(html) == ["Hegel bemerkte irgendwo."]


def test_marx_pgde_content_region_handles_nested_divs():
    """Nested divs inside the body must not be mistaken for its end."""

    mod = importlib.import_module("download_marx_pgde")
    html = _pgde_page("<div><p>Erster Satz.</p></div><p>Zweiter Satz.</p>")
    assert mod._extract_paragraphs(html) == ["Erster Satz.", "Zweiter Satz."]


def test_marx_pgde_warns_loudly_when_the_wrapper_is_gone(capsys):
    """If PG-DE renames the container the chrome returns, so the fallback
    must announce itself rather than quietly degrade."""

    mod = importlib.import_module("download_marx_pgde")
    paragraphs = mod._extract_paragraphs(
        b"<html><body><p>Hegel bemerkte irgendwo.</p></body></html>"
    )
    assert "Hegel bemerkte irgendwo." in paragraphs
    assert "WARNING" in capsys.readouterr().out


def test_marx_pgde_content_region_returns_none_without_the_marker():
    mod = importlib.import_module("download_marx_pgde")
    assert mod._content_region("<html><body><p>x</p></body></html>") is None


def test_marx_pgde_content_region_tolerates_an_unclosed_wrapper():
    mod = importlib.import_module("download_marx_pgde")
    region = mod._content_region(f'<div class="{_PGDE_WRAPPER}"><p>Satz.</p>')
    assert region is not None
    assert "Satz." in region


def test_marx_archive_strips_wayback_toolbar():
    """Die deutsche Ideologie comes via a web.archive.org wrapper.

    Updated for #152, not rewritten around: this test used to assert on
    ``<div class="wm-ipp">`` and passed, which is exactly how the wrong
    premise survived. web.archive.org marks its toolbar with
    ``id="wm-ipp"`` and gives it no distinguishing class — measured
    against the live archived ``me03_NNN.htm``, all seven of the class
    tokens this scraper used to carry matched zero elements. The fixture
    below now says ``id``, so the assertion means what it claims.
    """

    mod = importlib.import_module("download_marx_archive")
    joined = " ".join(mod._extract_paragraphs(_WAYBACK_HTML))
    assert "WAYBACK TOOLBAR" not in joined
    assert "Prima sententia operis." in joined


def test_marx_archive_excises_the_wayback_insert_region():
    """The toolbar's own markup is tag-unbalanced, so subtree skipping
    cannot contain it — a stray ``</form>`` drove the depth counter to
    zero partway through and leaked the capture banner. The
    BEGIN/END comment pair web.archive.org emits is the reliable seam.
    """

    mod = importlib.import_module("download_marx_archive")
    html = (
        b"<html><body>"
        b"<!-- BEGIN WAYBACK TOOLBAR INSERT -->"
        b"<div><form>269 captures 20 Feb 2001</form>"
        b"<p>Collection: Wikipedia Outlinks March 2016</p></div>"
        b"<!-- END WAYBACK TOOLBAR INSERT -->"
        b"<p>Prima sententia operis.</p>"
        b"</body></html>"
    )
    joined = " ".join(mod._extract_paragraphs(html))
    assert "269 captures" not in joined
    assert "Wikipedia Outlinks" not in joined
    assert "Prima sententia operis." in joined


def test_marx_archive_drops_mlwerke_native_chrome():
    """mlwerke.de's running head, index link and MEW edition note carry
    no class or id to skip on, and the committed
    ``deutsche_ideologie.txt`` contains none of them.
    """

    mod = importlib.import_module("download_marx_archive")
    kept = mod._drop_mlwerke_chrome(
        [
            "Karl Marx-Friedrich Engels - Die deutsche Ideologie",
            "Zurück zum Gesamtverzeichnis Karl Marx/Friedrich Engels - Werke",
            "Seitenzahlen verweisen auf: Karl Marx - Friedrich Engels - Werke, Band 3",
            "Die Voraussetzungen, mit denen wir beginnen, sind keine willkürlichen.",
        ]
    )
    assert kept == [
        "Die Voraussetzungen, mit denen wir beginnen, sind keine willkürlichen."
    ]


def test_marx_archive_keeps_marxists_org_body_and_notes():
    """``p.toplink`` / ``p.link`` are marxists.org chrome; ``p.fst``
    (body) and ``p.note`` (Marx's own manuscript notes) are content.
    """

    mod = importlib.import_module("download_marx_archive")
    html = (
        b'<html><body><p class="toplink">MIA &gt; Deutsch &gt; Marxisten</p>'
        b'<p class="fst">Wir sind ausgegangen von den Voraussetzungen.</p>'
        b'<p class="note">1*. Nach diesem Absatz gestrichen.</p>'
        b'<p class="link">Anfang der Seite Zuletzt aktualisiert am 4. August 2019</p>'
        b"</body></html>"
    )
    joined = " ".join(mod._extract_paragraphs(html))
    assert "MIA" not in joined
    assert "Zuletzt aktualisiert" not in joined
    assert "Wir sind ausgegangen von den Voraussetzungen." in joined
    assert "1*. Nach diesem Absatz gestrichen." in joined


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


class TestCiceroSectionMarkers:
    """la.wikisource renders standalone section markers that duplicate the
    ``[N]`` numbering already in the body. The committed files contain
    zero of any form, and the old ``^[IVXLC]+$`` pattern caught 18 of the
    543 present across a full re-fetch — 3% (issue #151).
    """

    @pytest.mark.parametrize(
        "marker",
        [
            "I",  # bare Roman, the only form the old pattern caught
            "XVIII",
            "XIII.",  # dotted Roman — 381 of the 543
            "LXXXVIII.",
            "D",  # D and M were outside the old digit class
            "MCMXC",
            "1",  # bare Arabic — 104
            "42.",  # dotted Arabic — 40
            "(*****)",  # De re publica lacuna sigil — 46
            "(***)",
        ],
    )
    def test_marker_forms_are_recognised(self, marker):
        mod = importlib.import_module("download_cicero_wikisource")
        assert mod._is_marker(marker)

    @pytest.mark.parametrize(
        "text",
        [
            "[1] Cum multae res in philosophia.",
            "M. TVLLI CICERONIS De legibus - Liber I",
            "De officiis/Liber I",
            "Quamquam te, Marce fili.",
            "I. Cum multae res",  # a marker *plus* text is body
            "1. Quamquam te",
            "",
        ],
    )
    def test_body_text_is_not_a_marker(self, text):
        mod = importlib.import_module("download_cicero_wikisource")
        assert not mod._is_marker(text)


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
