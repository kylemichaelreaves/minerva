#!/usr/bin/env python3
"""Download Marcus Aurelius's Meditations bilingually.

Greek: el.wikisource.org hosts Τὰ εἰς ἑαυτόν (Farquharson critical
edition base text), split into 12 sub-pages — one per book. We
fetch each /Τα_εις_εαυτόν/<N>, extract paragraphs, concatenate
with `ΒΙΒΛΙΟΝ N` headers.

English: Project Gutenberg PG 2680 (anonymous Long-derivative
translation). Single .txt file.

Output:
    data/marcus_aurelius/raw/meditations_grc.txt
    data/marcus_aurelius/raw/meditations_en.txt

Run: uv run python perseus/download_marcus_aurelius.py
"""

from __future__ import annotations

import argparse
import time
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote

from _download import make_fetcher


# Greek source: el.wikisource page tree.
_GRC_BASE_TITLE = "Τα εις εαυτόν"
_GRC_BOOKS = list(range(1, 13))  # 12 books

# English source: PG 2680 Long-derivative anonymous translation.
_PG_ID = 2680


_fetch = make_fetcher()

class _ParaExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._skip = 0
        self._buf = []
        self.paragraphs = []

    def _should_skip(self, attrs):
        for n, v in attrs:
            if n != "class" or v is None:
                continue
            if any(t in _SKIP_CLASS_TOKENS for t in v.split()):
                return True
        return False

    def _flush(self):
        text = " ".join("".join(self._buf).split()).strip()
        if text:
            self.paragraphs.append(text)
        self._buf.clear()

    def handle_starttag(self, tag, attrs):
        if self._skip:
            self._skip += 1
            return
        if tag in _SKIP_TAGS or self._should_skip(attrs):
            self._skip = 1
            return
        if tag == "p":
            self._flush()

    def handle_endtag(self, tag):
        if self._skip:
            self._skip -= 1
            return
        if tag in ("p", "li", "div"):
            self._flush()

    def handle_data(self, data):
        if not self._skip:
            self._buf.append(data)

    def close(self):
        super().close()
        self._flush()


def _extract(html: bytes) -> list[str]:
    p = _ParaExtractor()
    p.feed(html.decode("utf-8", errors="replace"))
    p.close()
    return p.paragraphs


def fetch_greek(*, out_dir: Path, delay: float = 1.5) -> Path:
    print("\n=== meditations_grc.txt: el.wikisource Τα εις εαυτόν ===")
    out_paragraphs: list[str] = []
    for book in _GRC_BOOKS:
        title = f"{_GRC_BASE_TITLE}/{book}"
        url = "https://el.wikisource.org/api/rest_v1/page/html/" + quote(title, safe="")
        print(f"  GET book {book}")
        try:
            raw = _fetch(url)
        except urllib.error.HTTPError as e:
            print(f"    HTTP {e.code} on book {book}; skipping")
            continue
        body = [p for p in _extract(raw) if len(p) >= 20]
        print(f"    book {book}: {len(body)} paragraphs")
        out_paragraphs.append("")
        out_paragraphs.append(f"ΒΙΒΛΙΟΝ {book}")
        out_paragraphs.append("")
        out_paragraphs.extend(body)
        time.sleep(delay)
    rendered = "\n\n".join(out_paragraphs).strip() + "\n"
    dest = out_dir / "meditations_grc.txt"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(rendered, encoding="utf-8")
    print(f"  → {dest} ({len(rendered):,} chars)")
    return dest


def fetch_english(*, out_dir: Path) -> Path:
    print(f"\n=== meditations_en.txt: PG {_PG_ID} ===")
    url = f"https://www.gutenberg.org/cache/epub/{_PG_ID}/pg{_PG_ID}.txt"
    raw = _fetch(url)
    body = raw.decode("utf-8", errors="replace")
    dest = out_dir / "meditations_en.txt"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(body, encoding="utf-8")
    print(f"  → {dest} ({len(body):,} chars)")
    return dest


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--data-root",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data",
    )
    ap.add_argument(
        "--delay",
        type=float,
        default=1.5,
    )
    args = ap.parse_args()
    out_dir = args.data_root / "marcus_aurelius" / "raw"
    fetch_greek(out_dir=out_dir, delay=args.delay)
    fetch_english(out_dir=out_dir)


if __name__ == "__main__":
    main()
