"""Offline tests for ``perseus/_zeno.py`` — the shared zeno.org BFS crawler.

Five crawlers (Hegel, Kant, Schiller, Marx, Nietzsche) each carried their
own copy of this walk, and every copy caught a bare ``Exception`` around
the page fetch and ``continue``d (#501). A failed page's links were never
enqueued, so its whole subtree dropped out of the written file with one
``[skip]`` line on stdout and an exit status of 0.

No network: every test drives the crawl with a fake ``fetch`` over a dict
of path → HTML.
"""

from __future__ import annotations

import sys
import urllib.error
from pathlib import Path

import pytest

perseus_dir = Path(__file__).resolve().parents[1] / "perseus"
sys.path.insert(0, str(perseus_dir))
import _zeno as zeno  # noqa: E402

ROOT = "/Philosophie/M/Autor/Werk"


def _page(*hrefs: str) -> str:
    return "<html><body>" + "".join(f'<a href="{h}">x</a>' for h in hrefs) + "</body></html>"


# root → A, B; A → A/1, B (dup), root (back-link); B → B/1, A/1 (dup).
SITE: dict[str, str] = {
    ROOT: _page(f"{ROOT}/A", f"{ROOT}/B"),
    f"{ROOT}/A": _page(f"{ROOT}/A/1", f"{ROOT}/B", ROOT),
    f"{ROOT}/B": _page(f"{ROOT}/B/1", f"{ROOT}/A/1"),
    f"{ROOT}/A/1": _page(),
    f"{ROOT}/B/1": _page(),
}


class FakeSite:
    """Fake fetch over ``SITE``; records every URL it was asked for."""

    def __init__(self, site: dict[str, str], fail: dict[str, BaseException] | None = None):
        self.site = site
        self.fail = fail or {}
        self.calls: list[str] = []

    def __call__(self, url: str) -> str:
        self.calls.append(url)
        path = url.removeprefix(zeno.ZENO_ROOT)
        if path in self.fail:
            raise self.fail[path]
        return self.site[path]


def _http_error(path: str, code: int = 500) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(zeno.ZENO_ROOT + path, code, "boom", {}, None)  # type: ignore[arg-type]


# ── BFS order and dedup ────────────────────────────────────────────


@pytest.mark.parametrize("jobs", [1, 2, 3])
def test_crawl_visits_breadth_first_and_fetches_each_page_once(jobs):
    fake = FakeSite(SITE)
    result = zeno.crawl(ROOT, fetch=fake, max_pages=100, delay=0, jobs=jobs)

    assert [p for p, _ in result.pages] == [
        ROOT,
        f"{ROOT}/A",
        f"{ROOT}/B",
        f"{ROOT}/A/1",
        f"{ROOT}/B/1",
    ]
    # Dedup: back-links and cross-links never cause a second fetch.
    assert sorted(fake.calls) == sorted({zeno.ZENO_ROOT + p for p in SITE})
    assert len(fake.calls) == len(SITE)
    assert result.failures == []
    assert result.truncated is False


def test_crawl_stops_at_max_pages_and_says_it_was_truncated():
    result = zeno.crawl(ROOT, fetch=FakeSite(SITE), max_pages=2, delay=0)
    assert [p for p, _ in result.pages] == [ROOT, f"{ROOT}/A"]
    assert result.truncated is True


def test_crawl_cap_is_strict_under_parallel_batches():
    # jobs=3 fetches a batch of three; the cap must still hold.
    result = zeno.crawl(ROOT, fetch=FakeSite(SITE), max_pages=2, delay=0, jobs=3)
    assert len(result.pages) == 2
    assert result.truncated is True


def test_crawl_reaching_max_pages_exactly_with_nothing_left_is_not_truncated():
    result = zeno.crawl(ROOT, fetch=FakeSite(SITE), max_pages=len(SITE), delay=0)
    assert len(result.pages) == len(SITE)
    assert result.truncated is False


# ── link filter ────────────────────────────────────────────────────


def test_extract_links_keeps_only_subpages_of_the_root():
    html = _page(
        f"{zeno.ZENO_ROOT}{ROOT}/abs",  # absolute zeno URL → stripped to a path
        f"{ROOT}/frag#fnA1",  # fragment dropped
        f"{ROOT}/query?x=1",  # query dropped
        f"{ROOT}/frag#fnA1ref",  # same page after fragment strip → deduped
        ROOT,  # the root itself
        f"{ROOT}#top",  # the root via a fragment
        "/Philosophie/M/Autor/Anderes+Werk/X",  # another work
        "relative/link",  # not site-absolute
        "https://elsewhere.example/x",  # off-site
    )
    assert zeno.extract_links(html, ROOT) == [
        f"{ROOT}/abs",
        f"{ROOT}/frag",
        f"{ROOT}/query",
    ]


def test_crawl_uses_the_link_filter_it_is_given():
    seen_roots: list[str] = []

    def only_a(html: str, root_path: str) -> list[str]:
        seen_roots.append(root_path)
        return [
            p
            for p in zeno.extract_links(html, root_path)
            if p.removeprefix(root_path).startswith("/A")
        ]

    result = zeno.crawl(ROOT, fetch=FakeSite(SITE), link_filter=only_a, max_pages=100, delay=0)
    assert [p for p, _ in result.pages] == [ROOT, f"{ROOT}/A", f"{ROOT}/A/1"]
    assert set(seen_roots) == {ROOT}


def test_crawl_dedups_a_link_filter_that_repeats_itself():
    def doubled(html: str, root_path: str) -> list[str]:
        return [p for p in zeno.extract_links(html, root_path) for _ in range(2)]

    fake = FakeSite(SITE)
    result = zeno.crawl(ROOT, fetch=fake, link_filter=doubled, max_pages=100, delay=0)
    assert len(result.pages) == len(SITE)
    assert len(fake.calls) == len(SITE)


def test_title_to_path_encodes_like_zeno():
    # zeno writes spaces as `+` and percent-encodes `:`, `[`, `]` (#420).
    path = zeno.title_to_path("/P", "Über: [1. Fassung]")
    assert path == "/P/%C3%9Cber%3A+%5B1.+Fassung%5D"


# ── failures must not truncate silently ────────────────────────────


@pytest.mark.parametrize("jobs", [1, 2])
@pytest.mark.parametrize(
    "exc",
    [
        _http_error(f"{ROOT}/A"),
        urllib.error.URLError("connection reset"),
        TimeoutError("read timed out"),
    ],
    ids=["http", "url", "timeout"],
)
def test_failed_page_is_reported_not_dropped(exc, jobs):
    fake = FakeSite(SITE, fail={f"{ROOT}/A": exc})
    result = zeno.crawl(ROOT, fetch=fake, max_pages=100, delay=0, jobs=jobs)

    assert [path for path, _ in result.failures] == [f"{ROOT}/A"]
    # A/1 is only reachable through A *and* B here, so it survives; the
    # point is that A is named, not swallowed.
    assert f"{ROOT}/A" not in [p for p, _ in result.pages]


@pytest.mark.parametrize("jobs", [1, 2])
def test_unexpected_exception_is_not_swallowed(jobs):
    fake = FakeSite(SITE, fail={f"{ROOT}/B": ValueError("a bug, not a network error")})
    with pytest.raises(ValueError, match="a bug"):
        zeno.crawl(ROOT, fetch=fake, max_pages=100, delay=0, jobs=jobs)


def _works() -> list[zeno.ZenoWork]:
    return [zeno.ZenoWork("werk.html", ROOT)]


def test_run_works_fails_loudly_and_writes_nothing_when_a_page_failed(tmp_path, capsys):
    fake = FakeSite(SITE, fail={f"{ROOT}/B": _http_error(f"{ROOT}/B", 503)})
    code = zeno.run_works(_works(), tmp_path, fetch=fake, max_pages=100, delay=0)

    assert code != 0
    assert not (tmp_path / "werk.html").exists()
    out = capsys.readouterr().out
    assert f"{ROOT}/B" in out  # the failed path is listed in the summary
    assert "--allow-partial" in out


def test_run_works_allow_partial_writes_what_it_got_and_exits_zero(tmp_path, capsys):
    fake = FakeSite(SITE, fail={f"{ROOT}/B": _http_error(f"{ROOT}/B", 503)})
    code = zeno.run_works(
        _works(), tmp_path, fetch=fake, max_pages=100, delay=0, allow_partial=True
    )

    assert code == 0
    text = (tmp_path / "werk.html").read_text(encoding="utf-8")
    assert f"<!-- ZENO_PAGE: {ROOT}/A -->" in text
    assert f"<!-- ZENO_PAGE: {ROOT}/B -->" not in text
    # B's own child is lost with it, and the summary still says so.
    assert f"{ROOT}/B/1" not in text
    assert f"{ROOT}/B" in capsys.readouterr().out


def test_run_works_failed_root_fails_the_run(tmp_path):
    fake = FakeSite(SITE, fail={ROOT: urllib.error.URLError("dns")})
    assert zeno.run_works(_works(), tmp_path, fetch=fake, max_pages=100, delay=0) != 0
    assert not (tmp_path / "werk.html").exists()


def test_run_works_clean_crawl_writes_the_concatenated_dump(tmp_path):
    code = zeno.run_works(_works(), tmp_path, fetch=FakeSite(SITE), max_pages=100, delay=0)
    assert code == 0
    text = (tmp_path / "werk.html").read_text(encoding="utf-8")
    # Byte shape the five crawlers wrote and `split_zeno` consumes.
    assert text == "\n\n".join(
        f"<!-- ZENO_PAGE: {p} -->\n{SITE[p]}"
        for p in [ROOT, f"{ROOT}/A", f"{ROOT}/B", f"{ROOT}/A/1", f"{ROOT}/B/1"]
    )


def test_render_pages_unquotes_the_marker_path():
    out = zeno.render_pages([("/P/%C3%9Cber", "<p>x</p>")])
    assert out == "<!-- ZENO_PAGE: /P/Über -->\n<p>x</p>"


# ── delegation to the shared fetch layer ───────────────────────────


def test_fetch_zeno_delegates_to_retry_helper_as_latin1(monkeypatch):
    seen: dict[str, object] = {}

    def fake_fetch_with_retry(url: str, **kwargs: object) -> str:
        seen["url"] = url
        seen.update(kwargs)
        return "ok"

    monkeypatch.setattr(zeno, "fetch_with_retry", fake_fetch_with_retry)
    assert zeno.fetch_zeno("http://www.zeno.org/x") == "ok"
    assert seen["url"] == "http://www.zeno.org/x"
    assert seen["encoding"] == "iso-8859-1"


def test_parse_args_shared_flags():
    import argparse

    ap = argparse.ArgumentParser()
    zeno.add_crawl_args(ap)
    args = ap.parse_args(["--only", "a.html", "--jobs", "2", "--allow-partial"])
    assert args.only == ["a.html"]
    assert args.jobs == 2
    assert args.allow_partial is True
    assert args.delay == 1.5
    assert zeno.select_works(_works(), ["nope.html"]) == []
    assert zeno.select_works(_works(), None) == _works()


def _cli_args(**overrides):
    import argparse

    ap = argparse.ArgumentParser()
    zeno.add_crawl_args(ap)
    args = ap.parse_args([])
    for k, v in overrides.items():
        setattr(args, k, v)
    return args


def test_main_for_refuses_an_output_dir_outside_the_repo_and_temp(tmp_path):
    # The output directory comes from --out / --data-root. Anything outside
    # the repo or the temp dir is refused before a directory is created.
    with pytest.raises(SystemExit, match="outside"):
        zeno.main_for([], Path("/etc/zeno-out"), _cli_args(), max_pages=1)
    assert not Path("/etc/zeno-out").exists()


def test_main_for_accepts_a_temp_output_dir(tmp_path):
    assert zeno.main_for([], tmp_path / "out", _cli_args(), max_pages=1) == 0
