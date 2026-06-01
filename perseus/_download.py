"""Shared download primitives for the ``perseus/download_*.py`` family.

Phase 5 of the 2026-05-30 ingestion-bottleneck remediation II plan
extracts what was previously duplicated across ~40 scripts:

* ``USER_AGENT`` — single declared identity for our bulk fetches.
* :func:`fetch_with_retry` — GET with exponential backoff over the
  HTTP error codes worth retrying (408 / 425 / 429 / 5xx) and the
  URL-level errors (connection-reset, DNS timeout).
* :class:`RateLimiter` — per-host token bucket so the parallel
  fetcher cannot DDOS a source even with many worker threads.
* :func:`fetch_parallel` — thread-pool wrapper that pulls a list of
  URLs concurrently, applying the rate limiter per host.

Threads — not processes — because ``urllib.request.urlopen`` releases
the GIL while blocked on the socket. Each downloader script is
I/O-bound (bytes off the wire, then a single ``str.decode`` call);
the GIL is released long enough that 4–8 threads keep the connection
pool busy without the per-process memory cost.
"""

from __future__ import annotations

import http.client
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterable, Mapping
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

USER_AGENT = (
    "minerva-research/1.0 (local research; one-shot bulk fetch with delays)"
)

# HTTP status codes worth retrying. 408/425/429 are server-side
# "slow down / try again later"; 5xx is server transient. The full
# 5xx range is included so a 504 Gateway Timeout from a CDN doesn't
# need a per-call exception in the script that imports us.
_RETRY_CODES: frozenset[int] = frozenset(
    {408, 425, 429, 500, 502, 503, 504}
)


def fetch_bytes_with_retry(
    url: str,
    *,
    timeout: float = 30,
    retries: int = 8,
    user_agent: str = USER_AGENT,
    extra_headers: Mapping[str, str] | None = None,
    backoff_initial: float = 2.0,
    backoff_max: float = 60.0,
) -> bytes:
    """GET ``url`` with capped exponential backoff on transient errors.

    Returns raw response bytes. Non-retryable HTTP errors (404, 403,
    …) propagate immediately. Retries on 408/425/429/5xx, ``URLError``,
    and ``IncompleteRead`` (common on large TEI/HTML payloads).

    ``extra_headers`` are merged with ``User-Agent`` — use for Perseus
    ``Referer``, Wikisource ``Accept``, etc.
    """

    headers = {"User-Agent": user_agent}
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(url, headers=headers)
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            if e.code in _RETRY_CODES and attempt + 1 < retries:
                wait = min(backoff_max, backoff_initial * (2**attempt))
                print(
                    f"  HTTP {e.code}; retry in {wait:.0f}s "
                    f"({attempt + 1}/{retries})"
                )
                time.sleep(wait)
                continue
            raise
        except urllib.error.URLError as e:
            if attempt + 1 < retries:
                wait = min(backoff_max, backoff_initial * (2**attempt))
                print(
                    f"  URL error {e.reason!r}; retry in {wait:.0f}s "
                    f"({attempt + 1}/{retries})"
                )
                time.sleep(wait)
                continue
            raise
        except http.client.IncompleteRead as e:
            if attempt + 1 < retries:
                wait = min(backoff_max, backoff_initial * (2**attempt))
                partial = getattr(e, "partial", None)
                print(
                    f"  IncompleteRead ({partial} bytes); retry in {wait:.0f}s "
                    f"({attempt + 1}/{retries})"
                )
                time.sleep(wait)
                continue
            raise
    raise RuntimeError(  # pragma: no cover
        f"fetch_bytes_with_retry: exhausted {retries} retries for {url}"
    )


def fetch_with_retry(
    url: str,
    *,
    timeout: float = 30,
    retries: int = 8,
    encoding: str = "utf-8",
    user_agent: str = USER_AGENT,
    extra_headers: Mapping[str, str] | None = None,
    backoff_initial: float = 2.0,
    backoff_max: float = 60.0,
) -> str:
    """GET ``url`` with retries; decode as ``encoding``.

    Pass ``"iso-8859-1"`` for zeno.org; default ``utf-8`` for PG /
    archive.org / Gallica.
    """

    data = fetch_bytes_with_retry(
        url,
        timeout=timeout,
        retries=retries,
        user_agent=user_agent,
        extra_headers=extra_headers,
        backoff_initial=backoff_initial,
        backoff_max=backoff_max,
    )
    return data.decode(encoding)


class RateLimiter:
    """Per-host minimum-interval enforcer.

    Calls to :meth:`acquire` for the same host return no sooner than
    ``min_interval`` seconds apart. Different hosts are independent —
    parallel downloads across e.g. zeno.org + archive.org don't
    serialize on each other.

    Thread-safe; the typical use is one shared ``RateLimiter``
    passed into :func:`fetch_parallel` so multiple workers respect
    the same per-host budget.

    The implementation is the dumbest possible thing that works for
    our scale: a per-host last-call timestamp under a lock. We're
    talking 10K-page-class crawls, not millions; contention on the
    lock is fine.
    """

    def __init__(self, min_interval: float = 1.0) -> None:
        self.min_interval = min_interval
        self._last: dict[str, float] = {}
        self._lock = Lock()

    def acquire(self, host: str) -> None:
        with self._lock:
            now = time.monotonic()
            last = self._last.get(host, 0.0)
            wait = (last + self.min_interval) - now
            if wait > 0:
                time.sleep(wait)
                now = time.monotonic()
            self._last[host] = now


def fetch_parallel(
    urls: Iterable[str],
    *,
    jobs: int = 4,
    limiter: RateLimiter | None = None,
    encoding: str = "utf-8",
    timeout: float = 30,
    retries: int = 8,
) -> list[tuple[str, str | Exception]]:
    """Thread-pool fetch over ``urls``. Returns ``[(url, html | exc),
    ...]`` in INPUT order — callers can zip the result against the
    original list without re-correlating.

    Errors are returned, not raised, so one bad URL out of many
    doesn't kill the batch. The caller decides whether to retry,
    log, or surface to the user.
    """

    url_list = list(urls)
    results: list[tuple[str, str | Exception]] = [
        (u, RuntimeError("unassigned")) for u in url_list
    ]

    def _one(idx: int, url: str) -> None:
        if limiter is not None:
            host = urllib.parse.urlsplit(url).netloc
            limiter.acquire(host)
        try:
            html = fetch_with_retry(
                url,
                timeout=timeout,
                retries=retries,
                encoding=encoding,
            )
            results[idx] = (url, html)
        except Exception as exc:
            results[idx] = (url, exc)

    with ThreadPoolExecutor(max_workers=jobs) as pool:
        for idx, url in enumerate(url_list):
            pool.submit(_one, idx, url)

    return results


__all__ = [
    "USER_AGENT",
    "RateLimiter",
    "fetch_bytes_with_retry",
    "fetch_parallel",
    "fetch_with_retry",
]
