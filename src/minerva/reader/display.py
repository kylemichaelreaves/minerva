"""Display-title helpers for RTL and trilingual works.

Each scripture corpus stores its books under the canonical English
title in ``chunks_full.work`` (so retrieval and cross-references
work uniformly across translations) but renders a native-language
title in the Reader sidebar + heading via ``display_title``. The
optional ``display_subtitle`` carries a transliteration plus the
English equivalent so readers who don't know the source script
can still browse.

Coverage today:

* **Hebrew Bible** — Hebrew script + transliteration + English.
* **Quran** — Arabic script + transliteration + English.
* **Vulgate** — Latin title + English subtitle.
* **Luther Bibel 1545 / 1912** — German title + English subtitle.
"""

from __future__ import annotations

from ..authors.hebrew_mt_works import find_book_by_english as _find_mt_book
from ..authors.luther_book_names import german_name as _luther_german
from ..authors.quran_works import find_surah_by_transliteration as _find_surah
from ..authors.vulgate_book_names import latin_name as _vulgate_latin


def trilingual_display(
    author: str, work: str, fallback_title: str
) -> tuple[str, str | None]:
    """Return ``(display_title, display_subtitle)`` for a (author, work)."""

    if author == "Hebrew Bible":
        book = _find_mt_book(work)
        if book is not None:
            return book.hebrew_script, f"{book.hebrew_transliterated} · {book.english}"
    if author == "Quran":
        surah = _find_surah(work)
        if surah is not None:
            return surah.arabic, f"{surah.transliteration} · {surah.english}"
    if author == "Vulgate":
        latin = _vulgate_latin(work)
        if latin is not None:
            # Suppress the subtitle when the Latin and English names
            # coincide (Genesis, Exodus, Amos, Daniel, …) — otherwise
            # the Reader heading renders the same word twice.
            return latin, work if latin != work else None
    if author in ("Luther Bibel 1545", "Luther Bibel 1912"):
        german = _luther_german(work)
        if german is not None:
            return german, work if german != work else None
    return fallback_title, None
