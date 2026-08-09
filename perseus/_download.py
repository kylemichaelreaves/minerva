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
from collections.abc import Callable, Iterable, Mapping
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
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
    min_bytes: int = 0,
    reject_markers: tuple[str, ...] = (),
) -> bytes:
    """GET ``url`` with capped exponential backoff on transient errors.

    Returns raw response bytes. Non-retryable HTTP errors (404, 403,
    …) propagate immediately. Retries on 408/425/429/5xx, ``URLError``,
    and ``IncompleteRead`` (common on large TEI/HTML payloads).

    ``extra_headers`` are merged with ``User-Agent`` — use for Perseus
    ``Referer``, Wikisource ``Accept``, etc.

    When ``min_bytes`` is set, responses shorter than that threshold
    raise ``RuntimeError`` (guards parking-page / empty-body traps).
    ``reject_markers`` are UTF-8 substrings that invalidate a body even
    when it passes the size gate — e.g. mlwerke.de's t-online stub.
    """

    headers = {"User-Agent": user_agent}
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(url, headers=headers)
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = resp.read()
            if min_bytes and len(data) < min_bytes:
                raise RuntimeError(
                    f"response too small ({len(data)} bytes < {min_bytes})"
                )
            if reject_markers:
                text = data.decode("utf-8", errors="replace")
                for marker in reject_markers:
                    if marker in text:
                        raise RuntimeError(
                            f"response rejected: found marker {marker!r}"
                        )
            return data
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
    min_bytes: int = 0,
    reject_markers: tuple[str, ...] = (),
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
        min_bytes=min_bytes,
        reject_markers=reject_markers,
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


# HTTP request headers shared by the HTML/REST scrapers. Identical
# across the Wikisource / Corpus Thomisticum / PG / githubusercontent
# downloaders — they all want HTML back and announce English.
HTML_HEADERS: dict[str, str] = {
    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def make_fetcher(
    *,
    timeout: float = 60,
    retries: int = 8,
) -> Callable[..., bytes]:
    """Return the ``_fetch(url, *, timeout=60, retries=8) -> bytes``
    callable that the HTML scrapers all duplicated verbatim.

    The returned callable fetches raw bytes with the canonical
    :data:`USER_AGENT`, :data:`HTML_HEADERS`, and the gentle
    5s→120s backoff the scrapers use against small academic sources.
    """

    def _fetch(url: str, *, timeout: float = timeout, retries: int = retries) -> bytes:
        return fetch_bytes_with_retry(
            url,
            timeout=timeout,
            retries=retries,
            user_agent=USER_AGENT,
            extra_headers=HTML_HEADERS,
            backoff_initial=5.0,
            backoff_max=120.0,
        )

    return _fetch


# HTML void elements: they have no end tag, so they must never move the
# skip-subtree depth counter. Getting this wrong loses the whole rest of
# the document — see `handle_starttag`.
_VOID_TAGS = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }
)


class ParagraphExtractor(HTMLParser):
    """``HTMLParser`` that emits whitespace-collapsed paragraph strings.

    Text inside any tag in ``skip_tags`` (and its descendants) is
    dropped; an end-tag in ``break_end_tags`` flushes the accumulated
    buffer as one paragraph. When ``skip_class_tokens`` is given, any
    element whose ``class`` attribute contains one of those tokens is
    skipped along with its subtree — the class-aware variant the
    Wikisource / mlwerke scrapers use to drop editorial apparatus.

    ``skip_id_tokens`` does the same against the ``id`` attribute.
    Class tokens are not always enough: web.archive.org marks its
    injected toolbar with ``id="wm-ipp"`` / ``id="donato"`` and gives
    those elements no distinguishing class at all, so a class-only
    skip set cannot see the wrapper it was written to strip (#152).
    Passing either set enables the class/id-aware code path.
    """

    def __init__(
        self,
        *,
        skip_tags: Iterable[str] = (),
        break_end_tags: Iterable[str] = (),
        skip_class_tokens: Iterable[str] | None = None,
        skip_id_tokens: Iterable[str] | None = None,
    ) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_tags = frozenset(skip_tags)
        self._break_end_tags = frozenset(break_end_tags)
        self._skip_class_tokens = (
            frozenset(skip_class_tokens) if skip_class_tokens is not None else None
        )
        self._skip_id_tokens = (
            frozenset(skip_id_tokens) if skip_id_tokens is not None else None
        )
        self._skip_depth = 0
        self._buf: list[str] = []
        self.paragraphs: list[str] = []

    @property
    def _attr_aware(self) -> bool:
        """True when a class or id skip set was supplied."""

        return self._skip_class_tokens is not None or self._skip_id_tokens is not None

    def _should_skip(self, attrs: list[tuple[str, str | None]]) -> bool:
        if not self._attr_aware:
            return False
        for name, value in attrs:
            if value is None:
                continue
            tokens = self._skip_class_tokens if name == "class" else (
                self._skip_id_tokens if name == "id" else None
            )
            if tokens is not None and any(tok in tokens for tok in value.split()):
                return True
        return False

    def _flush(self) -> None:
        text = " ".join("".join(self._buf).split()).strip()
        if text:
            self.paragraphs.append(text)
        self._buf.clear()

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        # A void element has no end tag, so counting it would strand the
        # depth above zero and silently swallow every following
        # paragraph. `<br/>` survives only because HTMLParser routes the
        # self-closed form through handle_startendtag (start *and* end);
        # the bare `<br>` old-school sources emit does not.
        void = tag in _VOID_TAGS
        if self._attr_aware:
            if self._skip_depth:
                if not void:
                    self._skip_depth += 1
                return
            if tag in self._skip_tags or self._should_skip(attrs):
                if not void:
                    self._skip_depth = 1
                return
            if tag == "p":
                self._flush()
            return
        if tag in self._skip_tags:
            if not void:
                self._skip_depth += 1
            return
        if tag in self._break_end_tags:
            self._flush()

    def handle_endtag(self, tag: str) -> None:
        # Symmetry with handle_starttag: a void element never moved the
        # counter up, so it must not move it down either. HTMLParser
        # synthesises this call for the self-closed `<br/>` form via
        # handle_startendtag, and decrementing here would end the skip one
        # level early and leak the very chrome we are inside.
        if tag in _VOID_TAGS:
            return
        if self._attr_aware:
            if self._skip_depth:
                self._skip_depth -= 1
                return
            if tag in self._break_end_tags:
                self._flush()
            return
        if tag in self._skip_tags:
            if self._skip_depth > 0:
                self._skip_depth -= 1
            return
        if tag in self._break_end_tags:
            self._flush()

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        self._buf.append(data)

    def close(self) -> None:  # type: ignore[override]
        super().close()
        self._flush()


def render_chunks(chunks: list[tuple[str, str]]) -> str:
    """Emit ``(marker, body)`` chunks in the canonical raw-text shape::

        [MARKER]
        <body>

        [MARKER]
        <body>

    Each marker sits on its own line (the corpus splitters anchor on
    ``^[MARKER]$``), separated from the next chunk by a blank line.
    """

    pieces: list[str] = []
    for marker, body in chunks:
        pieces.append(marker)
        pieces.append("")
        pieces.append(body)
    return "\n".join(pieces).strip() + "\n"


_ROMAN_DIGIT = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}


def roman_to_int(s: str) -> int | None:
    """Subtractive-rule Roman numeral → int; ``None`` on non-Roman input.

    Used in heading scans where the surrounding context is already
    known to be numeric; never trusted blind.
    """

    if not s:
        return None
    s = s.upper()
    if any(ch not in _ROMAN_DIGIT for ch in s):
        return None
    total = 0
    prev = 0
    for ch in reversed(s):
        v = _ROMAN_DIGIT[ch]
        if v < prev:
            total -= v
        else:
            total += v
        prev = v
    return total


__all__ = [
    "HTML_HEADERS",
    "USER_AGENT",
    "ParagraphExtractor",
    "RateLimiter",
    "fetch_bytes_with_retry",
    "fetch_parallel",
    "fetch_with_retry",
    "make_fetcher",
    "render_chunks",
    "roman_to_int",
]
