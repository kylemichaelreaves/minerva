"""Hardened XML parsing for corpus sources (#127).

Every XML ingest path parses with stdlib ``xml.etree.ElementTree``, which
per the Python docs is safe against external entity expansion and DTD
retrieval — no XXE file read, no SSRF — but still performs *internal*
entity expansion, so it remains vulnerable to billion laughs and
quadratic blowup. A ~1 KB document expands to gigabytes and OOM-kills
the ingest.

The documents are not local fixtures: `perseus/download_*.py` fetches
them from Perseus, First1KGreek, gratis-bible, Tanzil and SBLGNT, over
URLs a hijacked upstream controls.

Rather than add `defusedxml`, this refuses any document carrying a
DOCTYPE at all. Internal entities can only be declared in a DOCTYPE's
internal subset, so refusing the declaration removes the entire class,
and none of the corpus formats — TEI P5, EpiDoc, OSIS, SBLGNT, Tanzil —
has any legitimate use for one. Verified against the corpus at the time
of writing: 0 of 78 XML files under `data/` contain `<!DOCTYPE`.

Deliberately a *refusal* rather than a sanitisation. A source that
starts shipping a DOCTYPE should stop the ingest and get a human's
attention, not be silently reinterpreted.
"""

from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET

from .errors import MinervaError

# A DOCTYPE is only legal in the prolog, so there is no need to read a
# 300 MB TEI file to rule one out. Generous enough to cover any real
# prolog — an XML declaration, comments, processing instructions.
_PROLOG_SCAN_BYTES = 64 * 1024

# Byte-level on purpose: the encoding is not known until the XML
# declaration has been read, and `<!DOCTYPE` is ASCII in every encoding
# the sources use.
_DOCTYPE = b"<!DOCTYPE"


class UnsafeXMLError(MinervaError):
    """An XML document declares a DTD, which the corpus formats never need."""


def _reject_doctype(path: Path) -> None:
    with path.open("rb") as fh:
        head = fh.read(_PROLOG_SCAN_BYTES)
    idx = head.find(_DOCTYPE)
    if idx == -1:
        return
    raise UnsafeXMLError(
        f"{path} declares a DTD at byte {idx}. Corpus XML (TEI/OSIS/SBLGNT/Tanzil) "
        f"has no legitimate use for one, and a DOCTYPE is how internal-entity "
        f"expansion attacks (billion laughs) are delivered. If the upstream source "
        f"genuinely changed, verify the document by hand before allowing it."
    )


def parse(path: str | Path) -> ET.ElementTree:
    """``ElementTree.parse``, refusing documents that declare a DTD."""

    p = Path(path)
    _reject_doctype(p)
    return ET.parse(p)
