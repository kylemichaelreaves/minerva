"""Shared HTTP fetch helper for the Perseus per-author download scripts."""

from __future__ import annotations

import time
import urllib.error
from collections.abc import Callable
from pathlib import Path
from urllib.parse import quote

from _download import USER_AGENT, FailureAccumulator, fetch_bytes_with_retry


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


def _fetch_one(
    *,
    download_one_fn: Callable[..., None],
    base_url: str,
    doc: str,
    path: Path,
    user_agent: str,
    skip_existing: bool,
    failures: FailureAccumulator,
) -> bool:
    """Download one dltext item, recording (not raising) a per-item failure.

    Returns whether the caller's pacing delay should still apply — true
    on a skip or a success, false on a recorded failure (matching the
    per-script behaviour this was extracted from).
    """

    if skip_existing and path.is_file() and path.stat().st_size > 0:
        print("  skip (already exists)")
        return True
    try:
        download_one_fn(base_url=base_url, doc=doc, dest=path, user_agent=user_agent)
    except urllib.error.HTTPError as e:
        failures.record(path.name, f"HTTP {e.code}: {e.reason}")
        return False
    except urllib.error.URLError as e:
        failures.record(path.name, f"URL error: {e.reason}")
        return False
    return True


def run_dltext_batches(
    *,
    base_url: str,
    batches: list[tuple[str, list[tuple[str, str]]]],
    out: Path,
    filename: Callable[[str], str],
    delay: float,
    user_agent: str,
    skip_existing: bool,
    download_one_fn: Callable[..., None],
    unit: str = "works",
) -> int:
    """Download every ``(suffix, stem)`` pair across ``batches``, isolating
    per-item HTTP failures so one dead work doesn't abort the rest (#452).

    ``download_one_fn`` is passed in rather than called directly so tests
    can monkeypatch a script's own module-level ``download_one`` and have
    it take effect here.  Returns the process exit code.
    """

    total = sum(len(vols) for _, vols in batches)
    n = 0
    failures = FailureAccumulator()
    for label, vols in batches:
        print(f"=== {label} ({len(vols)} {unit}) ===")
        for suffix, stem in vols:
            n += 1
            doc = doc_id(suffix)
            path = out / filename(stem)
            print(f"[{n}/{total}] {doc} -> {path.name}")
            ok = _fetch_one(
                download_one_fn=download_one_fn,
                base_url=base_url,
                doc=doc,
                path=path,
                user_agent=user_agent,
                skip_existing=skip_existing,
                failures=failures,
            )
            if ok and n < total:
                time.sleep(delay)
        print()

    print(f"Done. Wrote {total} file(s) under {out.resolve()}")
    return failures.exit_code()


# Default identity for scripts that don't override USER_AGENT.
DEFAULT_USER_AGENT = USER_AGENT
