"""Offline tests for ``perseus/download_kant_de.py``'s ``title_to_path``
and the shared ``_zeno.extract_links`` (issue #420).

zeno.org percent-encodes ``:``, ``[`` and ``]`` in its own outbound
hrefs (``%3A``, ``%5B``, ``%5D``), but ``title_to_path`` left those
three characters in its `quote(..., safe=...)` allowlist and emitted
them literally. ``extract_links`` matches children with
``path.startswith(root_path)``, so any title containing one of those
characters produced a ``root_path`` that never matched its own child
hrefs — the BFS crawler stopped after the first page, silently, for
any such work that zeno actually splits into chapters.

No network — feeds real zeno-shaped href markup in directly.
"""

from __future__ import annotations

import sys
from pathlib import Path

perseus_dir = Path(__file__).resolve().parents[1] / "perseus"
sys.path.insert(0, str(perseus_dir))
import _zeno as zeno  # noqa: E402
import download_kant_de as kant  # noqa: E402

_BRACKETED_TITLE = "Einleitung in die Kritik der Urteilskraft [1. Fassung]"

# Real href shape copied from data/kant/ku_einl_de.html: zeno encodes
# the title's own brackets as %5B / %5D in the chapter links it emits.
_TOC_HTML = """
<html><body>
<a href="/Philosophie/M/Kant,+Immanuel/Einleitung+in+die+Kritik+der+Urteilskraft+%5B1.+Fassung%5D/I.+Von+der+Philosophie+als+einem+System">I.</a>
<a href="/Philosophie/M/Kant,+Immanuel/Einleitung+in+die+Kritik+der+Urteilskraft+%5B1.+Fassung%5D/II.+Von+dem+System+der+obern+Erkenntnisverm%C3%B6gen">II.</a>
</body></html>
"""


def test_title_to_path_encodes_brackets_like_zeno_does():
    path = kant.title_to_path(_BRACKETED_TITLE)
    assert "%5B1." in path
    assert "[1." not in path


def test_extract_links_finds_chapter_children_of_a_bracketed_title():
    root_path = kant.title_to_path(_BRACKETED_TITLE)
    children = zeno.extract_links(_TOC_HTML, root_path)
    assert len(children) == 2
