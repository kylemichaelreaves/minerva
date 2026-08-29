"""Offline test for ``perseus/download_schiller_de.py``'s ``title_to_path``
(issue #420 — same defect as ``download_kant_de.title_to_path``, found
while fixing that one).

zeno.org percent-encodes ``[`` and ``]`` in its own outbound hrefs
(``%5B``/``%5D``), but ``title_to_path`` left them in its
``quote(..., safe=...)`` allowlist and emitted them literally, so a
bracketed title's own `root_path` never matches its children's hrefs
via `extract_links`'s `path.startswith(root_path)` check.

Latent here — ``kallias_de.html`` (title ``"[Kallias oder über die
Schönheit]"``) is the only affected entry, and that work fits on
zeno's single root page, so there are no undiscovered children to
lose currently. Fixed anyway, for the next bracketed/coloned title.

No network — this only exercises the URL-encoding helper.
"""

from __future__ import annotations

import sys
from pathlib import Path

perseus_dir = Path(__file__).resolve().parents[1] / "perseus"
sys.path.insert(0, str(perseus_dir))
import download_schiller_de as schiller  # noqa: E402


def test_title_to_path_encodes_brackets_like_zeno_does():
    path = schiller.title_to_path("[Kallias oder über die Schönheit]")
    assert "%5BKallias" in path
    assert "[Kallias" not in path
