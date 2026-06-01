"""Shared HTTP fetch helper for the Perseus per-author download scripts."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from _download import USER_AGENT, fetch_bytes_with_retry


def doc_id(num_suffix: str) -> str:
    return f"Perseus:text:1999.01.{num_suffix}"


def download_one(
    *,
    base_url: str,
    doc: str,
    dest: Path,
    user_agent: str,
    retries: int = 12,
    timeout: float = 180,
) -> None:
    """Fetch one Perseus dltext URL with retries on transient failures."""

    url = f"{base_url}?doc={quote(doc, safe='')}"
    data = fetch_bytes_with_retry(
        url,
        timeout=timeout,
        retries=retries,
        user_agent=user_agent,
        extra_headers={
            "Accept": "application/xml,text/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            # Some caches/WAFs behave better when the referer is the project site.
            "Referer": "https://www.perseus.tufts.edu/",
        },
        backoff_initial=5.0,
        backoff_max=120.0,
    )
    dest.write_bytes(data)


# Default identity for scripts that don't override USER_AGENT.
DEFAULT_USER_AGENT = USER_AGENT
