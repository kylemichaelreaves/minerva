#!/usr/bin/env python3
"""Re-OCR the *Lectures on the Philosophy of World History* scan (#540).

The 2011 OUP PDF is a 575-page image scan carrying a bad embedded OCR
layer. The corruption is in the PDF's own text — raw PyMuPDF output on
page 80 reads ``representationaL That is how., for`` where the page says
``representational. That is how, for`` — so no extraction change reaches
it, and no cleaning script can either: the damaged tokens
(``refnma`` for ``Reformation``, ``bappm`` for ``happen``) are not
mechanically recoverable, while the work's legitimate vocabulary is the
most unusual in the corpus (``bactria``, ``manchu``, ``darya``), so a
dictionary-driven cleaner would have its highest false-positive rate
exactly here.

The page images are 300 dpi, which is what a modern engine wants.
Measured over all 575 pages, embedded layer vs this:

    signature               embedded   vision   change
    tilde in word                411        5   -99%
    digit in word                280        3   -99%
    th/to misread                537       47   -91%
    capital mid-word             788        8   -99%
    glued words (20+)             11        9   -18%
    TOTAL                       2027       72   -96%

    embedded   201,726 word tokens, 12,451 unknown = 6.17%
    vision     202,431 word tokens,  7,815 unknown = 3.86%

Word counts land within 0.35% of each other, so the gain is not bought
by dropping or inventing text. The residual 3.86% is the legitimate rare
vocabulary above, which should stay unknown.

**Glued words barely move (11 -> 9).** Losing inter-word spaces is not
an OCR-engine failure and survives a re-OCR; that is #561 and needs its
own treatment.

Output is per-page line lists rather than flat text, because page
furniture is a property of the page: `corpus_extract._clean_page_lines`
needs the page structure to spot a running head, and flattening first
throws away what identifies it.

macOS only — Vision is the system OCR framework. Not installable in CI,
which is why this lives in `perseus/` (coverage-excluded) and why the
dependencies are not in the project environment:

    uv venv /tmp/ocrvenv
    uv pip install --python /tmp/ocrvenv/bin/python \
        pyobjc-framework-Vision pyobjc-framework-Quartz pymupdf
    /tmp/ocrvenv/bin/python perseus/ocr_lpwh.py

`data/` is gitignored, so the artefact this writes is no more in version
control than the PDF it comes from. This script is the durable half.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_PDF = _ROOT / "data" / "hegel" / (
    "Georg Wilhelm Friedrich Hegel, Peter C. Hodgson, Robert F. Brown - Lectures on the "
    "Philosophy of World History_ Manuscripts of the introduction and the lectures of "
    "1822-3-Oxford University Press (2011.pdf"
)
_OUT = _ROOT / "data" / "hegel" / "lwh_vision.ocr.json"

#: 300 dpi matches the scan's own resolution. Rendering higher does not
#: add information and costs time; lower loses it.
_DPI = 300


def _ocr_page(page, Quartz, Vision, NSData) -> list[str]:
    """One page's lines, in reading order."""

    png = page.get_pixmap(dpi=_DPI).tobytes("png")
    data = NSData.dataWithBytes_length_(png, len(png))
    src = Quartz.CGImageSourceCreateWithData(data, None)
    cg = Quartz.CGImageSourceCreateImageAtIndex(src, 0, None)

    lines: list[tuple[float, str]] = []

    def handler(request, error) -> None:
        for obs in request.results():
            # Vision's origin is bottom-left, so negate to sort top-down.
            lines.append((-obs.boundingBox().origin.y, obs.topCandidates_(1)[0].string()))

    req = Vision.VNRecognizeTextRequest.alloc().initWithCompletionHandler_(handler)
    req.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    # German matters: the text quotes Hegel's own wording throughout.
    req.setRecognitionLanguages_(["en-US", "de-DE"])
    req.setUsesLanguageCorrection_(True)
    Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(cg, None).performRequests_error_(
        [req], None
    )
    return [text for _, text in sorted(lines)]


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    pdf = Path(argv[0]) if argv else _PDF
    out = Path(argv[1]) if len(argv) > 1 else _OUT

    if not pdf.exists():
        print(f"ocr-lpwh: no such PDF: {pdf}", file=sys.stderr)
        return 1
    try:
        import pymupdf
        import Quartz
        import Vision
        from Foundation import NSData
    except ImportError as exc:
        print(
            f"ocr-lpwh: needs pymupdf + pyobjc (macOS only): {exc}\n"
            "  uv venv /tmp/ocrvenv && uv pip install --python /tmp/ocrvenv/bin/python "
            "pyobjc-framework-Vision pyobjc-framework-Quartz pymupdf",
            file=sys.stderr,
        )
        return 1

    doc = pymupdf.open(pdf)
    pages: list[list[str]] = []
    started = time.monotonic()
    for i in range(doc.page_count):
        pages.append(_ocr_page(doc[i], Quartz, Vision, NSData))
        if (i + 1) % 50 == 0:
            elapsed = time.monotonic() - started
            remaining = elapsed / (i + 1) * (doc.page_count - i - 1)
            print(f"  {i + 1}/{doc.page_count} pages  {elapsed:.0f}s  ~{remaining:.0f}s left", flush=True)

    out.write_text(json.dumps({"pages": pages}), encoding="utf-8")
    print(
        f"ocr-lpwh: {doc.page_count} pages, {sum(len(p) for p in pages)} lines, "
        f"{time.monotonic() - started:.0f}s -> {out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
