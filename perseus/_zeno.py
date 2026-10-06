"""Shared BFS crawler for the zeno.org downloaders.

Five scripts — ``download_hegel_de``, ``download_kant_de``,
``download_schiller_de``, ``download_marx_zeno`` and
``download_nietzsche_de`` — each carried their own copy of this walk
(#501). The copies agreed on everything that mattered except one thing
they all got wrong the same way: a bare ``except Exception`` around the
page fetch that printed ``[skip]`` and ``continue``d. A failed page's
links were never enqueued, so its whole subtree dropped out of the dump,
the file was written anyway, and the script exited 0.

Here a page that still fails after :func:`_download.fetch_with_retry`'s
own backoff is *collected*: :func:`run_works` withholds that work's file,
lists every failed path, and returns a non-zero exit code — unless the
caller passes ``allow_partial=True`` (``--allow-partial``), in which case
the partial dump is written and the failures are still listed. Only the
network/HTTP errors a fetch is expected to raise are caught; anything
else is a bug and propagates.

This module sits on top of ``_download.py`` and owns nothing below the
crawl: fetching, retrying, decoding and thread-pool fan-out all delegate
there.
"""

from __future__ import annotations

import argparse
import http.client
import re
import tempfile
import time
import urllib.parse
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import NamedTuple

from _download import RateLimiter, fetch_parallel, fetch_with_retry

ZENO_ROOT = "http://www.zeno.org"
ZENO_ENCODING = "iso-8859-1"

# What a fetch is *expected* to raise once the retry helper has given up.
# `urllib.error.URLError` / `HTTPError`, socket timeouts and connection
# resets are all `OSError`; `IncompleteRead` is an `HTTPException`.
FETCH_ERRORS: tuple[type[BaseException], ...] = (OSError, http.client.HTTPException)

Fetch = Callable[[str], str]
LinkFilter = Callable[[str, str], list[str]]

_HREF_RE = re.compile(r'href="([^"]+)"', re.IGNORECASE)


def fetch_zeno(url: str) -> str:
    """GET a zeno.org page with the shared retry/backoff, decoded as
    ISO-8859-1 (zeno's declared charset)."""

    return fetch_with_retry(url, encoding=ZENO_ENCODING)


def title_to_path(prefix: str, title: str) -> str:
    """Work title → zeno URL path under ``prefix``.

    zeno writes spaces as ``+`` and percent-encodes non-ASCII. ``:``,
    ``[`` and ``]`` are deliberately left out of ``safe``: zeno encodes
    those three in its own outbound hrefs (``%3A``/``%5B``/``%5D``), and
    :func:`extract_links` matches children by prefix, so leaving them
    literal silently stops the crawl at the first page (#420).
    """

    return prefix + "/" + urllib.parse.quote(title.replace(" ", "+"), safe="+,./")


def _site_path(raw: str, site_root: str) -> str | None:
    if raw.startswith(site_root):
        raw = raw[len(site_root) :]
    if not raw.startswith("/"):
        return None
    return raw.split("#", 1)[0].split("?", 1)[0]


def extract_links(html: str, root_path: str, *, site_root: str = ZENO_ROOT) -> list[str]:
    """Paths under ``root_path`` linked from ``html``, in document order.

    Fragments and queries are stripped (so footnote anchors collapse onto
    their page), the root itself is excluded, and duplicates are dropped.
    The prefix match has no ``/`` boundary — measured 2026-10-06 over all
    4,125 ``ZENO_PAGE`` markers in the five crawlers' dumps, none crossed
    into a sibling work, so the looser rule is kept as-is.
    """

    out: list[str] = []
    seen: set[str] = set()
    for raw in _HREF_RE.findall(html):
        path = _site_path(raw, site_root)
        if path is None or path == root_path or path in seen:
            continue
        if not path.startswith(root_path):
            continue
        seen.add(path)
        out.append(path)
    return out


@dataclass
class CrawlResult:
    """Outcome of one :func:`crawl`.

    ``failures`` holds ``(path, reason)`` for every page that could not be
    fetched; its subtree is missing from ``pages`` unless reachable some
    other way. ``truncated`` is true when ``max_pages`` stopped the walk
    with paths still queued.
    """

    pages: list[tuple[str, str]] = field(default_factory=list)
    failures: list[tuple[str, str]] = field(default_factory=list)
    truncated: bool = False


def _fetch_batch(
    paths: Sequence[str],
    *,
    fetch: Fetch,
    jobs: int,
    limiter: RateLimiter | None,
    delay: float,
    site_root: str,
) -> list[str | BaseException]:
    """Fetch ``paths`` in order; each slot is the HTML or the expected
    fetch error. Unexpected exceptions propagate."""

    if jobs > 1:
        fetched = fetch_parallel(
            [site_root + p for p in paths], jobs=jobs, limiter=limiter, fetch=fetch
        )
        out: list[str | BaseException] = [res for _, res in fetched]
        for res in out:
            if isinstance(res, BaseException) and not isinstance(res, FETCH_ERRORS):
                raise res
        return out
    results: list[str | BaseException] = []
    for p in paths:
        try:
            results.append(fetch(site_root + p))
        except FETCH_ERRORS as exc:
            results.append(exc)
        time.sleep(delay)
    return results


def crawl(
    root_path: str,
    *,
    max_pages: int,
    fetch: Fetch = fetch_zeno,
    link_filter: LinkFilter = extract_links,
    delay: float = 1.5,
    jobs: int = 1,
    site_root: str = ZENO_ROOT,
) -> CrawlResult:
    """BFS-walk ``root_path``'s subtree. Pages come back in visit order.

    ``jobs=1`` fetches one page at a time and sleeps ``delay`` after each.
    ``jobs>1`` takes ``jobs`` paths off the queue per round and fetches
    them through :func:`_download.fetch_parallel` with a per-host
    ``RateLimiter(delay)``; results are consumed in queue order, so the
    visit order does not depend on ``jobs``.
    """

    result = CrawlResult()
    queue: list[str] = [root_path]
    seen: set[str] = {root_path}
    limiter = RateLimiter(min_interval=delay) if jobs > 1 else None
    while queue and len(result.pages) < max_pages:
        take = min(max(jobs, 1), max_pages - len(result.pages))
        batch, queue = queue[:take], queue[take:]
        fetched = _fetch_batch(
            batch, fetch=fetch, jobs=jobs, limiter=limiter, delay=delay, site_root=site_root
        )
        for path, res in zip(batch, fetched, strict=True):
            if isinstance(res, BaseException):
                print(f"  [FAILED] {path}: {res}")
                result.failures.append((path, str(res)))
                continue
            result.pages.append((path, res))
            decoded = urllib.parse.unquote(path)
            print(f"  [{len(result.pages):>3}] {decoded[-80:]:<80}  {len(res):>7,} bytes")
            # dict.fromkeys: a custom link_filter need not dedup its own output.
            fresh = [c for c in dict.fromkeys(link_filter(res, root_path)) if c not in seen]
            seen.update(fresh)
            queue.extend(fresh)
    result.truncated = bool(queue)
    if result.truncated:
        print(f"  (hit max_pages={max_pages}; stopping with {len(queue)} path(s) unvisited)")
    return result


def render_pages(pages: Iterable[tuple[str, str]]) -> str:
    """Concatenate pages with the ``<!-- ZENO_PAGE: … -->`` markers the
    ``split_zeno`` splitter anchors on."""

    return "\n\n".join(
        f"<!-- ZENO_PAGE: {urllib.parse.unquote(p)} -->\n{html}" for p, html in pages
    )


class ZenoWork(NamedTuple):
    """One output file. ``label`` (a human title) switches the header to
    ``=== file: label ===`` plus a ``URL:`` line; without it the header
    shows the decoded root path."""

    filename: str
    root_path: str
    label: str | None = None


def _print_header(work: ZenoWork, site_root: str) -> None:
    if work.label is None:
        print(f"\n=== {work.filename}: {urllib.parse.unquote(work.root_path)} ===")
        return
    print(f"\n=== {work.filename}: {work.label} ===")
    print(f"  URL: {site_root}{work.root_path}")


def _print_failures(failed: list[tuple[str, list[tuple[str, str]]]], allow_partial: bool) -> None:
    total = sum(len(f) for _, f in failed)
    print(f"\n=== {total} PAGE(S) FAILED in {len(failed)} work(s) ===")
    for filename, failures in failed:
        for path, reason in failures:
            print(f"  {filename}  {urllib.parse.unquote(path)}: {reason}")
    if allow_partial:
        print("  --allow-partial: partial dumps were written; their subtrees are missing.")
    else:
        print("  Those works were NOT written. Re-run, or pass --allow-partial to keep them.")


def run_works(
    works: Iterable[ZenoWork],
    out_dir: Path,
    *,
    max_pages: int,
    delay: float = 1.5,
    jobs: int = 1,
    allow_partial: bool = False,
    fetch: Fetch = fetch_zeno,
    site_root: str = ZENO_ROOT,
) -> int:
    """Crawl each work and write ``out_dir/<filename>``. Returns the exit
    code: 0 when every page was fetched (or ``allow_partial``), else 1.

    A work with any failed page is withheld unless ``allow_partial``, so a
    good dump already on disk is never overwritten by a truncated one.
    """

    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    failed: list[tuple[str, list[tuple[str, str]]]] = []
    for work in works:
        _print_header(work, site_root)
        result = crawl(
            work.root_path,
            max_pages=max_pages,
            fetch=fetch,
            delay=delay,
            jobs=jobs,
            site_root=site_root,
        )
        if result.failures:
            failed.append((work.filename, result.failures))
        if not result.pages or (result.failures and not allow_partial):
            print(f"  {work.filename} not written")
            continue
        out_path = out_dir / work.filename
        out_path.write_text(render_pages(result.pages), encoding="utf-8")
        print(f"  → {out_path} ({len(result.pages)} pages, {out_path.stat().st_size:,} bytes)")
        written.append(out_path)

    print(f"\nDone. Wrote {len(written)} file(s):")
    for p in written:
        print(f"  {p}")
    if not failed:
        return 0
    _print_failures(failed, allow_partial)
    return 0 if allow_partial else 1


def add_crawl_args(ap: argparse.ArgumentParser) -> None:
    """The flags every zeno crawler shares. Each script adds its own
    output-location flag (``--out`` or ``--data-root``)."""

    ap.add_argument(
        "--delay",
        type=float,
        default=1.5,
        help="Seconds between requests (default: 1.5; please be polite to zeno.org).",
    )
    ap.add_argument(
        "--only",
        nargs="*",
        default=None,
        help="Restrict to these output filenames.",
    )
    ap.add_argument(
        "--jobs",
        type=int,
        default=1,
        help=(
            "Parallel fetch workers (default: 1 — sequential). When >1, that many "
            "queued paths are fetched at a time under a per-host RateLimiter(delay). "
            "Cap at 2-3 for zeno.org."
        ),
    )
    ap.add_argument(
        "--allow-partial",
        action="store_true",
        help=(
            "Write a work even if some of its pages failed after retries, and exit 0. "
            "Default: withhold it, list the failed paths, and exit 1."
        ),
    )


def select_works(works: Sequence[ZenoWork], only: Sequence[str] | None) -> list[ZenoWork]:
    """``works`` filtered to the ``--only`` filenames (all when unset)."""

    return [w for w in works if not only or w.filename in only]


# Where a crawl may write. The output directory arrives from a CLI flag, so
# it is resolved and confined before anything is created (SonarCloud
# pythonsecurity:S8707). The repo covers `data/`; the temp dir covers the
# before/after comparison crawls a refactor is checked with.
_REPO_ROOT = Path(__file__).resolve().parent.parent
_ALLOWED_OUT_BASES = (
    _REPO_ROOT,
    Path(tempfile.gettempdir()).resolve(),
    Path("/tmp").resolve(),
)


def _confined_out_dir(out_dir: Path) -> Path:
    resolved = out_dir.resolve()
    if not any(resolved.is_relative_to(base) for base in _ALLOWED_OUT_BASES):
        raise SystemExit(f"refusing to write outside the repo or the temp dir: {resolved}")
    return resolved


def main_for(
    works: Sequence[ZenoWork], out_dir: Path, args: argparse.Namespace, *, max_pages: int
) -> int:
    """Run ``works`` with the parsed :func:`add_crawl_args` flags."""

    return run_works(
        select_works(works, args.only),
        _confined_out_dir(out_dir),
        max_pages=max_pages,
        delay=args.delay,
        jobs=args.jobs,
        allow_partial=args.allow_partial,
    )


__all__ = [
    "FETCH_ERRORS",
    "ZENO_ENCODING",
    "ZENO_ROOT",
    "CrawlResult",
    "ZenoWork",
    "add_crawl_args",
    "crawl",
    "extract_links",
    "fetch_zeno",
    "main_for",
    "render_pages",
    "run_works",
    "select_works",
    "title_to_path",
]
