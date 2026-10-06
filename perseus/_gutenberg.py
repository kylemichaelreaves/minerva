"""Shared Project Gutenberg fetch helpers for perseus/download_*.py scripts."""

from __future__ import annotations

import re

from _download import USER_AGENT, fetch_bytes_with_retry

_PG_START = re.compile(
    r"\*\*\*\s*START OF (?:THIS |THE )?PROJECT GUTENBERG E[BO]+OK[^\*]*\*\*\*",
    re.IGNORECASE,
)
_PG_END = re.compile(
    r"\*\*\*\s*END OF (?:THIS |THE )?PROJECT GUTENBERG E[BO]+OK[^\*]*\*\*\*",
    re.IGNORECASE,
)


def pg_txt_url(ebook_id: int) -> str:
    return f"https://www.gutenberg.org/cache/epub/{ebook_id}/pg{ebook_id}.txt"


def fetch(url: str, *, timeout: float = 60, retries: int = 8) -> bytes:
    """GET with exponential backoff on transient HTTP/network errors."""

    return fetch_bytes_with_retry(
        url,
        timeout=timeout,
        retries=retries,
        user_agent=USER_AGENT,
        extra_headers={
            "Accept": "text/plain,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        },
        backoff_initial=5.0,
        backoff_max=120.0,
    )


def strip_pg_boilerplate(raw: str) -> str:
    start = _PG_START.search(raw)
    end = _PG_END.search(raw)
    if not start or not end or end.start() <= start.end():
        print("  WARN: PG START/END markers not both found; returning raw text.")
        return raw
    return raw[start.end() : end.start()].strip() + "\n"


def verify_language(raw: str, expected: str) -> None:
    """Raise if Gutenberg's ``Language:`` header doesn't match *expected*."""

    m = re.search(r"^Language:\s*(.+)$", raw[:4000], re.MULTILINE)
    # A missing header fails too: a wrong PG ID is likeliest to show up as an
    # artefact that is not the shape we expected at all (#499). Every PG id
    # this repo fetches carries the header within its first ~760 bytes.
    if m is None:
        raise RuntimeError(
            f"Gutenberg download has no Language: header in its first 4000 "
            f"chars; expected {expected!r}. Wrong PG ID, or not a PG text?"
        )
    if m.group(1).strip().lower() != expected.lower():
        raise RuntimeError(
            f"Gutenberg header says Language: {m.group(1).strip()!r}; "
            f"expected {expected!r}. Wrong PG ID?"
        )


def fetch_pg_text(ebook_id: int, *, language: str) -> str:
    """Download one PG ``.txt`` ebook and return the body without boilerplate."""

    url = pg_txt_url(ebook_id)
    print(f"GET {url}")
    raw = fetch(url).decode("utf-8")
    verify_language(raw, language)
    return strip_pg_boilerplate(raw)
