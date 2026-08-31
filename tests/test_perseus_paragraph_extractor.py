"""Behaviour of the shared ``ParagraphExtractor`` (issue #152).

The class-aware extractor is what every HTML scraper uses to keep site
chrome out of corpus text, and chrome bleed is not cosmetic — editorial
and navigation text landing in chunks is what produces spurious
cross-references downstream.

Two properties are pinned here that #152's investigation showed were
unpinned, and one of which was silently wrong:

* skipping by ``id``, because web.archive.org marks its injected toolbar
  with ``id="wm-ipp"`` and gives it no distinguishing class at all — a
  class-only skip set cannot see it;
* void elements must not move the subtree-depth counter, or the rest of
  the document is discarded without a word.

Network is never touched: every test feeds markup in directly.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PERSEUS = Path(__file__).resolve().parents[1] / "perseus"


@pytest.fixture(autouse=True)
def _perseus_on_path():
    sys.path.insert(0, str(PERSEUS))
    try:
        yield
    finally:
        sys.path.remove(str(PERSEUS))
        sys.modules.pop("_download", None)


def _extract(html: str, **kwargs) -> list[str]:
    from _download import ParagraphExtractor

    p = ParagraphExtractor(
        skip_tags={"script", "style", "table"},
        break_end_tags={"p", "li", "div"},
        **kwargs,
    )
    p.feed(html)
    p.close()
    return p.paragraphs


class TestVoidTagsDoNotStrandTheSkipDepth:
    """A void element has no end tag, so counting it as a nesting level
    leaves the depth permanently above zero — and every paragraph after
    it is dropped in silence.

    The self-closed form always worked, because HTMLParser routes
    ``<br/>`` through ``handle_startendtag`` (start *and* end). The bare
    form old-school sources emit did not, which is the whole bug.
    """

    @pytest.mark.parametrize("void", ["br", "img", "input", "hr", "meta", "wbr"])
    def test_bare_void_tag_inside_skipped_subtree(self, void):
        html = f'<div class="chrome"><{void}>junk</div><p>REAL TEXT</p>'
        assert _extract(html, skip_class_tokens={"chrome"}) == ["REAL TEXT"]

    def test_self_closed_void_tag_inside_skipped_subtree(self):
        html = '<div class="chrome"><br/>junk</div><p>REAL TEXT</p>'
        assert _extract(html, skip_class_tokens={"chrome"}) == ["REAL TEXT"]

    def test_void_tag_in_skip_tags_on_the_plain_path(self):
        """The non-attribute path counts ``skip_tags`` the same way, so a
        void tag named there would strand it identically."""

        html = "<img>junk<p>REAL TEXT</p>"
        from _download import ParagraphExtractor

        p = ParagraphExtractor(skip_tags={"img"}, break_end_tags={"p"})
        p.feed(html)
        p.close()
        assert "REAL TEXT" in p.paragraphs

    def test_many_bare_void_tags_do_not_accumulate(self):
        html = '<div class="chrome"><br><br><img><input>junk</div><p>FIRST</p><p>SECOND</p>'
        assert _extract(html, skip_class_tokens={"chrome"}) == ["FIRST", "SECOND"]


class TestUnbalancedEndTagsDoNotEndTheSkipEarly:
    """Counting start and end tags assumes well-formed markup, and
    ``HTMLParser`` does not synthesise the end tags a browser would
    (#297). A stray ``</form>`` unwound the counter to zero partway
    through web.archive.org's toolbar, and four chrome paragraphs came
    out — with no error and no warning.

    A tag stack fixes it: an end tag closes the innermost element of the
    same name, and one that matches nothing open is ignored, exactly as
    a browser does.
    """

    def test_stray_end_tag_with_no_matching_start_is_ignored(self):
        # The wayback shape: `</form>` arrives inside the toolbar with no
        # <form> ever opened, so it must not close the <div> skip.
        html = '<div id="wm-ipp-base">269 captures</form>Collection</div><p>REAL</p>'
        assert _extract(html, skip_id_tokens={"wm-ipp-base"}) == ["REAL"]

    def test_several_stray_end_tags_do_not_accumulate(self):
        html = '<div id="wm-ipp-base">a</form>b</table>c</tr></div><p>REAL</p>'
        assert _extract(html, skip_id_tokens={"wm-ipp-base"}) == ["REAL"]

    def test_unclosed_children_do_not_outlive_their_skipped_parent(self):
        # `<div class=chrome><span><p>junk</div>` — the span and p are
        # never closed, and the div's end tag has to end the skip anyway
        # or every later paragraph is swallowed.
        html = '<div class="chrome"><span><p>junk</div><p>REAL</p>'
        assert _extract(html, skip_class_tokens={"chrome"}) == ["REAL"]

    def test_the_innermost_element_of_a_name_is_the_one_closed(self):
        html = '<div class="chrome"><div>inner</div>still chrome</div><p>REAL</p>'
        assert _extract(html, skip_class_tokens={"chrome"}) == ["REAL"]

    def test_a_stray_end_tag_outside_any_skip_still_breaks_a_paragraph(self):
        # Nothing about the stack may change what happens when no skip is
        # open: `</div>` is a break_end_tag and still flushes.
        html = "<div>FIRST</div><div>SECOND</div>"
        assert _extract("<p>x</p>" + html)[1:] == ["FIRST", "SECOND"]

    def test_the_plain_path_ignores_an_unmatched_skip_end_tag(self):
        # Non-attribute callers pass only `skip_tags`; a `</style>` with
        # no `<style>` open must neither flush nor go negative.
        from _download import ParagraphExtractor

        p = ParagraphExtractor(skip_tags={"style"}, break_end_tags={"p"})
        p.feed("<p>FIRST</p></style><p>SECOND</p>")
        p.close()
        assert p.paragraphs == ["FIRST", "SECOND"]


class TestSkipByIdToken:
    def test_id_token_skips_subtree(self):
        html = '<div id="wm-ipp">TOOLBAR</div><p>REAL TEXT</p>'
        assert _extract(html, skip_id_tokens={"wm-ipp"}) == ["REAL TEXT"]

    def test_id_and_class_sets_compose(self):
        html = '<div id="wm-ipp">TOOLBAR</div><p class="toplink">BREADCRUMB</p><p>REAL TEXT</p>'
        got = _extract(html, skip_class_tokens={"toplink"}, skip_id_tokens={"wm-ipp"})
        assert got == ["REAL TEXT"]

    def test_id_set_alone_enables_the_attribute_aware_path(self):
        """Passing only ``skip_id_tokens`` must not fall back to the
        plain path, where the id would be ignored."""

        html = '<div id="chrome">JUNK</div><p>REAL TEXT</p>'
        assert _extract(html, skip_id_tokens={"chrome"}) == ["REAL TEXT"]

    def test_non_matching_id_is_kept(self):
        html = '<div id="content">KEEP ME</div><p>REAL TEXT</p>'
        got = _extract(html, skip_id_tokens={"wm-ipp"})
        assert "KEEP ME" in got
        assert "REAL TEXT" in got

    def test_id_matching_is_per_token_not_substring(self):
        """``no-sidebar`` must not be matched by ``sidebar`` — on PG-DE
        that token sits on ``<body>``, so a substring match would empty
        the whole document."""

        html = '<body class="no-sidebar"><p>REAL TEXT</p></body>'
        assert _extract(html, skip_class_tokens={"sidebar"}) == ["REAL TEXT"]

    def test_class_only_caller_ignores_ids(self):
        """Existing scrapers pass no id set and must be unaffected."""

        html = '<div id="wm-ipp">TOOLBAR</div><p>REAL TEXT</p>'
        got = _extract(html, skip_class_tokens={"chrome"})
        assert got == ["TOOLBAR", "REAL TEXT"]
